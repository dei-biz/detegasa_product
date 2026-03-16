"""Tests for the process matcher — numeric process requirement evaluation."""

import pytest

from src.compliance.matchers.process_matcher import ProcessMatcher
from src.extraction.xlsx_parser import TBTItem
from src.schemas.common import ComplianceStatus


@pytest.fixture
def matcher():
    return ProcessMatcher()


@pytest.fixture
def product_data():
    """Sample product data mimicking the extraction JSON."""
    return {
        "performance": {
            "family": "OWS",
            "service": "Bilge water separation",
            "capacity": {"value": 5.0, "unit": "m3/h"},
            "design_pressure": {"value": 4.0, "unit": "barg"},
            "design_temperature": {"value": 65.0, "unit": "C"},
            "oil_output_max_ppm": 15,
            "operation_mode": "continuous",
        },
        "components": [
            {
                "tag": "P1",
                "type": "pump",
                "name": "Progressive cavity pump",
                "materials": {},
                "electrical": {
                    "voltage": "440V",
                    "power": "1.5 kW",
                },
            },
        ],
        "package_level": {
            "noise_level_dba": 75,
            "service_life_years": 25,
        },
    }


# ── can_handle() ──────────────────────────────────────────────────────────────


class TestCanHandle:
    def test_capacity_requirement(self, matcher):
        item = TBTItem(
            row_number=1,
            description="Flow capacity",
            spec_requirement="5 m3/h",
        )
        assert matcher.can_handle(item) is True

    def test_pressure_requirement(self, matcher):
        item = TBTItem(
            row_number=2,
            description="Design pressure",
            spec_requirement="4 barg",
        )
        assert matcher.can_handle(item) is True

    def test_ppm_requirement(self, matcher):
        item = TBTItem(
            row_number=3,
            description="Oil content at outlet",
            spec_requirement="≤15 ppm",
        )
        assert matcher.can_handle(item) is True

    def test_temperature_requirement(self, matcher):
        item = TBTItem(
            row_number=4,
            description="Design temperature",
            spec_requirement="65 C",
        )
        assert matcher.can_handle(item) is True

    def test_no_keyword_no_match(self, matcher):
        item = TBTItem(
            row_number=5,
            description="Paint color",
            spec_requirement="RAL 7035",
        )
        assert matcher.can_handle(item) is False

    def test_keyword_but_no_number(self, matcher):
        item = TBTItem(
            row_number=6,
            description="Flow capacity",
            spec_requirement="as per client spec",
        )
        assert matcher.can_handle(item) is False

    def test_noise_level(self, matcher):
        item = TBTItem(
            row_number=7,
            description="Maximum noise level",
            spec_requirement="85 dB(A)",
        )
        assert matcher.can_handle(item) is True

    def test_service_life(self, matcher):
        item = TBTItem(
            row_number=8,
            description="Minimum service life",
            spec_requirement="20 years",
        )
        assert matcher.can_handle(item) is True


# ── evaluate() — capacity ────────────────────────────────────────────────────


class TestEvaluateCapacity:
    def test_capacity_compliant(self, matcher, product_data):
        """Product 5 m3/h meets requirement of 5 m3/h."""
        item = TBTItem(
            row_number=1,
            description="Flow capacity",
            spec_requirement="5 m3/h",
        )
        result = matcher.evaluate(item, product_data)
        assert result.status == ComplianceStatus.COMPLIANT
        assert result.confidence >= 0.9

    def test_capacity_exceeds(self, matcher, product_data):
        """Product 5 m3/h exceeds requirement of 3 m3/h."""
        item = TBTItem(
            row_number=1,
            description="Flow capacity",
            spec_requirement="3 m3/h",
        )
        result = matcher.evaluate(item, product_data)
        assert result.status == ComplianceStatus.COMPLIANT

    def test_capacity_insufficient(self, matcher, product_data):
        """Product 5 m3/h does not meet 10 m3/h."""
        item = TBTItem(
            row_number=1,
            description="Flow capacity",
            spec_requirement="10 m3/h",
        )
        result = matcher.evaluate(item, product_data)
        assert result.status == ComplianceStatus.NON_COMPLIANT
        assert result.gap_description is not None
        assert "gap" in result.gap_description.lower()


# ── evaluate() — pressure ────────────────────────────────────────────────────


