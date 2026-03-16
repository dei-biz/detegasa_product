"""Certification matcher — deterministic evaluation of certification requirements.

Uses an equivalence database to determine if product certifications
cover the tender requirements. For example, IMO MEPC 107(49) covers
MARPOL Annex I Reg 21 requirements.
"""

from __future__ import annotations

import logging

from src.compliance.matchers.base import BaseMatcher, MatchResult
from src.extraction.xlsx_parser import TBTItem
from src.schemas.common import ComplianceStatus

logger = logging.getLogger(__name__)


# ── Certification equivalences ───────────────────────────────────────────────
# Each entry: standard_code -> set of codes it covers/implies.

CERT_COVERS: dict[str, set[str]] = {
    "IMO MEPC 107(49)": {"MARPOL", "MARPOL Annex I", "MEPC 107", "MEPC.107(49)"},
    "IMO MEPC.107(49)": {"MARPOL", "MARPOL Annex I", "MEPC 107", "IMO MEPC 107(49)"},
    "MARPOL Annex I": {"MARPOL"},
    "ASME VIII": {"ASME Section VIII", "ASME Sec VIII", "ASME VIII Div 1"},
    "ASME Section VIII": {"ASME VIII", "ASME Sec VIII", "ASME VIII Div 1"},
    "IEC 60092": {"IEC 61892", "marine electrical"},
    "IEC 61892": {"IEC 60092", "marine electrical"},
    "ATEX 2014/34/EU": {"IECEx", "ATEX"},
    "IECEx": {"ATEX 2014/34/EU", "ATEX"},
    "ISO 9001": {"ISO 9001:2015", "quality management"},
    "ISO 9001:2015": {"ISO 9001", "quality management"},
    "ABS": {"class society", "classification"},
    "DNV": {"class society", "classification", "DNV-GL"},
    "DNV-GL": {"class society", "classification", "DNV"},
    "BV": {"class society", "classification", "Bureau Veritas"},
    "LR": {"class society", "classification", "Lloyd's Register"},
    "RINA": {"class society", "classification"},
    "PED 2014/68/EU": {"PED", "Pressure Equipment Directive"},
    "PED": {"PED 2014/68/EU", "Pressure Equipment Directive"},
    "EU MED": {"Marine Equipment Directive", "MED"},
    "MED": {"EU MED", "Marine Equipment Directive"},
}

# Keywords that trigger certification matching
_CERT_KEYWORDS = {
    "certification",
    "certificate",
    "approval",
    "type approval",
    "class society",
    "classification",
    "imo",
    "mepc",
    "marpol",
    "solas",
    "atex",
    "iecex",
    "asme",
    "ped",
    "iso 9001",
    "iso 14001",
    "med",
    "marine equipment",
    "inmetro",
    "ul listed",
    "ce marking",
    "abs",
    "dnv",
    "bureau veritas",
    "lloyd",
    "rina",
}


def _normalize_cert_code(code: str) -> str:
    """Normalize a certification code for comparison."""
    return code.strip().upper().replace(".", " ").replace("-", " ").replace("  ", " ")


def _cert_matches(product_cert_code: str, required_code: str) -> bool:
    """Check if a product certification covers a required certification."""
    p = _normalize_cert_code(product_cert_code)
    r = _normalize_cert_code(required_code)

    # Direct match
    if p == r or r in p or p in r:
        return True

    # Check equivalence table
    for cert_code, covered in CERT_COVERS.items():
        norm_cert = _normalize_cert_code(cert_code)
        if norm_cert == p or p in norm_cert or norm_cert in p:
            # Product has this cert — does it cover the requirement?
            for covered_code in covered:
                norm_covered = _normalize_cert_code(covered_code)
                if norm_covered == r or r in norm_covered or norm_covered in r:
                    return True

    return False


class CertificationMatcher(BaseMatcher):
    """Evaluate certification requirements against product certifications."""

    @property
    def name(self) -> str:
        return "certification"

    def can_handle(self, tbt_item: TBTItem) -> bool:
        text = f"{tbt_item.description} {tbt_item.spec_requirement}".lower()
        return any(kw in text for kw in _CERT_KEYWORDS)

    def evaluate(self, tbt_item: TBTItem, product_data: dict) -> MatchResult:
        spec = tbt_item.spec_requirement
        desc = tbt_item.description
        search_text = f"{desc} {spec}"

        # Get product certifications
        certs = product_data.get("certifications", [])

        # Try to find a matching certification
        for cert in certs:
            cert_code = cert.get("standard_code", "")
            applicability = cert.get("applicability", "")

            if _cert_matches(cert_code, search_text):
                # Found a match — check applicability status
                if applicability in ("certified", "compliant"):
                    return MatchResult(
                        status=ComplianceStatus.COMPLIANT,
                        product_value=f"{cert_code} ({applicability})",
                        tender_value=spec or desc,
                        confidence=0.90,
                    )
                elif applicability == "pending":
                    return MatchResult(
                        status=ComplianceStatus.PARTIAL,
                        product_value=f"{cert_code} (pending)",
                        tender_value=spec or desc,
                        gap_description="Certification is pending",
                        confidence=0.75,
                    )
                elif applicability in ("expired", "non_compliant"):
                    return MatchResult(
                        status=ComplianceStatus.NON_COMPLIANT,
                        product_value=f"{cert_code} ({applicability})",
                        tender_value=spec or desc,
                        gap_description=f"Certification is {applicability}",
                        confidence=0.85,
                    )

        # No matching certification found
        return MatchResult(
            status=ComplianceStatus.CLARIFICATION_NEEDED,
            tender_value=spec or desc,
            gap_description=(
                f"No matching certification found for '{spec or desc}'. "
                f"Product has {len(certs)} certifications: "
                f"{', '.join(c.get('standard_code', '?') for c in certs[:5])}"
            ),
            confidence=0.5,
        )
