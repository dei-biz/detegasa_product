"""Product specification schemas — multi-family support via discriminated union."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Discriminator, Field, Tag, field_validator

from src.schemas.common import CertificationSpec, MaterialSpec, MeasuredValue


# Valid component types extracted from real DETEGASA data sheets
VALID_COMPONENT_TYPES = {
    "pump",
    "heater",
    "sensor",
    "valve",
    "gauge",
    "display",
    "monitor",
    "strainer",
    "regulator",
    "separator",
    "tank",
    "filter",
    "controller",
    "switch",
    "transmitter",
    "indicator",
    "flow_meter",
    "analyzer",
    "alarm",
    "panel",
    "motor",
    "actuator",
    "junction_box",
    "thermostat",
    "thermometer",
    "safety_valve",
    "plc",
}


class ComponentSpec(BaseModel):
    """Specification of a single product component (pump, valve, sensor, etc.)."""

    tag: str = Field(..., description="Component tag, e.g. 'P1', 'RS1', 'LS3', 'PS1'")
    type: str = Field(..., description="Component type: pump, heater, sensor, valve, etc.")
    name: str = Field(..., description="Component name/model, e.g. 'Progressive cavity pump PCM 13c12s'")
    materials: dict[str, MaterialSpec] = Field(
        default_factory=dict,
        description="Materials by part: {'body': ..., 'rotor': ..., 'stator': ...}",
    )
    mechanical: dict | None = Field(
        default=None,
        description="Mechanical specs: capacity, pressure, connections, etc.",
    )
    electrical: dict | None = Field(
        default=None,
        description="Electrical specs: voltage, power, IP rating, insulation class, etc.",
    )
    instrumentation: dict | None = Field(
        default=None,
        description="Instrumentation specs: range, accuracy, output signal, etc.",
    )
    dimensional: dict | None = Field(
        default=None,
        description="Dimensional data: weight, dimensions (L, W, H), etc.",
    )

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        """Normalize and validate component type.

        Handles compound types from LLM output like "solenoid valve" → "valve",
        "progressive cavity pump" → "pump", "level switch" → "switch".
        """
        normalized = v.lower().strip().replace(" ", "_")
        if normalized in VALID_COMPONENT_TYPES:
            return normalized

        # Try matching the last word (e.g. "solenoid_valve" → "valve")
        parts = normalized.split("_")
        if parts[-1] in VALID_COMPONENT_TYPES:
            return parts[-1]

        # Try matching any word in the compound type
        for part in parts:
            if part in VALID_COMPONENT_TYPES:
                return part

        raise ValueError(
            f"Unknown component type: '{v}'. "
            f"Valid types: {sorted(VALID_COMPONENT_TYPES)}"
        )


# ── Performance schemas per product family ────────────────────────────────────


class BasePerformance(BaseModel):
    """Common performance fields shared by all product families."""

    service: str = Field(..., description="Service description: 'Bilge water separation'")
    capacity: MeasuredValue = Field(..., description="Flow capacity")
    design_pressure: MeasuredValue = Field(..., description="Design pressure")
    design_temperature: MeasuredValue = Field(..., description="Design temperature")
    operation_mode: str = Field(
        ...,
        description="Operation mode: 'continuous' or 'intermittent'",
    )


class OWSPerformance(BasePerformance):
    """OWS — Oily Water Separator performance."""

    family: Literal["OWS"] = "OWS"
    oil_input_max_ppm: int = Field(..., description="Maximum oil content at inlet (ppm)")
    oil_output_max_ppm: int = Field(..., description="Maximum oil content at outlet (ppm)")


class GWTPerformance(BasePerformance):
    """GWT — Grey Water Treatment performance (future)."""

    family: Literal["GWT"] = "GWT"
    bod_input_mg_l: float | None = Field(default=None, description="BOD at inlet (mg/L)")
    bod_output_mg_l: float | None = Field(default=None, description="BOD at outlet (mg/L)")
    tss_input_mg_l: float | None = Field(default=None, description="TSS at inlet (mg/L)")
    tss_output_mg_l: float | None = Field(default=None, description="TSS at outlet (mg/L)")


# Discriminated union — routes by "family" field
ProductPerformance = Annotated[
    Union[
        Annotated[OWSPerformance, Tag("OWS")],
        Annotated[GWTPerformance, Tag("GWT")],
    ],
    Discriminator("family"),
]


class ProductSpec(BaseModel):
    """Complete product specification — the structured representation of a DETEGASA product."""

    product_id: str = Field(..., description="Internal product identifier")
    product_family: str = Field(
        default="OWS",
        description="Product family: OWS, GWT, REFUELLING, etc.",
    )
    manufacturer: str = Field(default="DETEGASA")
    model: str = Field(..., description="Product model designation")
    revision: str = Field(default="", description="Document revision letter")
    performance: ProductPerformance
    certifications: list[CertificationSpec] = Field(
        default_factory=list,
        description="Standards, certifications, and design codes with applicability status",
    )
    components: list[ComponentSpec] = Field(
        default_factory=list,
        description="List of component specifications",
    )
    package_level: dict | None = Field(
        default=None,
        description="Package-level specs: total weight, dimensions, noise, electrical load",
    )
