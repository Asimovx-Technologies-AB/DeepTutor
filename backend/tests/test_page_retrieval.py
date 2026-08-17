import sys
from pathlib import Path

# Add backend to sys.path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.rag.graph_rag import extract_requested_pages
from app.rag.vector_store import vector_store


def test_extract_requested_pages():
    # Test cases
    cases = [
        ("explain page number 33", [33]),
        ("explain page 33", [33]),
        ("what is on page 33?", [33]),
        ("summarize page 33", [33]),
        ("page 33", [33]),
        ("page no 33", [33]),
        ("page no. 33", [33]),
        ("page #33", [33]),
        ("pg 33", [33]),
        ("pg. 33", [33]),
        ("p. 33", [33]),
        ("p33", [33]),
        ("Explain the summary in page number 94 and 95", [94, 95]),
        ("What does pages 94-96 talk about?", [94, 95, 96]),
        ("Summary of page 42", [42]),
        ("Check p. 12, 14 and 15", [12, 14, 15]),
        ("33rd page summary", [33]),
        ("Explain general quantum computing", []),
    ]

    for text, expected in cases:
        result = extract_requested_pages(text)
        assert result == expected, f"Failed for '{text}': expected {expected}, got {result}"
        print(f"[OK] Extracted successfully for '{text}': {result}")


def test_vector_store_get_chunks_by_pages():
    # Add dummy chunks
    topic_id = "test_page_filtering"
    dummy_chunks = [
        {"text": "Content of page 94", "metadata": {"source": "test.pdf", "page": 94}},
        {"text": "Content of page 95", "metadata": {"source": "test.pdf", "page": 95}},
        {"text": "Content of page 10", "metadata": {"source": "test.pdf", "page": 10}},
    ]
    dummy_embeddings = [[0.1] * 384 for _ in range(3)]
    
    vector_store.add_chunks(topic_id, dummy_chunks, dummy_embeddings)

    retrieved = vector_store.get_chunks_by_pages(topic_id, [94, 95])
    pages = [c["metadata"]["page"] for c in retrieved]
    assert set(pages) == {94, 95}, f"Expected pages [94, 95], got {pages}"
    print("[OK] Vector store get_chunks_by_pages verified successfully!")

def test_faiss_store_get_chunks_by_pages():
    from app.rag.storage.faiss_store import FAISSVectorStore
    store = FAISSVectorStore()
    topic_id = "test_page_filtering_faiss"
    dummy_chunks = [
        {"text": "Content of page 33 discussing SVM", "metadata": {"source": "ml.pdf", "page": 33}},
        {"text": "Content of page 34 discussing Kernels", "metadata": {"source": "ml.pdf", "page": 34}},
    ]
    dummy_embeddings = [[0.05] * 384 for _ in range(2)]

    store.add_chunks(topic_id, dummy_chunks, dummy_embeddings)

    retrieved = store.get_chunks_by_pages(topic_id, [33])
    assert len(retrieved) == 1, f"Expected 1 chunk for page 33, got {len(retrieved)}"
    assert retrieved[0]["metadata"]["page"] == 33
    print("[OK] FAISS store get_chunks_by_pages verified successfully!")

    # Cleanup
    store.delete_topic(topic_id)


def test_confidence_scorer_page_query():
    from app.rag.query_engine import ConfidenceScorer
    scorer = ConfidenceScorer()
    chunks = [
        {"text": "Linear regression minimizes sum of squared residuals.", "metadata": {"source": "ml.pdf", "page": 33}, "score": 1.0}
    ]
    score, label = scorer.score(chunks=chunks, graph_entities=[], query="explain page number 33")
    assert label == "high", f"Expected 'high' confidence for page query, got {label} (score: {score})"
    assert score == 1.0
    print("[OK] ConfidenceScorer page query score verified successfully!")


if __name__ == "__main__":
    test_extract_requested_pages()
    test_vector_store_get_chunks_by_pages()
    test_faiss_store_get_chunks_by_pages()
    test_confidence_scorer_page_query()
    print("ALL TESTS PASSED!")
