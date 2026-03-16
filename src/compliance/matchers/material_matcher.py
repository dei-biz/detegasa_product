"""Material matcher — deterministic evaluation of material requirements.

Uses a material hierarchy to determine if the product material meets or
exceeds the tender requirement. For example, SS 316L is superior to SS 304.
"""

from __future__ import annotations

import logging
import re

from src.compliance.matchers.base import BaseMatcher, MatchResult
from src.extraction.xlsx_parser import TBTItem
from src.schemas.common import ComplianceStatus

logger = logging.getLogger(__name__)


# ── Material hierarchy ───────────────────────────────────────────────────────
# Higher rank = better corrosion resistance / quality.
# When product rank >= required rank -> compliant.

MATERIAL_HIERARCHY: dict[str, int] = {
    "carbon_steel": 10,
    "low_alloy_steel": 20,
    "ss_304": 30,
    "ss_316": 40,
    "ss_316l": 45,
    "duplex": 50,
    "super_duplex": 60,
    "monel": 65,
    "inconel": 70,
    "titanium": 80,
    "hastelloy": 85,
}

# Alias mapping: common designations -> hierarchy key
MATERIAL_ALIASES: dict[str, str] = {
    # Carbon steel
    "carbon steel": "carbon_steel",
    "cs": "carbon_steel",
    "a516": "carbon_steel",
    "astm a516": "carbon_steel",
    "a106": "carbon_steel",
    "a105": "carbon_steel",
    # Low alloy
    "low alloy": "low_alloy_steel",
    "a335": "low_alloy_steel",
    # SS 304
    "304": "ss_304",
    "ss 304": "ss_304",
    "aisi 304": "ss_304",
    "1.4301": "ss_304",
    "cf8": "ss_304",
    # SS 316
    "316": "ss_316",
    "ss 316": "ss_316",
    "aisi 316": "ss_316",
    "1.4401": "ss_316",
    "cf8m": "ss_316",
    # SS 316L
    "316l": "ss_316l",
    "ss 316l": "ss_316l",
    "aisi 316l": "ss_316l",
    "aisi-316l": "ss_316l",
    "1.4404": "ss_316l",
    "1.4435": "ss_316l",
    "1.4571": "ss_316l",
    "316ti": "ss_316l",
    # Duplex
    "duplex": "duplex",
    "2205": "duplex",
    "1.4462": "duplex",
    "saf 2205": "duplex",
    # Super duplex
    "super duplex": "super_duplex",
    "2507": "super_duplex",
    "1.4410": "super_duplex",
    "saf 2507": "super_duplex",
    # Monel
    "monel": "monel",
    "monel 400": "monel",
    # Inconel
    "inconel": "inconel",
    "inconel 625": "inconel",
    "alloy 625": "inconel",
    # Titanium
    "titanium": "titanium",
    "ti gr 2": "titanium",
    # Hastelloy
    "hastelloy": "hastelloy",
    "hastelloy c276": "hastelloy",
    # Austenitic stainless (generic -> 316)
    "austenitic stainless steel": "ss_316",
    "austenitic stainless": "ss_316",
    "stainless steel": "ss_304",
}

# Keywords that trigger material matching
_MATERIAL_KEYWORDS = {
    "material",
    "steel",
    "stainless",
    "carbon steel",
    "duplex",
    "titanium",
    "ss 316",
    "ss 304",
    "316l",
    "inconel",
    "monel",
    "hastelloy",
    "aisi",
    "astm",
    "corrosion",
    "wetted parts",
    "body material",
    "cf8m",
}


def resolve_material(designation: str) -> str | None:
    """Resolve a material designation to a hierarchy key.

    Returns None if the material is not recognized (e.g. polymers, elastomers).
    """
    lower = designation.lower().strip()

    # Direct alias match
    if lower in MATERIAL_ALIASES:
        return MATERIAL_ALIASES[lower]

    # Partial match — check if any alias is contained in the designation
    for alias, key in sorted(MATERIAL_ALIASES.items(), key=lambda x: -len(x[0])):
        if alias in lower:
            return key

    return None


class MaterialMatcher(BaseMatcher):
    """Evaluate material requirements using hierarchy comparison."""

    @property
    def name(self) -> str:
        return "material"

    def can_handle(self, tbt_item: TBTItem) -> bool:
        text = f"{tbt_item.description} {tbt_item.spec_requirement}".lower()
        return any(kw in text for kw in _MATERIAL_KEYWORDS)

    def evaluate(self, tbt_item: TBTItem, product_data: dict) -> MatchResult:
        spec = tbt_item.spec_requirement
        text = f"{tbt_item.description} {spec}".lower()

        # Resolve required material
        required_key = resolve_material(spec)
        if not required_key:
            # Try from description
            required_key = resolve_material(tbt_item.description)

        if not required_key:
            return MatchResult(
                status=ComplianceStatus.CLARIFICATION_NEEDED,
                tender_value=spec,
                gap_description="Could not resolve material requirement to hierarchy",
                confidence=0.3,
            )

        required_rank = MATERIAL_HIERARCHY.get(required_key, 0)

        # Search product components for matching materials
        best_rank = -1
        best_designation = None

        components = product_data.get("components", [])
        for comp in components:
            materials = comp.get("materials", {})
            for part_name, mat in materials.items():
                designation = mat.get("designation", "")
                key = resolve_material(designation)
                if key:
                    rank = MATERIAL_HIERARCHY.get(key, 0)
                    if rank > best_rank:
                        best_rank = rank
                        best_designation = designation

        if best_designation is None:
            return MatchResult(
                status=ComplianceStatus.CLARIFICATION_NEEDED,
                tender_value=spec,
                gap_description="No metallic materials found in product data",
                confidence=0.4,
            )

        # Compare
        if best_rank >= required_rank:
            return MatchResult(
                status=ComplianceStatus.COMPLIANT,
                product_value=best_designation,
                tender_value=spec,
                confidence=0.85,
            )
        else:
            product_key = resolve_material(best_designation) or "unknown"
            return MatchResult(
                status=ComplianceStatus.NON_COMPLIANT,
                product_value=best_designation,
                tender_value=spec,
                gap_description=(
                    f"Product best material '{best_designation}' ({product_key}) is below "
                    f"required '{spec}' ({required_key})"
                ),
                confidence=0.80,
            )
