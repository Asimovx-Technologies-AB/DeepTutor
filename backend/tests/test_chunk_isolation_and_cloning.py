"""
test_chunk_isolation_and_cloning.py
===================================
Validates:
1. Linking a document to a new session makes it immediately searchable via search_bm25 and search_dense.
2. Linking the same document twice does not create duplicate chunks (idempotency check).
3. Fast-dedup upload path results in searchable chunks in the new session.
4. study_plan.py's note generation retrieves non-empty context for a linked document.
"""

import uuid
import pytest
from unittest.mock import patch, AsyncMock
from app.core import database as db
from app.rag.pg_fts_store import pg_fts_store
from tests.conftest import get_auth_headers
import pymupdf


def _make_valid_pdf_bytes(title: str, text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), f"{title}\n\n{text}")
    data = doc.tobytes()
    doc.close()
    return data


def test_link_document_makes_chunks_searchable_bm25_and_dense():
    """Requirement 4.1: Linking a document to a new session makes it searchable via BM25 and dense search."""
    run_id = uuid.uuid4().hex[:8]
    source_session = f"src_sess_{run_id}"
    target_session = f"tgt_sess_{run_id}"
    doc_id = f"doc_{run_id}"

    dim = pg_fts_store.dimensions
    dummy_vec = [0.1] * dim
    # Normalize dummy vector
    norm = sum(x * x for x in dummy_vec) ** 0.5
    normalized_vec = [x / norm for x in dummy_vec]

    chunks = [
        {
            "chunk_id": f"chunk_1_{run_id}",
            "content": f"Supervised learning algorithms optimize loss functions on labeled data {run_id}.",
            "page": 1,
            "source_type": "text",
        },
        {
            "chunk_id": f"chunk_2_{run_id}",
            "content": f"Support Vector Machines find maximal margin hyperplanes {run_id}.",
            "page": 2,
            "source_type": "text",
        },
    ]

    # 1. Index chunks into source session
    indexed = pg_fts_store.index_chunks(
        session_id=source_session,
        doc_id=doc_id,
        chunks=chunks,
        embeddings=[normalized_vec, normalized_vec],
    )
    assert indexed == 2

    # Target session should initially have zero chunks
    assert len(pg_fts_store.get_all_chunks(target_session)) == 0

    # 2. Clone chunks to target session
    cloned = pg_fts_store.clone_document_chunks_to_session(
        target_session_id=target_session,
        source_doc_id=doc_id,
        source_session_id=source_session,
    )
    assert cloned >= 0

    # 3. Verify BM25 search in target session
    bm25_results = pg_fts_store.search_bm25(target_session, "hyperplanes")
    assert len(bm25_results) > 0
    assert any("Support Vector Machines" in r.get("content", "") for r in bm25_results)

    # 4. Verify search_chunks alias in target session
    chunks_results = pg_fts_store.search_chunks(target_session, "supervised")
    assert len(chunks_results) > 0
    assert any("Supervised learning" in r.get("content", "") for r in chunks_results)

    # 5. Verify dense pgvector search in target session
    dense_results = pg_fts_store.search_dense(target_session, normalized_vec, limit=2)
    assert len(dense_results) > 0


def test_linking_idempotency_chunk_count():
    """Requirement 4.2: Linking the same document twice does not create duplicate chunks."""
    run_id = uuid.uuid4().hex[:8]
    source_session = f"idemp_src_{run_id}"
    target_session = f"idemp_tgt_{run_id}"
    doc_id = f"doc_idemp_{run_id}"

    chunks = [
        {
            "chunk_id": f"c1_{run_id}",
            "content": f"Gradient descent minimizes the objective function iteratively {run_id}.",
            "page": 1,
            "source_type": "text",
        },
        {
            "chunk_id": f"c2_{run_id}",
            "content": f"Learning rate determines the step size at each iteration {run_id}.",
            "page": 1,
            "source_type": "text",
        },
    ]

    pg_fts_store.index_chunks(
        session_id=source_session,
        doc_id=doc_id,
        chunks=chunks,
    )

    # First clone
    cloned_1 = pg_fts_store.clone_document_chunks_to_session(
        target_session_id=target_session,
        source_doc_id=doc_id,
        source_session_id=source_session,
    )
    all_chunks_1 = pg_fts_store.get_all_chunks(target_session)
    assert len(all_chunks_1) == 2

    # Second clone of the exact same document/session
    cloned_2 = pg_fts_store.clone_document_chunks_to_session(
        target_session_id=target_session,
        source_doc_id=doc_id,
        source_session_id=source_session,
    )
    # Re-running must not create duplicate chunks in target session
    all_chunks_2 = pg_fts_store.get_all_chunks(target_session)
    assert len(all_chunks_2) == 2, f"Expected 2 chunks, got {len(all_chunks_2)}"


