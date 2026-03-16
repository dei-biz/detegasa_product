"""Compliance Engine — orchestrates deterministic matchers + LLM fallback.

Receives a product JSON and a list of TBT items, routes each requirement
through the deterministic matchers first, and sends unresolved items to the
LLM comparator in batches.  Produces a ComplianceResult (with ComplianceItems
and a summary) that can be serialized to JSON or used to auto-fill the TBT.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from src.compliance.llm_comparator import LLMComparator
from src.compliance.matchers.base import BaseMatcher, MatchResult
from src.compliance.matchers.certification_matcher import CertificationMatcher
from src.compliance.matchers.material_matcher import MaterialMatcher
from src.compliance.matchers.process_matcher import ProcessMatcher
from src.extraction.xlsx_parser import TBTItem
from src.llm.adapter import LLMAdapter
from src.schemas.common import ComplianceStatus, RiskLevel
from src.schemas.compliance import ComplianceItem, ComplianceResult, ComplianceSummary

logger = logging.getLogger(__name__)


# ── Risk assessment helpers ──────────────────────────────────────────────────

_HIGH_RISK_KEYWORDS = {
    "safety",
    "hazardous",
    "explosion",
    "atex",
    "sil",
    "fire",
    "emergency",
    "imo",
    "marpol",
    "solas",
}

_MEDIUM_RISK_KEYWORDS = {
    "pressure",
    "design pressure",
    "test pressure",
    "certification",
    "class society",
    "material",
    "temperature",
    "ppm",
}


def _assess_risk(tbt_item: TBTItem, status: ComplianceStatus) -> RiskLevel:
    """Assess risk level based on requirement content and compliance status."""
    if status in (ComplianceStatus.COMPLIANT, ComplianceStatus.NOT_APPLICABLE):
        return RiskLevel.LOW

    text = f"{tbt_item.description} {tbt_item.spec_requirement}".lower()

    if any(kw in text for kw in _HIGH_RISK_KEYWORDS):
        if status == ComplianceStatus.NON_COMPLIANT:
            return RiskLevel.DISQUALIFYING
        return RiskLevel.HIGH

    if any(kw in text for kw in _MEDIUM_RISK_KEYWORDS):
        if status == ComplianceStatus.NON_COMPLIANT:
            return RiskLevel.HIGH
        return RiskLevel.MEDIUM

    if status == ComplianceStatus.NON_COMPLIANT:
        return RiskLevel.MEDIUM

    return RiskLevel.LOW


def _infer_category(tbt_item: TBTItem, matcher_name: str | None) -> str:
    """Infer the requirement category from the matcher or item content."""
    if matcher_name:
        return matcher_name  # "process", "material", "certification"

    text = f"{tbt_item.description} {tbt_item.section}".lower()

    if any(kw in text for kw in ("electric", "voltage", "power", "cable", "wiring")):
        return "electrical"
    if any(kw in text for kw in ("instrument", "sensor", "transmitter", "signal")):
        return "instrumentation"
    if any(kw in text for kw in ("paint", "coating", "surface", "finish")):
        return "coating"
    if any(kw in text for kw in ("document", "drawing", "manual", "report")):
        return "documentation"
    if any(kw in text for kw in ("delivery", "schedule", "lead time", "shipping")):
        return "commercial"
    if any(kw in text for kw in ("test", "inspection", "fat", "sat", "witness")):
        return "testing"
    if any(kw in text for kw in ("spare", "tool", "accessory")):
        return "spares"

    return "general"


# ── Main engine ──────────────────────────────────────────────────────────────


class ComplianceEngine:
    """Orchestrate compliance evaluation: deterministic matchers + LLM fallback.

    Usage
    -----
    >>> engine = ComplianceEngine(llm_adapter)
    >>> result = await engine.evaluate(product_data, tbt_items, product_id, tender_id)
    """

    def __init__(
        self,
        llm: LLMAdapter | None = None,
        *,
        matchers: list[BaseMatcher] | None = None,
    ):
        # Deterministic matchers — order matters: first match wins
        self.matchers: list[BaseMatcher] = matchers or [
            ProcessMatcher(),
            MaterialMatcher(),
            CertificationMatcher(),
        ]
        # LLM comparator for items no matcher can handle
        self.llm_comparator: LLMComparator | None = (
            LLMComparator(llm) if llm else None
        )
        # Tracking
        self.stats: dict[str, int] = {}

    async def evaluate(
        self,
        product_data: dict,
        tbt_items: list[TBTItem],
        product_id: str = "",
        tender_id: str = "",
    ) -> ComplianceResult:
        """Run the full compliance evaluation pipeline.

        Parameters
        ----------
        product_data:
            Product JSON (from extraction pipeline).
        tbt_items:
            TBT rows parsed from the tender Excel.
        product_id:
            Product identifier for the result.
        tender_id:
            Tender identifier for the result.

        Returns
        -------
        ComplianceResult
            Complete compliance evaluation with items and summary.
        """
        start = time.time()
        logger.info(
            "Starting compliance evaluation: %d TBT items, %d matchers",
            len(tbt_items),
            len(self.matchers),
        )

        # Reset stats
        self.stats = {m.name: 0 for m in self.matchers}
        self.stats["llm"] = 0
        self.stats["total"] = len(tbt_items)

        # Phase 1: Deterministic matching
        compliance_items: list[ComplianceItem] = []
        llm_queue: list[tuple[int, TBTItem]] = []  # (index, item)

        for i, tbt_item in enumerate(tbt_items):
            match_result, matcher_name = self._try_deterministic(
                tbt_item, product_data
            )

            if match_result is not None:
                self.stats[matcher_name] += 1
                item = self._to_compliance_item(
                    tbt_item, match_result, matcher_name
                )
                compliance_items.append(item)
            else:
                # Queue for LLM
                llm_queue.append((i, tbt_item))
                # Placeholder — will be replaced
                compliance_items.append(None)  # type: ignore[arg-type]

        logger.info(
            "Deterministic phase: %d resolved, %d queued for LLM",
            len(tbt_items) - len(llm_queue),
            len(llm_queue),
        )
        for name, count in self.stats.items():
            if count > 0 and name not in ("llm", "total"):
                logger.info("  %s matcher: %d items", name, count)

        # Phase 2: LLM evaluation for unresolved items
        if llm_queue and self.llm_comparator:
            llm_items = [item for _, item in llm_queue]
            product_json_str = json.dumps(product_data, ensure_ascii=False)

            llm_results = await self.llm_comparator.batch_evaluate(
                llm_items, product_json_str
            )

            for (idx, tbt_item), match_result in zip(llm_queue, llm_results):
                self.stats["llm"] += 1
                item = self._to_compliance_item(tbt_item, match_result, "llm")
                compliance_items[idx] = item

            logger.info(
                "LLM phase: %d items evaluated (cost: $%.4f, %d calls)",
                len(llm_queue),
                self.llm_comparator.total_cost_usd,
                self.llm_comparator.call_count,
            )
        elif llm_queue:
            # No LLM available — mark all as clarification_needed
            logger.warning(
                "No LLM adapter configured — %d items marked as clarification_needed",
                len(llm_queue),
            )
            for idx, tbt_item in llm_queue:
                compliance_items[idx] = ComplianceItem(
                    requirement_id=f"TBT-{tbt_item.row_number}",
                    category=_infer_category(tbt_item, None),
                    requirement_text=tbt_item.description,
                    tender_value=tbt_item.spec_requirement or tbt_item.description,
                    status=ComplianceStatus.CLARIFICATION_NEEDED,
                    gap_description="No LLM configured for non-deterministic evaluation",
                    risk_level=RiskLevel.MEDIUM,
                    source_section=tbt_item.section,
                )

        # Build summary
        elapsed = time.time() - start
        summary = self._build_summary(compliance_items)

        # Compute overall score
        score = self._compute_score(compliance_items)

        comparison_id = f"CMP-{uuid.uuid4().hex[:8].upper()}"

        logger.info(
            "Compliance evaluation complete in %.1fs — score: %.1f%%, "
            "%d compliant, %d non-compliant, %d partial, %d clarification",
            elapsed,
            score,
            summary.compliant_count,
            summary.non_compliant_count,
            summary.partial_count,
            summary.clarification_count,
        )

        return ComplianceResult(
            comparison_id=comparison_id,
            product_id=product_id or "unknown",
            tender_id=tender_id or "unknown",
            overall_score=score,
            items=compliance_items,
            summary=summary,
        )

    def _try_deterministic(
        self, tbt_item: TBTItem, product_data: dict
    ) -> tuple[MatchResult | None, str | None]:
        """Try each deterministic matcher in order. Return first match."""
        for matcher in self.matchers:
            try:
                if matcher.can_handle(tbt_item):
                    result = matcher.evaluate(tbt_item, product_data)
                    logger.debug(
                        "Matcher '%s' handled TBT row %d: %s (conf=%.2f)",
                        matcher.name,
                        tbt_item.row_number,
                        result.status.value,
                        result.confidence,
                    )
                    return result, matcher.name
            except Exception as exc:
                logger.warning(
                    "Matcher '%s' failed on TBT row %d: %s",
                    matcher.name,
                    tbt_item.row_number,
                    exc,
                )
                continue
        return None, None

    @staticmethod
    def _to_compliance_item(
        tbt_item: TBTItem,
        match_result: MatchResult,
        matcher_name: str,
    ) -> ComplianceItem:
        """Convert a MatchResult into a ComplianceItem for the final report."""
        return ComplianceItem(
            requirement_id=f"TBT-{tbt_item.row_number}",
            category=_infer_category(tbt_item, matcher_name),
            requirement_text=tbt_item.description,
            product_value=match_result.product_value,
            tender_value=match_result.tender_value,
            status=match_result.status,
            gap_description=match_result.gap_description,
            risk_level=_assess_risk(tbt_item, match_result.status),
            source_section=tbt_item.section,
        )

    @staticmethod
    def _build_summary(items: list[ComplianceItem]) -> ComplianceSummary:
        """Aggregate compliance items into a summary."""
        total = len(items)
        compliant = sum(
            1 for i in items if i.status == ComplianceStatus.COMPLIANT
        )
        non_compliant = sum(
            1 for i in items if i.status == ComplianceStatus.NON_COMPLIANT
        )
        partial = sum(
            1 for i in items if i.status == ComplianceStatus.PARTIAL
        )
        clarification = sum(
            1
            for i in items
            if i.status == ComplianceStatus.CLARIFICATION_NEEDED
        )

        # Identify disqualifying gaps
        disqualifying = [
            f"[{i.requirement_id}] {i.requirement_text}: {i.gap_description}"
            for i in items
            if i.risk_level == RiskLevel.DISQUALIFYING
        ]

        # Key deviations: non-compliant items with HIGH risk
        key_deviations = [
            f"[{i.requirement_id}] {i.requirement_text}: {i.gap_description}"
            for i in items
            if i.status == ComplianceStatus.NON_COMPLIANT
            and i.risk_level in (RiskLevel.HIGH, RiskLevel.DISQUALIFYING)
        ]

        return ComplianceSummary(
            total_requirements=total,
            compliant_count=compliant,
            non_compliant_count=non_compliant,
            partial_count=partial,
            clarification_count=clarification,
            disqualifying_gaps=disqualifying,
            key_deviations=key_deviations,
        )

    @staticmethod
    def _compute_score(items: list[ComplianceItem]) -> float:
        """Compute an overall compliance score (0-100).

        Scoring:
        - Compliant: 1.0 point
        - Deviation acceptable: 0.9 points
        - Partial: 0.5 points
        - Not applicable: excluded from scoring
        - Clarification needed: 0.3 points (penalize unknowns mildly)
        - Non-compliant: 0.0 points
        """
        _WEIGHTS = {
            ComplianceStatus.COMPLIANT: 1.0,
            ComplianceStatus.DEVIATION_ACCEPTABLE: 0.9,
            ComplianceStatus.PARTIAL: 0.5,
            ComplianceStatus.CLARIFICATION_NEEDED: 0.3,
            ComplianceStatus.NON_COMPLIANT: 0.0,
        }

        scored_items = [
            i for i in items if i.status != ComplianceStatus.NOT_APPLICABLE
        ]

        if not scored_items:
            return 100.0

        total_score = sum(
            _WEIGHTS.get(i.status, 0.0) for i in scored_items
        )

        return round(total_score / len(scored_items) * 100, 1)
