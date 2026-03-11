"""Tests for LLM extraction pipeline — using mocked LLM adapter (no API calls).

Tests verify:
1. Intermediate models validate correctly
2. Extractors handle LLM responses properly
3. Conversion logic (intermediate → final schema) works
4. TBT → requirements conversion (deterministic, no LLM)
5. Cost tracking works
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.extraction.chunker import Chunk
from src.extraction.xlsx_parser import TBTItem
from src.llm.types import LLMResponse
from src.llm_extraction.product_extractor import (
    ExtractedCertification,
    ExtractedCertifications,
    ExtractedComponent,
    ExtractedComponents,
    ExtractedMaterial,
    ExtractedPerformance,
    ProductExtractor,
)
from src.llm_extraction.tender_extractor import (
    ExtractedMetadata,
    ExtractedProcessReq,
    ExtractedRequirement,
    ExtractedRequirements,
    TenderExtractor,
)
from src.schemas.common import ApplicabilityStatus, CertType
from src.schemas.product import ComponentSpec, OWSPerformance, GWTPerformance


# ── Fixtures ─────────────────────────────────────────────────────────────────


def _mock_llm_response(cost: float = 0.01) -> LLMResponse:
    return LLMResponse(
        content="{}",
        model="test-model",
        input_tokens=100,
        output_tokens=50,
        cost_usd=cost,
    )


def _make_mock_llm() -> MagicMock:
    """Create a mock LLM adapter with extract_structured as AsyncMock."""
    llm = MagicMock()
    llm.extract_structured = AsyncMock()
    llm.provider = "mock"
    llm.model = "mock-model"
    return llm


# ── Intermediate models ──────────────────────────────────────────────────────


class TestExtractedModels:
    def test_extracted_component(self):
        ec = ExtractedComponent(
            tag="P1",
            component_type="pump",
            name="PCM 13c12s",
            materials=[
                ExtractedMaterial(part_name="body", designation="SS 316L", grade="316L"),
            ],
            mechanical={"capacity_m3h": 5},
        )
        assert ec.tag == "P1"
        assert len(ec.materials) == 1

    def test_extracted_performance_ows(self):
        ep = ExtractedPerformance(
            family="OWS",
            service="Bilge water separation",
            capacity_value=5.0,
            oil_input_max_ppm=500,
            oil_output_max_ppm=15,
            design_pressure_value=6.7,
            design_temperature_value=60,
            operation_mode="intermittent",
        )
        assert ep.family == "OWS"
        assert ep.oil_output_max_ppm == 15

    def test_extracted_performance_gwt(self):
        ep = ExtractedPerformance(
            family="GWT",
            service="Grey water treatment",
            capacity_value=10.0,
            bod_input_mg_l=250.0,
            bod_output_mg_l=25.0,
        )
        assert ep.family == "GWT"

    def test_extracted_certification(self):
        ec = ExtractedCertification(
            standard_code="IMO MEPC 107(49)",
            cert_type="regulatory",
            applicability="certified",
            issuing_body="ABS",
        )
        assert ec.cert_type == "regulatory"

    def test_extracted_requirement(self):
        er = ExtractedRequirement(
            category="material",
            requirement_text="All wetted parts shall be SS 316L",
            mandatory=True,
            extracted_values={"material": "SS 316L"},
        )
        assert er.mandatory is True

    def test_extracted_metadata(self):
        em = ExtractedMetadata(
            project_name="P-78 FPSO Buzios",
            client="Petrobras",
            contractor="Keppel/HHI",
        )
        assert em.client == "Petrobras"


# ── Product Extractor ────────────────────────────────────────────────────────


class TestProductExtractorConversion:
    """Test conversion logic without LLM calls."""

    def test_convert_component(self):
        ec = ExtractedComponent(
            tag="P1",
            component_type="pump",
            name="Progressive cavity pump",
            materials=[
                ExtractedMaterial(part_name="body", designation="SS 316L", grade="316L", family="stainless_steel"),
            ],
            electrical={"voltage": "440V", "power_kw": 3},
        )
        comp = ProductExtractor._convert_component(ec)
        assert comp is not None
        assert isinstance(comp, ComponentSpec)
        assert comp.tag == "P1"
        assert comp.type == "pump"
        assert comp.materials["body"].grade == "316L"
        assert comp.electrical["voltage"] == "440V"

    def test_convert_component_invalid_type(self):
        ec = ExtractedComponent(tag="X1", component_type="nuclear_reactor", name="Bad")
        comp = ProductExtractor._convert_component(ec)
        assert comp is None  # Should fail validation gracefully

    def test_convert_performance_ows(self):
        ep = ExtractedPerformance(
            family="OWS",
            service="Bilge water separation",
            capacity_value=5.0,
            oil_input_max_ppm=500,
            oil_output_max_ppm=15,
            design_pressure_value=6.7,
            design_temperature_value=60,
            operation_mode="intermittent",
        )
        perf = ProductExtractor._convert_performance(ep)
        assert isinstance(perf, OWSPerformance)
        assert perf.oil_output_max_ppm == 15
        assert perf.capacity.value == 5.0

    def test_convert_performance_gwt(self):
        ep = ExtractedPerformance(
            family="GWT",
            service="Grey water treatment",
            capacity_value=10.0,
            design_pressure_value=4.0,
            design_temperature_value=45,
            operation_mode="continuous",
            bod_input_mg_l=250.0,
            bod_output_mg_l=25.0,
        )
        perf = ProductExtractor._convert_performance(ep)
        assert isinstance(perf, GWTPerformance)
        assert perf.bod_input_mg_l == 250.0

    def test_convert_certification(self):
        ec = ExtractedCertification(
            standard_code="IMO MEPC 107(49)",
            cert_type="regulatory",
            applicability="certified",
            issuing_body="ABS",
            certificate_no="TAC-001",
        )
        cert = ProductExtractor._convert_certification(ec)
        assert cert.cert_type == CertType.REGULATORY
        assert cert.applicability == ApplicabilityStatus.CERTIFIED
        assert cert.certificate_no == "TAC-001"

    def test_convert_certification_unknown_type(self):
        """Unknown cert_type should fallback to DESIGN_CODE."""
        ec = ExtractedCertification(
            standard_code="XYZ-123",
            cert_type="unknown_type",
            applicability="compliant",
        )
        cert = ProductExtractor._convert_certification(ec)
        assert cert.cert_type == CertType.DESIGN_CODE


class TestProductExtractorAsync:
    """Test async extraction methods with mocked LLM."""

    @pytest.mark.asyncio
    async def test_extract_components(self):
        llm = _make_mock_llm()
        llm.extract_structured.return_value = (
            ExtractedComponents(
                components=[
                    ExtractedComponent(tag="P1", component_type="pump", name="Test pump"),
                ]
            ),
            _mock_llm_response(0.02),
        )

        extractor = ProductExtractor(llm)
        chunks = [Chunk(index=0, text="Pump P1: Progressive cavity 5 m3/h" + " " * 50)]
        components = await extractor.extract_components(chunks)

        assert len(components) == 1
        assert components[0].tag == "P1"
        assert extractor.total_cost_usd == pytest.approx(0.02)
        assert extractor.call_count == 1

    @pytest.mark.asyncio
    async def test_extract_performance(self):
        llm = _make_mock_llm()
        llm.extract_structured.return_value = (
            ExtractedPerformance(
                family="OWS",
                service="Bilge water separation",
                capacity_value=5.0,
                oil_input_max_ppm=500,
                oil_output_max_ppm=15,
                design_pressure_value=6.7,
                design_temperature_value=60,
                operation_mode="intermittent",
            ),
            _mock_llm_response(0.03),
        )

        extractor = ProductExtractor(llm)
        perf = await extractor.extract_performance("Some text about OWS performance...")

        assert isinstance(perf, OWSPerformance)
        assert perf.capacity.value == 5.0
        assert extractor.total_cost_usd == pytest.approx(0.03)

    @pytest.mark.asyncio
    async def test_extract_certifications(self):
        llm = _make_mock_llm()
        llm.extract_structured.return_value = (
            ExtractedCertifications(
                items=[
                    ExtractedCertification(
                        standard_code="IMO MEPC 107(49)",
                        cert_type="regulatory",
                        applicability="certified",
                    ),
                    ExtractedCertification(
                        standard_code="ASME VIII",
                        cert_type="design_code",
                        applicability="compliant",
                    ),
                ]
            ),
            _mock_llm_response(0.01),
        )

        extractor = ProductExtractor(llm)
        certs = await extractor.extract_certifications("Text about certifications...")

        assert len(certs) == 2
        assert certs[0].cert_type == CertType.REGULATORY
        assert certs[1].cert_type == CertType.DESIGN_CODE

    @pytest.mark.asyncio
    async def test_extract_handles_llm_error(self):
        llm = _make_mock_llm()
        llm.extract_structured.side_effect = Exception("API error")

        extractor = ProductExtractor(llm)
        perf = await extractor.extract_performance("Some text")
        assert perf is None

    @pytest.mark.asyncio
    async def test_skip_short_chunks(self):
        llm = _make_mock_llm()
        extractor = ProductExtractor(llm)

        chunks = [Chunk(index=0, text="Short")]
        components = await extractor.extract_components(chunks)

        assert len(components) == 0
        assert extractor.call_count == 0  # Should not call LLM


# ── Tender Extractor ─────────────────────────────────────────────────────────


class TestTenderExtractorAsync:
    @pytest.mark.asyncio
    async def test_extract_metadata(self):
        llm = _make_mock_llm()
        llm.extract_structured.return_value = (
            ExtractedMetadata(
                project_name="P-78 FPSO Buzios",
                client="Petrobras",
                contractor="Keppel/HHI",
                classification_society="ABS",
                vessel_type="FPSO",
                location="Santos Basin",
            ),
            _mock_llm_response(),
        )

        extractor = TenderExtractor(llm)
        meta = await extractor.extract_metadata("Cover page text...")

        assert meta is not None
        assert meta.project_name == "P-78 FPSO Buzios"
        assert meta.client == "Petrobras"

    @pytest.mark.asyncio
    async def test_extract_process_requirements(self):
        llm = _make_mock_llm()
        llm.extract_structured.return_value = (
            ExtractedProcessReq(
                service="Bilge water separation",
                flow_rate_value=5.0,
                oil_input_max_ppm=500,
                oil_output_max_ppm=15,
                design_pressure_value=6.7,
                design_temperature_value=60,
                operation_mode="intermittent",
                regulatory_compliance=["IMO MEPC 107(49)"],
            ),
            _mock_llm_response(),
        )

        extractor = TenderExtractor(llm)
        process = await extractor.extract_process_requirements("Process section text...")

        assert process is not None
        assert process.flow_rate.value == 5.0
        assert process.oil_output_max_ppm == 15
        assert "IMO MEPC 107(49)" in process.regulatory_compliance

    @pytest.mark.asyncio
    async def test_extract_requirements_from_chunks(self):
        llm = _make_mock_llm()
        llm.extract_structured.return_value = (
            ExtractedRequirements(
                requirements=[
                    ExtractedRequirement(
                        category="material",
                        requirement_text="All wetted parts shall be SS 316L",
                        mandatory=True,
                        extracted_values={"material": "SS 316L"},
                    ),
                    ExtractedRequirement(
                        category="electrical",
                        requirement_text="Motors shall be 440V/60Hz",
                        mandatory=True,
                    ),
                ]
            ),
            _mock_llm_response(),
        )

        extractor = TenderExtractor(llm)
        chunks = [
            Chunk(index=0, text="Section about materials and electrical " + "x" * 50),
        ]
        reqs = await extractor.extract_requirements(chunks, source_document="I-ET-test")

        assert len(reqs) == 2
        assert reqs[0].id == "REQ-MAT-001"
        assert reqs[0].category == "material"
        assert reqs[0].mandatory is True
        assert reqs[1].category == "electrical"


class TestTBTConversion:
    """Test TBT → requirements conversion (deterministic, no LLM)."""

    def test_basic_conversion(self):
        items = [
            TBTItem(
                row_number=5,
                section="3.1",
                description="Pump capacity",
                spec_requirement="5 m3/h minimum",
                bidder_response="5 m3/h",
                status="F",
            ),
            TBTItem(
                row_number=6,
                section="3.2",
                description="Body material steel",
                spec_requirement="SS 316L minimum",
                bidder_response="SS 316L",
                status="F",
            ),
        ]

        extractor = TenderExtractor(_make_mock_llm())
        reqs = extractor.requirements_from_tbt(items, source_document="TBT.xlsx")

        assert len(reqs) == 2
        assert reqs[0].id == "TBT-001"
        assert reqs[0].source_document == "TBT.xlsx"
        assert reqs[0].extracted_values["status"] == "F"

    def test_category_guessing(self):
        items = [
            TBTItem(row_number=1, section="", description="Motor voltage 440V", status="F"),
            TBTItem(row_number=2, section="", description="Body material SS 316L", status="F"),
            TBTItem(row_number=3, section="", description="Pressure transmitter 4-20mA", status="A"),
            TBTItem(row_number=4, section="", description="IMO MEPC certification", status="X"),
            TBTItem(row_number=5, section="", description="FAT test required", status="F"),
            TBTItem(row_number=6, section="", description="Design capacity 5 m3/h", status="F"),
        ]

        extractor = TenderExtractor(_make_mock_llm())
        reqs = extractor.requirements_from_tbt(items)

        categories = [r.category for r in reqs]
        assert categories[0] == "electrical"
        assert categories[1] == "material"
        assert categories[2] == "instrumentation"
        assert categories[3] == "certification"
        assert categories[4] == "qa_qc"
        assert categories[5] == "process"

    def test_not_applicable_items(self):
        """Items with status 'Y' (not applicable) should be non-mandatory."""
        items = [
            TBTItem(row_number=1, description="Some requirement", status="Y"),
            TBTItem(row_number=2, description="Another requirement", status="F"),
        ]

        extractor = TenderExtractor(_make_mock_llm())
        reqs = extractor.requirements_from_tbt(items)

        assert reqs[0].mandatory is False  # Y = not applicable
        assert reqs[1].mandatory is True   # F = fully compliant

    def test_empty_descriptions_skipped(self):
        items = [
            TBTItem(row_number=1, description="", status=""),
            TBTItem(row_number=2, description="Real requirement", status="F"),
        ]

        extractor = TenderExtractor(_make_mock_llm())
        reqs = extractor.requirements_from_tbt(items)

        assert len(reqs) == 1  # Empty description skipped

    def test_zero_cost(self):
        """TBT conversion should not incur any LLM cost."""
        extractor = TenderExtractor(_make_mock_llm())
        items = [TBTItem(row_number=1, description="Test", status="F")]
        extractor.requirements_from_tbt(items)

        assert extractor.total_cost_usd == 0.0
        assert extractor.call_count == 0
