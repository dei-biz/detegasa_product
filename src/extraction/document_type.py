"""Document type detection based on Petrobras / DETEGASA filename conventions.

Petrobras document codes follow the pattern:
    I-{TYPE}-{project}.{discipline}-{system}-{sequential}-{origin}-{rev}

Common prefixes:
    I-FD  → Data Sheet (Folha de Dados)
    I-RM  → Material Requisition (Requisicao de Material)
    I-ET  → Technical Specification (Especificacao Tecnica)
    I-DE  → Drawing (Desenho)
    I-LI  → Data List (Lista)
    I-RL  → Report/Analysis (Relatorio)
    MA-   → Manual
"""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path


class DocumentType(str, Enum):
    """Types of documents in a Petrobras/DETEGASA tender package."""

    DATA_SHEET = "data_sheet"                   # I-FD-*
    MATERIAL_REQUISITION = "material_requisition"  # I-RM-*
    TECHNICAL_SPEC = "technical_spec"            # I-ET-*
    DRAWING = "drawing"                          # I-DE-*
    DATA_LIST = "data_list"                      # I-LI-*
    REPORT = "report"                            # I-RL-*
    MANUAL = "manual"                            # MA-*
    EVALUATION_TABLE = "evaluation_table"        # TBT / Technical Bid Evaluation
    COMPLIANCE_CHECK = "compliance_check"        # E&I Compliance Check Sheet
    VENDOR_DATA_LIST = "vendor_data_list"        # VDRL / Vendor Data Requirement List
    TECHNICAL_CLARIFICATION = "technical_clarification"  # TC / Technical Clarification
    TEMPLATE = "template"                        # Attachment / Form templates
    UNKNOWN = "unknown"


# Ordered list: first match wins.
_PATTERNS: list[tuple[re.Pattern[str], DocumentType]] = [
    (re.compile(r"I-FD-", re.IGNORECASE), DocumentType.DATA_SHEET),
    (re.compile(r"I-RM-", re.IGNORECASE), DocumentType.MATERIAL_REQUISITION),
    (re.compile(r"I-ET-", re.IGNORECASE), DocumentType.TECHNICAL_SPEC),
    (re.compile(r"I-DE-", re.IGNORECASE), DocumentType.DRAWING),
    (re.compile(r"I-LI-", re.IGNORECASE), DocumentType.DATA_LIST),
    (re.compile(r"I-RL-", re.IGNORECASE), DocumentType.REPORT),
    (re.compile(r"^MA-", re.IGNORECASE), DocumentType.MANUAL),
    (re.compile(r"TBT|Technical\s*Bid\s*Evaluation", re.IGNORECASE), DocumentType.EVALUATION_TABLE),
    (re.compile(r"compliance\s*check|E&I\s*technical\s*compliance", re.IGNORECASE), DocumentType.COMPLIANCE_CHECK),
    (re.compile(r"VDRL|Vendor\s*Data\s*Requirement", re.IGNORECASE), DocumentType.VENDOR_DATA_LIST),
    (re.compile(r"Technical\s*Clarification|\bTC\b.*Detegasa", re.IGNORECASE), DocumentType.TECHNICAL_CLARIFICATION),
    (re.compile(r"ATTACH(?:MENT|MEHT)|Form-\d|Template", re.IGNORECASE), DocumentType.TEMPLATE),
]


def detect_document_type(filename: str | Path) -> DocumentType:
    """Detect the document type from a filename or path.

    Parameters
    ----------
    filename:
        Full path or just the filename.  Only the stem + suffix are inspected.

    Returns
    -------
    DocumentType
        Best-guess type based on filename patterns.
    """
    name = Path(filename).name
    for pattern, doc_type in _PATTERNS:
        if pattern.search(name):
            return doc_type
    return DocumentType.UNKNOWN
