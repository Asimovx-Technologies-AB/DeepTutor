#!/usr/bin/env python3
"""
Terminal Document Processing Pipeline Test Harness
===================================================
Exercises the full 3-stage doc_processor pipeline against a real PDF:
  Stage 1: Text extraction (fast path)
  Stage 2: Table extraction (pdfplumber)
  Stage 3: Image captioning (Gemini VLM)

Then verifies that image-related and table-related queries retrieve the
correct chunk types via retrieve_context().

Usage:
    cd backend
    python test_doc_pipeline.py
    python test_doc_pipeline.py --pdf path/to/custom.pdf
    python test_doc_pipeline.py --max-pages 5
"""
import os
import sys
import time
import asyncio
import argparse
from pathlib import Path

# Fix Windows terminal encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    os.system("")

# ── Ensure backend is on sys.path ────────────────────────────────────────────
_backend_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(_backend_dir))

from app.rag.doc_processor import DocumentProcessor, DocumentChunk


# ── Terminal formatting helpers ──────────────────────────────────────────────

class _C:
    """ANSI color codes for terminal output."""
    BOLD   = "\033[1m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    CYAN   = "\033[96m"
    DIM    = "\033[2m"
    RESET  = "\033[0m"


def _banner(text: str):
    width = 60
    print(f"\n{_C.BOLD}{_C.CYAN}{'=' * width}{_C.RESET}")
    print(f"{_C.BOLD}{_C.CYAN}  {text}{_C.RESET}")
    print(f"{_C.BOLD}{_C.CYAN}{'=' * width}{_C.RESET}\n")


def _section(text: str):
    print(f"\n{_C.BOLD}-- {text} --{_C.RESET}\n")


def _ok(text: str):
    print(f"  {_C.GREEN}[✓]{_C.RESET} {text}")


def _warn(text: str):
    print(f"  {_C.YELLOW}[!]{_C.RESET} {text}")


def _fail(text: str):
    print(f"  {_C.RED}[✗]{_C.RESET} {text}")


def _info(text: str):
    print(f"  {_C.DIM}{text}{_C.RESET}")


def _pass_fail(label: str, passed: bool):
    status = f"{_C.GREEN}✅ PASS{_C.RESET}" if passed else f"{_C.RED}❌ FAIL{_C.RESET}"
    print(f"  {label}: {status}")


# ── Main test harness ───────────────────────────────────────────────────────

async def run_pipeline_test(pdf_path: str, max_pages: int = 8):
    """Run the full 3-stage pipeline and query verification."""

    doc_id = "test_pipeline_doc"
    session_id = "test_pipeline_session"
    file_name = Path(pdf_path).name

    # Use a fresh processor instance so we don't pollute the global singleton
    processor = DocumentProcessor()

    results = {
        "text_chunks": 0,
        "table_chunks": 0,
        "image_chunks": 0,
        "image_query_pass": 0,
        "image_query_total": 0,
        "table_query_pass": 0,
        "table_query_total": 0,
    }

    # ═══════════════════════════════════════════════════════════════════════
    # STAGE 1: TEXT EXTRACTION
    # ═══════════════════════════════════════════════════════════════════════
    _banner("STAGE 1: TEXT EXTRACTION (fast path)")
    print(f"  File: {file_name}")
    print(f"  Path: {pdf_path}")

    t0 = time.perf_counter()
    doc = await processor.ingest_document(
        doc_id=doc_id,
        file_path=pdf_path,
        file_name=file_name,
        subject="Chemistry",
        session_id=session_id,
    )
    t1 = time.perf_counter()

    # Display text chunk results grouped by page
    text_chunks = [c for c in doc.chunks if c.source_type == "text"]
    pages_seen: dict[int, list[DocumentChunk]] = {}
    for c in text_chunks:
        pages_seen.setdefault(c.page, []).append(c)

    for page_num in sorted(pages_seen.keys()):
        chunks = pages_seen[page_num]
        total_chars = sum(len(c.content) for c in chunks)
        _ok(f"Page {page_num:>3}: {len(chunks)} chunk(s)  ({total_chars:,} chars)")

    results["text_chunks"] = len(text_chunks)

    _section(f"Stage 1 Complete: {len(text_chunks)} text chunks in {t1 - t0:.2f}s")
    print(f"  Status: {_C.GREEN}{doc.status}{_C.RESET}")

    # ═══════════════════════════════════════════════════════════════════════
    # STAGE 2: TABLE EXTRACTION
    # ═══════════════════════════════════════════════════════════════════════
    _banner("STAGE 2: TABLE EXTRACTION (pdfplumber)")

    t2 = time.perf_counter()
    try:
        table_chunks = await asyncio.to_thread(
            processor._extract_tables_from_pdf, pdf_path, doc_id
        )
    except Exception as e:
        table_chunks = []
        _fail(f"Table extraction error: {e}")

    t3 = time.perf_counter()

    if table_chunks:
        # Add them to the doc record so retrieve_context can find them
        doc.chunks.extend(table_chunks)
        doc.stats["tables"] = len(table_chunks)

        for tc in table_chunks:
            rows_meta = tc.metadata.get("rows", "?")
            cols_meta = tc.metadata.get("cols", "?")
            _ok(f"Page {tc.page}, Table {tc.metadata.get('table_index', '?')} "
                f"({rows_meta} rows x {cols_meta} cols)")
            # Print the markdown table content (truncated for display)
            for line in tc.content.strip().split("\n")[:6]:
                _info(f"    {line}")
            if tc.content.strip().count("\n") > 5:
                _info(f"    ... ({tc.content.strip().count(chr(10)) + 1} total rows)")
    else:
        _warn("No tables found in this PDF")

    results["table_chunks"] = len(table_chunks)

    _section(f"Stage 2 Complete: {len(table_chunks)} table(s) in {t3 - t2:.2f}s")

    # ═══════════════════════════════════════════════════════════════════════
    # STAGE 3: IMAGE CAPTIONING (VLM)
    # ═══════════════════════════════════════════════════════════════════════
    _banner("STAGE 3: IMAGE CAPTIONING (Gemini VLM)")

    # Check if Gemini API key is available
    from app.rag.vlm_client import _get_active_gemini_key
    api_key = _get_active_gemini_key()
    vlm_available = bool(api_key and len(api_key) > 10 and api_key != "your_gemini_api_key_here")

    if not vlm_available:
        _warn("GEMINI_API_KEY not configured — skipping image captioning")
        _warn("Set GEMINI_API_KEY in backend/.env to enable Stage 3")
        image_chunks = []
    else:
        print(f"  VLM: Gemini API configured ✓")
        print(f"  Max images: {max_pages}")

        t4 = time.perf_counter()
        try:
            image_chunks = await processor._extract_and_caption_images(
                pdf_path, doc_id, max_images=max_pages
            )
        except Exception as e:
            image_chunks = []
            _fail(f"Image captioning error: {e}")

        t5 = time.perf_counter()

        if image_chunks:
            doc.chunks.extend(image_chunks)
            doc.stats["images"] = len(image_chunks)

            for ic in image_chunks:
                caption_preview = ic.content[:120].replace("\n", " ")
                if len(ic.content) > 120:
                    caption_preview += "..."
                _ok(f"Page {ic.page}, Image {ic.metadata.get('image_index', '?')}:")
                _info(f"    \"{caption_preview}\"")
        else:
            _warn("No images captioned (images may be too small or VLM returned empty)")

        results["image_chunks"] = len(image_chunks)
        _section(f"Stage 3 Complete: {len(image_chunks)} image caption(s) in {t5 - t4:.2f}s")

    doc.status = "fully_processed"
    print(f"\n  Final status: {_C.GREEN}{doc.status}{_C.RESET}")
    print(f"  Total chunks: {len(doc.chunks)} "
          f"(text: {results['text_chunks']}, "
          f"tables: {results['table_chunks']}, "
          f"images: {results['image_chunks']})")

    # ═══════════════════════════════════════════════════════════════════════
    # QUERY VERIFICATION: IMAGE QUERIES
    # ═══════════════════════════════════════════════════════════════════════
    _banner("QUERY TEST: IMAGE QUERIES")

    image_queries = [
        "explain the diagram on page 5",
        "what does the figure show?",
        "describe the image in the document",
    ]

    if results["image_chunks"] == 0:
        _warn("No image_caption chunks available — skipping image query tests")
        _warn("(Stage 3 was skipped or produced no captions)")
    else:
        for q in image_queries:
            results["image_query_total"] += 1
            context, status_note, meta = processor.retrieve_context(
                doc_id=doc_id, query=q, session_id=session_id
            )
            source_types = meta.get("source_types_retrieved", [])

            print(f"\n  Query: \"{_C.CYAN}{q}{_C.RESET}\"")
            _info(f"Retrieved {meta.get('retrieved_count', 0)} chunks, "
                  f"source_types: {source_types}")

            if context:
                first_block = context.split("\n\n")[0][:150].replace("\n", " ")
                _info(f"Top match: {first_block}...")

            if "image_caption" in source_types:
                results["image_query_pass"] += 1
                _pass_fail("image_caption chunks retrieved", True)
            else:
                _pass_fail("image_caption chunks retrieved", False)

    # ═══════════════════════════════════════════════════════════════════════
    # QUERY VERIFICATION: TABLE QUERIES
    # ═══════════════════════════════════════════════════════════════════════
    _banner("QUERY TEST: TABLE QUERIES")

    table_queries = [
        "fill the table on page 9",
        "show me the table with alkyl group",
        "what are the values in the table?",
    ]

    if results["table_chunks"] == 0:
        _warn("No table chunks available — skipping table query tests")
    else:
        for q in table_queries:
            results["table_query_total"] += 1
            context, status_note, meta = processor.retrieve_context(
                doc_id=doc_id, query=q, session_id=session_id
            )
            source_types = meta.get("source_types_retrieved", [])

            print(f"\n  Query: \"{_C.CYAN}{q}{_C.RESET}\"")
            _info(f"Retrieved {meta.get('retrieved_count', 0)} chunks, "
                  f"source_types: {source_types}")

            if context:
                # Show first table-type block if any
                blocks = context.split("\n\n")
                table_block = next((b for b in blocks if "table" in b.lower()[:50]), blocks[0])
                for line in table_block.split("\n")[:5]:
                    _info(f"    {line}")

            if "table" in source_types:
                results["table_query_pass"] += 1
                _pass_fail("table chunks retrieved", True)
            else:
                _pass_fail("table chunks retrieved", False)

    # ═══════════════════════════════════════════════════════════════════════
    # FINAL SUMMARY
    # ═══════════════════════════════════════════════════════════════════════
    print(f"\n\n{_C.BOLD}{'=' * 60}{_C.RESET}")
    print(f"{_C.BOLD}  PIPELINE SUMMARY{_C.RESET}")
    print(f"{_C.BOLD}{'=' * 60}{_C.RESET}")
    print(f"  Text chunks:     {results['text_chunks']}")
    print(f"  Table chunks:    {results['table_chunks']}")
    print(f"  Image captions:  {results['image_chunks']}")
    print(f"  Total chunks:    {results['text_chunks'] + results['table_chunks'] + results['image_chunks']}")
    print()

    # Image query results
    if results["image_query_total"] > 0:
        img_pass = results["image_query_pass"] == results["image_query_total"]
        _pass_fail(
            f"Image query test ({results['image_query_pass']}/{results['image_query_total']})",
            img_pass
        )
    else:
        print(f"  Image query test: {_C.YELLOW}⏭ SKIPPED{_C.RESET} (no image captions)")

    # Table query results
    if results["table_query_total"] > 0:
        tbl_pass = results["table_query_pass"] == results["table_query_total"]
        _pass_fail(
            f"Table query test ({results['table_query_pass']}/{results['table_query_total']})",
            tbl_pass
        )
    else:
        print(f"  Table query test: {_C.YELLOW}⏭ SKIPPED{_C.RESET} (no tables)")

    # Overall
    all_passed = (
        (results["image_query_total"] == 0 or results["image_query_pass"] == results["image_query_total"])
        and
        (results["table_query_total"] == 0 or results["table_query_pass"] == results["table_query_total"])
        and
        results["text_chunks"] > 0
    )

    print()
    if all_passed:
        print(f"  {_C.BOLD}{_C.GREEN}Overall: ✅ ALL TESTS PASSED{_C.RESET}")
    else:
        print(f"  {_C.BOLD}{_C.RED}Overall: ❌ SOME TESTS FAILED{_C.RESET}")

    print(f"{_C.BOLD}{'=' * 60}{_C.RESET}\n")

    return all_passed


def main():
    parser = argparse.ArgumentParser(
        description="Terminal Document Processing Pipeline Test Harness"
    )
    parser.add_argument(
        "--pdf",
        default=str(_backend_dir.parent / "TextBook" / "Hsslive-19_Chemistry Eng.pdf"),
        help="Path to PDF file to test (default: TextBook/Hsslive-19_Chemistry Eng.pdf)"
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=8,
        help="Max images to caption via VLM (default: 8)"
    )
    args = parser.parse_args()

    pdf_path = args.pdf
    if not Path(pdf_path).exists():
        print(f"{_C.RED}Error: PDF not found: {pdf_path}{_C.RESET}")
        sys.exit(1)

    print(f"\n{_C.BOLD}DeepTutor Document Processing Pipeline Test{_C.RESET}")
    print(f"{_C.DIM}{'-' * 50}{_C.RESET}")

    success = asyncio.run(run_pipeline_test(pdf_path, max_pages=args.max_pages))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
