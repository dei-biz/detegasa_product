"""Tests for document type detection."""

import pytest

from src.extraction.document_type import DocumentType, detect_document_type


class TestDetectDocumentType:
    """Test filename pattern matching for Petrobras document conventions."""

    @pytest.mark.parametrize(
        "filename, expected",
        [
            # Data sheets (I-FD-)
            ("I-FD-3010.2G-5330-540-DTG-302-C.pdf", DocumentType.DATA_SHEET),
            ("I-FD-3010.2G-5330-800-DTG-301-IAB.pdf", DocumentType.DATA_SHEET),
            ("I-FD-3010.2G-5330-660-KES-303_REVA.pdf", DocumentType.DATA_SHEET),
            # Material requisition (I-RM-)
            ("I-RM-3010.2G-5330-667-KES-301_REVA.pdf", DocumentType.MATERIAL_REQUISITION),
            # Technical specification (I-ET-)
            ("I-ET-3010.1M-5330-667-P4X-001_C_SPECIF. FOR OWS PACKAGE.pdf", DocumentType.TECHNICAL_SPEC),
            ("I-ET-3010.00-1200-956-P4X-002_F_GENERAL PAINTING.pdf", DocumentType.TECHNICAL_SPEC),
            # Drawings (I-DE-)
            ("I-DE-3010.2G-5330-712-DTG-301-IAB.pdf", DocumentType.DRAWING),
            ("I-DE-3010.2G-1200-944-KES-301_REV0_FPDC_P&ID GENERAL NOTES.pdf", DocumentType.DRAWING),
            # Data lists (I-LI-)
            ("I-LI-3010.2G-5330-220-DTG-301-B.pdf", DocumentType.DATA_LIST),
            ("I-LI-3010.2G-5400-940-KES-301_REV0_FPDC_AREA CLASSIFICATION DATA LIST.pdf", DocumentType.DATA_LIST),
            # Reports (I-RL-)
            ("I-RL-3010.1M-1350-960-P4X-009_C_MOTION ANALYSIS.pdf", DocumentType.REPORT),
            # Manuals (MA-)
            ("MA-3010.2G-5330-973-DTG-301_B.pdf", DocumentType.MANUAL),
            # Evaluation table (TBT)
            ("Technical Bid Evaluation Table(TBT).xlsx", DocumentType.EVALUATION_TABLE),
            ("Technical Bid Evaluation Table(TBT).pdf", DocumentType.EVALUATION_TABLE),
            # Compliance check
            ("E&I technical compliance check sheet_DETEGASA.pdf", DocumentType.COMPLIANCE_CHECK),
            # Vendor data list
            ("APPENDIX5_VENDOR DATA REQUIREMENT LIST.xls", DocumentType.VENDOR_DATA_LIST),
            ("APPENDIX5_VENDOR DATA REQUIREMENT LIST_actualizado DTG.xls", DocumentType.VENDOR_DATA_LIST),
            # Technical clarification
            ("Technical Clarification(TC)_Detegasa.xlsx", DocumentType.TECHNICAL_CLARIFICATION),
            ("Technical Clarification(TC)_Detegasa.pdf", DocumentType.TECHNICAL_CLARIFICATION),
            # Templates
            ("ATTACHMENT #1.  SPIR.xls", DocumentType.TEMPLATE),
            ("Form-1) Electric Load List Format_FPSO P-78 Buzios.xlsx", DocumentType.TEMPLATE),
            ("TQF-P78-KES-DD-HUL-SUB-00XX _Template (2).xlsx", DocumentType.TEMPLATE),
        ],
    )
    def test_known_types(self, filename: str, expected: DocumentType):
        assert detect_document_type(filename) == expected

    def test_unknown_file(self):
        assert detect_document_type("random_notes.txt") == DocumentType.UNKNOWN

    def test_full_path(self):
        """Detection works with full paths, not just filenames."""
        path = "C:/Users/User/Documents/ESPECIFICACION/I-FD-3010.2G-5330-540-DTG-302-C.pdf"
        assert detect_document_type(path) == DocumentType.DATA_SHEET

    def test_case_insensitive(self):
        assert detect_document_type("i-fd-test.pdf") == DocumentType.DATA_SHEET
        assert detect_document_type("I-FD-TEST.PDF") == DocumentType.DATA_SHEET

    def test_all_enum_values_are_strings(self):
        """DocumentType inherits from str for JSON serialization."""
        for dt in DocumentType:
            assert isinstance(dt, str)
            assert isinstance(dt.value, str)
