"""
Automated Document Coverage & Accuracy Test Suite for DeepTutor.

Evaluates:
  1. Full Document Page Coverage (%) — checks if early, middle, and late pages are indexed & retrievable.
  2. Multi-Topic Recall — tests retrieval precision across distinct PDF sections.
  3. Grounding Accuracy Score — runs Self-RAG verification across generated responses.
"""
import os
import sys
import asyncio
from pathlib import Path

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent))

from app.core.config import get_settings
from app.rag.document_processor import process_pdf
from app.rag.vector_store import vector_store
from app.rag.ollama_client import ollama
from app.rag.graph_rag import graph_rag
from app.rag.hallucination_guard import verify_response_grounding

settings = get_settings()


async def run_coverage_benchmark(pdf_path: str = None):
    print("=" * 70)
    print("DEEPTUTOR AUTOMATED DOCUMENT COVERAGE & ACCURACY BENCHMARK")
    print("=" * 70)

    # 1. Locate test PDF
    if len(sys.argv) > 1 and sys.argv[1]:
        pdf_path = sys.argv[1]

    if not pdf_path or not os.path.exists(pdf_path):
        uploads_dir = Path("./uploads")
        pdfs = list(uploads_dir.glob("*.pdf"))
        if not pdfs:
            print("[!] No test PDF found in ./uploads directory.")
            print("    Please upload a PDF via the web app or pass a file path.")
            return
        pdf_path = str(pdfs[0])

    pdf_file = Path(pdf_path)
    print(f"[+] Testing Document: {pdf_file.name}")
    print("-" * 70)

    # 2. Parse PDF and extract page statistics
    all_chunks = process_pdf(pdf_path)
    if not all_chunks:
        print("[!] Could not extract text from document.")
        return

    pages_list = [c.get("metadata", {}).get("page", 1) for c in all_chunks]
    total_pages = max(pages_list) if pages_list else 1
    total_chars = sum(len(c.get("text", "")) for c in all_chunks)
    print(f"[*] Document Stats: {total_pages} Pages | {len(all_chunks)} Chunks | Total {total_chars:,} Characters")

    # Identify sample page targets: Early (Page 1), Middle (Page N/2), Late (Page N)
    p_early = 1
    p_mid = max(1, total_pages // 2)
    p_late = total_pages

    topic_id = f"test_{pdf_file.stem}"

    # Save to vector store
    if all_chunks:
        sample_embed = await ollama.embed("test")
        vector_store.delete_collection(topic_id)
        
        # Batch embed
        texts = [c["text"] for c in all_chunks]
        embeddings = await ollama.embed_batch(texts)
        
        vector_store.add_chunks(
            topic_id=topic_id,
            chunks=all_chunks,
            embeddings=embeddings,
        )
        print("[OK] Vector Index Created & Populated in ChromaDB")

    # 3. Test Cases
    test_cases = [
        {
            "name": f"Early Document Test (Page {p_early})",
            "target_page": p_early,
            "query": f"What concepts are discussed on page {p_early} of the document?",
        },
        {
            "name": f"Middle Section Test (Page {p_mid})",
            "target_page": p_mid,
            "query": f"Summarize the main points on page {p_mid}.",
        },
        {
            "name": f"Late Section Test (Page {p_late})",
            "target_page": p_late,
            "query": f"What is explained on page {p_late} near the end of the document?",
        },
        {
            "name": "Broad Full-Document Overview Test",
            "target_page": None,
            "query": f"Provide a comprehensive summary of {pdf_file.stem} covering all key chapters.",
        },
    ]

    print("\n" + "=" * 70)
    print("EXECUTING MULTI-SECTION COVERAGE TEST SUITE")
    print("=" * 70)

    results = []

    for tc in test_cases:
        print(f"\n[*] Executing Test: {tc['name']}")
        print(f"   Query: '{tc['query']}'")

        # Stream query response
        full_response = ""
        retrieved_sources = []
        
        async for event_str in graph_rag.query_stream(topic_id, tc['query'], []):
            if not event_str.startswith("data: "):
                continue
            import json
            try:
                evt = json.loads(event_str[6:])
                if evt["type"] == "token":
                    full_response += evt["data"]
                elif evt["type"] == "sources":
                    retrieved_sources = evt["data"]
            except Exception:
                pass

        # Check page coverage
        retrieved_pages = [s.get("page") for s in retrieved_sources if s.get("page")]
        
        if tc["target_page"] is not None:
            page_matched = tc["target_page"] in retrieved_pages
            page_status = "PASS" if page_matched else "PAGE MISSING"
        else:
            # Broad query should retrieve chunks from multiple distinct pages
            unique_pages = set(retrieved_pages)
            page_matched = len(unique_pages) >= min(3, total_pages)
            page_status = f"PASS ({len(unique_pages)} pages)" if page_matched else f"LIMITED COVERAGE ({len(unique_pages)} pages)"

        # Verify Self-RAG Grounding Score
        grounding = verify_response_grounding(full_response, retrieved_sources)
        g_score = grounding.get("grounding_score", 1.0)

        results.append({
            "name": tc["name"],
            "page_status": page_status,
            "grounding_score": f"{int(g_score * 100)}%",
            "retrieved_pages": sorted(list(set(retrieved_pages))),
            "response_snippet": full_response[:150].strip() + "...",
        })

        print(f"   Status: {page_status}")
        print(f"   Retrieved Pages: {sorted(list(set(retrieved_pages)))}")
        print(f"   Grounding Accuracy: {int(g_score * 100)}%")

    # 4. Generate Final Matrix Summary Table
    print("\n" + "=" * 70)
    print("FINAL DOCUMENT COVERAGE & ACCURACY BENCHMARK REPORT")
    print("=" * 70)
    print(f"{'Test Case':<35} | {'Page Coverage':<22} | {'Grounding %':<12}")
    print("-" * 75)

    passed_count = 0
    for r in results:
        print(f"{r['name']:<35} | {r['page_status']:<22} | {r['grounding_score']:<12}")
        if "PASS" in r["page_status"]:
            passed_count += 1

    total_tests = len(results)
    coverage_rate = int((passed_count / total_tests) * 100)

    print("-" * 75)
    print(f"Overall Document Coverage Rate: {coverage_rate}% ({passed_count}/{total_tests} Tests Passed)")
    print("=" * 70)

    # Cleanup test collection
    vector_store.delete_collection(topic_id)


if __name__ == "__main__":
    asyncio.run(run_coverage_benchmark())
