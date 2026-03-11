"""Tests for Pydantic schemas — using real data from DETEGASA P-78 OWS."""

import pytest
from pydantic import ValidationError

from src.schemas.common import (
    ApplicabilityStatus,
    CertificationSpec,
    CertType,
    ComplianceStatus,
    ConnectionSpec,
    MaterialSpec,
    MeasuredValue,
    RiskLevel,
)
from src.schemas.compliance import (
    ComplianceItem,
    ComplianceResult,
    ComplianceSummary,
    CostImpact,
)
from src.schemas.product import (
    BasePerformance,
    ComponentSpec,
    GWTPerformance,
    OWSPerformance,
    ProductSpec,
)
from src.schemas.tender import (
    ProcessRequirement,
    TenderMetadata,
    TenderRequirementItem,
    TenderSpec,
)


# ── Common types ─────────────────────────────────────────────────────────────


class TestMeasuredValue:
    def test_basic(self):
        mv = MeasuredValue(value=5.0, unit="m3/h")
        assert mv.value == 5.0
        assert mv.unit == "m3/h"
        assert str(mv) == "5.0 m3/h"

    def test_negative_value(self):
        mv = MeasuredValue(value=-0.3, unit="barg")
        assert mv.value == -0.3


class TestMaterialSpec:
    def test_full_spec(self):
        mat = MaterialSpec(
            designation="SS 316L",
            grade="316L",
            family="stainless_steel",
            standard="AISI",
        )
        assert mat.designation == "SS 316L"
        assert mat.grade == "316L"

    def test_minimal(self):
        mat = MaterialSpec(designation="Carbon Steel")
        assert mat.grade is None
        assert mat.family is None


class TestConnectionSpec:
    def test_flanged(self):
        conn = ConnectionSpec(type="Flanged", size="DN50", rating="PN40")
        assert conn.type == "Flanged"
        assert conn.rating == "PN40"


# ── Certification schemas ────────────────────────────────────────────────────


class TestCertificationSpec:
    def test_full_certification(self):
        """Test a fully populated certification (IMO type-approval)."""
        from datetime import date

        cert = CertificationSpec(
            standard_code="IMO MEPC 107(49)",
            standard_title="Guidelines for Oil-Water Separators",
            cert_type=CertType.REGULATORY,
            applicability=ApplicabilityStatus.CERTIFIED,
            issuing_body="ABS",
            certificate_no="TAC-2024-00123",
            valid_from=date(2024, 3, 15),
            valid_until=date(2029, 3, 14),
            scope="OWS 1-5 m3/h bilge water separators",
            notes="Renewed March 2024",
        )
        assert cert.standard_code == "IMO MEPC 107(49)"
        assert cert.cert_type == CertType.REGULATORY
        assert cert.applicability == ApplicabilityStatus.CERTIFIED
        assert cert.valid_until == date(2029, 3, 14)

    def test_minimal_certification(self):
        """Only mandatory fields: code, type, applicability."""
        cert = CertificationSpec(
            standard_code="ASME VIII Div.1",
            cert_type=CertType.DESIGN_CODE,
            applicability=ApplicabilityStatus.COMPLIANT,
        )
        assert cert.issuing_body == ""
        assert cert.certificate_no == ""
        assert cert.valid_until is None

    def test_pending_certification(self):
        """INMETRO pending — common in Petrobras bids."""
        cert = CertificationSpec(
            standard_code="INMETRO",
            cert_type=CertType.COUNTRY,
            applicability=ApplicabilityStatus.PENDING,
            notes="Certification process started Q1 2025",
        )
        assert cert.applicability == ApplicabilityStatus.PENDING
        assert "Q1 2025" in cert.notes

    def test_not_applicable(self):
        """ATEX not applicable for non-hazardous area."""
        cert = CertificationSpec(
            standard_code="ATEX 2014/34/EU",
            cert_type=CertType.HAZARDOUS_AREA,
            applicability=ApplicabilityStatus.NOT_APPLICABLE,
            notes="Equipment installed in non-hazardous engine room",
        )
        assert cert.applicability == ApplicabilityStatus.NOT_APPLICABLE

    def test_potentially_applicable(self):
        """Standard that may or may not apply depending on project."""
        cert = CertificationSpec(
            standard_code="IECEx",
            cert_type=CertType.HAZARDOUS_AREA,
            applicability=ApplicabilityStatus.POTENTIALLY_APPLICABLE,
            notes="Depends on area classification at installation site",
        )
        assert cert.applicability == ApplicabilityStatus.POTENTIALLY_APPLICABLE

    def test_expired(self):
        """Certificate that has lapsed."""
        from datetime import date

        cert = CertificationSpec(
            standard_code="DNV GL",
            cert_type=CertType.CLASS_SOCIETY,
            applicability=ApplicabilityStatus.EXPIRED,
            issuing_body="DNV",
            certificate_no="TAP-2019-456",
            valid_until=date(2024, 6, 30),
            notes="Renewal pending",
        )
        assert cert.applicability == ApplicabilityStatus.EXPIRED

    def test_all_cert_types_are_strings(self):
        """Enums serialize to strings for JSON."""
        for ct in CertType:
            assert isinstance(ct.value, str)
        for ap in ApplicabilityStatus:
            assert isinstance(ap.value, str)

    def test_from_dict(self):
        """Verify CertificationSpec works from dict/JSON input."""
        data = {
            "standard_code": "ISO 9001:2015",
            "cert_type": "quality",
            "applicability": "certified",
            "issuing_body": "TÜV Rheinland",
            "certificate_no": "QMS-2023-789",
        }
        cert = CertificationSpec.model_validate(data)
        assert cert.cert_type == CertType.QUALITY
        assert cert.applicability == ApplicabilityStatus.CERTIFIED


