"""Tests for the certification matcher — certification equivalence evaluation."""

import pytest

from src.compliance.matchers.certification_matcher import (
    CertificationMatcher,
    _cert_matches,
)
from src.extraction.xlsx_parser import TBTItem
from src.schemas.common import ComplianceStatus


@pytest.fixture
def matcher():
    return CertificationMatcher()


@pytest.fixture
def product_data():
    """Product with typical DETEGASA certifications."""
    return {
        "certifications": [
            {
                "standard_code": "IMO MEPC 107(49)",
                "cert_type": "regulatory",
                "applicability": "certified",
                "issuing_body": "ABS",
                "certificate_no": "20-HS1234567-PDA",
            },
            {
                "standard_code": "ASME VIII Div.1",
                "cert_type": "design_code",
                "applicability": "compliant",
                "issuing_body": "",
            },
            {
                "standard_code": "IEC 60092",
                "cert_type": "design_code",
                "applicability": "compliant",
                "issuing_body": "",
            },
            {
                "standard_code": "PED 2014/68/EU",
                "cert_type": "quality",
                "applicability": "certified",
                "issuing_body": "TUV",
            },
            {
                "standard_code": "ISO 9001:2015",
                "cert_type": "quality",
                "applicability": "certified",
                "issuing_body": "Bureau Veritas",
            },
            {
                "standard_code": "ATEX 2014/34/EU",
                "cert_type": "hazardous_area",
                "applicability": "pending",
                "issuing_body": "",
            },
        ],
    }


# ── _cert_matches() ──────────────────────────────────────────────────────────


class TestCertMatches:
    def test_direct_match(self):
        assert _cert_matches("IMO MEPC 107(49)", "IMO MEPC 107(49)") is True

    def test_substring_match(self):
        assert _cert_matches("ASME VIII Div.1", "ASME VIII") is True

    def test_equivalence_imo_marpol(self):
        """IMO MEPC 107(49) covers MARPOL requirements."""
        assert _cert_matches("IMO MEPC 107(49)", "MARPOL") is True

    def test_equivalence_imo_marpol_annex(self):
        assert _cert_matches("IMO MEPC 107(49)", "MARPOL Annex I") is True

    def test_equivalence_asme(self):
        assert _cert_matches("ASME VIII", "ASME Section VIII") is True

    def test_equivalence_iec(self):
        assert _cert_matches("IEC 60092", "IEC 61892") is True

    def test_equivalence_atex_iecex(self):
        assert _cert_matches("ATEX 2014/34/EU", "IECEx") is True

    def test_equivalence_ped(self):
        assert _cert_matches("PED 2014/68/EU", "PED") is True

    def test_no_match(self):
        assert _cert_matches("ISO 9001", "ATEX") is False

    def test_case_insensitive_through_normalization(self):
        assert _cert_matches("imo mepc 107(49)", "IMO MEPC 107(49)") is True


# ── can_handle() ──────────────────────────────────────────────────────────────


class TestCanHandle:
    def test_certification_keyword(self, matcher):
        item = TBTItem(
            row_number=1,
            description="Type approval certification",
            spec_requirement="IMO MEPC 107(49)",
        )
        assert matcher.can_handle(item) is True

    def test_imo_keyword(self, matcher):
        item = TBTItem(
            row_number=2,
            description="Compliance with IMO regulations",
            spec_requirement="Required",
        )
        assert matcher.can_handle(item) is True

    def test_marpol_keyword(self, matcher):
        item = TBTItem(
            row_number=3,
            description="MARPOL compliance",
            spec_requirement="Annex I",
        )
        assert matcher.can_handle(item) is True

    def test_atex_keyword(self, matcher):
        item = TBTItem(
            row_number=4,
            description="ATEX certification",
            spec_requirement="Zone 1",
        )
        assert matcher.can_handle(item) is True

    def test_asme_keyword(self, matcher):
        item = TBTItem(
            row_number=5,
            description="ASME code compliance",
            spec_requirement="Section VIII",
        )
        assert matcher.can_handle(item) is True

    def test_no_cert_keyword(self, matcher):
        item = TBTItem(
            row_number=6,
            description="Pump flow rate",
            spec_requirement="5 m3/h",
        )
        assert matcher.can_handle(item) is False


# ── evaluate() ────────────────────────────────────────────────────────────────


class TestEvaluate:
    def test_imo_certified(self, matcher, product_data):
        """Product has IMO MEPC 107(49) certified."""
        item = TBTItem(
            row_number=1,
            description="Type approval",
            spec_requirement="IMO MEPC 107(49)",
        )
        result = matcher.evaluate(item, product_data)
        assert result.status == ComplianceStatus.COMPLIANT
        assert "certified" in result.product_value.lower()

    def test_marpol_covered_by_imo(self, matcher, product_data):
        """IMO MEPC 107(49) covers MARPOL requirement."""
        item = TBTItem(
            row_number=2,
            description="MARPOL compliance",
            spec_requirement="MARPOL Annex I",
        )
        result = matcher.evaluate(item, product_data)
        assert result.status == ComplianceStatus.COMPLIANT

    def test_asme_compliant(self, matcher, product_data):
        """Product has ASME VIII compliant."""
        item = TBTItem(
            row_number=3,
            description="Design code",
            spec_requirement="ASME Section VIII",
        )
        result = matcher.evaluate(item, product_data)
        assert result.status == ComplianceStatus.COMPLIANT

    def test_atex_pending(self, matcher, product_data):
        """ATEX is pending — should be partial."""
        item = TBTItem(
            row_number=4,
            description="Hazardous area certification",
            spec_requirement="ATEX",
        )
        result = matcher.evaluate(item, product_data)
        assert result.status == ComplianceStatus.PARTIAL
        assert "pending" in result.product_value.lower()

    def test_iso_9001_certified(self, matcher, product_data):
        """Product has ISO 9001:2015 certified."""
        item = TBTItem(
            row_number=5,
            description="Quality management",
            spec_requirement="ISO 9001",
        )
        result = matcher.evaluate(item, product_data)
        assert result.status == ComplianceStatus.COMPLIANT

    def test_missing_certification(self, matcher, product_data):
        """Product does not have INMETRO."""
        item = TBTItem(
            row_number=6,
            description="Country certification",
            spec_requirement="INMETRO certified",
        )
        result = matcher.evaluate(item, product_data)
        assert result.status == ComplianceStatus.CLARIFICATION_NEEDED

    def test_no_certifications(self, matcher):
        """Product with no certifications at all."""
        item = TBTItem(
            row_number=7,
            description="IMO certification",
            spec_requirement="IMO MEPC 107(49)",
        )
        result = matcher.evaluate(item, {"certifications": []})
        assert result.status == ComplianceStatus.CLARIFICATION_NEEDED
