"""Product specification schemas — based on DETEGASA OWS data sheets."""

from pydantic import BaseModel, Field, field_validator

from src.schemas.common import MaterialSpec, MeasuredValue


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
        """Normalize and validate component type."""
        normalized = v.lower().strip().replace(" ", "_")
        if normalized not in VALID_COMPONENT_TYPES:
            raise ValueError(
                f"Unknown component type: '{v}'. "
                f"Valid types: {sorted(VALID_COMPONENT_TYPES)}"
            )
        return normalized


class ProductPerformance(BaseModel):
    """Overall product performance characteristics."""

    service: str = Field(..., description="Service description: 'Bilge water separation'")
    capacity: MeasuredValue = Field(..., description="Flow capacity")
    oil_input_max_ppm: int = Field(..., description="Maximum oil content at inlet (ppm)")
    oil_output_max_ppm: int = Field(..., description="Maximum oil content at outlet (ppm)")
    design_pressure: MeasuredValue = Field(..., description="Design pressure")
    design_temperature: MeasuredValue = Field(..., description="Design temperature")
    operation_mode: str = Field(
        ...,
        description="Operation mode: 'continuous' or 'intermittent'",
    )


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
    certifications: list[str] = Field(
        default_factory=list,
        description="List of certifications: 'IMO MEPC 107(49)', 'ABS', etc.",
    )
    components: list[ComponentSpec] = Field(
        default_factory=list,
        description="List of component specifications",
    )
    package_level: dict | None = Field(
        default=None,
        description="Package-level specs: total weight, dimensions, noise, electrical load",
    )
