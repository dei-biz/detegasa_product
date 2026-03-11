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

    # ── Material Requisition headers ──────────────────────────────────────

    def test_remove_material_requisition_header(self):
        text = (
            "MATERIAL REQUISITION\n"
            "Section 4 Process Requirements\n"
            "The equipment shall be designed for...\n"
        )
        result = self.cleaner.clean(text)
        assert "MATERIAL REQUISITION" not in result.text
        assert "Process Requirements" in result.text

    def test_remove_continuation_header(self):
        text = (
            "CONT. 3 OF 10\n"
            "4.2 Design Conditions\n"
            "Pressure: 6.7 barg\n"
        )
        result = self.cleaner.clean(text)
        assert "CONT." not in result.text
        assert "Pressure: 6.7 barg" in result.text

    # ── Data Sheet headers ────────────────────────────────────────────────

    def test_remove_data_sheet_header(self):
        text = (
            "DATA SHEET\n"
            "Type: Progressive cavity pump\n"
            "Capacity: 5 m3/h\n"
        )
        result = self.cleaner.clean(text)
        assert "DATA SHEET" not in result.text
        assert "Progressive cavity pump" in result.text

    def test_remove_folha_de_dados(self):
        text = (
            "FOLHA DE DADOS\n"
            "Tipo: Bomba de cavidade progressiva\n"
        )
        result = self.cleaner.clean(text)
        assert "FOLHA DE DADOS" not in result.text

    # ── Revision footer ──────────────────────────────────────────────────

    def test_remove_revision_footer(self):
        text = (
            "Some technical content.\n"
            "REV. 3\n"
            "More content.\n"
        )
        result = self.cleaner.clean(text)
        assert "REV. 3\n" not in result.text
        assert "technical content" in result.text

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

    # ── TOC detection ─────────────────────────────────────────────────────

    def test_is_toc_line_with_dots(self):
        """Lines with section number + title + dots + page number are TOC."""
        assert self.cleaner.is_toc_line("4.2.1 General Requirements .................. 23")
        assert self.cleaner.is_toc_line("5 SCOPE OF SUPPLY ......... 15")
        assert self.cleaner.is_toc_line("3.1 Design Conditions .............. 8")

    def test_is_toc_line_with_spaces(self):
        """Lines with section number + title + spaces + page number are TOC."""
        assert self.cleaner.is_toc_line("4.2.1 General Requirements                  23")
        assert self.cleaner.is_toc_line("5 SCOPE OF SUPPLY                           15")

    def test_is_toc_line_header(self):
        """TABLE OF CONTENTS header."""
        assert self.cleaner.is_toc_line("TABLE OF CONTENTS")
        assert self.cleaner.is_toc_line("  CONTENTS  ")
        assert self.cleaner.is_toc_line("INDEX")

    def test_is_not_toc_line(self):
        """Regular content lines should not be detected as TOC."""
        assert not self.cleaner.is_toc_line("The pump capacity is 5 m3/h")
        assert not self.cleaner.is_toc_line("4.2 Design Conditions")
        assert not self.cleaner.is_toc_line("Pressure: 42 bar")
        assert not self.cleaner.is_toc_line("")
        assert not self.cleaner.is_toc_line("   ")

    def test_is_toc_page(self):
        """A page where >50% of lines are TOC entries is a TOC page."""
        toc_page = (
            "TABLE OF CONTENTS\n"
            "1 INTRODUCTION .................. 3\n"
            "2 SCOPE OF SUPPLY ............... 5\n"
            "3 DESIGN CONDITIONS ............. 8\n"
            "3.1 General ..................... 8\n"
            "3.2 Operating Conditions ........ 9\n"
            "4 PROCESS REQUIREMENTS .......... 12\n"
            "5 MATERIALS ..................... 15\n"
        )
        assert self.cleaner.is_toc_page(toc_page)

    def test_is_not_toc_page(self):
        """A page with mostly content should not be a TOC page."""
        content_page = (
            "4.2 Design Conditions\n"
            "The equipment shall be designed for the following conditions:\n"
            "- Operating pressure: 6.7 barg\n"
            "- Design pressure: 10 barg\n"
            "- Operating temperature: 60°C max\n"
            "- Design temperature: 80°C\n"
            "All materials shall comply with NACE MR0175.\n"
        )
        assert not self.cleaner.is_toc_page(content_page)

    def test_is_toc_page_short_text(self):
        """Pages with very few lines should not be TOC."""
        assert not self.cleaner.is_toc_page("Title")
        assert not self.cleaner.is_toc_page("A\nB")

    def test_remove_toc_lines(self):
        """remove_toc_lines should strip TOC entries from mixed text."""
        text = (
            "4.2 Design Conditions\n"
            "4.2.1 General Requirements .................. 23\n"
            "The equipment shall be designed for the following:\n"
            "5 SCOPE OF SUPPLY ......... 15\n"
            "Pressure: 6.7 barg\n"
        )
        result = self.cleaner.remove_toc_lines(text)
        assert "General Requirements ..." not in result
        assert "SCOPE OF SUPPLY ..." not in result
        assert "4.2 Design Conditions" in result
        assert "Pressure: 6.7 barg" in result

    def test_clean_sets_is_toc_flag(self):
        """The clean() method should set is_toc on CleanResult for TOC pages."""
        toc_text = (
            "TABLE OF CONTENTS\n"
            "1 INTRODUCTION .................. 3\n"
            "2 SCOPE ......................... 5\n"
            "3 DESIGN ........................ 8\n"
            "4 PROCESS ....................... 12\n"
        )
        result = self.cleaner.clean(toc_text)
        assert result.is_toc is True

    def test_clean_not_toc_flag(self):
        """Normal content pages should have is_toc=False."""
        result = self.cleaner.clean("Normal text content.\nMore content here.")
        assert result.is_toc is False

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
