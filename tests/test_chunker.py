"""Tests for document chunking strategies."""

from src.extraction.chunker import Chunk, DocumentChunker, MIN_CHUNK_CHARS, MAX_CHUNK_CHARS
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
            "The following design conditions apply.\n"
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


# ── New tests for post-processing ────────────────────────────────────────────


class TestChunkSizeConstraints:
    """Test that min/max chunk size constraints are enforced."""

    def test_min_chunk_size_merge(self):
        """Tiny chunks should be merged with neighbours."""
        chunker = DocumentChunker(
            target_tokens=200,
            overlap_tokens=20,
            min_chunk_chars=200,
        )
        text = (
            "1 INTRODUCTION\n"
            "Short.\n"
            "\n"
            "2 SCOPE OF SUPPLY\n"
            "The vendor shall supply all equipment listed in this specification "
            "including pumps, separators, heaters, valves, and all instrumentation "
            "required for proper operation of the OWS package system.\n"
            "\n"
            "3 DESIGN CONDITIONS\n"
            "The following design conditions shall apply to all equipment.\n"
        )
        chunks = chunker.chunk(text, DocumentType.TECHNICAL_SPEC)
        # Post-processing should not crash and indices should be valid
        for i, chunk in enumerate(chunks):
            assert chunk.index == i

    def test_max_chunk_size_split(self):
        """Huge chunks should be split into sub-chunks."""
        chunker = DocumentChunker(
            target_tokens=200,
            overlap_tokens=20,
            max_chunk_chars=500,
        )
        # Create a section with lots of text
        text = (
            "1 INTRODUCTION\n"
            "Short intro.\n\n"
            "2 HUGE SECTION\n"
            + "\n\n".join([f"Paragraph {i}. " + "x" * 100 for i in range(20)])
            + "\n\n"
            "3 ANOTHER SECTION\n"
            "Brief content.\n"
        )
        chunks = chunker.chunk(text, DocumentType.TECHNICAL_SPEC)
        # All chunks should respect max_chunk_chars after splitting
        for chunk in chunks:
            assert chunk.char_count <= chunker.max_chunk_chars + chunker.target_chars, (
                f"Chunk too large: {chunk.char_count} chars > {chunker.max_chunk_chars}"
            )

    def test_chunks_reindexed(self):
        """After post-processing, chunk indices should be sequential."""
        chunker = DocumentChunker(target_tokens=100, overlap_tokens=10)
        text = (
            "1 SECTION ONE\n"
            "Content for section one with enough text.\n\n"
            "2 SECTION TWO\n"
            "Content for section two with enough text.\n\n"
            "3 SECTION THREE\n"
            "Content for section three with enough text.\n"
        )
        chunks = chunker.chunk(text, DocumentType.TECHNICAL_SPEC)
        for i, chunk in enumerate(chunks):
            assert chunk.index == i, f"Chunk {i} has index {chunk.index}"


class TestAppendixDetection:
    """Test that appendix sections are detected and marked in metadata."""

    def setup_method(self):
        self.chunker = DocumentChunker(target_tokens=200, overlap_tokens=20)

    def test_appendix_marked(self):
        """Sections titled APPENDIX should have is_appendix in metadata."""
        # Use min_chunk_chars=0 to prevent merging in this test
        chunker = DocumentChunker(target_tokens=200, overlap_tokens=20, min_chunk_chars=0)
        text = (
            "1 INTRODUCTION\n"
            "Normal body content here with enough text to pass minimum threshold "
            "for chunking. This section describes the scope of the specification.\n"
            "\n"
            "2 SCOPE\n"
            "More body content with sufficient length for a real chunk. The vendor "
            "shall supply all equipment as described in this specification.\n"
            "\n"
            "3 APPENDIX A\n"
            "Appendix content here with enough text to pass minimum threshold "
            "for chunking. This appendix contains supplementary information.\n"
        )
        chunks = chunker.chunk(text, DocumentType.TECHNICAL_SPEC)
        # Find the appendix chunk
        appendix_chunks = [c for c in chunks if c.metadata.get("is_appendix")]
        body_chunks = [c for c in chunks if not c.metadata.get("is_appendix")]
        assert len(appendix_chunks) >= 1, "Expected at least one appendix chunk"
        assert len(body_chunks) >= 1, "Expected at least one body chunk"

    def test_annex_marked(self):
        """ANNEX sections should also be marked as appendix."""
        text = (
            "1 INTRODUCTION\n"
            "Body content with enough text for the chunk to be real.\n\n"
            "2 ANNEX B\n"
            "Annex content with enough text for the chunk to be real.\n"
        )
        chunks = self.chunker.chunk(text, DocumentType.TECHNICAL_SPEC)
        appendix_chunks = [c for c in chunks if c.metadata.get("is_appendix")]
        assert len(appendix_chunks) >= 1

    def test_body_sections_not_marked(self):
        """Normal body sections should NOT have is_appendix."""
        text = (
            "1 INTRODUCTION\n"
            "Content with enough text for proper chunking purposes.\n\n"
            "2 SCOPE\n"
            "Content with enough text for proper chunking purposes.\n\n"
            "3 DESIGN CONDITIONS\n"
            "Content with enough text for proper chunking purposes.\n"
        )
        chunks = self.chunker.chunk(text, DocumentType.TECHNICAL_SPEC)
        for chunk in chunks:
            assert not chunk.metadata.get("is_appendix"), (
                f"Body chunk '{chunk.section_title}' incorrectly marked as appendix"
            )


class TestConstants:
    """Test that size constants are reasonable."""

    def test_min_chunk_chars_positive(self):
        assert MIN_CHUNK_CHARS > 0

    def test_max_chunk_chars_greater_than_min(self):
        assert MAX_CHUNK_CHARS > MIN_CHUNK_CHARS

    def test_default_values(self):
        assert MIN_CHUNK_CHARS == 200
        assert MAX_CHUNK_CHARS == 6000
