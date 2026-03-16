"""Tests for the material matcher — material hierarchy evaluation."""

import pytest

from src.compliance.matchers.material_matcher import (
    MaterialMatcher,
    resolve_material,
)
from src.extraction.xlsx_parser import TBTItem
from src.schemas.common import ComplianceStatus


@pytest.fixture
def matcher():
    return MaterialMatcher()


@pytest.fixture
def product_data():
    """Product with SS 316L wetted parts."""
    return {
        "components": [
            {
                "tag": "P1",
                "type": "pump",
                "name": "Progressive cavity pump",
                "materials": {
                    "body": {"designation": "SS 316L", "grade": "316L"},
                    "rotor": {"designation": "Duplex 2205", "grade": "2205"},
                    "stator": {"designation": "NBR (rubber)", "grade": None},
                },
            },
            {
                "tag": "V1",
                "type": "valve",
                "name": "Solenoid valve",
                "materials": {
                    "body": {"designation": "Carbon Steel A105", "grade": "A105"},
                },
            },
        ],
    }


# ── resolve_material() ───────────────────────────────────────────────────────


class TestResolveMaterial:
    def test_exact_alias(self):
        assert resolve_material("316l") == "ss_316l"

    def test_case_insensitive(self):
        assert resolve_material("SS 316L") == "ss_316l"

    def test_din_number(self):
        assert resolve_material("1.4404") == "ss_316l"

    def test_cf8m(self):
        assert resolve_material("CF8M") == "ss_316"

    def test_duplex(self):
        assert resolve_material("Duplex 2205") == "duplex"

    def test_super_duplex(self):
        assert resolve_material("SAF 2507") == "super_duplex"

    def test_carbon_steel(self):
        assert resolve_material("Carbon Steel") == "carbon_steel"

    def test_astm_designation(self):
        assert resolve_material("ASTM A516") == "carbon_steel"

    def test_inconel(self):
        assert resolve_material("Inconel 625") == "inconel"

    def test_titanium(self):
        assert resolve_material("Titanium") == "titanium"

    def test_monel(self):
        assert resolve_material("Monel 400") == "monel"

    def test_generic_stainless(self):
        assert resolve_material("Stainless Steel") == "ss_304"

    def test_austenitic(self):
        assert resolve_material("Austenitic Stainless Steel") == "ss_316"

    def test_polymer_returns_none(self):
        """Non-metallic materials should return None."""
        assert resolve_material("NBR (rubber)") is None

    def test_unknown_returns_none(self):
        assert resolve_material("something completely unknown") is None

    def test_partial_match_316l(self):
        """Designation like 'AISI-316L' should match via partial."""
        assert resolve_material("AISI-316L") == "ss_316l"


# ── can_handle() ──────────────────────────────────────────────────────────────


class TestCanHandle:
    def test_material_keyword(self, matcher):
        item = TBTItem(
            row_number=1,
            description="Body material",
            spec_requirement="SS 316L",
        )
        assert matcher.can_handle(item) is True

    def test_steel_keyword(self, matcher):
        item = TBTItem(
            row_number=2,
            description="Wetted parts",
            spec_requirement="Stainless steel",
        )
        assert matcher.can_handle(item) is True

    def test_cf8m_keyword(self, matcher):
        item = TBTItem(
            row_number=3,
            description="Valve body",
            spec_requirement="CF8M or equivalent",
        )
        assert matcher.can_handle(item) is True

    def test_no_material_keyword(self, matcher):
        item = TBTItem(
            row_number=4,
            description="Operating mode",
            spec_requirement="Continuous",
        )
        assert matcher.can_handle(item) is False


# ── evaluate() ────────────────────────────────────────────────────────────────


class TestEvaluate:
    def test_compliant_same_material(self, matcher, product_data):
        """Product has SS 316L, requirement is SS 316L."""
        item = TBTItem(
            row_number=1,
            description="Body material",
            spec_requirement="SS 316L",
        )
        result = matcher.evaluate(item, product_data)
        assert result.status == ComplianceStatus.COMPLIANT

    def test_compliant_superior_material(self, matcher, product_data):
        """Product has Duplex 2205 (rank 50) >= SS 304 (rank 30)."""
        item = TBTItem(
            row_number=2,
            description="Wetted parts material",
            spec_requirement="SS 304",
        )
        result = matcher.evaluate(item, product_data)
        assert result.status == ComplianceStatus.COMPLIANT

    def test_compliant_higher_than_carbon(self, matcher, product_data):
        """Product has SS 316L (rank 45) >= carbon steel (rank 10)."""
        item = TBTItem(
            row_number=3,
            description="Body material",
            spec_requirement="Carbon Steel",
        )
        result = matcher.evaluate(item, product_data)
        assert result.status == ComplianceStatus.COMPLIANT

    def test_non_compliant_inferior(self, matcher, product_data):
        """Product best is Duplex (50) but Titanium (80) required."""
        item = TBTItem(
            row_number=4,
            description="Material",
            spec_requirement="Titanium",
        )
        result = matcher.evaluate(item, product_data)
        assert result.status == ComplianceStatus.NON_COMPLIANT
        assert result.gap_description is not None

    def test_unresolvable_requirement(self, matcher, product_data):
        """Unrecognized material in requirement."""
        item = TBTItem(
            row_number=5,
            description="Gasket material",
            spec_requirement="Viton O-ring",
        )
        result = matcher.evaluate(item, product_data)
        assert result.status == ComplianceStatus.CLARIFICATION_NEEDED

    def test_no_components(self, matcher):
        """No components in product data."""
        item = TBTItem(
            row_number=6,
            description="Body material",
            spec_requirement="SS 316",
        )
        result = matcher.evaluate(item, {"components": []})
        assert result.status == ComplianceStatus.CLARIFICATION_NEEDED

    def test_only_polymer_components(self, matcher):
        """Product has only non-metallic materials."""
        data = {
            "components": [
                {
                    "tag": "G1",
                    "type": "gauge",
                    "name": "Level gauge",
                    "materials": {
                        "body": {"designation": "Polycarbonate", "grade": None},
                    },
                },
            ],
        }
        item = TBTItem(
            row_number=7,
            description="Material",
            spec_requirement="SS 316",
        )
        result = matcher.evaluate(item, data)
        assert result.status == ComplianceStatus.CLARIFICATION_NEEDED
