"""PDF text extraction using PyMuPDF (fitz).

Produces a structured PDFDocument with per-page text, metadata, and
basic detection of image-only pages (drawings, scanned content).
"""

from __future__ import annotations

import logging
from pathlib import Path

import fitz  # PyMuPDF
from pydantic import BaseModel, Field

from src.extraction.document_type import DocumentType, detect_document_type

logger = logging.getLogger(__name__)

# Pages with fewer characters than this are considered image-only.
_MIN_TEXT_CHARS = 30


class PDFPage(BaseModel):
    """Extracted content from a single PDF page."""

    page_number: int
    text: str
    has_images: bool = False
    image_only: bool = False
    char_count: int = 0


class PDFDocument(BaseModel):
    """Full extraction result for one PDF file."""

    filename: str
    total_pages: int
    document_type: DocumentType = DocumentType.UNKNOWN
    pages: list[PDFPage] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)

    @property
    def full_text(self) -> str:
        """Concatenate all page texts separated by page breaks."""
        return "\n\n".join(p.text for p in self.pages if p.text.strip())

    @property
    def text_pages(self) -> list[PDFPage]:
        """Return only pages that contain meaningful text."""
        return [p for p in self.pages if not p.image_only]

    @property
    def image_only_pages(self) -> list[PDFPage]:
        """Return pages that are image-only (drawings, scans)."""
        return [p for p in self.pages if p.image_only]


class PDFParser:
    """Extract text from PDF files using PyMuPDF."""

    def parse(self, file_path: str | Path) -> PDFDocument:
        """Parse a PDF file and return structured content.

        Parameters
        ----------
        file_path:
            Path to the PDF file.

        Returns
        -------
        PDFDocument
            Structured extraction with per-page text and metadata.

        Raises
        ------
        FileNotFoundError
            If the file does not exist.
        ValueError
            If the file is not a PDF or cannot be opened.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {path}")
        if path.suffix.lower() != ".pdf":
            raise ValueError(f"Not a PDF file: {path}")

        doc_type = detect_document_type(path)
        pages: list[PDFPage] = []

        try:
            with fitz.open(str(path)) as doc:
                metadata = dict(doc.metadata) if doc.metadata else {}
                total_pages = len(doc)

                for page_num in range(total_pages):
                    page = doc[page_num]
                    text = page.get_text("text")
                    has_images = len(page.get_images()) > 0
                    char_count = len(text.strip())
                    image_only = char_count < _MIN_TEXT_CHARS and has_images

                    pages.append(
                        PDFPage(
                            page_number=page_num + 1,  # 1-indexed
                            text=text,
                            has_images=has_images,
                            image_only=image_only,
                            char_count=char_count,
                        )
                    )

                logger.info(
                    "Parsed %s: %d pages (%d text, %d image-only)",
                    path.name,
                    total_pages,
                    len([p for p in pages if not p.image_only]),
                    len([p for p in pages if p.image_only]),
                )

        except Exception as exc:
            raise ValueError(f"Failed to parse PDF {path.name}: {exc}") from exc

        return PDFDocument(
            filename=path.name,
            total_pages=total_pages,
            document_type=doc_type,
            pages=pages,
            metadata=metadata,
        )
