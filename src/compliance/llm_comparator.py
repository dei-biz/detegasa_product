"""LLM-based compliance comparator for requirements that cannot be evaluated
deterministically.

Processes TBT items in batches, sending the product JSON as context and
asking the LLM to evaluate each requirement. Uses Instructor for structured output.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from src.compliance.matchers.base import MatchResult
from src.extraction.xlsx_parser import TBTItem
from src.llm.adapter import LLMAdapter
from src.llm.types import LLMResponse
from src.schemas.common import ComplianceStatus

logger = logging.getLogger(__name__)


# ── Batch size ───────────────────────────────────────────────────────────────
# Process this many TBT items per LLM call to balance cost vs quality.
BATCH_SIZE = 10


# ── Instructor response models ──────────────────────────────────────────────


class LLMComplianceItem(BaseModel):
    """LLM evaluation of a single TBT requirement."""

    requirement_index: int = Field(..., description="Zero-based index in the batch")
    status: str = Field(
        ...,
        description=(
            "Compliance status: 'compliant', 'non_compliant', 'partial', "
            "'clarification_needed', 'not_applicable'"
        ),
    )
    product_value: str = Field(
        default="",
        description="What the product offers for this requirement (brief)",
    )
    gap_description: str = Field(
        default="",
        description="If non-compliant or partial, what is missing or insufficient",
    )
    bidder_response: str = Field(
        default="",
        description="Suggested response text for the TBT bidder column (1-2 sentences)",
    )


class LLMComplianceBatch(BaseModel):
    """Batch of LLM compliance evaluations."""

    evaluations: list[LLMComplianceItem] = Field(
        default_factory=list,
        description="One evaluation per requirement in the batch",
    )


# ── System prompt ────────────────────────────────────────────────────────────

COMPLIANCE_SYSTEM_PROMPT = """\
You are a maritime equipment compliance engineer evaluating whether a \
DETEGASA Oily Water Separator (OWS) package meets tender requirements.

You will receive:
1. A product specification (JSON) with components, performance, certifications
2. A batch of tender requirements from a Technical Bid Evaluation Table (TBT)

For EACH requirement, evaluate compliance and provide:
- status: compliant / non_compliant / partial / clarification_needed / not_applicable
- product_value: what the product offers (be specific with values/specs)
- gap_description: if not compliant, explain what is missing
- bidder_response: suggested response text for the TBT (1-2 sentences, professional)

Guidelines:
- Be conservative: if unsure, use 'clarification_needed' rather than 'compliant'
- 'not_applicable' for requirements about delivery, commercial terms, or documentation
- For material requirements, check if product materials meet or exceed the requirement
- For certification requirements, check if product has the certificate or equivalent
- For performance requirements, compare numeric values with correct units
- Consider that the product JSON may be incomplete — missing data is 'clarification_needed'
"""

COMPLIANCE_USER_PROMPT = """\
## Product Specification

```json
{product_json}
```

## Requirements to Evaluate

{requirements_text}

Evaluate each requirement against the product specification above.
"""


# ── Status mapping ───────────────────────────────────────────────────────────

_STATUS_MAP: dict[str, ComplianceStatus] = {
    "compliant": ComplianceStatus.COMPLIANT,
    "non_compliant": ComplianceStatus.NON_COMPLIANT,
    "partial": ComplianceStatus.PARTIAL,
    "clarification_needed": ComplianceStatus.CLARIFICATION_NEEDED,
    "not_applicable": ComplianceStatus.NOT_APPLICABLE,
    "deviation_acceptable": ComplianceStatus.DEVIATION_ACCEPTABLE,
}


class LLMComparator:
    """Evaluate TBT requirements using LLM when deterministic matchers cannot."""

    def __init__(self, llm: LLMAdapter):
        self.llm = llm
        self.total_cost_usd: float = 0.0
        self.call_count: int = 0

    def _track_cost(self, response: LLMResponse) -> None:
        self.total_cost_usd += response.cost_usd
        self.call_count += 1

    async def batch_evaluate(
        self,
        items: list[TBTItem],
        product_json: str,
    ) -> list[MatchResult]:
        """Evaluate a list of TBT items using LLM in batches.

        Parameters
        ----------
        items:
            TBT items that could not be evaluated deterministically.
        product_json:
            Full product JSON string as context.

        Returns
        -------
        list[MatchResult]
            One result per input item, in the same order.
        """
        if not items:
            return []

        all_results: list[MatchResult] = []

        # Process in batches
        for batch_start in range(0, len(items), BATCH_SIZE):
            batch = items[batch_start : batch_start + BATCH_SIZE]
            batch_results = await self._evaluate_batch(batch, product_json)
            all_results.extend(batch_results)

        return all_results

    async def _evaluate_batch(
        self,
        batch: list[TBTItem],
        product_json: str,
    ) -> list[MatchResult]:
        """Evaluate a single batch of TBT items."""
        # Format requirements for the prompt
        req_lines = []
        for i, item in enumerate(batch):
            req_lines.append(
                f"[{i}] Section: {item.section}\n"
                f"    Description: {item.description}\n"
                f"    Spec Requirement: {item.spec_requirement}"
            )
        requirements_text = "\n\n".join(req_lines)

        # Truncate product JSON if too large (keep under ~30k chars)
        if len(product_json) > 30000:
            product_json = product_json[:30000] + "\n... (truncated)"

        prompt = COMPLIANCE_USER_PROMPT.format(
            product_json=product_json,
            requirements_text=requirements_text,
        )

        try:
            result, response = await self.llm.extract_structured(
                prompt=prompt,
                response_model=LLMComplianceBatch,
                system_prompt=COMPLIANCE_SYSTEM_PROMPT,
                max_tokens=4096,
            )
            self._track_cost(response)

            # Map LLM results back to MatchResults
            return self._map_batch_results(batch, result)

        except Exception as exc:
            logger.warning("LLM batch evaluation failed: %s", exc)
            # Return clarification_needed for all items in the failed batch
            return [
                MatchResult(
                    status=ComplianceStatus.CLARIFICATION_NEEDED,
                    tender_value=item.spec_requirement or item.description,
                    gap_description=f"LLM evaluation failed: {exc}",
                    confidence=0.0,
                )
                for item in batch
            ]

    def _map_batch_results(
        self,
        batch: list[TBTItem],
        llm_result: LLMComplianceBatch,
    ) -> list[MatchResult]:
        """Map LLM batch output to MatchResult list."""
        # Index the LLM evaluations
        eval_by_idx: dict[int, LLMComplianceItem] = {
            e.requirement_index: e for e in llm_result.evaluations
        }

        results: list[MatchResult] = []
        for i, item in enumerate(batch):
            evaluation = eval_by_idx.get(i)

            if evaluation is None:
                # LLM didn't evaluate this item
                results.append(
                    MatchResult(
                        status=ComplianceStatus.CLARIFICATION_NEEDED,
                        tender_value=item.spec_requirement or item.description,
                        gap_description="LLM did not return evaluation for this item",
                        confidence=0.0,
                    )
                )
                continue

            status = _STATUS_MAP.get(
                evaluation.status.lower().strip(),
                ComplianceStatus.CLARIFICATION_NEEDED,
            )

            results.append(
                MatchResult(
                    status=status,
                    product_value=evaluation.product_value or None,
                    tender_value=item.spec_requirement or item.description,
                    gap_description=evaluation.gap_description or None,
                    confidence=0.7,  # LLM evaluations have moderate confidence
                )
            )

        return results
