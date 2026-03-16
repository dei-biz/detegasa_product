"""Base matcher interface for deterministic compliance evaluation."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from src.extraction.xlsx_parser import TBTItem
from src.schemas.common import ComplianceStatus


class MatchResult(BaseModel):
    """Result of a single deterministic match evaluation."""

    status: ComplianceStatus
    product_value: str | None = Field(
        default=None,
        description="What the product offers for this requirement",
    )
    tender_value: str = Field(
        ...,
        description="What the tender requires",
    )
    gap_description: str | None = Field(
        default=None,
        description="Description of the gap if non-compliant",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence in this evaluation (1.0 = certain)",
    )


class BaseMatcher(ABC):
    """Abstract base class for deterministic compliance matchers.

    Each matcher handles a specific category of requirements (process,
    material, certification, etc.) and can evaluate them without LLM calls.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Matcher name for logging and reporting."""
        ...

    @abstractmethod
    def can_handle(self, tbt_item: TBTItem) -> bool:
        """Check if this matcher can evaluate the given TBT item.

        Should be fast — only look at keywords in description/spec_requirement.
        """
        ...

    @abstractmethod
    def evaluate(self, tbt_item: TBTItem, product_data: dict) -> MatchResult:
        """Evaluate a TBT requirement against the product data.

        Parameters
        ----------
        tbt_item:
            The TBT row to evaluate.
        product_data:
            Full product JSON (from E2E extraction).

        Returns
        -------
        MatchResult
            The evaluation result.
        """
        ...
