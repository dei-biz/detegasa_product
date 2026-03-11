"""Shared types used across product, tender, and compliance schemas."""

from __future__ import annotations

from datetime import date
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


# ── Standards & certifications ────────────────────────────────────────────────


class CertType(str, Enum):
    """Category of a standard or certification."""

    REGULATORY = "regulatory"          # IMO, MARPOL, SOLAS, EU MED
    CLASS_SOCIETY = "class_society"    # ABS, DNV, BV, LR, RINA
    HAZARDOUS_AREA = "hazardous_area"  # ATEX, IECEx
    COUNTRY = "country"                # INMETRO, UL, CSA, CCS
    QUALITY = "quality"                # ISO 9001, PED, CE marking
    DESIGN_CODE = "design_code"        # ASME, API, IEC, NEMA, EN


class ApplicabilityStatus(str, Enum):
    """Tracks where a standard/certification stands for a given product.

    Covers the full lifecycle: from "might be relevant" to "certified" or
    "explicitly not applicable".
    """

    CERTIFIED = "certified"            # Has valid, current certificate
    COMPLIANT = "compliant"            # Meets the standard but no formal cert
    PENDING = "pending"                # Certification process in progress
    APPLICABLE = "applicable"          # Applies and needs to be addressed
    POTENTIALLY_APPLICABLE = "potentially_applicable"  # May apply depending on project
    NOT_APPLICABLE = "not_applicable"  # Explicitly does not apply
    NON_COMPLIANT = "non_compliant"    # Assessed and does not comply
    EXPIRED = "expired"                # Had certification but it lapsed


class CertificationSpec(BaseModel):
    """Structured representation of a standard, certification, or design code
    and its applicability status for a product.

    Flexible enough to represent:
    - A valid IMO type-approval certificate with number and expiry
    - An INMETRO certification that is pending
    - An ATEX directive that doesn't apply to a specific installation
    - A design code (ASME VIII) that the product follows
    """

    standard_code: str = Field(
        ...,
        description="Standard or regulation code: 'IMO MEPC 107(49)', 'ATEX 2014/34/EU', 'ASME VIII Div.1'",
    )
    standard_title: str = Field(
        default="",
        description="Full title of the standard (optional, for clarity)",
    )
    cert_type: CertType = Field(
        ...,
        description="Category: regulatory, class_society, hazardous_area, country, quality, design_code",
    )
    applicability: ApplicabilityStatus = Field(
        ...,
        description="Current status: certified, compliant, pending, applicable, "
        "potentially_applicable, not_applicable, non_compliant, expired",
    )
    issuing_body: str = Field(
        default="",
        description="Organisation that issues/evaluates: 'ABS', 'RINA', 'INMETRO', 'TÜV'",
    )
    certificate_no: str = Field(
        default="",
        description="Certificate or type-approval number, if issued",
    )
    valid_from: date | None = Field(
        default=None,
        description="Date the certification was issued/became effective",
    )
    valid_until: date | None = Field(
        default=None,
        description="Expiry date of the certification, if applicable",
    )
    scope: str = Field(
        default="",
        description="Scope of the certification: 'OWS 1-5 m3/h bilge water separators'",
    )
    notes: str = Field(
        default="",
        description="Free text for additional context, conditions, or evolution notes",
    )


# ── Compliance evaluation ────────────────────────────────────────────────────


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
