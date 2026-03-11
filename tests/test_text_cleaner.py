"""Tests for text cleaning pipeline."""

from src.extraction.text_cleaner import TextCleaner


class TestTextCleaner:
    def setup_method(self):
        self.cleaner = TextCleaner()

    # ── Petrobras header removal ─────────────────────────────────────────

    def test_remove_petrobras_notice(self):
        text = (
            "5.2 SCOPE OF SUPPLY\n"
            "INFORMATION IN THIS DOCUMENT IS PROPERTY OF PETROBRAS AND SHALL NOT BE COPIED\n"
            "The OWS package shall include:\n"
        )
        result = self.cleaner.clean(text)
        assert "PROPERTY OF PETROBRAS" not in result.text
        assert "SCOPE OF SUPPLY" in result.text
        assert "OWS package" in result.text
        assert result.lines_removed >= 1

    def test_remove_standard_reference(self):
        text = "See requirements per N-0381 REV.L and applicable standards.\nPump specs:"
        result = self.cleaner.clean(text)
        assert "N-0381 REV.L" not in result.text
        assert "Pump specs" in result.text

    # ── Page numbers ─────────────────────────────────────────────────────

    def test_remove_standalone_page_numbers(self):
        text = "Some text about pumps.\n42\nMore text about valves."
        result = self.cleaner.clean(text)
        assert "\n42\n" not in result.text
        assert "pumps" in result.text
        assert "valves" in result.text

    def test_remove_page_x_of_y(self):
        text = "Pump specifications:\nSheet 3 of 56\nCapacity: 5 m3/h"
        result = self.cleaner.clean(text)
        assert "Sheet 3 of 56" not in result.text
        assert "Capacity" in result.text

    def test_keep_numbers_in_context(self):
        """Numbers that are part of specs should NOT be removed."""
        text = "Flow rate: 5 m3/h\nPressure: 42 bar\nTemperature range: 0 to 60 C"
        result = self.cleaner.clean(text)
        assert "42 bar" in result.text
        assert "5 m3/h" in result.text

    # ── Whitespace normalization ─────────────────────────────────────────

    def test_normalize_multiple_spaces(self):
        text = "Flow   rate:     5   m3/h"
        result = self.cleaner.normalize_whitespace(text)
        assert "Flow rate: 5 m3/h" == result

    def test_normalize_excessive_newlines(self):
        text = "Section A\n\n\n\n\nSection B"
        result = self.cleaner.normalize_whitespace(text)
        assert result == "Section A\n\nSection B"

    def test_strip_trailing_spaces(self):
        text = "Line one   \nLine two  \n"
        result = self.cleaner.normalize_whitespace(text)
        assert "   \n" not in result
        assert "  \n" not in result

    # ── Metadata extraction ──────────────────────────────────────────────

    def test_extract_sheet_number(self):
        text = "SHEET 3 of 56\nContent here"
        meta = self.cleaner.extract_page_metadata(text)
        assert meta.sheet_number == 3
        assert meta.total_sheets == 56

    def test_extract_document_code(self):
        text = "I-FD-3010.2G-5330-540-DTG-302-C\nSome content"
        meta = self.cleaner.extract_page_metadata(text)
        assert "I-FD-3010" in meta.document_code

    def test_extract_revision(self):
        text = "Document REV. C\nContent"
        meta = self.cleaner.extract_page_metadata(text)
        assert meta.revision == "C"

    # ── Edge cases ───────────────────────────────────────────────────────

    def test_empty_text(self):
        result = self.cleaner.clean("")
        assert result.text == ""
        assert result.lines_removed == 0

    def test_whitespace_only(self):
        result = self.cleaner.clean("   \n\n  \n  ")
        assert result.text == ""

    def test_clean_pages(self):
        pages = [
            "Page 1 content\nSHEET 1 of 3",
            "Page 2 content\nINFORMATION IN THIS DOCUMENT IS PROPERTY OF PETROBRAS",
            "Page 3 content",
        ]
        results = self.cleaner.clean_pages(pages)
        assert len(results) == 3
        assert "SHEET 1 of 3" not in results[0].text
        assert "PROPERTY OF PETROBRAS" not in results[1].text
        assert "Page 3 content" in results[2].text
