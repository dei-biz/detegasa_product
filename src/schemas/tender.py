"""Tender/bid requirement schemas — based on Material Requisition structure."""

from pydantic import BaseModel, Field

from src.schemas.common import MeasuredValue


class TenderMetadata(BaseModel):
    """Metadata about the tender/bid."""

    project_name: str = Field(..., description="Project name: 'P-78 FPSO Buzios'")
    project_code: str | None = Field(default=None, description="Project code")
    client: str = Field(..., description="End client: 'Petrobras'")
    contractor: str = Field(default="", description="EPC contractor: 'Keppel/HHI'")
    classification_society: str = Field(
        default="",
        description="Classification society: 'ABS', 'DNV', 'BV', etc.",
    )
    vessel_type: str | None = Field(
        default=None,
        description="Vessel type: 'FPSO', 'FSRU', 'Platform', etc.",
    )
    location: str | None = Field(
        default=None,
        description="Installation location: 'Santos Basin, Brazil'",
    )


class ProcessRequirement(BaseModel):
    """Process/performance requirements from the tender."""

    service: str = Field(..., description="Required service: 'Bilge water separation'")
    flow_rate: MeasuredValue = Field(..., description="Required flow rate")
    oil_input_max_ppm: int = Field(..., description="Maximum oil at inlet (ppm)")
    oil_output_max_ppm: int = Field(..., description="Maximum oil at outlet (ppm)")
    design_pressure: MeasuredValue = Field(..., description="Required design pressure")
    design_temperature: MeasuredValue = Field(..., description="Required design temperature")
    suction_pressure_min: MeasuredValue | None = Field(
        default=None,
        description="Minimum suction pressure",
    )
    discharge_pressure_min: MeasuredValue | None = Field(
        default=None,
        description="Minimum discharge pressure",
    )
    operation_mode: str = Field(
        default="",
        description="Required operation mode: 'continuous' or 'intermittent'",
    )
    regulatory_compliance: list[str] = Field(
        default_factory=list,
        description="Required regulatory standards: 'IMO MEPC 107(49)', etc.",
    )


class TenderRequirementItem(BaseModel):
    """A single extractable requirement from the tender documents."""

    id: str = Field(..., description="Unique requirement identifier, e.g. 'REQ-MAT-001'")
    category: str = Field(
        ...,
        description="Requirement category: process, material, electrical, "
        "instrumentation, certification, qa_qc, general, documentation",
    )
    requirement_text: str = Field(..., description="Full text of the requirement")
    mandatory: bool = Field(
        default=True,
        description="True if SHALL/MUST requirement, False if SHOULD/MAY",
    )
    source_document: str = Field(..., description="Source document filename")
    source_section: str = Field(default="", description="Section number in source document")
    extracted_values: dict | None = Field(
        default=None,
        description="Structured values extracted from the requirement text",
    )


class TenderSpec(BaseModel):
    """Complete tender specification — structured representation of bid requirements."""

    tender_id: str = Field(..., description="Internal tender identifier")
    metadata: TenderMetadata
    general_requirements: dict = Field(
        default_factory=dict,
        description="General requirements: design_life, field_proven, asbestos_free, noise, etc.",
    )
    process_requirements: ProcessRequirement
    material_requirements: list[TenderRequirementItem] = Field(
        default_factory=list,
        description="Material-specific requirements",
    )
    electrical_requirements: dict = Field(
        default_factory=dict,
        description="Electrical requirements: voltage, frequency, hazardous area, INMETRO, etc.",
    )
    instrumentation_requirements: dict = Field(
        default_factory=dict,
        description="Instrumentation requirements",
    )
    applicable_standards: list[dict] = Field(
        default_factory=list,
        description="List of applicable standards with code, title, and edition",
    )
    qa_qc_requirements: dict = Field(
        default_factory=dict,
        description="QA/QC requirements: ISO 9001, FAT, hydro test, PMI, etc.",
    )
    scope_line_items: list[dict] = Field(
        default_factory=list,
        description="Scope of supply line items",
    )
