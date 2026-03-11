"""Tests for document chunking strategies."""

from src.extraction.chunker import Chunk, DocumentChunker
from src.extraction.document_type import DocumentType


class TestChunkModel:
    def test_basic_chunk(self):
        c = Chunk(index=0, text="Hello world")
        assert c.index == 0
        assert c.char_count == 11
        assert c.estimated_tokens > 0

    def test_estimated_tokens(self):
        # ~4 chars per token
        text = "a" * 400
        c = Chunk(index=0, text=text)
        assert c.estimated_tokens == 100

    def test_metadata(self):
        c = Chunk(index=0, text="test", metadata={"source": "pdf"})
        assert c.metadata["source"] == "pdf"


class TestGenericChunking:
    def setup_method(self):
        self.chunker = DocumentChunker(target_tokens=50, overlap_tokens=10)

    def test_short_text_single_chunk(self):
        text = "Short text that fits in one chunk."
        chunks = self.chunker.chunk_generic(text)
        assert len(chunks) == 1
        assert chunks[0].text == text

    def test_long_text_splits(self):
        # Create text with multiple paragraphs exceeding target
        paragraphs = [f"Paragraph {i}. " + "x" * 150 for i in range(10)]
        text = "\n\n".join(paragraphs)
        chunks = self.chunker.chunk_generic(text)
        assert len(chunks) > 1
        # All text should be covered
        for chunk in chunks:
            assert len(chunk.text) > 0

    def test_empty_text(self):
        chunks = self.chunker.chunk_generic("")
        assert chunks == []

    def test_chunk_indices_sequential(self):
        text = "\n\n".join(["Paragraph " + "x" * 200 for _ in range(5)])
        chunks = self.chunker.chunk_generic(text)
        for i, chunk in enumerate(chunks):
            assert chunk.index == i


class TestDataSheetChunking:
    def setup_method(self):
        self.chunker = DocumentChunker(target_tokens=200, overlap_tokens=20)

    def test_component_splitting(self):
        """Data sheet text with component headers should split by component."""
        text = (
            "1 PROGRESSIVE CAVITY PUMP\n"
            "Model: PCM 13c12s\n"
            "Capacity: 5 m3/h\n"
            "Material: SS 316L\n"
            "\n"
            "2 OILY WATER SEPARATOR\n"
            "Type: Coalescence\n"
            "Capacity: 5 m3/h\n"
            "Oil content output: <15 ppm\n"
            "\n"
            "3 HEATER UNIT\n"
            "Type: Electric immersion\n"
            "Power: 24 kW\n"
        )
        chunks = self.chunker.chunk_data_sheet(text)
        assert len(chunks) >= 3
        assert "PROGRESSIVE CAVITY PUMP" in chunks[0].section_title
        assert "OILY WATER SEPARATOR" in chunks[1].section_title
        assert chunks[0].chunk_type == "component"

    def test_no_components_falls_back(self):
        """Text without component headers falls back to generic chunking."""
        text = "Just plain text without any component headers.\n" * 5
        chunks = self.chunker.chunk_data_sheet(text)
        assert len(chunks) >= 1


class TestSectionChunking:
    def setup_method(self):
        self.chunker = DocumentChunker(target_tokens=200, overlap_tokens=20)

    def test_numbered_sections(self):
        text = (
            "1 INTRODUCTION\n"
            "This specification covers the OWS package.\n"
            "\n"
            "2 SCOPE OF SUPPLY\n"
            "The vendor shall supply all equipment listed.\n"
            "\n"
            "3 DESIGN CONDITIONS\n"
            "3.1 General\n"
            "The following design conditions apply.\n"
            "3.2 Pressure\n"
            "Design pressure: 6.7 barg.\n"
        )
        chunks = self.chunker.chunk_by_section(text)
        assert len(chunks) >= 3
        assert chunks[0].chunk_type == "section"
        # Section titles should include the number
        assert "1" in chunks[0].section_title

    def test_no_sections_falls_back(self):
        text = "Plain text without numbered sections."
        chunks = self.chunker.chunk_by_section(text)
        assert len(chunks) >= 1


class TestDocumentTypeRouting:
    def setup_method(self):
        self.chunker = DocumentChunker(target_tokens=200, overlap_tokens=20)

    def test_data_sheet_routes(self):
        text = (
            "1 PUMP\nFlow: 5 m3/h\n\n"
            "2 SEPARATOR\nType: coalescence\n\n"
            "3 HEATER\nPower: 24 kW\n"
        )
        chunks = self.chunker.chunk(text, DocumentType.DATA_SHEET)
        assert any(c.chunk_type == "component" for c in chunks)

    def test_spec_routes(self):
        text = (
            "1 INTRODUCTION\nText here.\n\n"
            "2 SCOPE\nMore text.\n"
        )
        chunks = self.chunker.chunk(text, DocumentType.TECHNICAL_SPEC)
        assert any(c.chunk_type == "section" for c in chunks)

    def test_unknown_routes_to_generic(self):
        text = "Some generic text.\n\nAnother paragraph."
        chunks = self.chunker.chunk(text, DocumentType.UNKNOWN)
        assert len(chunks) >= 1
        assert chunks[0].chunk_type == "text"


class TestPageMapping:
    def setup_method(self):
        self.chunker = DocumentChunker(target_tokens=50, overlap_tokens=10)

    def test_page_mapping(self):
        text = "Page one content.\n\nPage two content."
        mapping = {0: 1, 18: 2}
        chunks = self.chunker.chunk_generic(text, page_mapping=mapping)
        assert len(chunks) >= 1
        assert chunks[0].page_start is not None

    def test_no_mapping(self):
        text = "Some text."
        chunks = self.chunker.chunk_generic(text)
        assert chunks[0].page_start is None
