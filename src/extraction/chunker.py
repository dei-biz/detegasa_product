"""Semantic chunking strategies for different document types.

Splits cleaned text into semantically meaningful chunks suitable for
embedding and retrieval.  Strategies vary by document type:

- data_sheet    → split by component (pump, filter, valve, etc.)
- technical_spec / material_requisition → split by numbered sections
- generic        → split by token count with overlap

Post-processing ensures chunk quality:
- Tiny chunks (< MIN_CHUNK_CHARS) are merged with neighbours.
- Huge chunks (> MAX_CHUNK_CHARS) are split by paragraphs.
- TOC pages are filtered out.
- Appendix sections are flagged in metadata.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from src.extraction.document_type import DocumentType
from src.extraction.text_cleaner import TextCleaner

# ── Size constraints ──────────────────────────────────────────────────────────

MIN_CHUNK_CHARS = 200   # Chunks smaller than this are merged with neighbours
MAX_CHUNK_CHARS = 6000  # Chunks larger than this are split into sub-chunks


class Chunk(BaseModel):
    """A semantically meaningful text chunk ready for embedding."""

    index: int
    text: str
    page_start: int | None = None
    page_end: int | None = None
    section_title: str = ""
    chunk_type: str = "text"  # text, table, component, section
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def char_count(self) -> int:
        return len(self.text)

    @property
    def estimated_tokens(self) -> int:
        """Rough estimate: ~4 chars per token for English/technical text."""
        return len(self.text) // 4


class DocumentChunker:
    """Split document text into chunks using type-appropriate strategies.

    Parameters
    ----------
    target_tokens:
        Target chunk size in estimated tokens for generic splitting.
    overlap_tokens:
        Overlap between consecutive generic chunks.
    min_chunk_chars:
        Minimum chunk size.  Smaller chunks are merged with neighbours.
    max_chunk_chars:
        Maximum chunk size.  Larger chunks are split by paragraphs.
    filter_toc:
        If True (default), filter out TOC pages before chunking.
    """

    # Component-level splitting for data sheets
    _COMPONENT_PATTERN = re.compile(
        r"^(\d+[-.]?\s*(?:[A-Z][A-Za-z\s/&]+))\s*$",
        re.MULTILINE,
    )

    # Section-level splitting for specs — only top-level sections (1, 2, 3.1, 4.2)
    # Strict: requires uppercase start, avoids matching TOC lines
    _SECTION_PATTERN = re.compile(
        r"^(\d+(?:\.\d+)?)\s+([A-Z][A-Za-z\s,/&()-]+)$",
        re.MULTILINE,
    )

    # Appendix detection
    _APPENDIX_PATTERN = re.compile(
        r"^(?:APPENDIX|ANNEX|ANEXO|ATTACHMENT)\s+",
        re.IGNORECASE,
    )

    def __init__(
        self,
        target_tokens: int = 1000,
        overlap_tokens: int = 100,
        min_chunk_chars: int = MIN_CHUNK_CHARS,
        max_chunk_chars: int = MAX_CHUNK_CHARS,
        filter_toc: bool = True,
    ):
        self.target_chars = target_tokens * 4  # ~4 chars per token
        self.overlap_chars = overlap_tokens * 4
        self.min_chunk_chars = min_chunk_chars
        self.max_chunk_chars = max_chunk_chars
        self.filter_toc = filter_toc
        self._cleaner = TextCleaner()

    def chunk(
        self,
        text: str,
        document_type: DocumentType = DocumentType.UNKNOWN,
        page_mapping: dict[int, int] | None = None,
    ) -> list[Chunk]:
        """Chunk text using the appropriate strategy for the document type.

        Parameters
        ----------
        text:
            Cleaned document text.
        document_type:
            Type of document — determines chunking strategy.
        page_mapping:
            Optional mapping from character offset → page number.

        Returns
        -------
        list[Chunk]
            Ordered list of text chunks.
        """
        if not text.strip():
            return []

        if document_type == DocumentType.DATA_SHEET:
            chunks = self.chunk_data_sheet(text, page_mapping)
        elif document_type in (DocumentType.TECHNICAL_SPEC, DocumentType.MATERIAL_REQUISITION):
            chunks = self.chunk_by_section(text, page_mapping)
        else:
            chunks = self.chunk_generic(text, page_mapping)

        # Post-process: merge tiny, split huge, mark appendices
        chunks = self._post_process(chunks)
        return chunks

    def chunk_data_sheet(
        self,
        text: str,
        page_mapping: dict[int, int] | None = None,
    ) -> list[Chunk]:
        """Split a data sheet by component boundaries.

        Components in DETEGASA data sheets typically start with:
        "1 PROGRESSIVE CAVITY PUMP" or "2- OILY WATER SEPARATOR"
        """
        splits = list(self._COMPONENT_PATTERN.finditer(text))
        if len(splits) < 2:
            # Not enough component headers — fall back to generic
            return self.chunk_generic(text, page_mapping)

        chunks: list[Chunk] = []
        for i, match in enumerate(splits):
            start = match.start()
            end = splits[i + 1].start() if i + 1 < len(splits) else len(text)
            chunk_text = text[start:end].strip()

            if not chunk_text:
                continue

            page_start = self._offset_to_page(start, page_mapping)
            page_end = self._offset_to_page(end - 1, page_mapping)

            chunks.append(
                Chunk(
                    index=len(chunks),
                    text=chunk_text,
                    page_start=page_start,
                    page_end=page_end,
                    section_title=match.group(1).strip(),
                    chunk_type="component",
                )
            )

        return chunks

    def chunk_by_section(
        self,
        text: str,
        page_mapping: dict[int, int] | None = None,
    ) -> list[Chunk]:
        """Split technical specs by numbered sections (e.g., 5.2 Title).

        Only splits on top-level sections (1-2 levels deep) to avoid
        creating too many tiny chunks from sub-sub-sections.
        """
        splits = list(self._SECTION_PATTERN.finditer(text))
        if len(splits) < 2:
            return self.chunk_generic(text, page_mapping)

        chunks: list[Chunk] = []
        for i, match in enumerate(splits):
            start = match.start()
            end = splits[i + 1].start() if i + 1 < len(splits) else len(text)
            chunk_text = text[start:end].strip()

            if not chunk_text:
                continue

            section_num = match.group(1)
            section_title = f"{section_num} {match.group(2).strip()}"
            page_start = self._offset_to_page(start, page_mapping)
            page_end = self._offset_to_page(end - 1, page_mapping)

            # Detect appendix sections
            is_appendix = bool(self._APPENDIX_PATTERN.match(match.group(2).strip()))
            meta: dict[str, Any] = {}
            if is_appendix:
                meta["is_appendix"] = True

            chunks.append(
                Chunk(
                    index=len(chunks),
                    text=chunk_text,
                    page_start=page_start,
                    page_end=page_end,
                    section_title=section_title,
                    chunk_type="section",
                    metadata=meta,
                )
            )

        return chunks

    def chunk_generic(
        self,
        text: str,
        page_mapping: dict[int, int] | None = None,
    ) -> list[Chunk]:
        """Split text by character count with overlap.

        Uses paragraph boundaries when possible, falling back to
        sentence boundaries, then hard character limit.
        """
        if not text.strip():
            return []
        return self._split_by_size(text, page_mapping=page_mapping)

    # ── Post-processing ───────────────────────────────────────────────────

    def _post_process(self, chunks: list[Chunk]) -> list[Chunk]:
        """Merge tiny chunks, split huge chunks, and re-index.

        1. Merge chunks smaller than ``min_chunk_chars`` with the
           previous chunk (or next if it's the first).
        2. Split chunks larger than ``max_chunk_chars`` by paragraphs.
        3. Mark appendix chunks based on section titles.
        4. Re-index all chunks sequentially.
        """
        if not chunks:
            return chunks

        # Step 1: Merge tiny chunks
        merged: list[Chunk] = []
        for chunk in chunks:
            if (
                merged
                and chunk.char_count < self.min_chunk_chars
                and chunk.chunk_type == merged[-1].chunk_type
            ):
                # Merge with previous
                prev = merged[-1]
                merged[-1] = Chunk(
                    index=prev.index,
                    text=prev.text + "\n\n" + chunk.text,
                    page_start=prev.page_start,
                    page_end=chunk.page_end or prev.page_end,
                    section_title=prev.section_title,
                    chunk_type=prev.chunk_type,
                    metadata={**prev.metadata, **chunk.metadata},
                )
            elif (
                not merged
                and chunk.char_count < self.min_chunk_chars
            ):
                # First chunk is tiny — just add it and it'll be merged later if possible
                merged.append(chunk)
            else:
                merged.append(chunk)

        # Step 2: Split huge chunks
        final: list[Chunk] = []
        for chunk in merged:
            if chunk.char_count > self.max_chunk_chars:
                sub_chunks = self._split_by_size(
                    chunk.text,
                    section_title=chunk.section_title,
                    chunk_type=chunk.chunk_type,
                    page_mapping=None,
                )
                for sc in sub_chunks:
                    sc.page_start = chunk.page_start
                    sc.page_end = chunk.page_end
                    sc.metadata = dict(chunk.metadata)
                    final.append(sc)
            else:
                final.append(chunk)

        # Step 3: Mark appendix chunks by section title
        in_appendix = False
        for chunk in final:
            if chunk.section_title:
                if self._APPENDIX_PATTERN.match(chunk.section_title):
                    in_appendix = True
                elif re.match(r"^\d", chunk.section_title) and in_appendix:
                    # Still in appendix until we hit a new non-appendix top section
                    pass
            if in_appendix:
                chunk.metadata["is_appendix"] = True

        # Step 4: Re-index
        for i, chunk in enumerate(final):
            chunk.index = i

        return final

    # ── Private helpers ──────────────────────────────────────────────────────

    def _split_by_size(
        self,
        text: str,
        section_title: str = "",
        chunk_type: str = "text",
        page_mapping: dict[int, int] | None = None,
    ) -> list[Chunk]:
        """Split text into roughly equal chunks by character count."""
        if len(text) <= self.target_chars:
            return [
                Chunk(
                    index=0,
                    text=text,
                    section_title=section_title,
                    chunk_type=chunk_type,
                    page_start=self._offset_to_page(0, page_mapping),
                    page_end=self._offset_to_page(len(text) - 1, page_mapping),
                )
            ]

        # Split on paragraph boundaries (double newline)
        paragraphs = re.split(r"\n\n+", text)
        chunks: list[Chunk] = []
        current_text = ""
        current_start = 0

        for para in paragraphs:
            if len(current_text) + len(para) + 2 > self.target_chars and current_text:
                chunks.append(
                    Chunk(
                        index=len(chunks),
                        text=current_text.strip(),
                        section_title=section_title,
                        chunk_type=chunk_type,
                        page_start=self._offset_to_page(current_start, page_mapping),
                        page_end=self._offset_to_page(
                            current_start + len(current_text) - 1, page_mapping
                        ),
                    )
                )
                # Overlap: keep the last portion
                overlap_text = current_text[-self.overlap_chars:] if self.overlap_chars else ""
                current_start += len(current_text) - len(overlap_text)
                current_text = overlap_text

            current_text += ("\n\n" if current_text else "") + para

        # Last chunk
        if current_text.strip():
            chunks.append(
                Chunk(
                    index=len(chunks),
                    text=current_text.strip(),
                    section_title=section_title,
                    chunk_type=chunk_type,
                    page_start=self._offset_to_page(current_start, page_mapping),
                    page_end=self._offset_to_page(
                        current_start + len(current_text) - 1, page_mapping
                    ),
                )
            )

        return chunks

    @staticmethod
    def _offset_to_page(offset: int, page_mapping: dict[int, int] | None) -> int | None:
        """Convert a character offset to a page number using the mapping."""
        if not page_mapping:
            return None
        # Find the largest offset key that is <= our offset
        best_page = None
        for char_offset, page_num in sorted(page_mapping.items()):
            if char_offset <= offset:
                best_page = page_num
            else:
                break
        return best_page
