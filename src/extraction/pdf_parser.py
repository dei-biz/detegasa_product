"""PDF text extraction using PyMuPDF (fitz).

Produces a structured PDFDocument with per-page text, tables, metadata,
and basic detection of image-only pages (drawings, scanned content).

Supports:
- Text extraction via ``page.get_text("text")``
- Table extraction via ``page.find_tables()``
- Optional OCR for image-only pages via ``page.get_textpage_ocr()``
  (requires Tesseract OCR binary installed on the system)
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
from pydantic import BaseModel, Field

from src.extraction.document_type import DocumentType, detect_document_type

logger = logging.getLogger(__name__)

# Pages with fewer characters than this are considered image-only.
_MIN_TEXT_CHARS = 30

# Pages with fewer meaningful characters than this are candidates for OCR.
# Higher than _MIN_TEXT_CHARS because scanned pages often have header/footer
# text (e.g., 139 chars of "DATA SHEETS\nNo.\nI-FD-...") while the real
# content is in images.
_OCR_TEXT_THRESHOLD = 200

# Default tessdata path on Windows (UB-Mannheim installer)
_DEFAULT_TESSDATA_WIN = r"C:\Program Files\Tesseract-OCR\tessdata"


def _find_tessdata() -> str | None:
    """Find the Tesseract tessdata directory."""
    # Check TESSDATA_PREFIX env var first
    env_path = os.environ.get("TESSDATA_PREFIX")
    if env_path and Path(env_path).exists():
        return env_path

    # Windows default
    if Path(_DEFAULT_TESSDATA_WIN).exists():
        return _DEFAULT_TESSDATA_WIN

    # Check if tesseract is on PATH and infer tessdata
    tesseract_bin = shutil.which("tesseract")
    if tesseract_bin:
        tessdata = Path(tesseract_bin).parent / "tessdata"
        if tessdata.exists():
            return str(tessdata)

    return None


def is_tesseract_available() -> bool:
    """Check whether Tesseract OCR is available on this system."""
    return _find_tessdata() is not None


class PDFPage(BaseModel):
    """Extracted content from a single PDF page."""

    page_number: int
    text: str
    has_images: bool = False
    image_only: bool = False
    char_count: int = 0
    tables: list[list[list[Any]]] = Field(
        default_factory=list,
        description="Tables extracted via find_tables(). Each table is a list of rows, each row a list of cell values.",
    )
    ocr_applied: bool = Field(
        default=False,
        description="Whether OCR was used to extract text from this page.",
    )

    @property
    def has_tables(self) -> bool:
        """Whether any tables were extracted from this page."""
        return len(self.tables) > 0

    def tables_as_text(self) -> str:
        """Format extracted tables as readable key-value text for LLM consumption.

        For 2-column tables, formats as ``key: value`` pairs.
        For wider tables, formats as tab-separated rows.
        """
        if not self.tables:
            return ""

        parts: list[str] = []
        for table in self.tables:
            rows = [row for row in table if any(cell for cell in row)]
            if not rows:
                continue

            # 2-column table → key: value
            if all(len(row) == 2 for row in rows):
                for row in rows:
                    key = str(row[0] or "").strip()
                    val = str(row[1] or "").strip()
                    if key and val:
                        parts.append(f"{key}: {val}")
            else:
                # Multi-column → tab-separated
                for row in rows:
                    cells = [str(c or "").strip() for c in row]
                    parts.append("\t".join(cells))
            parts.append("")  # blank line between tables

        return "\n".join(parts).strip()


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

    @property
    def ocr_pages(self) -> list[PDFPage]:
        """Return pages where OCR was applied."""
        return [p for p in self.pages if p.ocr_applied]

    @property
    def pages_with_tables(self) -> list[PDFPage]:
        """Return pages that contain extracted tables."""
        return [p for p in self.pages if p.has_tables]

    def full_text_with_tables(self) -> str:
        """Concatenate page text + table data for richer LLM input."""
        parts: list[str] = []
        for page in self.pages:
            page_text = page.text.strip()
            table_text = page.tables_as_text()
            combined = page_text
            if table_text:
                combined += "\n\n[TABLE DATA]\n" + table_text
            if combined.strip():
                parts.append(combined)
        return "\n\n".join(parts)


class PDFParser:
    """Extract text, tables, and optionally OCR from PDF files using PyMuPDF."""

    def parse(
        self,
        file_path: str | Path,
        *,
        ocr: bool = False,
        extract_tables: bool = True,
    ) -> PDFDocument:
        """Parse a PDF file and return structured content.

        Parameters
        ----------
        file_path:
            Path to the PDF file.
        ocr:
            If True, apply OCR to image-only pages using Tesseract.
            Requires Tesseract to be installed. Falls back gracefully
            if not available.
        extract_tables:
            If True (default), use ``find_tables()`` to extract
            structured table data from each page.

        Returns
        -------
        PDFDocument
            Structured extraction with per-page text, tables, and metadata.

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

        # Resolve tessdata for OCR
        tessdata = _find_tessdata() if ocr else None
        if ocr and tessdata is None:
            logger.warning(
                "OCR requested but Tesseract not found. "
                "Install Tesseract-OCR or set TESSDATA_PREFIX. "
                "Proceeding without OCR."
            )

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
                    ocr_applied = False

                    # ── Table extraction ──
                    tables: list[list[list[Any]]] = []
                    if extract_tables:
                        try:
                            tab_finder = page.find_tables()
                            for table in tab_finder.tables:
                                extracted = table.extract()
                                if extracted:
                                    tables.append(extracted)
                        except Exception as exc:
                            logger.debug(
                                "Table extraction failed on page %d: %s",
                                page_num + 1, exc,
                            )

                    # ── OCR for image-heavy pages ──
                    # Use _OCR_TEXT_THRESHOLD (not _MIN_TEXT_CHARS) because
                    # scanned pages often have header/footer text above 30 chars
                    if ocr and char_count < _OCR_TEXT_THRESHOLD and has_images and tessdata:
                        try:
                            tp = page.get_textpage_ocr(
                                language="eng",
                                tessdata=tessdata,
                            )
                            ocr_text = page.get_text("text", textpage=tp)
                            if len(ocr_text.strip()) > len(text.strip()):
                                text = ocr_text
                                char_count = len(text.strip())
                                # Re-evaluate: may no longer be image-only
                                image_only = char_count < _MIN_TEXT_CHARS
                                ocr_applied = True
                        except Exception as exc:
                            logger.debug(
                                "OCR failed on page %d: %s",
                                page_num + 1, exc,
                            )

                    pages.append(
                        PDFPage(
                            page_number=page_num + 1,
                            text=text,
                            has_images=has_images,
                            image_only=image_only,
                            char_count=char_count,
                            tables=tables,
                            ocr_applied=ocr_applied,
                        )
                    )

                text_count = len([p for p in pages if not p.image_only])
                img_count = len([p for p in pages if p.image_only])
                ocr_count = len([p for p in pages if p.ocr_applied])
                table_count = len([p for p in pages if p.has_tables])

                logger.info(
                    "Parsed %s: %d pages (%d text, %d image-only, %d OCR, %d with tables)",
                    path.name, total_pages, text_count, img_count, ocr_count, table_count,
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
