"""Compliance comparison result schemas."""

from pydantic import BaseModel, Field

from src.schemas.common import ComplianceStatus, RiskLevel


class CostImpact(BaseModel):
    """Estimated cost impact of a required modification."""

    estimated_delta_eur: float = Field(
        ...,
        description="Estimated additional cost in EUR",
    )
    confidence: str = Field(
        default="medium",
        description="Estimation confidence: 'high', 'medium', 'low'",
    )
    notes: str | None = Field(
        default=None,
        description="Additional notes about the cost estimation",
    )


class ComplianceItem(BaseModel):
    """Result of evaluating a single requirement against the product."""

    requirement_id: str = Field(..., description="Reference to the tender requirement")
    category: str = Field(
        ...,
        description="Requirement category: process, material, electrical, etc.",
    )
    requirement_text: str = Field(..., description="Original requirement text")
    product_value: str | None = Field(
        default=None,
        description="What the product currently offers",
    )
    tender_value: str = Field(..., description="What the tender requires")
    status: ComplianceStatus = Field(..., description="Compliance evaluation result")
    gap_description: str | None = Field(
        default=None,
        description="Description of the gap (if non-compliant)",
    )
    modification_needed: str | None = Field(
        default=None,
        description="Description of the modification needed",
    )
    cost_impact: CostImpact | None = Field(
        default=None,
        description="Estimated cost impact of the modification",
    )
    risk_level: RiskLevel = Field(
        default=RiskLevel.LOW,
        description="Risk level of this gap",
    )
    source_document: str = Field(default="", description="Source document of the requirement")
    source_section: str | None = Field(
        default=None,
        description="Section in the source document",
    )


class ComplianceSummary(BaseModel):
    """Aggregated summary of a compliance comparison."""

    total_requirements: int = Field(..., description="Total requirements evaluated")
    compliant_count: int = Field(default=0)
    non_compliant_count: int = Field(default=0)
    partial_count: int = Field(default=0)
    clarification_count: int = Field(default=0)
    estimated_total_delta_eur: float = Field(
        default=0.0,
        description="Total estimated cost of all modifications",
    )
    disqualifying_gaps: list[str] = Field(
        default_factory=list,
        description="Gaps that may disqualify the bid entirely",
    )
    key_deviations: list[str] = Field(
        default_factory=list,
        description="Most significant deviations to highlight",
    )


class ComplianceResult(BaseModel):
    """Complete result of comparing a product against a tender."""

    comparison_id: str = Field(..., description="Unique comparison identifier")
    product_id: str = Field(..., description="Product that was evaluated")
    tender_id: str = Field(..., description="Tender that was evaluated against")
    overall_score: float = Field(
        ...,
        ge=0,
        le=100,
        description="Overall compliance score (0-100)",
    )
    items: list[ComplianceItem] = Field(
        default_factory=list,
        description="Individual requirement evaluations",
    )
    summary: ComplianceSummary
