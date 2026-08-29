from types import SimpleNamespace

import pytest

from app.rag.storage.pgvector_store import PgVectorStore, _rrf


class _UnusedEngine:
    """Constructor dependency for unit tests that never touch PostgreSQL."""


def _store(dimensions: int = 3) -> PgVectorStore:
    return PgVectorStore(dimensions=dimensions, engine=_UnusedEngine())


def test_embedding_dimension_must_match_exactly():
    store = _store(3)

    assert store._validate_embedding([0.1, 0.2, 0.3]) == [0.1, 0.2, 0.3]
    with pytest.raises(ValueError, match="expects 3"):
        store._validate_embedding([0.1, 0.2])


def test_hnsw_rejects_unsupported_vector_dimensions():
    with pytest.raises(ValueError, match="between 1 and 2000"):
        _store(3072)


def test_chunk_ids_are_deterministic():
    first = PgVectorStore._chunk_id("math-10", 2, "Pythagoras")
    second = PgVectorStore._chunk_id("math-10", 2, "Pythagoras")

    assert first == second
    assert first.startswith("math-10_2_")


def test_weighted_rrf_rewards_results_present_in_both_lists():
    fused = _rrf(
        dense=[("dense-only", 0.99), ("shared", 0.8)],
        sparse=[("shared", 1.0), ("sparse-only", 0.7)],
        dw=0.7,
        sw=0.3,
    )

    assert fused[0][0] == "shared"


def test_row_mapping_preserves_parent_child_contract():
    row = SimpleNamespace(
        id="chunk-1",
        chunk_text="child",
        metadata={"parent_text": "parent", "page": 4},
    )

    result = PgVectorStore._row_to_chunk(row, 0.87654)

    assert result == {
        "id": "chunk-1",
        "text": "parent",
        "child_text": "child",
        "metadata": {"parent_text": "parent", "page": 4},
        "score": 0.8765,
    }
