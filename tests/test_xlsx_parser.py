"""Tests for Excel parser — unit tests + integration with real documents.

Integration tests are skipped if the documents are not present (CI-friendly).
"""

import pytest
from pathlib import Path

from src.extraction.xlsx_parser import (
    ExcelParser,
    ExcelSheet,
    TBTItem,
    ComplianceCheckItem,
)

PROJECT_ROOT = Path(__file__).parent.parent


class TestModels:
    def test_tbt_item(self):
        item = TBTItem(
            row_number=5,
            section="3.1",
            description="Pump capacity",
            spec_requirement="5 m3/h min",
            bidder_response="5 m3/h",
            status="F",
        )
        assert item.status == "F"
        assert item.row_number == 5

    def test_compliance_item(self):
        item = ComplianceCheckItem(
            row_number=10,
            section_no="4.2",
            subject="Cable sizing",
            complies=True,
        )
        assert item.complies is True

    def test_excel_sheet(self):
        sheet = ExcelSheet(
            sheet_name="Data",
            headers=["A", "B", "C"],
            rows=[{"A": "1", "B": "2", "C": "3"}],
            total_rows=1,
        )
        assert sheet.total_rows == 1


class TestExcelParserErrors:
    def setup_method(self):
        self.parser = ExcelParser()

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            self.parser.parse_generic("nonexistent.xlsx")

    def test_not_excel(self, tmp_path):
        txt = tmp_path / "test.txt"
        txt.write_text("not excel")
        with pytest.raises(ValueError, match="Not an Excel"):
            self.parser.parse_generic(txt)


# ── Integration tests with real documents ────────────────────────────────────

_TBT_FILE = (
    PROJECT_ROOT
    / "ESPECIFICACION DE CLIENTE"
    / "APPENDIX 12_TECHNICAL BID EVALUATION TABLE"
    / "Technical Bid Evaluation Table(TBT).xlsx"
)

_TC_FILE = (
    PROJECT_ROOT
    / "ESPECIFICACION DE CLIENTE"
    / "APPENDIX 6_TECHNICAL CLARIFICATION SHEET"
    / "Technical Clarification(TC)_Detegasa.xlsx"
)

_VDRL_FILE = (
    PROJECT_ROOT
    / "ESPECIFICACION DE CLIENTE"
    / "APPENDIX 5_VDRL"
    / "APPENDIX5_VENDOR DATA REQUIREMENT LIST.xls"
)


@pytest.mark.skipif(not _TBT_FILE.exists(), reason="TBT file not available")
class TestTBTParsing:
    """Integration test with real Technical Bid Evaluation Table."""

    def setup_method(self):
        self.parser = ExcelParser()
        self.items = self.parser.parse_tbt(_TBT_FILE)

    def test_parses_items(self):
        assert len(self.items) > 50  # Expect ~273 rows

    def test_items_are_tbt_type(self):
        assert all(isinstance(item, TBTItem) for item in self.items)

    def test_rows_have_content(self):
        """Most rows should have a description."""
        with_desc = [i for i in self.items if i.description.strip()]
        assert len(with_desc) > 30

    def test_status_codes_present(self):
        """Should find some status codes (F/A/X etc.)."""
        statuses = {i.status for i in self.items if i.status}
        assert len(statuses) > 0


@pytest.mark.skipif(not _TBT_FILE.exists(), reason="TBT file not available")
class TestTBTGeneric:
    """Parse TBT as generic to verify sheet structure."""

    def setup_method(self):
        self.parser = ExcelParser()
        self.sheets = self.parser.parse_generic(_TBT_FILE)

    def test_has_sheets(self):
        assert len(self.sheets) >= 1

    def test_has_headers(self):
        assert len(self.sheets[0].headers) > 3

    def test_has_rows(self):
        assert self.sheets[0].total_rows > 50


@pytest.mark.skipif(not _VDRL_FILE.exists(), reason="VDRL file not available")
class TestVDRLParsing:
    """Integration test with Vendor Data Requirement List (.xls)."""

    def setup_method(self):
        self.parser = ExcelParser()
        self.sheets = self.parser.parse_generic(_VDRL_FILE)

    def test_parses_xls(self):
        assert len(self.sheets) >= 1

    def test_has_rows(self):
        total = sum(s.total_rows for s in self.sheets)
        assert total > 10


@pytest.mark.skipif(not _TC_FILE.exists(), reason="TC file not available")
class TestTCParsing:
    """Integration test with Technical Clarification (.xlsx)."""

    def setup_method(self):
        self.parser = ExcelParser()
        self.sheets = self.parser.parse_generic(_TC_FILE)

    def test_parses_xlsx(self):
        assert len(self.sheets) >= 1