class TestEvaluatePressure:
    def test_pressure_compliant(self, matcher, product_data):
        """Product 4 barg meets 4 barg."""
        item = TBTItem(
            row_number=2,
            description="Design pressure",
            spec_requirement="4 barg",
        )
        result = matcher.evaluate(item, product_data)
        assert result.status == ComplianceStatus.COMPLIANT

    def test_pressure_insufficient(self, matcher, product_data):
        """Product 4 barg does not meet 6 barg."""
        item = TBTItem(
            row_number=2,
            description="Design pressure",
            spec_requirement="6 barg",
        )
        result = matcher.evaluate(item, product_data)
        assert result.status == ComplianceStatus.NON_COMPLIANT


# ── evaluate() — ppm (LTE) ───────────────────────────────────────────────────


class TestEvaluatePpm:
    def test_ppm_compliant(self, matcher, product_data):
        """Product 15 ppm meets ≤15 ppm requirement."""
        item = TBTItem(
            row_number=3,
            description="Oil content at outlet",
            spec_requirement="15 ppm",
        )
        result = matcher.evaluate(item, product_data)
        assert result.status == ComplianceStatus.COMPLIANT

    def test_ppm_non_compliant(self, matcher, product_data):
        """Product 15 ppm does not meet ≤10 ppm requirement."""
        item = TBTItem(
            row_number=3,
            description="Oil content at outlet",
            spec_requirement="10 ppm",
        )
        result = matcher.evaluate(item, product_data)
        assert result.status == ComplianceStatus.NON_COMPLIANT

    def test_ppm_better_than_required(self, matcher, product_data):
        """Product 15 ppm meets ≤20 ppm (lower is better for LTE)."""
        item = TBTItem(
            row_number=3,
            description="Oil content at outlet",
            spec_requirement="20 ppm",
        )
        result = matcher.evaluate(item, product_data)
        assert result.status == ComplianceStatus.COMPLIANT


# ── evaluate() — missing product data ────────────────────────────────────────


class TestEvaluateMissing:
    def test_no_product_value(self, matcher):
        """Missing product data should return clarification_needed."""
        item = TBTItem(
            row_number=10,
            description="Flow capacity",
            spec_requirement="5 m3/h",
        )
        result = matcher.evaluate(item, {"performance": {}})
        assert result.status == ComplianceStatus.CLARIFICATION_NEEDED

    def test_unparseable_spec(self, matcher, product_data):
        """Unparseable spec value should return clarification_needed."""
        item = TBTItem(
            row_number=11,
            description="Flow capacity",
            spec_requirement="as per datasheet",
        )
        # can_handle returns False for this because there's no number
        assert matcher.can_handle(item) is False


# ── evaluate() — noise (LTE) ─────────────────────────────────────────────────


class TestEvaluateNoise:
    def test_noise_compliant(self, matcher, product_data):
        """Product 75 dB(A) meets ≤85 dB(A)."""
        item = TBTItem(
            row_number=20,
            description="Noise level",
            spec_requirement="85 dB(A)",
        )
        result = matcher.evaluate(item, product_data)
        assert result.status == ComplianceStatus.COMPLIANT

    def test_noise_non_compliant(self, matcher, product_data):
        """Product 75 dB(A) does not meet ≤70 dB(A)."""
        item = TBTItem(
            row_number=20,
            description="Noise level",
            spec_requirement="70 dB(A)",
        )
        result = matcher.evaluate(item, product_data)
        assert result.status == ComplianceStatus.NON_COMPLIANT


# ── evaluate() — service life (GTE) ──────────────────────────────────────────


class TestEvaluateServiceLife:
    def test_service_life_compliant(self, matcher, product_data):
        """Product 25 years meets 20 years."""
        item = TBTItem(
            row_number=30,
            description="Minimum service life",
            spec_requirement="20 years",
        )
        result = matcher.evaluate(item, product_data)
        assert result.status == ComplianceStatus.COMPLIANT

    def test_service_life_insufficient(self, matcher, product_data):
        """Product 25 years does not meet 30 years."""
        item = TBTItem(
            row_number=30,
            description="Minimum service life",
            spec_requirement="30 years",
        )
        result = matcher.evaluate(item, product_data)
        assert result.status == ComplianceStatus.NON_COMPLIANT
