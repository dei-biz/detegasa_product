"""End-to-end compliance evaluation — runs the compliance engine on extracted data.

Usage:
    python -m scripts.compliance_test [--provider anthropic|openai] [--model MODEL]
                                      [--product-json PATH] [--no-llm]

Requires:
    - A product extraction JSON in product/ (from e2e_extraction_test.py)
    - ANTHROPIC_API_KEY or OPENAI_API_KEY in .env (unless --no-llm)
    - TBT Excel file in ESPECIFICACION DE CLIENTE/APPENDIX 12_...

What it does:
    1. Loads the product JSON from a previous E2E extraction
    2. Parses the TBT Excel to get tender requirements
    3. Runs ComplianceEngine (deterministic matchers + LLM fallback)
    4. Saves results to product/<timestamp>_compliance.json
    5. Prints summary: compliant/non-compliant/partial/clarification by category

Outputs:
    - product/<timestamp>_compliance.json  — full compliance results
    - logs/<timestamp>_compliance.log      — complete system log
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

# Ensure project root is on path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

load_dotenv(project_root / ".env", override=True)

# Fix Windows console encoding for Unicode characters
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from src.compliance.engine import ComplianceEngine
from src.extraction.xlsx_parser import ExcelParser, TBTItem
from src.schemas.common import ComplianceStatus


# ── Output directories ───────────────────────────────────────────────────────

PRODUCT_DIR = project_root / "product"
LOGS_DIR = project_root / "logs"
PRODUCT_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)


# ── Paths ─────────────────────────────────────────────────────────────────────

CLIENT_DIR = project_root / "ESPECIFICACION DE CLIENTE"
TBT_DIR = CLIENT_DIR / "APPENDIX 12_TECHNICAL BID EVALUATION TABLE"


# ── Logging setup ────────────────────────────────────────────────────────────


def _setup_logging(timestamp: str) -> Path:
    """Configure logging to both console and timestamped log file."""
    log_file = LOGS_DIR / f"{timestamp}_compliance.log"

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Console handler — INFO level
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    console_handler.setFormatter(console_fmt)

    # File handler — DEBUG level
    file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)-30s | %(funcName)-25s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_fmt)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    return log_file


logger = logging.getLogger("compliance")


# ── Helpers ───────────────────────────────────────────────────────────────────


def _print_section(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}\n")


def _find_tbt_file() -> Path | None:
    """Find the TBT Excel file in the appendix directory."""
    if not TBT_DIR.exists():
        return None
    for ext in ("*.xlsx", "*.xls"):
        files = list(TBT_DIR.glob(ext))
        if files:
            return files[0]
    return None


def _find_latest_product_json() -> Path | None:
    """Find the most recent E2E extraction JSON in product/."""
    if not PRODUCT_DIR.exists():
        return None
    json_files = sorted(
        PRODUCT_DIR.glob("*_e2e_*.json"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    return json_files[0] if json_files else None


def _load_product_data(json_path: Path) -> dict:
    """Load product data from an E2E extraction JSON.

    Rebuilds the product_data dict expected by the ComplianceEngine:
    {
        "performance": {...},
        "components": [...],
        "certifications": [...],
        "package_level": {...},
    }
    """
    with open(json_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    product_section = raw.get("product", {})

    product_data = {
        "performance": product_section.get("performance", {}),
        "components": product_section.get("components", []),
        "certifications": product_section.get("certifications", []),
        "package_level": product_section.get("package_level"),
    }

    # Extract metadata for IDs
    run = raw.get("run", {})
    meta = {
        "product_id": product_data.get("performance", {}).get("service", "unknown"),
        "source_file": json_path.name,
        "extraction_timestamp": run.get("timestamp", ""),
        "provider": run.get("provider", ""),
        "model": run.get("model_actual", run.get("model", "")),
    }

    return product_data, meta


def _make_adapter(provider: str, model: str | None = None):
    """Create an LLM adapter from environment variables."""
    import os

    from src.llm.claude_adapter import ClaudeAdapter
    from src.llm.openai_adapter import OpenAIAdapter

    if provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            logger.error("ANTHROPIC_API_KEY not set in .env")
            sys.exit(1)
        return ClaudeAdapter(api_key=api_key, model=model)
    elif provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            logger.error("OPENAI_API_KEY not set in .env")
            sys.exit(1)
        return OpenAIAdapter(api_key=api_key, model=model)
    else:
        logger.error("Unknown provider: %s", provider)
        sys.exit(1)


def _status_symbol(status: ComplianceStatus) -> str:
    """Return a symbol for terminal display."""
    return {
        ComplianceStatus.COMPLIANT: "OK",
        ComplianceStatus.NON_COMPLIANT: "XX",
        ComplianceStatus.PARTIAL: "~~",
        ComplianceStatus.CLARIFICATION_NEEDED: "??",
        ComplianceStatus.NOT_APPLICABLE: "--",
        ComplianceStatus.DEVIATION_ACCEPTABLE: "~OK",
    }.get(status, "??")


# ── Main ──────────────────────────────────────────────────────────────────────


async def main():
    parser = argparse.ArgumentParser(description="E2E compliance evaluation")
    parser.add_argument(
        "--provider",
        default="anthropic",
        choices=["anthropic", "openai"],
        help="LLM provider for non-deterministic evaluation (default: anthropic)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override model (e.g. claude-haiku-4-5-20251001)",
    )
    parser.add_argument(
        "--product-json",
        default=None,
        help="Path to product JSON (default: latest in product/)",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip LLM evaluation — only deterministic matchers",
    )
    args = parser.parse_args()

    # Timestamp for this run
    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = _setup_logging(run_timestamp)

    _print_section("COMPLIANCE EVALUATION")
    print(f"  Provider: {args.provider}")
    print(f"  Model:    {args.model or 'default'}")
    print(f"  LLM:      {'OFF (deterministic only)' if args.no_llm else 'ON'}")
    print(f"  Project:  {project_root}")
    print(f"  Log file: {log_file}")

    logger.info("=== Compliance run started: %s ===", run_timestamp)

    # ── Step 1: Load product data ────────────────────────────────────────────

    _print_section("STEP 1: Load Product Data")

    if args.product_json:
        product_json_path = Path(args.product_json)
    else:
        product_json_path = _find_latest_product_json()

    if not product_json_path or not product_json_path.exists():
        logger.error(
            "No product JSON found. Run e2e_extraction_test.py first, "
            "or specify --product-json PATH"
        )
        sys.exit(1)

    product_data, extraction_meta = _load_product_data(product_json_path)

    n_comp = len(product_data.get("components", []))
    n_cert = len(product_data.get("certifications", []))
    perf_family = product_data.get("performance", {}).get("family", "?")

    print(f"  Source: {product_json_path.name}")
    print(f"  Components: {n_comp}")
    print(f"  Certifications: {n_cert}")
    print(f"  Performance family: {perf_family}")

    logger.info(
        "Loaded product data from %s: %d components, %d certifications, family=%s",
        product_json_path.name,
        n_comp,
        n_cert,
        perf_family,
    )

    # ── Step 2: Parse TBT ────────────────────────────────────────────────────

    _print_section("STEP 2: Parse TBT (Technical Bid Evaluation Table)")

    tbt_file = _find_tbt_file()
    if not tbt_file:
        logger.error("TBT file not found in %s", TBT_DIR)
        sys.exit(1)

    t0 = time.perf_counter()
    tbt_items = ExcelParser().parse_tbt(tbt_file)
    parse_time = time.perf_counter() - t0

    print(f"  TBT file: {tbt_file.name}")
    print(f"  Items parsed: {len(tbt_items)}")
    print(f"  Parse time: {parse_time:.2f}s")

    logger.info("Parsed TBT: %d items from %s (%.2fs)", len(tbt_items), tbt_file.name, parse_time)

    # Show sample items
    for item in tbt_items[:3]:
        print(f"    Row {item.row_number}: {item.description[:70]}...")

    # ── Step 3: Run Compliance Engine ────────────────────────────────────────

    _print_section("STEP 3: Run Compliance Engine")

    llm_adapter = None
    if not args.no_llm:
        llm_adapter = _make_adapter(args.provider, args.model)
        logger.info("LLM adapter: %s/%s", llm_adapter.provider, llm_adapter.model)

    engine = ComplianceEngine(llm=llm_adapter)

    t0 = time.perf_counter()
    result = await engine.evaluate(
        product_data=product_data,
        tbt_items=tbt_items,
        product_id=extraction_meta.get("product_id", ""),
        tender_id=tbt_file.stem,
    )
    eval_time = time.perf_counter() - t0

    print(f"  Evaluation time: {eval_time:.1f}s")
    print(f"  Overall score: {result.overall_score:.1f}%")
    print(f"  Total items: {result.summary.total_requirements}")

    # ── Step 4: Display Results ──────────────────────────────────────────────

    _print_section("RESULTS SUMMARY")

    # Status counts
    s = result.summary
    print(f"  Compliant:        {s.compliant_count:4d}  "
          f"({s.compliant_count / max(s.total_requirements, 1) * 100:.1f}%)")
    print(f"  Non-compliant:    {s.non_compliant_count:4d}  "
          f"({s.non_compliant_count / max(s.total_requirements, 1) * 100:.1f}%)")
    print(f"  Partial:          {s.partial_count:4d}  "
          f"({s.partial_count / max(s.total_requirements, 1) * 100:.1f}%)")
    print(f"  Clarification:    {s.clarification_count:4d}  "
          f"({s.clarification_count / max(s.total_requirements, 1) * 100:.1f}%)")

    not_applicable = sum(
        1 for i in result.items if i.status == ComplianceStatus.NOT_APPLICABLE
    )
    print(f"  Not applicable:   {not_applicable:4d}  "
          f"({not_applicable / max(s.total_requirements, 1) * 100:.1f}%)")

    # Category breakdown
    print("\n  By category:")
    cat_status: dict[str, Counter] = {}
    for item in result.items:
        if item.category not in cat_status:
            cat_status[item.category] = Counter()
        cat_status[item.category][item.status.value] += 1

    for cat in sorted(cat_status.keys()):
        counts = cat_status[cat]
        total = sum(counts.values())
        ok = counts.get("compliant", 0)
        nok = counts.get("non_compliant", 0)
        print(f"    {cat:20s}: {total:3d} items  "
              f"({ok} OK, {nok} NOK, {total - ok - nok} other)")

    # Matcher stats
    print("\n  Matcher distribution:")
    for name, count in engine.stats.items():
        if name != "total" and count > 0:
            pct = count / max(engine.stats["total"], 1) * 100
            print(f"    {name:20s}: {count:4d} ({pct:.1f}%)")

    # Disqualifying gaps
    if s.disqualifying_gaps:
        print(f"\n  DISQUALIFYING GAPS ({len(s.disqualifying_gaps)}):")
        for gap in s.disqualifying_gaps:
            print(f"    !! {gap}")

    # Key deviations
    if s.key_deviations:
        print(f"\n  KEY DEVIATIONS ({len(s.key_deviations)}):")
        for dev in s.key_deviations[:10]:
            print(f"    >> {dev}")
        if len(s.key_deviations) > 10:
            print(f"    ... and {len(s.key_deviations) - 10} more")

    # Non-compliant items detail
    nok_items = [i for i in result.items if i.status == ComplianceStatus.NON_COMPLIANT]
    if nok_items:
        print(f"\n  NON-COMPLIANT ITEMS ({len(nok_items)}):")
        for item in nok_items[:15]:
            print(f"    [{item.requirement_id}] {item.requirement_text[:60]}...")
            if item.product_value:
                print(f"      Product: {item.product_value}")
            print(f"      Required: {item.tender_value}")
            if item.gap_description:
                print(f"      Gap: {item.gap_description}")
            print()
        if len(nok_items) > 15:
            print(f"    ... and {len(nok_items) - 15} more non-compliant items")

    # LLM cost (if used)
    llm_cost = 0.0
    llm_calls = 0
    if engine.llm_comparator:
        llm_cost = engine.llm_comparator.total_cost_usd
        llm_calls = engine.llm_comparator.call_count
        print(f"\n  LLM cost: ${llm_cost:.4f} ({llm_calls} calls)")

    # ── Step 5: Save results ─────────────────────────────────────────────────

    _print_section("SAVING RESULTS")

    # Build output dict
    llm_tag = "no-llm" if args.no_llm else args.provider
    filename = f"{run_timestamp}_compliance_{llm_tag}.json"
    output_file = PRODUCT_DIR / filename

    output_data = {
        "run": {
            "type": "compliance",
            "timestamp": run_timestamp,
            "provider": "none" if args.no_llm else args.provider,
            "model": "none" if args.no_llm else (args.model or "default"),
            "product_source": product_json_path.name,
            "tbt_source": tbt_file.name,
            "eval_time_s": round(eval_time, 2),
            "llm_cost": round(llm_cost, 4),
            "llm_calls": llm_calls,
        },
        "result": result.model_dump(mode="json", exclude_none=True),
        "engine_stats": engine.stats,
        "extraction_meta": extraction_meta,
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False, default=str)

    print(f"  Results: {output_file}")
    print(f"  Log:     {log_file}")
    print(f"\n  Score: {result.overall_score:.1f}%")

    logger.info(
        "=== Compliance run completed: %s (%.1fs, $%.4f, score=%.1f%%) ===",
        run_timestamp,
        eval_time,
        llm_cost,
        result.overall_score,
    )


if __name__ == "__main__":
    asyncio.run(main())
