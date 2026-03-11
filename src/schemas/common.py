"""Shared types used across product, tender, and compliance schemas."""

from enum import Enum

from pydantic import BaseModel, Field


class MeasuredValue(BaseModel):
    """A numeric value with its unit of measurement."""

    value: float
    unit: str = Field(
        ...,
        description="Unit of measurement: bar, barg, m3/h, kW, mm, dB(A), C, etc.",
    )

    def __str__(self) -> str:
        return f"{self.value} {self.unit}"


class MaterialSpec(BaseModel):
    """Material specification with designation and classification."""

    designation: str = Field(
        ...,
        description="Full material designation, e.g. 'SS 316L', 'Carbon Steel ASTM A516 Gr60'",
    )
    grade: str | None = Field(
        default=None,
        description="Material grade, e.g. '316L', '420', 'Gr60'",
    )
    family: str | None = Field(
        default=None,
        description="Material family: stainless_steel, carbon_steel, duplex, polymer, etc.",
    )
    standard: str | None = Field(
        default=None,
        description="Reference standard: ASTM, AISI, DIN, EN, etc.",
    )


class ConnectionSpec(BaseModel):
    """Pipe/fitting connection specification."""

    type: str = Field(..., description="Connection type: NPT, Flanged, Welded, Threaded")
    size: str = Field(..., description="Connection size: '2 inch', 'DN50', 'NPS 2'")
    rating: str | None = Field(
        default=None,
        description="Pressure rating: PN40, Class 150, ANSI 150",
    )


class ComplianceStatus(str, Enum):
    """Compliance evaluation result for a single requirement."""

    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    PARTIAL = "partial"
    CLARIFICATION_NEEDED = "clarification_needed"
    NOT_APPLICABLE = "not_applicable"
    DEVIATION_ACCEPTABLE = "deviation_acceptable"


class RiskLevel(str, Enum):
    """Risk level associated with a compliance gap."""

    DISQUALIFYING = "disqualifying"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
