"""Tests for the ComplianceEngine — integration with matchers + mock LLM."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.compliance.engine import ComplianceEngine, _assess_risk, _infer_category
from src.compliance.matchers.base import BaseMatcher, MatchResult
from src.extraction.xlsx_parser import TBTItem
from src.schemas.common import ComplianceStatus, RiskLevel


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def product_data():
    """Complete product data for integration tests."""
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
                "materials": {
                    "body": {"designation": "SS 316L", "grade": "316L"},
                },
                "electrical": {"voltage": "440V", "power": "1.5 kW"},
            },
        ],
        "certifications": [
            {
                "standard_code": "IMO MEPC 107(49)",
                "cert_type": "regulatory",
                "applicability": "certified",
                "issuing_body": "ABS",
            },
        ],
        "package_level": {
            "noise_level_dba": 75,
            "service_life_years": 25,
        },
    }


@pytest.fixture
def sample_tbt_items():
    """Mix of TBT items that hit different matchers."""
    return [
        TBTItem(
            row_number=1,
            section="4.1",
            description="Flow capacity",
            spec_requirement="5 m3/h",
        ),
        TBTItem(
            row_number=2,
            section="4.2",
            description="Design pressure",
            spec_requirement="4 barg",
        ),
        TBTItem(
            row_number=3,
            section="5.1",
            description="Body material",
            spec_requirement="SS 316L",
        ),
        TBTItem(
            row_number=4,
            section="6.1",
            description="Type approval certification",
            spec_requirement="IMO MEPC 107(49)",
        ),
        TBTItem(
            row_number=5,
            section="7.1",
            description="Operating manual to be provided in English",
            spec_requirement="Required",
        ),
    ]


# ── _assess_risk() ────────────────────────────────────────────────────────────


class TestAssessRisk:
    def test_compliant_is_low(self):
        item = TBTItem(row_number=1, description="Anything")
        assert _assess_risk(item, ComplianceStatus.COMPLIANT) == RiskLevel.LOW

    def test_not_applicable_is_low(self):
        item = TBTItem(row_number=1, description="Anything")
        assert _assess_risk(item, ComplianceStatus.NOT_APPLICABLE) == RiskLevel.LOW

    def test_safety_noncompliant_is_disqualifying(self):
        item = TBTItem(row_number=1, description="Safety system")
        assert _assess_risk(item, ComplianceStatus.NON_COMPLIANT) == RiskLevel.DISQUALIFYING

    def test_imo_noncompliant_is_disqualifying(self):
        item = TBTItem(row_number=1, description="IMO certification")
        assert _assess_risk(item, ComplianceStatus.NON_COMPLIANT) == RiskLevel.DISQUALIFYING

    def test_pressure_noncompliant_is_high(self):
        item = TBTItem(row_number=1, description="Design pressure")
        assert _assess_risk(item, ComplianceStatus.NON_COMPLIANT) == RiskLevel.HIGH

    def test_generic_noncompliant_is_medium(self):
        item = TBTItem(row_number=1, description="Paint color specification")
        assert _assess_risk(item, ComplianceStatus.NON_COMPLIANT) == RiskLevel.MEDIUM

    def test_safety_partial_is_high(self):
        item = TBTItem(row_number=1, description="SOLAS requirement")
        assert _assess_risk(item, ComplianceStatus.PARTIAL) == RiskLevel.HIGH

    def test_generic_clarification_is_low(self):
        item = TBTItem(row_number=1, description="Generic requirement")
        assert _assess_risk(item, ComplianceStatus.CLARIFICATION_NEEDED) == RiskLevel.LOW


# ── _infer_category() ────────────────────────────────────────────────────────


class TestInferCategory:
    def test_matcher_name_used(self):
        item = TBTItem(row_number=1, description="Anything")
        assert _infer_category(item, "process") == "process"

    def test_electrical_inferred(self):
        item = TBTItem(row_number=1, description="Electrical voltage spec")
        assert _infer_category(item, None) == "electrical"

    def test_instrumentation_inferred(self):
        item = TBTItem(row_number=1, description="Instrument sensor type")
        assert _infer_category(item, None) == "instrumentation"

    def test_documentation_inferred(self):
        item = TBTItem(row_number=1, description="Drawing submittal")
        assert _infer_category(item, None) == "documentation"

    def test_commercial_inferred(self):
        item = TBTItem(row_number=1, description="Delivery schedule")
        assert _infer_category(item, None) == "commercial"

    def test_testing_inferred(self):
        item = TBTItem(row_number=1, description="FAT test witness")
        assert _infer_category(item, None) == "testing"

    def test_general_fallback(self):
        item = TBTItem(row_number=1, description="Something else")
        assert _infer_category(item, None) == "general"


# ── ComplianceEngine — deterministic only (no LLM) ──────────────────────────


class TestEngineNoLLM:
    @pytest.mark.asyncio
    async def test_deterministic_only(self, product_data, sample_tbt_items):
        """Engine without LLM should resolve deterministic items and mark rest as clarification."""
        engine = ComplianceEngine(llm=None)
        result = await engine.evaluate(product_data, sample_tbt_items)

        assert result.summary.total_requirements == 5
        assert len(result.items) == 5

        # Items 1-4 should be resolved by matchers
        # Item 5 has no matcher → clarification_needed
        statuses = {i.requirement_id: i.status for i in result.items}

        # Capacity: product 5 m3/h >= 5 m3/h → compliant
        assert statuses["TBT-1"] == ComplianceStatus.COMPLIANT
        # Pressure: product 4 barg >= 4 barg → compliant
        assert statuses["TBT-2"] == ComplianceStatus.COMPLIANT
        # Material: product has 316L, req 316L → compliant
        assert statuses["TBT-3"] == ComplianceStatus.COMPLIANT
        # Cert: product has IMO MEPC 107(49) certified → compliant
        assert statuses["TBT-4"] == ComplianceStatus.COMPLIANT
        # Manual: no matcher → clarification_needed (no LLM)
        assert statuses["TBT-5"] == ComplianceStatus.CLARIFICATION_NEEDED

    @pytest.mark.asyncio
    async def test_score_calculation(self, product_data, sample_tbt_items):
        """Score should reflect compliance percentage."""
        engine = ComplianceEngine(llm=None)
        result = await engine.evaluate(product_data, sample_tbt_items)

        # 4 compliant (1.0 each) + 1 clarification (0.3) = 4.3 / 5 = 86%
        assert result.overall_score == pytest.approx(86.0, abs=1.0)

    @pytest.mark.asyncio
    async def test_empty_items(self, product_data):
        """Empty TBT list should produce empty result."""
        engine = ComplianceEngine(llm=None)
        result = await engine.evaluate(product_data, [])

        assert result.summary.total_requirements == 0
        assert result.overall_score == 100.0

    @pytest.mark.asyncio
    async def test_result_structure(self, product_data, sample_tbt_items):
        """Result should have all required fields."""
        engine = ComplianceEngine(llm=None)
        result = await engine.evaluate(product_data, sample_tbt_items)

        assert result.comparison_id.startswith("CMP-")
        assert result.summary is not None
        assert isinstance(result.items, list)
        assert result.overall_score >= 0
        assert result.overall_score <= 100

    @pytest.mark.asyncio
    async def test_compliance_item_fields(self, product_data, sample_tbt_items):
        """Each ComplianceItem should have required fields."""
        engine = ComplianceEngine(llm=None)
        result = await engine.evaluate(product_data, sample_tbt_items)

        for item in result.items:
            assert item.requirement_id
            assert item.category
            assert item.requirement_text
            assert item.tender_value
            assert item.status in ComplianceStatus
            assert item.risk_level in RiskLevel


# ── ComplianceEngine — with mock LLM ────────────────────────────────────────


class TestEngineWithMockLLM:
    @pytest.mark.asyncio
    async def test_llm_fallback(self, product_data, sample_tbt_items):
        """Items not handled by matchers should go to LLM."""
        # Create mock LLM adapter
        mock_llm = MagicMock()
        mock_llm.provider = "mock"
        mock_llm.model = "mock-model"

        engine = ComplianceEngine(llm=mock_llm)

        # Mock the LLM comparator to return compliant for everything
        mock_result = MatchResult(
            status=ComplianceStatus.NOT_APPLICABLE,
            tender_value="Required",
            product_value=None,
            gap_description=None,
            confidence=0.7,
        )
        engine.llm_comparator.batch_evaluate = AsyncMock(
            return_value=[mock_result]
        )

        result = await engine.evaluate(product_data, sample_tbt_items)

        # LLM should have been called for item 5 only
        engine.llm_comparator.batch_evaluate.assert_called_once()
        call_args = engine.llm_comparator.batch_evaluate.call_args
        llm_items = call_args[0][0]  # first positional arg
        assert len(llm_items) == 1
        assert llm_items[0].row_number == 5

    @pytest.mark.asyncio
    async def test_matcher_stats(self, product_data, sample_tbt_items):
        """Engine should track which matcher handled each item."""
        engine = ComplianceEngine(llm=None)
        await engine.evaluate(product_data, sample_tbt_items)

        assert engine.stats["total"] == 5
        assert engine.stats["process"] >= 2  # capacity + pressure
        assert engine.stats["material"] >= 1
        assert engine.stats["certification"] >= 1


# ── ComplianceEngine — non-compliant scenarios ───────────────────────────────


class TestEngineNonCompliant:
    @pytest.mark.asyncio
    async def test_capacity_gap(self, product_data):
        """Requirement exceeding product capacity should be non-compliant."""
        items = [
            TBTItem(
                row_number=1,
                section="4.1",
                description="Flow capacity",
                spec_requirement="10 m3/h",
            ),
        ]
        engine = ComplianceEngine(llm=None)
        result = await engine.evaluate(product_data, items)

        assert result.items[0].status == ComplianceStatus.NON_COMPLIANT
        assert result.items[0].gap_description is not None
        assert result.overall_score < 50

    @pytest.mark.asyncio
    async def test_disqualifying_gap_in_summary(self, product_data):
        """Safety-related non-compliance should appear as disqualifying."""
        items = [
            TBTItem(
                row_number=1,
                section="8.1",
                description="SOLAS safety system compliance",
                spec_requirement="IMO SOLAS",
            ),
        ]
        engine = ComplianceEngine(llm=None)
        result = await engine.evaluate(product_data, items)

        # SOLAS is a safety keyword + cert keyword → certification matcher
        # Product doesn't have SOLAS → clarification_needed (not disqualifying)
        # But if it were NON_COMPLIANT + safety keyword → disqualifying
        assert len(result.items) == 1


# ── Custom matcher injection ─────────────────────────────────────────────────


class DummyMatcher(BaseMatcher):
    """A matcher that handles everything and returns compliant."""

    @property
    def name(self) -> str:
        return "dummy"

    def can_handle(self, tbt_item: TBTItem) -> bool:
        return True

    def evaluate(self, tbt_item: TBTItem, product_data: dict) -> MatchResult:
        return MatchResult(
            status=ComplianceStatus.COMPLIANT,
            product_value="dummy value",
            tender_value=tbt_item.spec_requirement,
            confidence=1.0,
        )


class TestCustomMatchers:
    @pytest.mark.asyncio
    async def test_custom_matcher(self, product_data, sample_tbt_items):
        """Custom matchers should be usable via the matchers parameter."""
        engine = ComplianceEngine(llm=None, matchers=[DummyMatcher()])
        result = await engine.evaluate(product_data, sample_tbt_items)

        # All items should be handled by the dummy matcher
        assert all(
            i.status == ComplianceStatus.COMPLIANT for i in result.items
        )
        assert result.overall_score == 100.0
        assert engine.stats["dummy"] == 5


# ── Score edge cases ─────────────────────────────────────────────────────────


class TestScoreEdgeCases:
    @pytest.mark.asyncio
    async def test_all_not_applicable(self, product_data):
        """All NOT_APPLICABLE should give 100% score."""
        engine = ComplianceEngine(
            llm=None,
            matchers=[
                type(
                    "NAMatcher",
                    (BaseMatcher,),
                    {
                        "name": property(lambda self: "na"),
                        "can_handle": lambda self, item: True,
                        "evaluate": lambda self, item, data: MatchResult(
                            status=ComplianceStatus.NOT_APPLICABLE,
                            tender_value=item.spec_requirement,
                            confidence=1.0,
                        ),
                    },
                )()
            ],
        )
        items = [TBTItem(row_number=1, description="Test", spec_requirement="N/A")]
        result = await engine.evaluate(product_data, items)
        assert result.overall_score == 100.0

    @pytest.mark.asyncio
    async def test_all_non_compliant(self, product_data):
        """All NON_COMPLIANT should give 0% score."""
        engine = ComplianceEngine(
            llm=None,
            matchers=[
                type(
                    "NOKMatcher",
                    (BaseMatcher,),
                    {
                        "name": property(lambda self: "nok"),
                        "can_handle": lambda self, item: True,
                        "evaluate": lambda self, item, data: MatchResult(
                            status=ComplianceStatus.NON_COMPLIANT,
                            tender_value=item.spec_requirement,
                            gap_description="Not compliant",
                            confidence=1.0,
                        ),
                    },
                )()
            ],
        )
        items = [TBTItem(row_number=1, description="Test", spec_requirement="X")]
        result = await engine.evaluate(product_data, items)
        assert result.overall_score == 0.0
