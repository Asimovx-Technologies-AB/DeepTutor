"""
test_unit_fts_store.py
=======================
Criteria §1.3 / §4 — SQLite FTS5 Store (Database Operations & Performance).

Tests:
- Chunks are indexed and retrievable by BM25 search
- Duplicate chunk_ids are upserted (not duplicated)
- Relevant results are returned for matching queries
- Non-matching queries return empty results
- Session isolation: different sessions have independent stores
- FTS5 query sanitizer strips stop-words and produces valid OR tokens
- Search latency is within the <20ms performance target
"""
import time
import pytest
from pathlib import Path


class TestSQLiteFTSStore:

    @pytest.fixture
    def isolated_store(self, temp_db_path):
        """Create a fresh isolated FTS store for each test."""
        from app.rag.sqlite_fts_store import SQLiteFTSStore
        import tempfile, os
        # Each test gets its own temp DB file
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        store = SQLiteFTSStore(db_path=Path(path))
        yield store
        os.unlink(path)

    SAMPLE_CHUNKS = [
        {
            "chunk_id": "chunk_001",
            "doc_id": "doc_ml_001",
            "page": 1,
            "source_type": "text",
            "content": "Supervised learning uses labelled training data to learn a mapping from inputs to outputs.",
        },
        {
            "chunk_id": "chunk_002",
            "doc_id": "doc_ml_001",
            "page": 2,
            "source_type": "text",
            "content": "Support Vector Machines find the optimal hyperplane to maximise the margin between classes.",
        },
        {
            "chunk_id": "chunk_003",
            "doc_id": "doc_ml_001",
            "page": 2,
            "source_type": "table",
            "content": "| Algorithm | Accuracy | Speed |\n| SVM | 94% | Medium |",
        },
    ]

    def test_index_chunks_returns_count(self, isolated_store):
        """index_chunks must return the number of non-empty chunks indexed."""
        n = isolated_store.index_chunks(self.SAMPLE_CHUNKS)
        assert n == 3

    def test_index_empty_list_returns_zero(self, isolated_store):
        """Indexing an empty list must return 0."""
        assert isolated_store.index_chunks([]) == 0

    def test_search_retrieves_relevant_chunk(self, isolated_store):
        """BM25 search must return the most relevant chunk for a specific query."""
        isolated_store.index_chunks(self.SAMPLE_CHUNKS)
        results = isolated_store.search("doc_ml_001", "hyperplane margin SVM")
        contents = [r["content"] for r in results]
        assert any("hyperplane" in c for c in contents), \
            "Expected the SVM chunk to be retrieved for hyperplane query"

    def test_search_empty_on_no_match(self, isolated_store):
        """Query for content that doesn't exist must return empty results."""
        isolated_store.index_chunks(self.SAMPLE_CHUNKS)
        results = isolated_store.search("doc_ml_001", "quantum entanglement")
        assert results == [], "No results expected for unrelated query"

    def test_search_respects_source_type_filter(self, isolated_store):
        """Filtering by source_type=table must only return table chunks."""
        isolated_store.index_chunks(self.SAMPLE_CHUNKS)
        results = isolated_store.search("doc_ml_001", "SVM accuracy", source_type="table")
        for r in results:
            assert r["source_type"] == "table"

    def test_duplicate_chunk_upserted_not_duplicated(self, isolated_store):
        """Re-indexing the same chunk_id must update, not duplicate."""
        isolated_store.index_chunks(self.SAMPLE_CHUNKS)
        # Re-index chunk_001 with updated content
        isolated_store.index_chunks([{
            "chunk_id": "chunk_001",
            "doc_id": "doc_ml_001",
            "page": 1,
            "source_type": "text",
            "content": "UPDATED: Supervised learning is a type of machine learning.",
        }])
        results = isolated_store.search("doc_ml_001", "supervised")
        # There should not be two entries for chunk_001
        ids = [r["chunk_id"] for r in results]
        assert ids.count("chunk_001") <= 1, "Chunk should not be duplicated on re-index"

    def test_session_isolation(self, temp_db_path):
        """Two different sessions must have completely independent stores."""
        from app.rag.sqlite_fts_store import get_session_store
        store_a = get_session_store("session_A")
        store_b = get_session_store("session_B")

        store_a.index_chunks([{
            "chunk_id": "a_chunk",
            "doc_id": "doc_a",
            "page": 1,
            "source_type": "text",
            "content": "Biology cell mitochondria energy ATP synthesis",
        }])

        # session_B should not see session_A's data
        results = store_b.search("doc_a", "mitochondria ATP")
        assert results == [], "Session B must not see Session A's indexed data"

    def test_bm25_search_latency_under_20ms(self, isolated_store):
        """BM25 search must complete in under 20ms (Criteria §4)."""
        isolated_store.index_chunks(self.SAMPLE_CHUNKS)
        start = time.perf_counter()
        isolated_store.search("doc_ml_001", "SVM hyperplane")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 20, f"BM25 search took {elapsed_ms:.1f}ms — target is <20ms"

    def test_fts_query_sanitizer_strips_stopwords(self):
        """_sanitize_fts_query must filter out stop-words and return OR-joined tokens."""
        from app.rag.sqlite_fts_store import SQLiteFTSStore
        result = SQLiteFTSStore._sanitize_fts_query("what is the SVM hyperplane")
        assert '"SVM"' in result or '"svm"' in result.lower()
        assert '"what"' not in result.lower()
        assert '"the"' not in result.lower()
        assert " OR " in result

    def test_fts_query_sanitizer_all_stopwords_returns_original(self):
        """If all words are stop-words, sanitizer must not return empty string."""
        from app.rag.sqlite_fts_store import SQLiteFTSStore
        result = SQLiteFTSStore._sanitize_fts_query("what is the")
        # Should not be empty; falls back to original tokens
        assert result != ""