def test_fast_dedup_upload_makes_chunks_searchable(sync_client):
    """Requirement 4.3: Fast-dedup upload path results in searchable chunks in the new session."""
    from unittest.mock import MagicMock
    run_id = uuid.uuid4().hex[:8]
    headers = get_auth_headers(sync_client, username=f"dedup_usr_{run_id}", password="TestPassword123!")

    session_1 = f"dedup_s1_{run_id}"
    session_2 = f"dedup_s2_{run_id}"
    doc_text = (
        f"Thermodynamics principles govern heat, work, and internal energy conversion in physical systems. "
        f"The first law states that energy cannot be created or destroyed, only transformed {run_id}. "
        f"The second law introduces entropy as a measure of irreversible molecular disorder."
    )
    pdf_bytes = _make_valid_pdf_bytes(f"Physics {run_id}", doc_text)

    mock_topics = (
        True,
        "Valid academic study material",
        [{"id": "t1", "title": "Thermodynamics", "document_name": f"Physics_{run_id}.pdf"}],
    )

    with patch("app.api.study.extract_topics_and_validate", new=AsyncMock(return_value=mock_topics)), \
         patch("app.api.study._vlm_sample", new=AsyncMock(return_value="")), \
         patch("app.rag.storage.azure_blob_store.azure_blob_store.upload_file", new=MagicMock()), \
         patch("app.services.study_doc_processor.azure_blob_store.upload_file", new=MagicMock()):
        # First upload
        resp1 = sync_client.post(
            f"/api/study/upload?subject=Physics&session_id={session_1}",
            files={"file": (f"Physics_{run_id}.pdf", pdf_bytes, "application/pdf")},
            headers=headers,
        )
        assert resp1.status_code == 200
        doc_hash = resp1.json()["doc_hash"]

        # Second upload with identical file in session_2 (triggers fast-path deduplication)
        resp2 = sync_client.post(
            f"/api/study/upload?subject=Physics&session_id={session_2}",
            files={"file": (f"Physics_{run_id}.pdf", pdf_bytes, "application/pdf")},
            headers=headers,
        )
        assert resp2.status_code == 200
        assert resp2.json().get("reused") is True

    # Verify session_2 immediately has the searchable chunks
    chunks_s2 = pg_fts_store.get_all_chunks(session_2)
    assert len(chunks_s2) > 0

    search_res = pg_fts_store.search_bm25(session_2, "Thermodynamics")
    assert len(search_res) > 0
    assert any("energy" in r.get("content", "").lower() for r in search_res)


@pytest.mark.asyncio
async def test_study_plan_notes_generation_retrieves_linked_material():
    """Requirement 4.4: study_plan.py's note generation retrieves non-empty context for linked document."""
    from app.api.study_plan import _generate_day_study_notes

    run_id = uuid.uuid4().hex[:8]
    session_id = f"plan_sess_{run_id}"
    doc_id = f"plan_doc_{run_id}"

    unique_fact = f"Photosystem II photolysis yields molecular oxygen and protons {run_id}."
    pg_fts_store.index_chunks(
        session_id=session_id,
        doc_id=doc_id,
        chunks=[
            {
                "chunk_id": f"bio_1_{run_id}",
                "content": unique_fact,
                "page": 1,
                "source_type": "text",
            }
        ],
    )

    captured_prompt = None

    async def mock_chat(messages, **kwargs):
        nonlocal captured_prompt
        captured_prompt = messages[0]["content"]
        return "# Photosynthesis — Study Notes\n\n> **Summary**: Test summary\n\n## Content\nSample notes."

    with patch("app.api.study_plan.llm_client.chat", new=mock_chat):
        notes = await _generate_day_study_notes(
            day_topic="Photolysis",
            key_concepts=["Photosystem II"],
            topic_id=session_id,
        )

    assert notes is not None
    assert captured_prompt is not None
    assert "EXCERPTS FROM UPLOADED MATERIAL:" in captured_prompt
    assert unique_fact in captured_prompt
