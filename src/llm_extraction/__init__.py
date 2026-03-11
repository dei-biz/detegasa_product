"""LLM-powered structured extraction from document chunks.

Converts raw text (from PDFs/Excel) into validated Pydantic schemas
(ProductSpec, TenderSpec) using Claude/OpenAI via Instructor.
"""

from src.llm_extraction.product_extractor import ProductExtractor
from src.llm_extraction.tender_extractor import TenderExtractor

__all__ = [
    "ProductExtractor",
    "TenderExtractor",
]