# ── Product schemas ──────────────────────────────────────────────────────────


class TestComponentSpec:
    def test_pump_from_real_data(self):
        """Test with real data from DETEGASA OWS P1 pump."""
        comp = ComponentSpec(
            tag="P1",
            type="pump",
            name="Progressive cavity pump PCM 13c12s",
            materials={
                "body": MaterialSpec(designation="SS 316L", grade="316L", family="stainless_steel"),
                "rotor": MaterialSpec(designation="SS 420", grade="420", family="stainless_steel"),
                "stator": MaterialSpec(designation="NBR", family="polymer"),
            },
            mechanical={
                "connections": "PN40 DN50 Class 150 NPS 2\"",
                "capacity_m3h": 5,
                "max_pressure_bar": 3.5,
            },
            electrical={
                "voltage": "440V",
                "frequency_hz": 60,
                "phases": 3,
                "power_kw": 3,
                "ip_rating": "IP66",
                "insulation_class": "F",
                "speed_rpm": 600,
            },
        )
        assert comp.tag == "P1"
        assert comp.type == "pump"
        assert comp.materials["body"].grade == "316L"

    def test_type_validation(self):
        """Unknown component types should be rejected."""
        with pytest.raises(ValidationError, match="Unknown component type"):
            ComponentSpec(
                tag="X1",
                type="nuclear_reactor",
                name="Test",
            )

    def test_type_normalization(self):
        """Component types should be normalized to lowercase."""
        comp = ComponentSpec(tag="P1", type="PUMP", name="Test pump")
        assert comp.type == "pump"

    def test_sensor(self):
        comp = ComponentSpec(
            tag="LS3",
            type="sensor",
            name="Level switch",
            instrumentation={"range": "0-100%", "output": "4-20mA"},
        )
        assert comp.type == "sensor"


class TestProductSpec:
    def test_ows_product(self):
        """Test with structure matching real DETEGASA OWS."""
        product = ProductSpec(
            product_id="OWS-5330501",
            product_family="OWS",
            manufacturer="DETEGASA",
            model="OWS-5",
            revision="C",
            performance=OWSPerformance(
                service="Bilge water separation",
                capacity=MeasuredValue(value=5.0, unit="m3/h"),
                oil_input_max_ppm=500,
                oil_output_max_ppm=15,
                design_pressure=MeasuredValue(value=6.7, unit="barg"),
                design_temperature=MeasuredValue(value=60, unit="C"),
                operation_mode="intermittent",
            ),
            certifications=[
                CertificationSpec(
                    standard_code="IMO MEPC 107(49)",
                    cert_type=CertType.REGULATORY,
                    applicability=ApplicabilityStatus.CERTIFIED,
                    issuing_body="IMO",
                    certificate_no="TAC-2024-001",
                    scope="OWS 1-5 m3/h",
                ),
                CertificationSpec(
                    standard_code="MARPOL Annex I Reg.21",
                    cert_type=CertType.REGULATORY,
                    applicability=ApplicabilityStatus.COMPLIANT,
                ),
                CertificationSpec(
                    standard_code="ABS",
                    cert_type=CertType.CLASS_SOCIETY,
                    applicability=ApplicabilityStatus.CERTIFIED,
                    issuing_body="ABS",
                ),
            ],
            components=[
                ComponentSpec(
                    tag="P1",
                    type="pump",
                    name="Progressive cavity pump PCM 13c12s",
                ),
            ],
        )
        assert product.product_family == "OWS"
        assert product.performance.capacity.value == 5.0
        assert isinstance(product.performance, OWSPerformance)
        assert product.performance.oil_output_max_ppm == 15

    def test_gwt_product(self):
        """Test GWT product with discriminated union."""
        product = ProductSpec(
            product_id="GWT-001",
            product_family="GWT",
            model="GWT-10",
            performance=GWTPerformance(
                service="Grey water treatment",
                capacity=MeasuredValue(value=10.0, unit="m3/h"),
                design_pressure=MeasuredValue(value=4.0, unit="barg"),
                design_temperature=MeasuredValue(value=45, unit="C"),
                operation_mode="continuous",
                bod_input_mg_l=250.0,
                bod_output_mg_l=25.0,
            ),
        )
        assert isinstance(product.performance, GWTPerformance)
        assert product.performance.family == "GWT"
        assert product.performance.bod_input_mg_l == 250.0

    def test_discriminated_union_from_dict(self):
        """Test that JSON/dict with 'family' field routes correctly."""
        data = {
            "product_id": "OWS-001",
            "model": "OWS-5",
            "performance": {
                "family": "OWS",
                "service": "Bilge water separation",
                "capacity": {"value": 5.0, "unit": "m3/h"},
                "oil_input_max_ppm": 500,
                "oil_output_max_ppm": 15,
                "design_pressure": {"value": 6.7, "unit": "barg"},
                "design_temperature": {"value": 60, "unit": "C"},
                "operation_mode": "intermittent",
            },
        }
        product = ProductSpec.model_validate(data)
        assert isinstance(product.performance, OWSPerformance)
        assert product.performance.oil_input_max_ppm == 500
        assert product.performance.oil_output_max_ppm == 15


