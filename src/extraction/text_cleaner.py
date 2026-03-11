"""Text cleaning pipeline for Petrobras / DETEGASA PDF extractions.

Removes boilerplate headers, footers, page numbers, and proprietary notices
that appear repeatedly across pages in Petrobras engineering documents.

Also provides TOC (Table of Contents) detection to help downstream chunking
filter out non-content pages.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class PageMetadata:
    """Metadata extracted from a page header/footer before cleaning."""

    sheet_number: int | None = None
    total_sheets: int | None = None
    revision: str = ""
    document_code: str = ""


@dataclass
class CleanResult:
    """Result of text cleaning with optional extracted metadata."""

    text: str
    metadata: PageMetadata = field(default_factory=PageMetadata)
    lines_removed: int = 0
    is_toc: bool = False


class TextCleaner:
    """Clean extracted PDF text from Petrobras/DETEGASA documents.

    Removes:
    - Proprietary information notices
    - Repeated page headers with document codes
    - Page numbering (SHEET X of Y)
    - Petrobras standard footers (N-xxxx references)
    - Material Requisition (I-RM) header blocks
    - Data Sheet (I-FD) header blocks
    - Revision footer lines
    - Excessive whitespace

    Detects:
    - Table of Contents (TOC) pages
    """

    # Patterns to remove entirely (compiled once)
    _REMOVE_PATTERNS: list[re.Pattern[str]] = [
        # Petrobras proprietary notice (various forms)
        re.compile(
            r"INFORMATION\s+IN\s+THIS\s+DOCUMENT\s+IS\s+PROPERTY\s+OF\s+PETROBRAS.*",
            re.IGNORECASE,
        ),
        re.compile(
            r"THIS\s+DOCUMENT\s+(?:IS|SHALL\s+BE)\s+(?:THE\s+)?PROPERTY\s+OF\s+PETROBRAS.*",
            re.IGNORECASE,
        ),
        # Petrobras standard references in footers
        re.compile(r"N-\d{3,4}\s+REV\.?\s*[A-Z]", re.IGNORECASE),
        # Title block repeated lines (REV / DESCRIPTION / DATE patterns)
        re.compile(r"^REV\.?\s+DESCRIPTION\s+DATE\s+", re.IGNORECASE | re.MULTILINE),
        # Approval stamp lines
        re.compile(r"^(?:PREPARED|CHECKED|APPROVED)\s+BY\s*:?\s*$", re.IGNORECASE | re.MULTILINE),
        # Material Requisition header blocks
        re.compile(r"^.*MATERIAL\s+REQUISITION.*$", re.IGNORECASE | re.MULTILINE),
        # Continuation lines (CONT. X OF Y)
        re.compile(r"^.*CONT\.?\s*\d+\s*(?:OF|/)\s*\d+.*$", re.IGNORECASE | re.MULTILINE),
        # Data Sheet header blocks
        re.compile(r"^.*(?:DATA\s+SHEET|FOLHA\s+DE\s+DADOS).*$", re.IGNORECASE | re.MULTILINE),
        # Revision footer lines (standalone REV. X or REV X at start of line)
        re.compile(r"^REV\.?\s+\d+\s*$", re.IGNORECASE | re.MULTILINE),
    ]

    # TOC line detection patterns
    # Pattern 1: "4.2.1  Title text ......... 23"  (dots + page number)
    _TOC_DOTS_PATTERN = re.compile(
        r"^\d+(?:\.\d+)*\s+.{5,80}\s*\.{3,}\s*\d+\s*$"
    )
    # Pattern 2: "4.2.1  Title text          23"  (spaces + page number at end)
    _TOC_SPACES_PATTERN = re.compile(
        r"^\d+(?:\.\d+)*\s+.{5,80}\s{3,}\d+\s*$"
    )
    # Pattern 3: Standalone "TABLE OF CONTENTS" or "INDEX"
    _TOC_HEADER_PATTERN = re.compile(
        r"^\s*(?:TABLE\s+OF\s+CONTENTS|INDEX|CONTENTS|ÍNDICE)\s*$",
        re.IGNORECASE,
    )

    # Threshold: if more than this fraction of non-empty lines are TOC, it's a TOC page
    _TOC_PAGE_THRESHOLD = 0.50

    # Page metadata extraction
    _SHEET_PATTERN = re.compile(r"SHEET\s+(\d+)\s+(?:OF|/)\s+(\d+)", re.IGNORECASE)
    _DOC_CODE_PATTERN = re.compile(r"(I-[A-Z]{2}-[\d.]+[-\w]*)", re.IGNORECASE)
    _REVISION_PATTERN = re.compile(r"REV\.?\s*([A-Z0-9]+)", re.IGNORECASE)

    def clean(self, text: str) -> CleanResult:
        """Apply full cleaning pipeline to extracted text.

        Parameters
        ----------
        text:
            Raw text extracted from a PDF page or document.

        Returns
        -------
        CleanResult
            Cleaned text with metadata and removal stats.
        """
        if not text or not text.strip():
            return CleanResult(text="")

        # Extract metadata before cleaning
        metadata = self.extract_page_metadata(text)

        # Detect TOC before cleaning (patterns rely on original formatting)
        is_toc = self.is_toc_page(text)

        # Apply removal patterns
        cleaned = text
        lines_removed = 0
        for pattern in self._REMOVE_PATTERNS:
            matches = pattern.findall(cleaned)
            lines_removed += len(matches)
            cleaned = pattern.sub("", cleaned)

        # Remove page number lines
        cleaned, page_removals = self._remove_page_numbers(cleaned)
        lines_removed += page_removals

        # Remove TOC lines from content pages (keeps real content)
        cleaned = self.remove_toc_lines(cleaned)

        # Normalize whitespace
        cleaned = self.normalize_whitespace(cleaned)

        return CleanResult(
            text=cleaned,
            metadata=metadata,
            lines_removed=lines_removed,
            is_toc=is_toc,
        )

    def clean_pages(self, pages_text: list[str]) -> list[CleanResult]:
        """Clean a list of page texts.

        Parameters
        ----------
        pages_text:
            List of raw text strings, one per page.

        Returns
        -------
        list[CleanResult]
            Cleaned results in the same order.
        """
        return [self.clean(page) for page in pages_text]

    def extract_page_metadata(self, text: str) -> PageMetadata:
        """Extract structured metadata from page header/footer text.

        Parameters
        ----------
        text:
            Raw text that may contain sheet numbers, revision codes, etc.

        Returns
        -------
        PageMetadata
            Extracted metadata fields.
        """
        meta = PageMetadata()

        sheet_match = self._SHEET_PATTERN.search(text)
        if sheet_match:
            meta.sheet_number = int(sheet_match.group(1))
            meta.total_sheets = int(sheet_match.group(2))

        doc_match = self._DOC_CODE_PATTERN.search(text)
        if doc_match:
            meta.document_code = doc_match.group(1)

        rev_match = self._REVISION_PATTERN.search(text)
        if rev_match:
            meta.revision = rev_match.group(1)

        return meta

    # ── TOC detection ─────────────────────────────────────────────────────

    def is_toc_line(self, line: str) -> bool:
        """Check if a single line looks like a TOC entry.

        Parameters
        ----------
        line:
            A single line of text.

        Returns
        -------
        bool
            True if the line matches a TOC pattern.
        """
        stripped = line.strip()
        if not stripped:
            return False
        if self._TOC_DOTS_PATTERN.match(stripped):
            return True
        if self._TOC_SPACES_PATTERN.match(stripped):
            return True
        if self._TOC_HEADER_PATTERN.match(stripped):
            return True
        return False

    def is_toc_page(self, text: str) -> bool:
        """Check if a page is primarily a Table of Contents.

        A page is considered TOC if more than 50% of its non-empty lines
        match TOC patterns.

        Parameters
        ----------
        text:
            Raw text from a single page.

        Returns
        -------
        bool
            True if the page is primarily TOC.
        """
        lines = text.strip().split("\n")
        non_empty = [ln for ln in lines if ln.strip()]
        if len(non_empty) < 3:
            return False

        toc_count = sum(1 for ln in non_empty if self.is_toc_line(ln))
        return (toc_count / len(non_empty)) >= self._TOC_PAGE_THRESHOLD

    def remove_toc_lines(self, text: str) -> str:
        """Remove individual TOC-like lines from text.

        This is applied to non-TOC pages where a few TOC-like lines
        may appear (e.g., at the start of a section page).

        Parameters
        ----------
        text:
            Text that may contain some TOC lines.

        Returns
        -------
        str
            Text with TOC lines removed.
        """
        lines = text.split("\n")
        cleaned = [ln for ln in lines if not self.is_toc_line(ln)]
        return "\n".join(cleaned)

    # ── Whitespace ────────────────────────────────────────────────────────

    @staticmethod
    def normalize_whitespace(text: str) -> str:
        """Normalize whitespace while preserving paragraph structure.

        - Collapses multiple spaces into one
        - Collapses 3+ newlines into 2 (paragraph break)
        - Strips trailing whitespace per line
        """
        # Collapse multiple spaces (not newlines) into one
        text = re.sub(r"[^\S\n]+", " ", text)
        # Strip trailing whitespace per line
        text = re.sub(r" +\n", "\n", text)
        # Collapse 3+ consecutive newlines into 2
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def _remove_page_numbers(text: str) -> tuple[str, int]:
        """Remove standalone page number lines.

        Matches lines that are just a number, or 'Page X', 'Sheet X of Y'.
        """
        count = 0
        lines = text.split("\n")
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            # Pure number line
            if re.match(r"^\d{1,3}$", stripped):
                count += 1
                continue
            # "Page X" or "Sheet X of Y" standalone
            if re.match(r"^(?:Page|Sheet|Pg\.?)\s+\d+(?:\s+(?:of|/)\s+\d+)?$", stripped, re.IGNORECASE):
                count += 1
                continue
            cleaned_lines.append(line)
        return "\n".join(cleaned_lines), count
