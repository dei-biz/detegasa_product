"""Tests for PDF parser — unit tests + integration with real project documents.

Integration tests are skipped if the documents are not present (CI-friendly).
"""

import pytest
from pathlib import Path

from src.extraction.pdf_parser import PDFParser, PDFDocument, PDFPage
from src.extraction.document_type import DocumentType

# Project root for real document paths
PROJECT_ROOT = Path(__file__).parent.parent


class TestPDFPage:
    def test_basic(self):
        page = PDFPage(page_number=1, text="Hello", char_count=5)
        assert page.page_number == 1
        assert page.char_count == 5
        assert page.image_only is False


class TestPDFDocument:
    def test_full_text(self):
        doc = PDFDocument(
            filename="test.pdf",
            total_pages=2,
            pages=[
                PDFPage(page_number=1, text="Page one.", char_count=9),
                PDFPage(page_number=2, text="Page two.", char_count=9),
            ],
        )
        assert "Page one." in doc.full_text
        assert "Page two." in doc.full_text

    def test_text_vs_image_pages(self):
        doc = PDFDocument(
            filename="test.pdf",
            total_pages=3,
            pages=[
                PDFPage(page_number=1, text="Text page", char_count=100),
                PDFPage(page_number=2, text="", char_count=0, has_images=True, image_only=True),
                PDFPage(page_number=3, text="Another text", char_count=50),
            ],
        )
        assert len(doc.text_pages) == 2
        assert len(doc.image_only_pages) == 1


class TestPDFParserErrors:
    def setup_method(self):
        self.parser = PDFParser()

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            self.parser.parse("nonexistent.pdf")

    def test_not_a_pdf(self, tmp_path):
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("not a pdf")
        with pytest.raises(ValueError, match="Not a PDF"):
            self.parser.parse(txt_file)


# ── Integration tests with real documents ────────────────────────────────────

# Data sheet (I-FD): OWS-5 data sheet ~56 pages
_DATA_SHEET = PROJECT_ROOT / "DOCUMENTACION" / "I-FD-3010.2G-5330-540-DTG-302-C.pdf"

# Material requisition (I-RM): ~99 pages
_MAT_REQ = PROJECT_ROOT / "ESPECIFICACION DE CLIENTE" / "APPENDIX 2_PACKAGE SPECIFICATIONS" / \
    "01. I-ET-3010.1M-5330-667-P4X-001_C_SPECIF. FOR OWS PACKAGE.pdf"

# Client data sheet (I-FD from client)
_CLIENT_DS = PROJECT_ROOT / "ESPECIFICACION DE CLIENTE" / "APPENDIX 1_DATASHEETS" / \
    "I-FD-3010.2G-5330-660-KES-303_REVA.pdf"


@pytest.mark.skipif(not _DATA_SHEET.exists(), reason="Real documents not available")
class TestPDFParserRealDataSheet:
    """Integration test with real DETEGASA data sheet."""

    def setup_method(self):
        self.parser = PDFParser()
        self.doc = self.parser.parse(_DATA_SHEET)

    def test_parses_successfully(self):
        assert isinstance(self.doc, PDFDocument)
        assert self.doc.total_pages > 0

    def test_detects_document_type(self):
        assert self.doc.document_type == DocumentType.DATA_SHEET

    def test_has_text_content(self):
        """Most pages should have extracted text."""
        text_pages = [p for p in self.doc.pages if p.char_count > 30]
        assert len(text_pages) > 0

    def test_full_text_not_empty(self):
        assert len(self.doc.full_text) > 100

    def test_filename_preserved(self):
        assert "I-FD-3010" in self.doc.filename


@pytest.mark.skipif(not _MAT_REQ.exists(), reason="Real documents not available")
class TestPDFParserRealSpec:
    """Integration test with OWS package specification."""

    def setup_method(self):
        self.parser = PDFParser()
        self.doc = self.parser.parse(_MAT_REQ)

    def test_parses_successfully(self):
        assert self.doc.total_pages > 0

    def test_detects_spec_type(self):
        assert self.doc.document_type == DocumentType.TECHNICAL_SPEC

    def test_has_substantial_text(self):
        assert len(self.doc.full_text) > 500


@pytest.mark.skipif(not _CLIENT_DS.exists(), reason="Real documents not available")
class TestPDFParserClientDataSheet:
    """Integration test with client data sheet."""

    def setup_method(self):
        self.parser = PDFParser()
        self.doc = self.parser.parse(_CLIENT_DS)

    def test_parses_successfully(self):
        assert self.doc.total_pages > 0

    def test_detects_data_sheet(self):
        assert self.doc.document_type == DocumentType.DATA_SHEET
