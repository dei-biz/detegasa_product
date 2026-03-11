"""Extract structured TenderSpec from Petrobras tender documents using LLM.

Handles Material Requisitions (I-RM), Package Specifications (I-ET),
and Technical Bid Evaluation Tables (TBT).
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from src.extraction.chunker import Chunk
from src.extraction.xlsx_parser import TBTItem
from src.llm.adapter import LLMAdapter
from src.llm.types import LLMResponse
from src.llm_extraction.prompts import (
    TENDER_METADATA_PROMPT,
    TENDER_PROCESS_PROMPT,
    TENDER_REQUIREMENTS_PROMPT,
    TENDER_SYSTEM_PROMPT,
)
from src.schemas.common import MeasuredValue
from src.schemas.tender import (
    ProcessRequirement,
    TenderMetadata,
    TenderRequirementItem,
    TenderSpec,
)

logger = logging.getLogger(__name__)


# ── Intermediate extraction models ───────────────────────────────────────────


class ExtractedMetadata(BaseModel):
    """Project metadata extracted from tender document."""

    project_name: str = ""
    client: str = ""
    contractor: str = ""
    classification_society: str = ""
    vessel_type: str = ""
    location: str = ""


class ExtractedProcessReq(BaseModel):
    """Process requirements extracted from a chunk."""

    service: str = ""
    flow_rate_value: float | None = None
    flow_rate_unit: str = "m3/h"
    oil_input_max_ppm: int | None = None
    oil_output_max_ppm: int | None = None
    design_pressure_value: float | None = None
    design_pressure_unit: str = "barg"
    design_temperature_value: float | None = None
    design_temperature_unit: str = "C"
    operation_mode: str = ""
    regulatory_compliance: list[str] = Field(default_factory=list)


class ExtractedRequirement(BaseModel):
    """A single requirement extracted from tender text."""

    category: str = Field(
        ...,
        description="process, material, electrical, instrumentation, "
        "certification, qa_qc, general, documentation",
    )
    requirement_text: str = Field(..., description="Full requirement text")
    mandatory: bool = Field(default=True, description="True for SHALL/MUST")
    extracted_values: dict[str, Any] = Field(default_factory=dict)


class ExtractedRequirements(BaseModel):
    """Wrapper for a list of extracted requirements."""

    requirements: list[ExtractedRequirement] = Field(default_factory=list)


# ── Extractor ────────────────────────────────────────────────────────────────


class TenderExtractor:
    """Extract TenderSpec from tender document chunks using an LLM adapter.

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
        return self._total_cost

    @property
    def call_count(self) -> int:
        return self._call_count

    async def extract_metadata(self, text: str) -> TenderMetadata | None:
        """Extract project metadata from the cover page / header section.

        Parameters
        ----------
        text:
            Text from the first pages of the tender document.

        Returns
        -------
        TenderMetadata | None
        """
        prompt = TENDER_METADATA_PROMPT.format(text=text[:5000])
        try:
            result, response = await self.llm.extract_structured(
                prompt=prompt,
                response_model=ExtractedMetadata,
                system_prompt=TENDER_SYSTEM_PROMPT,
            )
            self._track_cost(response)
            return TenderMetadata(
                project_name=result.project_name or "Unknown Project",
                client=result.client or "Unknown Client",
                contractor=result.contractor,
                classification_society=result.classification_society,
                vessel_type=result.vessel_type,
                location=result.location,
            )
        except Exception as exc:
            logger.warning("Metadata extraction failed: %s", exc)
            return None

    async def extract_process_requirements(self, text: str) -> ProcessRequirement | None:
        """Extract process/performance requirements.

        Parameters
        ----------
        text:
            Text from the process requirements section.

        Returns
        -------
        ProcessRequirement | None
        """
        prompt = TENDER_PROCESS_PROMPT.format(text=text[:8000])
        try:
            result, response = await self.llm.extract_structured(
                prompt=prompt,
                response_model=ExtractedProcessReq,
                system_prompt=TENDER_SYSTEM_PROMPT,
            )
            self._track_cost(response)

            return ProcessRequirement(
                service=result.service or "Water treatment",
                flow_rate=MeasuredValue(
                    value=result.flow_rate_value or 0.0,
                    unit=result.flow_rate_unit,
                ),
                oil_input_max_ppm=result.oil_input_max_ppm or 0,
                oil_output_max_ppm=result.oil_output_max_ppm or 0,
                design_pressure=MeasuredValue(
                    value=result.design_pressure_value or 0.0,
                    unit=result.design_pressure_unit,
                ),
                design_temperature=MeasuredValue(
                    value=result.design_temperature_value or 0.0,
                    unit=result.design_temperature_unit,
                ),
                operation_mode=result.operation_mode,
                regulatory_compliance=result.regulatory_compliance,
            )
        except Exception as exc:
            logger.warning("Process requirements extraction failed: %s", exc)
            return None

    async def extract_requirements(
        self,
        chunks: list[Chunk],
        source_document: str = "",
    ) -> list[TenderRequirementItem]:
        """Extract individual requirements from tender document chunks.

        Parameters
        ----------
        chunks:
            Chunks from a tender document (specs, material requisition).
        source_document:
            Name of the source document for traceability.

        Returns
        -------
        list[TenderRequirementItem]
            Extracted and validated requirements.
        """
        all_requirements: list[TenderRequirementItem] = []
        req_counter = 0

        for chunk in chunks:
            if chunk.char_count < 50:
                continue

            prompt = TENDER_REQUIREMENTS_PROMPT.format(
                source_document=source_document,
                section=chunk.section_title or f"Chunk {chunk.index}",
                text=chunk.text,
            )

            try:
                result, response = await self.llm.extract_structured(
                    prompt=prompt,
                    response_model=ExtractedRequirements,
                    system_prompt=TENDER_SYSTEM_PROMPT,
                )
                self._track_cost(response)

                for er in result.requirements:
                    req_counter += 1
                    category = self._normalize_category(er.category)
                    all_requirements.append(
                        TenderRequirementItem(
                            id=f"REQ-{category[:3].upper()}-{req_counter:03d}",
                            category=category,
                            requirement_text=er.requirement_text,
                            mandatory=er.mandatory,
                            source_document=source_document,
                            source_section=chunk.section_title or "",
                            extracted_values=er.extracted_values or None,
                        )
                    )

            except Exception as exc:
                logger.warning(
                    "Failed to extract requirements from chunk %d: %s",
                    chunk.index,
                    exc,
                )

        logger.info(
            "Extracted %d requirements from %d chunks",
            len(all_requirements),
            len(chunks),
        )
        return all_requirements

    def requirements_from_tbt(
        self,
        tbt_items: list[TBTItem],
        source_document: str = "TBT",
    ) -> list[TenderRequirementItem]:
        """Convert TBT items directly to requirements without LLM.

        The TBT already has structured data, so we just need to map it.
        This is deterministic and free (no LLM cost).

        Parameters
        ----------
        tbt_items:
            Parsed TBT rows from ExcelParser.
        source_document:
            Source filename for traceability.

        Returns
        -------
        list[TenderRequirementItem]
        """
        requirements: list[TenderRequirementItem] = []

        for i, item in enumerate(tbt_items, start=1):
            if not item.description.strip():
                continue

            requirements.append(
                TenderRequirementItem(
                    id=f"TBT-{i:03d}",
                    category=self._guess_category_from_tbt(item),
                    requirement_text=item.spec_requirement or item.description,
                    mandatory=item.status.upper() not in ("Y", ""),  # Y = not applicable
                    source_document=source_document,
                    source_section=item.section,
                    extracted_values={
                        "bidder_response": item.bidder_response,
                        "status": item.status,
                        "remarks": item.remarks,
                    },
                )
            )

        logger.info(
            "Converted %d TBT items to requirements (no LLM)",
            len(requirements),
        )
        return requirements

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_category(raw: str) -> str:
        """Normalize category string to allowed values."""
        valid = {
            "process",
            "material",
            "electrical",
            "instrumentation",
            "certification",
            "qa_qc",
            "general",
            "documentation",
        }
        normalized = raw.lower().strip().replace(" ", "_")
        return normalized if normalized in valid else "general"

    @staticmethod
    def _guess_category_from_tbt(item: TBTItem) -> str:
        """Guess requirement category from TBT item content."""
        text = (item.description + " " + item.section).lower()
        if any(w in text for w in ("material", "steel", "alloy", "coating")):
            return "material"
        if any(w in text for w in ("voltage", "electric", "motor", "power", "ip ")):
            return "electrical"
        if any(w in text for w in ("instrument", "sensor", "transmitter", "signal")):
            return "instrumentation"
        if any(w in text for w in ("certif", "approval", "imo ", "marpol", "class")):
            return "certification"
        if any(w in text for w in ("test", "inspect", "quality", "fat", "pmi")):
            return "qa_qc"
        if any(w in text for w in ("document", "drawing", "manual", "report")):
            return "documentation"
        if any(w in text for w in ("capacity", "pressure", "temperature", "flow")):
            return "process"
        return "general"

    def _track_cost(self, response: LLMResponse) -> None:
        self._total_cost += response.cost_usd
        self._call_count += 1
