"""Extract structured ProductSpec from DETEGASA data sheets using LLM.

Orchestrates the extraction pipeline:
  chunks → LLM (per chunk) → merge → validated ProductSpec
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from src.extraction.chunker import Chunk
from src.llm.adapter import LLMAdapter
from src.llm.types import LLMResponse
from src.llm_extraction.prompts import (
    PRODUCT_CERTIFICATIONS_PROMPT,
    PRODUCT_COMPONENT_PROMPT,
    PRODUCT_FULL_PROMPT,
    PRODUCT_PERFORMANCE_PROMPT,
    PRODUCT_SYSTEM_PROMPT,
)
from src.schemas.common import (
    ApplicabilityStatus,
    CertificationSpec,
    CertType,
    MaterialSpec,
    MeasuredValue,
)
from src.schemas.product import (
    ComponentSpec,
    GWTPerformance,
    OWSPerformance,
    ProductSpec,
)

logger = logging.getLogger(__name__)


# ── Intermediate extraction models ───────────────────────────────────────────
# Simpler models for per-chunk extraction, later merged into full ProductSpec.


class ExtractedMaterial(BaseModel):
    """Material extracted from a chunk."""

    part_name: str = Field(..., description="Part: body, rotor, stator, internals, etc.")
    designation: str = Field(..., description="Material designation: SS 316L, Carbon Steel, NBR")
    grade: str = ""
    family: str = ""


class ExtractedComponent(BaseModel):
    """A single component extracted from a data sheet chunk."""

    tag: str = Field(..., description="Component tag: P1, RS1, LS3, etc.")
    component_type: str = Field(..., description="Type: pump, separator, heater, sensor, valve, etc.")
    name: str = Field(default="", description="Component name/model")
    materials: list[ExtractedMaterial] = Field(default_factory=list)
    mechanical: dict[str, Any] = Field(default_factory=dict)
    electrical: dict[str, Any] = Field(default_factory=dict)
    instrumentation: dict[str, Any] = Field(default_factory=dict)
    dimensional: dict[str, Any] = Field(default_factory=dict)


class ExtractedPerformance(BaseModel):
    """Performance data extracted from a chunk."""

    family: str = Field(..., description="Product family: OWS or GWT")
    service: str = ""
    capacity_value: float | None = None
    capacity_unit: str = "m3/h"
    oil_input_max_ppm: int | None = None
    oil_output_max_ppm: int | None = None
    design_pressure_value: float | None = None
    design_pressure_unit: str = "barg"
    design_temperature_value: float | None = None
    design_temperature_unit: str = "C"
    operation_mode: str = ""
    # GWT fields
    bod_input_mg_l: float | None = None
    bod_output_mg_l: float | None = None
    tss_input_mg_l: float | None = None
    tss_output_mg_l: float | None = None


class ExtractedCertification(BaseModel):
    """A certification/standard extracted from a chunk."""

    standard_code: str = Field(..., description="Standard code: IMO MEPC 107(49)")
    cert_type: str = Field(..., description="regulatory, class_society, hazardous_area, country, quality, design_code")
    applicability: str = Field(default="applicable", description="certified, compliant, pending, etc.")
    issuing_body: str = ""
    certificate_no: str = ""
    scope: str = ""
    notes: str = ""


class ExtractedCertifications(BaseModel):
    """Wrapper for a list of extracted certifications."""

    items: list[ExtractedCertification] = Field(default_factory=list)


class ExtractedComponents(BaseModel):
    """Wrapper for a list of extracted components."""

    components: list[ExtractedComponent] = Field(default_factory=list)


# ── Extractor ────────────────────────────────────────────────────────────────


class ProductExtractor:
    """Extract ProductSpec from document chunks using an LLM adapter.

    Supports two modes:
    1. Per-chunk extraction: extract components/performance from individual chunks
    2. Full extraction: send the full text for a single-pass extraction

    Parameters
    ----------
    llm:
        An LLM adapter (ClaudeAdapter or OpenAIAdapter).
    """

    def __init__(self, llm: LLMAdapter):
        self.llm = llm
        self._total_cost = 0.0
        self._call_count = 0

    @property
    def total_cost_usd(self) -> float:
        """Total cost of all LLM calls made by this extractor."""
        return self._total_cost

    @property
    def call_count(self) -> int:
        """Number of LLM calls made."""
        return self._call_count

    async def extract_components(self, chunks: list[Chunk]) -> list[ComponentSpec]:
        """Extract components from data sheet chunks.

        Each chunk should correspond to a component section (pump, separator, etc.).

        Parameters
        ----------
        chunks:
            Chunks from a data sheet, ideally split by component.

        Returns
        -------
        list[ComponentSpec]
            Validated component specifications.
        """
        components: list[ComponentSpec] = []

        for chunk in chunks:
            if chunk.char_count < 50:
                continue

            prompt = PRODUCT_COMPONENT_PROMPT.format(text=chunk.text)
            try:
                result, response = await self.llm.extract_structured(
                    prompt=prompt,
                    response_model=ExtractedComponents,
                    system_prompt=PRODUCT_SYSTEM_PROMPT,
                )
                self._track_cost(response)

                for ec in result.components:
                    comp = self._convert_component(ec)
                    if comp:
                        components.append(comp)

            except Exception as exc:
                logger.warning("Failed to extract component from chunk %d: %s", chunk.index, exc)

        components = self._deduplicate_components(components)
        logger.info("Extracted %d components from %d chunks", len(components), len(chunks))
        return components

    @staticmethod
    def _deduplicate_components(components: list[ComponentSpec]) -> list[ComponentSpec]:
        """Deduplicate components by tag, keeping the richest version.

        When the same tag appears multiple times (e.g. from a summary page
        and a detail page), keep the one with the most data.
        """
        if not components:
            return components

        def _richness(c: ComponentSpec) -> int:
            """Score how much data a component has."""
            score = len(c.materials)
            score += len(c.mechanical or {})
            score += len(c.electrical or {})
            score += len(c.instrumentation or {})
            score += len(c.dimensional or {})
            if c.name:
                score += 1
            return score

        best: dict[str, ComponentSpec] = {}
        for comp in components:
            key = comp.tag
            if key in best:
                if _richness(comp) > _richness(best[key]):
                    best[key] = comp
            else:
                best[key] = comp

        deduped = list(best.values())
        removed = len(components) - len(deduped)
        if removed:
            logger.info("Deduplicated components: %d removed (%d -> %d)", removed, len(components), len(deduped))
        return deduped

    async def extract_performance(self, text: str) -> OWSPerformance | GWTPerformance | None:
        """Extract performance data from document text.

        Parameters
        ----------
        text:
            Text containing performance/process data.

        Returns
        -------
        OWSPerformance | GWTPerformance | None
            Validated performance object, or None if extraction fails.
        """
        prompt = PRODUCT_PERFORMANCE_PROMPT.format(text=text[:8000])
        try:
            result, response = await self.llm.extract_structured(
                prompt=prompt,
                response_model=ExtractedPerformance,
                system_prompt=PRODUCT_SYSTEM_PROMPT,
            )
            self._track_cost(response)
            return self._convert_performance(result)
        except Exception as exc:
            logger.warning("Failed to extract performance: %s", exc)
            return None

    async def extract_certifications(self, text: str) -> list[CertificationSpec]:
        """Extract certifications and standards from document text.

        Parameters
        ----------
        text:
            Text mentioning certifications, standards, regulations.

        Returns
        -------
        list[CertificationSpec]
            Validated certification specifications.
        """
        prompt = PRODUCT_CERTIFICATIONS_PROMPT.format(text=text[:8000])
        try:
            result, response = await self.llm.extract_structured(
                prompt=prompt,
                response_model=ExtractedCertifications,
                system_prompt=PRODUCT_SYSTEM_PROMPT,
            )
            self._track_cost(response)
            return [self._convert_certification(ec) for ec in result.items]
        except Exception as exc:
            logger.warning("Failed to extract certifications: %s", exc)
            return []

    async def extract_full(
        self,
        text: str,
        product_family: str = "OWS",
        product_id: str = "",
        model: str = "",
    ) -> ProductSpec | None:
        """Single-pass full extraction of a ProductSpec.

        Best for shorter documents or when chunks aren't well-separated.

        Parameters
        ----------
        text:
            Full document text (will be truncated if too long).
        product_family:
            Product family hint: "OWS", "GWT", etc.
        product_id:
            Product ID to assign.
        model:
            Product model designation.

        Returns
        -------
        ProductSpec | None
            Complete validated product, or None if extraction fails.
        """
        # Truncate to reasonable LLM context
        truncated = text[:30000]
        prompt = PRODUCT_FULL_PROMPT.format(
            product_family=product_family,
            text=truncated,
        )

        try:
            result, response = await self.llm.extract_structured(
                prompt=prompt,
                response_model=ProductSpec,
                system_prompt=PRODUCT_SYSTEM_PROMPT,
                max_tokens=8192,
            )
            self._track_cost(response)
            return result
        except Exception as exc:
            logger.error("Full product extraction failed: %s", exc)
            return None

    # ── Conversion helpers ───────────────────────────────────────────────

    @staticmethod
    def _convert_component(ec: ExtractedComponent) -> ComponentSpec | None:
        """Convert an extracted component to a validated ComponentSpec."""
        try:
            materials = {}
            for mat in ec.materials:
                materials[mat.part_name] = MaterialSpec(
                    designation=mat.designation,
                    grade=mat.grade or None,
                    family=mat.family or None,
                )

            return ComponentSpec(
                tag=ec.tag,
                type=ec.component_type,
                name=ec.name,
                materials=materials,
                mechanical=ec.mechanical or None,
                electrical=ec.electrical or None,
                instrumentation=ec.instrumentation or None,
                dimensional=ec.dimensional or None,
            )
        except Exception as exc:
            logger.warning("Component conversion failed for %s: %s", ec.tag, exc)
            return None

    @staticmethod
    def _convert_performance(ep: ExtractedPerformance) -> OWSPerformance | GWTPerformance | None:
        """Convert extracted performance to the correct typed performance."""
        try:
            base_kwargs = {
                "service": ep.service or "Water treatment",
                "capacity": MeasuredValue(
                    value=ep.capacity_value or 0.0,
                    unit=ep.capacity_unit,
                ),
                "design_pressure": MeasuredValue(
                    value=ep.design_pressure_value or 0.0,
                    unit=ep.design_pressure_unit,
                ),
                "design_temperature": MeasuredValue(
                    value=ep.design_temperature_value or 0.0,
                    unit=ep.design_temperature_unit,
                ),
                "operation_mode": ep.operation_mode or "intermittent",
            }

            if ep.family.upper() == "GWT":
                return GWTPerformance(
                    **base_kwargs,
                    bod_input_mg_l=ep.bod_input_mg_l,
                    bod_output_mg_l=ep.bod_output_mg_l,
                    tss_input_mg_l=ep.tss_input_mg_l,
                    tss_output_mg_l=ep.tss_output_mg_l,
                )
            else:
                return OWSPerformance(
                    **base_kwargs,
                    oil_input_max_ppm=ep.oil_input_max_ppm or 0,
                    oil_output_max_ppm=ep.oil_output_max_ppm or 0,
                )
        except Exception as exc:
            logger.warning("Performance conversion failed: %s", exc)
            return None

    @staticmethod
    def _convert_certification(ec: ExtractedCertification) -> CertificationSpec:
        """Convert extracted certification to validated CertificationSpec."""
        # Map string to enum, with fallback
        try:
            cert_type = CertType(ec.cert_type.lower())
        except ValueError:
            cert_type = CertType.DESIGN_CODE

        try:
            applicability = ApplicabilityStatus(ec.applicability.lower())
        except ValueError:
            applicability = ApplicabilityStatus.APPLICABLE

        return CertificationSpec(
            standard_code=ec.standard_code,
            cert_type=cert_type,
            applicability=applicability,
            issuing_body=ec.issuing_body,
            certificate_no=ec.certificate_no,
            scope=ec.scope,
            notes=ec.notes,
        )

    def _track_cost(self, response: LLMResponse) -> None:
        """Track cumulative cost and call count."""
        self._total_cost += response.cost_usd
        self._call_count += 1
