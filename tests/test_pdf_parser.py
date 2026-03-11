"""Tests for PDF parser — unit tests + integration with real project documents.

Integration tests are skipped if the documents are not present (CI-friendly).
"""

import pytest
from pathlib import Path

from src.extraction.pdf_parser import PDFParser, PDFDocument, PDFPage, is_tesseract_available
from src.extraction.document_type import DocumentType

# Project root for real document paths
PROJECT_ROOT = Path(__file__).parent.parent


class TestPDFPage:
    def test_basic(self):
        page = PDFPage(page_number=1, text="Hello", char_count=5)
        assert page.page_number == 1
        assert page.char_count == 5
        assert page.image_only is False

    def test_tables_default_empty(self):
        page = PDFPage(page_number=1, text="Hello", char_count=5)
        assert page.tables == []
        assert page.has_tables is False

    def test_has_tables(self):
        page = PDFPage(
            page_number=1,
            text="Some text",
            char_count=9,
            tables=[[["Type", "Pump"], ["Capacity", "5 m3/h"]]],
        )
        assert page.has_tables is True

    def test_ocr_applied_default(self):
        page = PDFPage(page_number=1, text="Hello", char_count=5)
        assert page.ocr_applied is False

    def test_tables_as_text_two_col(self):
        """2-column tables should be formatted as key: value pairs."""
        page = PDFPage(
            page_number=1,
            text="",
            char_count=0,
            tables=[[["Type", "Pump"], ["Capacity", "5 m3/h"], ["Material", "SS 316L"]]],
        )
        text = page.tables_as_text()
        assert "Type: Pump" in text
        assert "Capacity: 5 m3/h" in text
        assert "Material: SS 316L" in text

    def test_tables_as_text_multi_col(self):
        """Multi-column tables should be tab-separated."""
        page = PDFPage(
            page_number=1,
            text="",
            char_count=0,
            tables=[[["Item", "Desc", "Qty"], ["1", "Pump", "2"], ["2", "Valve", "4"]]],
        )
        text = page.tables_as_text()
        assert "Item\tDesc\tQty" in text
        assert "1\tPump\t2" in text

    def test_tables_as_text_empty(self):
        page = PDFPage(page_number=1, text="Hello", char_count=5)
        assert page.tables_as_text() == ""

    def test_tables_as_text_skips_empty_rows(self):
        page = PDFPage(
            page_number=1,
            text="",
            char_count=0,
            tables=[[["Key", "Value"], [None, None], ["Type", "Pump"]]],
        )
        text = page.tables_as_text()
        assert "Type: Pump" in text
        # Empty row should be skipped
        assert text.count("\n") < 3  # Not many lines


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

    def test_ocr_pages(self):
        doc = PDFDocument(
            filename="test.pdf",
            total_pages=2,
            pages=[
                PDFPage(page_number=1, text="Normal", char_count=6),
                PDFPage(page_number=2, text="OCR text", char_count=8, ocr_applied=True),
            ],
        )
        assert len(doc.ocr_pages) == 1
        assert doc.ocr_pages[0].page_number == 2

    def test_pages_with_tables(self):
        doc = PDFDocument(
            filename="test.pdf",
            total_pages=2,
            pages=[
                PDFPage(
                    page_number=1, text="With table", char_count=10,
                    tables=[[["A", "B"]]],
                ),
                PDFPage(page_number=2, text="No table", char_count=8),
            ],
        )
        assert len(doc.pages_with_tables) == 1
        assert doc.pages_with_tables[0].page_number == 1

    def test_full_text_with_tables(self):
        doc = PDFDocument(
            filename="test.pdf",
            total_pages=2,
            pages=[
                PDFPage(
                    page_number=1, text="Page one text.", char_count=14,
                    tables=[[["Type", "Pump"]]],
                ),
                PDFPage(page_number=2, text="Page two text.", char_count=14),
            ],
        )
        combined = doc.full_text_with_tables()
        assert "Page one text." in combined
        assert "[TABLE DATA]" in combined
        assert "Type: Pump" in combined
        assert "Page two text." in combined


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


class TestPDFParserOCRFlag:
    """Test OCR parameter handling (without necessarily running OCR)."""

    def test_ocr_false_default(self, tmp_path):
        """By default OCR should not be applied."""
        # Create a minimal valid PDF
        import fitz
        pdf_path = tmp_path / "test.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Hello World")
        doc.save(str(pdf_path))
        doc.close()

        parser = PDFParser()
        result = parser.parse(pdf_path, ocr=False)
        assert all(not p.ocr_applied for p in result.pages)

    def test_ocr_flag_accepted(self, tmp_path):
        """The parse method should accept the ocr flag without error."""
        import fitz
        pdf_path = tmp_path / "test.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Text content here")
        doc.save(str(pdf_path))
        doc.close()

        parser = PDFParser()
        # This should not raise, even if Tesseract is not installed
        result = parser.parse(pdf_path, ocr=True)
        assert result.total_pages == 1

    def test_extract_tables_flag(self, tmp_path):
        """With extract_tables=False, no tables should be returned."""
        import fitz
        pdf_path = tmp_path / "test.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Some text")
        doc.save(str(pdf_path))
        doc.close()

        parser = PDFParser()
        result = parser.parse(pdf_path, extract_tables=False)
        assert all(p.tables == [] for p in result.pages)


class TestTesseractAvailability:
    def test_is_tesseract_available_returns_bool(self):
        """Should return a boolean without raising."""
        result = is_tesseract_available()
        assert isinstance(result, bool)


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
        self.doc = self.parser.parse(_DATA_SHEET, extract_tables=True)

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

    def test_extracts_tables(self):
        """At least some pages should have tables."""
        pages_with_tables = self.doc.pages_with_tables
        assert len(pages_with_tables) > 0, "Expected at least one page with tables"

    def test_tables_have_content(self):
        """Extracted tables should contain meaningful data."""
        for page in self.doc.pages_with_tables[:3]:
            for table in page.tables:
                # Each table should have at least 1 non-empty row
                non_empty = [r for r in table if any(c for c in r)]
                assert len(non_empty) > 0, f"Table on page {page.page_number} is empty"


@pytest.mark.skipif(not _DATA_SHEET.exists(), reason="Real documents not available")
@pytest.mark.skipif(not is_tesseract_available(), reason="Tesseract OCR not installed")
class TestPDFParserOCRReal:
    """Integration test: OCR on real data sheet image pages."""

    def test_ocr_produces_text_from_images(self):
        parser = PDFParser()
        doc_no_ocr = parser.parse(_DATA_SHEET, ocr=False)
        doc_with_ocr = parser.parse(_DATA_SHEET, ocr=True)

        # OCR should produce more text than no-OCR
        text_no_ocr = len(doc_no_ocr.full_text)
        text_with_ocr = len(doc_with_ocr.full_text)

        assert text_with_ocr >= text_no_ocr, (
            f"OCR text ({text_with_ocr}) should be >= non-OCR text ({text_no_ocr})"
        )

        # At least some pages should have ocr_applied=True
        ocr_pages = [p for p in doc_with_ocr.pages if p.ocr_applied]
        assert len(ocr_pages) > 0, "Expected at least one OCR page"


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
