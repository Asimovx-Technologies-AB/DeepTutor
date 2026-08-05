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
        ("Explain the summary in page number 94 and 95", [94, 95]),
        ("What does pages 94-96 talk about?", [94, 95, 96]),
        ("Summary of page 42", [42]),
        ("Check p. 12, 14 and 15", [12, 14, 15]),
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

    # Cleanup
    vector_store.delete_topic(topic_id)


if __name__ == "__main__":
    test_extract_requested_pages()
    test_vector_store_get_chunks_by_pages()
    print("ALL TESTS PASSED!")