# ── Tender schemas ───────────────────────────────────────────────────────────


class TestTenderSpec:
    def test_p78_tender(self):
        """Test with real P-78 FPSO Buzios tender structure."""
        tender = TenderSpec(
            tender_id="P78-OWS-001",
            metadata=TenderMetadata(
                project_name="P-78 FPSO Buzios",
                client="Petrobras",
                contractor="Keppel/HHI",
                classification_society="ABS",
                vessel_type="FPSO",
                location="Santos Basin, Brazil",
            ),
            process_requirements=ProcessRequirement(
                service="Bilge water separation",
                flow_rate=MeasuredValue(value=5.0, unit="m3/h"),
                oil_input_max_ppm=500,
                oil_output_max_ppm=15,
                design_pressure=MeasuredValue(value=6.7, unit="barg"),
                design_temperature=MeasuredValue(value=60, unit="C"),
                operation_mode="intermittent",
                regulatory_compliance=["IMO MEPC 107(49)", "MARPOL Annex I Reg.21"],
            ),
            general_requirements={
                "design_life_years": 30,
                "field_proven": {"min_installations": 3, "min_hours_each": 24000},
                "asbestos_free": True,
                "max_noise_db": 85,
            },
            electrical_requirements={
                "voltage": "440V",
                "frequency_hz": 60,
                "inmetro_required": True,
            },
        )
        assert tender.metadata.client == "Petrobras"
        assert tender.process_requirements.flow_rate.value == 5.0
        assert tender.general_requirements["design_life_years"] == 30


class TestTenderRequirementItem:
    def test_material_requirement(self):
        req = TenderRequirementItem(
            id="REQ-MAT-001",
            category="material",
            requirement_text="All wetted parts shall be SS 316L minimum",
            mandatory=True,
            source_document="I-ET-3010.1M-5330-667-P4X-001_C",
            source_section="5.2.1",
            extracted_values={"material": "SS 316L", "scope": "wetted_parts"},
        )
        assert req.mandatory is True
        assert req.category == "material"


# ── Compliance schemas ───────────────────────────────────────────────────────


class TestComplianceResult:
    def test_full_result(self):
        result = ComplianceResult(
            comparison_id="comp-001",
            product_id="OWS-5330501",
            tender_id="P78-OWS-001",
            overall_score=87.5,
            items=[
                ComplianceItem(
                    requirement_id="REQ-MAT-001",
                    category="material",
                    requirement_text="Body material SS 316L",
                    product_value="SS 316L",
                    tender_value="SS 316L",
                    status=ComplianceStatus.COMPLIANT,
                    risk_level=RiskLevel.LOW,
                ),
                ComplianceItem(
                    requirement_id="REQ-CERT-001",
                    category="certification",
                    requirement_text="INMETRO compliance required",
                    product_value="Not certified",
                    tender_value="Required",
                    status=ComplianceStatus.NON_COMPLIANT,
                    gap_description="INMETRO certification missing",
                    modification_needed="Obtain INMETRO certification",
                    cost_impact=CostImpact(
                        estimated_delta_eur=15000,
                        confidence="medium",
                        notes="Based on similar certification processes",
                    ),
                    risk_level=RiskLevel.HIGH,
                ),
            ],
            summary=ComplianceSummary(
                total_requirements=53,
                compliant_count=45,
                non_compliant_count=8,
                estimated_total_delta_eur=42000,
                disqualifying_gaps=["Field proven: only 2 installations documented"],
            ),
        )
        assert result.overall_score == 87.5
        assert len(result.items) == 2
        assert result.items[0].status == ComplianceStatus.COMPLIANT
        assert result.items[1].cost_impact.estimated_delta_eur == 15000
        assert result.summary.non_compliant_count == 8

    def test_score_validation(self):
        """Score must be 0-100."""
        with pytest.raises(ValidationError):
            ComplianceResult(
                comparison_id="x",
                product_id="x",
                tender_id="x",
                overall_score=150,  # Invalid!
                summary=ComplianceSummary(total_requirements=0),
            )
