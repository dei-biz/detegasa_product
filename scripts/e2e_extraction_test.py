"""End-to-end extraction test — runs the full pipeline on real documents.

Usage:
    python -m scripts.e2e_extraction_test [--provider anthropic|openai] [--model MODEL] [--ocr]

Requires:
    - ANTHROPIC_API_KEY or OPENAI_API_KEY in .env
    - Real documents in DOCUMENTACION/ and ESPECIFICACION DE CLIENTE/

What it does:
    1. Parses a real DETEGASA data sheet PDF (I-FD) — with tables and optional OCR
    2. Cleans and chunks the text (filters TOC, enforces min/max)
    3. Runs LLM extraction (components, performance, certifications)
    4. Parses the client's Material Requisition (I-RM)
    5. Runs tender metadata + process requirement extraction (body sections only)
    6. Parses the TBT Excel and converts deterministically
    7. Reports results, cost breakdown, quality metrics, and timing
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

# Ensure project root is on path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

load_dotenv(project_root / ".env", override=True)

from src.extraction.chunker import DocumentChunker
from src.extraction.document_type import detect_document_type
from src.extraction.pdf_parser import PDFParser
from src.extraction.text_cleaner import TextCleaner
from src.extraction.xlsx_parser import ExcelParser
from src.llm.claude_adapter import ClaudeAdapter
from src.llm.openai_adapter import OpenAIAdapter
from src.llm_extraction.product_extractor import ProductExtractor
from src.llm_extraction.tender_extractor import TenderExtractor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("e2e")


# ── Paths ────────────────────────────────────────────────────────────────────

DOCS_DIR = project_root / "DOCUMENTACION"
CLIENT_DIR = project_root / "ESPECIFICACION DE CLIENTE"

# DETEGASA data sheet (product)
DATA_SHEET_PDF = DOCS_DIR / "I-FD-3010.2G-5330-540-DTG-302-C.pdf"

# Client material requisition (tender)
MATERIAL_REQ_PDF = CLIENT_DIR / "I-RM-3010.2G-5330-667-KES-301_REVA.pdf"

# Technical Bid Evaluation Table (TBT)
TBT_DIR = CLIENT_DIR / "APPENDIX 12_TECHNICAL BID EVALUATION TABLE"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _find_tbt_file() -> Path | None:
    """Find the TBT Excel file in the appendix directory."""
    if not TBT_DIR.exists():
        return None
    for ext in ("*.xlsx", "*.xls"):
        files = list(TBT_DIR.glob(ext))
        if files:
            return files[0]
    return None


def _make_adapter(provider: str, model: str | None = None):
    """Create an LLM adapter directly from environment variables."""
    import os

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


def _print_section(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}\n")


def _print_json(obj, indent: int = 2) -> None:
    """Pretty-print a Pydantic model or dict."""
    if hasattr(obj, "model_dump"):
        data = obj.model_dump(mode="json", exclude_none=True)
    elif isinstance(obj, dict):
        data = obj
    else:
        data = str(obj)
    print(json.dumps(data, indent=indent, ensure_ascii=False, default=str))


def _format_table_as_text(table: list[list]) -> str:
    """Format an extracted table as readable text for LLM input."""
    rows = [row for row in table if any(cell for cell in row)]
    if not rows:
        return ""
    # 2-column table → key: value
    if all(len(row) == 2 for row in rows):
        lines = []
        for row in rows:
            key = str(row[0] or "").strip()
            val = str(row[1] or "").strip()
            if key and val:
                lines.append(f"{key}: {val}")
        return "\n".join(lines)
    # Multi-column → tab-separated
    lines = []
    for row in rows:
        cells = [str(c or "").strip() for c in row]
        lines.append("\t".join(cells))
    return "\n".join(lines)


# ── Test functions ───────────────────────────────────────────────────────────


async def test_product_extraction(adapter, *, use_ocr: bool = False) -> dict:
    """Test full product extraction from a DETEGASA data sheet."""
    _print_section("PRODUCT EXTRACTION (Data Sheet)")
    results = {}
    metrics = {}

    if not DATA_SHEET_PDF.exists():
        logger.warning("Data sheet not found: %s", DATA_SHEET_PDF)
        return results

    # Step 1: Parse PDF (with tables and optional OCR)
    t0 = time.perf_counter()
    doc = PDFParser().parse(DATA_SHEET_PDF, ocr=use_ocr, extract_tables=True)
    parse_time = time.perf_counter() - t0

    ocr_count = len(doc.ocr_pages)
    table_count = len(doc.pages_with_tables)
    total_tables = sum(len(p.tables) for p in doc.pages)

    logger.info(
        "Parsed %s: %d pages, %d chars (%.2fs) — %d OCR pages, %d pages with %d tables",
        doc.filename, doc.total_pages, len(doc.full_text), parse_time,
        ocr_count, table_count, total_tables,
    )
    metrics["ocr_pages"] = ocr_count
    metrics["pages_with_tables"] = table_count
    metrics["total_tables"] = total_tables

    # Step 2: Clean text (with TOC detection)
    t0 = time.perf_counter()
    cleaner = TextCleaner()
    raw_texts = [p.text for p in doc.pages]
    clean_results = cleaner.clean_pages(raw_texts)

    toc_pages = sum(1 for r in clean_results if r.is_toc)
    clean_text = "\n\n".join(r.text for r in clean_results if r.text.strip() and not r.is_toc)
    clean_time = time.perf_counter() - t0

    logger.info(
        "Cleaned text: %d chars (%.2fs) — %d TOC pages filtered",
        len(clean_text), clean_time, toc_pages,
    )
    metrics["toc_pages_filtered"] = toc_pages

    # Step 2b: Enrich text with table data
    enriched_text = clean_text
    table_texts = []
    for page in doc.pages:
        table_text = page.tables_as_text()
        if table_text:
            table_texts.append(table_text)
    if table_texts:
        enriched_text += "\n\n[EXTRACTED TABLE DATA]\n" + "\n\n".join(table_texts)
        logger.info("Added %d table extractions to enriched text", len(table_texts))

    # Step 3: Chunk
    t0 = time.perf_counter()
    doc_type = detect_document_type(doc.filename)
    chunker = DocumentChunker()
    chunks = chunker.chunk(clean_text, doc_type)
    chunk_time = time.perf_counter() - t0

    avg_chunk_size = sum(c.char_count for c in chunks) / max(len(chunks), 1)
    logger.info(
        "Document type: %s — %d chunks, avg %.0f chars (%.2fs)",
        doc_type.value, len(chunks), avg_chunk_size, chunk_time,
    )
    for i, c in enumerate(chunks[:5]):
        logger.info(
            "  Chunk %d: %d chars — %s",
            i, c.char_count, (c.section_title or "")[:60],
        )
    metrics["total_chunks"] = len(chunks)
    metrics["avg_chunk_chars"] = round(avg_chunk_size)

    # Step 4: LLM extraction
    extractor = ProductExtractor(adapter)

    # 4a. Components — use enriched text (with tables) for better extraction
    print("\n--- Components ---")
    t0 = time.perf_counter()
    components = await extractor.extract_components(chunks)
    comp_time = time.perf_counter() - t0
    logger.info(
        "Extracted %d components (%.2fs, $%.4f)",
        len(components), comp_time, extractor.total_cost_usd,
    )
    for comp in components:
        print(f"\n  [{comp.tag}] {comp.type} — {comp.name}")
        if comp.materials:
            for part, mat in comp.materials.items():
                print(f"    Material ({part}): {mat.designation} grade={mat.grade}")
        if comp.electrical:
            print(f"    Electrical: {comp.electrical}")
        if comp.mechanical:
            print(f"    Mechanical: {comp.mechanical}")

    results["components"] = len(components)
    cost_after_components = extractor.total_cost_usd

    # 4b. Performance — use enriched text with tables
    print("\n--- Performance ---")
    t0 = time.perf_counter()
    perf = await extractor.extract_performance(enriched_text)
    perf_time = time.perf_counter() - t0
    if perf:
        logger.info(
            "Performance: %s family (%.2fs, +$%.4f)",
            perf.family if hasattr(perf, 'family') else "?",
            perf_time,
            extractor.total_cost_usd - cost_after_components,
        )
        _print_json(perf)
    else:
        logger.warning("Performance extraction returned None")

    results["performance"] = perf is not None
    cost_after_perf = extractor.total_cost_usd

    # 4c. Certifications — use enriched text with tables
    print("\n--- Certifications ---")
    t0 = time.perf_counter()
    certs = await extractor.extract_certifications(enriched_text)
    cert_time = time.perf_counter() - t0
    logger.info(
        "Extracted %d certifications (%.2fs, +$%.4f)",
        len(certs), cert_time,
        extractor.total_cost_usd - cost_after_perf,
    )
    for cert in certs:
        print(f"  [{cert.cert_type.value}] {cert.standard_code} — "
              f"{cert.applicability.value} (by {cert.issuing_body or '?'})")

    results["certifications"] = len(certs)

    # Summary
    print(f"\n--- Product Summary ---")
    print(f"  Components: {len(components)}")
    print(f"  Performance: {'OK' if perf else 'FAILED'}")
    print(f"  Certifications: {len(certs)}")
    print(f"  Total LLM calls: {extractor.call_count}")
    print(f"  Total cost: ${extractor.total_cost_usd:.4f}")
    results["total_cost"] = extractor.total_cost_usd
    results["call_count"] = extractor.call_count
    results["metrics"] = metrics

    return results


async def test_tender_extraction(adapter, *, use_ocr: bool = False) -> dict:
    """Test tender extraction from client Material Requisition."""
    _print_section("TENDER EXTRACTION (Material Requisition)")
    results = {}
    metrics = {}

    if not MATERIAL_REQ_PDF.exists():
        logger.warning("Material requisition not found: %s", MATERIAL_REQ_PDF)
        return results

    # Step 1: Parse PDF
    t0 = time.perf_counter()
    doc = PDFParser().parse(MATERIAL_REQ_PDF, ocr=use_ocr, extract_tables=True)
    parse_time = time.perf_counter() - t0
    logger.info(
        "Parsed %s: %d pages, %d chars (%.2fs)",
        doc.filename, doc.total_pages, len(doc.full_text), parse_time,
    )

    # Step 2: Clean (with TOC filtering)
    cleaner = TextCleaner()
    raw_texts = [p.text for p in doc.pages]
    clean_results = cleaner.clean_pages(raw_texts)

    toc_pages = sum(1 for r in clean_results if r.is_toc)
    # Build clean text excluding TOC pages
    clean_text = "\n\n".join(r.text for r in clean_results if r.text.strip() and not r.is_toc)
    logger.info("Cleaned text: %d chars — %d TOC pages filtered", len(clean_text), toc_pages)
    metrics["toc_pages_filtered"] = toc_pages

    # Step 3: Chunk (with min/max enforcement and appendix detection)
    doc_type = detect_document_type(doc.filename)
    chunker = DocumentChunker()
    chunks = chunker.chunk(clean_text, doc_type)

    # Separate body vs appendix chunks
    body_chunks = [c for c in chunks if not c.metadata.get("is_appendix")]
    appendix_chunks = [c for c in chunks if c.metadata.get("is_appendix")]

    avg_size = sum(c.char_count for c in chunks) / max(len(chunks), 1)
    logger.info(
        "Document type: %s — %d chunks (%d body, %d appendix), avg %.0f chars",
        doc_type.value, len(chunks), len(body_chunks), len(appendix_chunks), avg_size,
    )
    metrics["total_chunks"] = len(chunks)
    metrics["body_chunks"] = len(body_chunks)
    metrics["appendix_chunks"] = len(appendix_chunks)
    metrics["avg_chunk_chars"] = round(avg_size)

    extractor = TenderExtractor(adapter)

    # 4a. Metadata (from first 5000 chars of body)
    print("\n--- Metadata ---")
    body_text = "\n\n".join(c.text for c in body_chunks)
    t0 = time.perf_counter()
    meta = await extractor.extract_metadata(body_text[:5000])
    meta_time = time.perf_counter() - t0
    if meta:
        logger.info("Metadata extracted (%.2fs, $%.4f)", meta_time, extractor.total_cost_usd)
        _print_json(meta)
    else:
        logger.warning("Metadata extraction failed")
    results["metadata"] = meta is not None
    cost_after_meta = extractor.total_cost_usd

    # 4b. Process requirements — search for sections 4-6 (where process data lives)
    print("\n--- Process Requirements ---")
    process_chunks = [
        c for c in body_chunks
        if c.section_title and any(
            c.section_title.startswith(s)
            for s in ["4", "5", "6"]
        )
    ]
    if process_chunks:
        process_text = "\n\n".join(c.text for c in process_chunks)[:8000]
        logger.info(
            "Using %d process chunks (sections 4-6): %d chars",
            len(process_chunks), len(process_text),
        )
    else:
        # Fallback: use first part of body text
        process_text = body_text[:8000]
        logger.info("No section 4-6 chunks found; using first 8000 chars of body")

    t0 = time.perf_counter()
    process = await extractor.extract_process_requirements(process_text)
    proc_time = time.perf_counter() - t0
    if process:
        logger.info(
            "Process requirements extracted (%.2fs, +$%.4f)",
            proc_time, extractor.total_cost_usd - cost_after_meta,
        )
        _print_json(process)
    else:
        logger.warning("Process requirements extraction failed")
    results["process"] = process is not None
    cost_after_process = extractor.total_cost_usd

    # 4c. Requirements from body chunks (limit to first 8 body chunks for cost control)
    print("\n--- Requirements (body chunks) ---")
    limited_chunks = body_chunks[:8]
    t0 = time.perf_counter()
    reqs = await extractor.extract_requirements(
        limited_chunks,
        source_document=doc.filename,
    )
    req_time = time.perf_counter() - t0
    logger.info(
        "Extracted %d requirements from %d body chunks (%.2fs, +$%.4f)",
        len(reqs), len(limited_chunks), req_time,
        extractor.total_cost_usd - cost_after_process,
    )
    for req in reqs[:10]:  # Show first 10
        print(f"  [{req.id}] ({req.category}) {'MANDATORY' if req.mandatory else 'optional'}")
        print(f"    {req.requirement_text[:100]}...")
    if len(reqs) > 10:
        print(f"  ... and {len(reqs) - 10} more requirements")

    results["requirements"] = len(reqs)

    print(f"\n--- Tender Summary ---")
    print(f"  Metadata: {'OK' if meta else 'FAILED'}")
    print(f"  Process: {'OK' if process else 'FAILED'}")
    print(f"  Requirements: {len(reqs)} (from {len(limited_chunks)} body chunks)")
    print(f"  Total LLM calls: {extractor.call_count}")
    print(f"  Total cost: ${extractor.total_cost_usd:.4f}")
    results["total_cost"] = extractor.total_cost_usd
    results["call_count"] = extractor.call_count
    results["metrics"] = metrics

    return results


def test_tbt_deterministic() -> dict:
    """Test TBT parsing and deterministic conversion (no LLM)."""
    _print_section("TBT CONVERSION (Deterministic, no LLM)")
    results = {}

    tbt_file = _find_tbt_file()
    if not tbt_file:
        logger.warning("TBT file not found in %s", TBT_DIR)
        return results

    # Parse
    t0 = time.perf_counter()
    parser = ExcelParser()
    items = parser.parse_tbt(tbt_file)
    parse_time = time.perf_counter() - t0
    logger.info("Parsed TBT: %d items (%.2fs)", len(items), parse_time)

    # Show some items
    for item in items[:5]:
        print(f"  Row {item.row_number}: [{item.status}] {item.description[:80]}")
    if len(items) > 5:
        print(f"  ... and {len(items) - 5} more items")

    # Convert to requirements
    from unittest.mock import MagicMock
    mock_llm = MagicMock()
    mock_llm.provider = "mock"
    mock_llm.model = "mock"

    extractor = TenderExtractor(mock_llm)
    t0 = time.perf_counter()
    reqs = extractor.requirements_from_tbt(items, source_document=tbt_file.name)
    convert_time = time.perf_counter() - t0

    logger.info(
        "Converted to %d requirements (%.3fs, $0.00)",
        len(reqs), convert_time,
    )

    # Category breakdown
    from collections import Counter
    cats = Counter(r.category for r in reqs)
    print("\n  Category breakdown:")
    for cat, count in cats.most_common():
        print(f"    {cat}: {count}")

    mandatory = sum(1 for r in reqs if r.mandatory)
    print(f"\n  Mandatory: {mandatory}/{len(reqs)}")

    results["items_parsed"] = len(items)
    results["requirements"] = len(reqs)
    results["categories"] = dict(cats)

    return results


def _save_results(all_results: dict) -> None:
    """Save results JSON to scripts/e2e_results.json."""
    output_file = project_root / "scripts" / "e2e_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)
    logger.info("Results saved to %s", output_file)


# ── Main ─────────────────────────────────────────────────────────────────────


async def main():
    parser = argparse.ArgumentParser(description="E2E extraction test")
    parser.add_argument(
        "--provider", default="anthropic",
        choices=["anthropic", "openai"],
        help="LLM provider to use (default: anthropic)",
    )
    parser.add_argument(
        "--model", default=None,
        help="Override model (e.g. claude-haiku-4-5-20251001, gpt-4o-mini)",
    )
    parser.add_argument(
        "--skip-product", action="store_true",
        help="Skip product extraction (saves cost)",
    )
    parser.add_argument(
        "--skip-tender", action="store_true",
        help="Skip tender extraction (saves cost)",
    )
    parser.add_argument(
        "--tbt-only", action="store_true",
        help="Only run TBT (deterministic, free)",
    )
    parser.add_argument(
        "--ocr", action="store_true",
        help="Enable OCR for image-only pages (requires Tesseract)",
    )
    args = parser.parse_args()

    _print_section("E2E EXTRACTION TEST")
    print(f"  Provider: {args.provider}")
    print(f"  Model:    {args.model or 'default'}")
    print(f"  OCR:      {'ON' if args.ocr else 'OFF'}")
    print(f"  Project:  {project_root}")

    # Check Tesseract availability
    if args.ocr:
        from src.extraction.pdf_parser import is_tesseract_available
        if is_tesseract_available():
            print("  Tesseract: AVAILABLE")
        else:
            print("  Tesseract: NOT FOUND — OCR will be skipped")

    all_results = {}
    total_cost = 0.0

    # TBT is always free — run it first
    tbt_results = test_tbt_deterministic()
    all_results["tbt"] = tbt_results

    if args.tbt_only:
        _save_results(all_results)
        _print_section("DONE (TBT only)")
        return

    # Create LLM adapter
    adapter = _make_adapter(args.provider, args.model)
    logger.info("Using %s/%s", adapter.provider, adapter.model)

    if not args.skip_product:
        product_results = await test_product_extraction(adapter, use_ocr=args.ocr)
        all_results["product"] = product_results
        total_cost += product_results.get("total_cost", 0)

    if not args.skip_tender:
        tender_results = await test_tender_extraction(adapter, use_ocr=args.ocr)
        all_results["tender"] = tender_results
        total_cost += tender_results.get("total_cost", 0)

    # Final summary
    _print_section("FINAL SUMMARY")
    print(f"  Provider: {adapter.provider}")
    print(f"  Model: {adapter.model}")
    print(f"  OCR: {'ON' if args.ocr else 'OFF'}")
    print(f"  Total LLM cost: ${total_cost:.4f}")
    print()

    if "product" in all_results:
        p = all_results["product"]
        m = p.get("metrics", {})
        print(f"  Product extraction:")
        print(f"    Components: {p.get('components', '?')}")
        print(f"    Performance: {p.get('performance', '?')}")
        print(f"    Certifications: {p.get('certifications', '?')}")
        print(f"    Cost: ${p.get('total_cost', 0):.4f}")
        if m:
            print(f"    Metrics: {m.get('total_chunks', '?')} chunks, "
                  f"{m.get('ocr_pages', 0)} OCR pages, "
                  f"{m.get('total_tables', 0)} tables extracted, "
                  f"{m.get('toc_pages_filtered', 0)} TOC pages filtered")

    if "tender" in all_results:
        t = all_results["tender"]
        m = t.get("metrics", {})
        print(f"  Tender extraction:")
        print(f"    Metadata: {t.get('metadata', '?')}")
        print(f"    Process: {t.get('process', '?')}")
        print(f"    Requirements: {t.get('requirements', '?')}")
        print(f"    Cost: ${t.get('total_cost', 0):.4f}")
        if m:
            print(f"    Metrics: {m.get('total_chunks', '?')} chunks "
                  f"({m.get('body_chunks', '?')} body, {m.get('appendix_chunks', '?')} appendix), "
                  f"{m.get('toc_pages_filtered', 0)} TOC pages filtered")

    if "tbt" in all_results:
        tb = all_results["tbt"]
        print(f"  TBT (deterministic):")
        print(f"    Items parsed: {tb.get('items_parsed', '?')}")
        print(f"    Requirements: {tb.get('requirements', '?')}")
        print(f"    Cost: $0.00")

    _save_results(all_results)


if __name__ == "__main__":
    asyncio.run(main())
