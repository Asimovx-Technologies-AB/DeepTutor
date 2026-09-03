"""
test_document_dedup.py
======================
Unit & Integration tests for content hash-based document deduplication
and multi-session linking in RAG.
"""

import pytest
import hashlib
from app.rag.document_dedup import (
    get_file_hash,
    is_already_processed,
    link_document_to_session,
    handle_upload,
    get_session_documents,
    get_document_status_for_ui,
)
from app.core import database as db


def test_get_file_hash_valid():
    """Hash should match python hashlib sha256 output."""
    sample_content = b"Introduction to Quantum Computing"
    expected = hashlib.sha256(sample_content).hexdigest()
    assert get_file_hash(sample_content) == expected
    assert len(expected) == 64


def test_get_file_hash_empty_raises():
    """Empty payload should raise ValueError."""
    with pytest.raises(ValueError):
        get_file_hash(b"")


def test_dedup_first_upload_and_reuse():
    """First upload processes document, second upload reuses existing embeddings."""
    import uuid
    test_run_id = uuid.uuid4().hex[:8]
    user_id = f"test_user_dedup_{test_run_id}"
    session_a = f"session_alpha_{test_run_id}"
    session_b = f"session_beta_{test_run_id}"
    file_bytes = f"Machine learning and deep neural network notes {test_run_id}".encode("utf-8")
    filename = f"ml_notes_{test_run_id}.txt"

    # 1. First upload in session_a
    called_count = 0
    def mock_processor(doc_record):
        nonlocal called_count
        called_count += 1
        return 12  # 12 chunks created

    res1 = handle_upload(
        file_bytes=file_bytes,
        filename=filename,
        session_id=session_a,
        user_id=user_id,
        file_type="txt",
        process_callback=mock_processor,
    )

    assert res1["status"] == "processed"
    assert res1["chunks_created"] == 12
    assert called_count == 1
    doc_hash = res1["doc_hash"]

    # Verify is_already_processed is now True
    assert is_already_processed(doc_hash, user_id) is True

    # 2. Second upload in session_b with the exact same bytes
    res2 = handle_upload(
        file_bytes=file_bytes,
        filename=filename,
        session_id=session_b,
        user_id=user_id,
        file_type="txt",
        process_callback=mock_processor,
    )

    assert res2["status"] == "already_processed"
    assert res2["chunks_created"] == 0
    # Processor should NOT have been invoked a second time
    assert called_count == 1
    assert res2["doc_hash"] == doc_hash

    # 3. Check session documents
    docs_a = get_session_documents(session_a, user_id)
    assert any(d["doc_hash"] == doc_hash for d in docs_a)

    docs_b = get_session_documents(session_b, user_id)
    assert any(d["doc_hash"] == doc_hash for d in docs_b)

    # 4. Check UI status signals
    ui_stats_a = get_document_status_for_ui(session_a, user_id)
    match_a = next(d for d in ui_stats_a if d["doc_hash"] == doc_hash)
    assert match_a["linked_sessions"] == 2
    assert match_a["status"] == "indexed"


def test_dedup_error_rollback():
    """If the processing callback raises an error, document status is set to failed."""
    import uuid
    uid = uuid.uuid4().hex[:8]
    user_id = f"test_user_dedup_err_{uid}"
    session_id = f"session_fail_{uid}"
    file_bytes = f"Corrupted document payload for testing error state {uid}".encode("utf-8")
    filename = f"corrupted_{uid}.pdf"

    def failing_processor(doc_record):
        raise RuntimeError("PDF parse error: file corrupted")

    res = handle_upload(
        file_bytes=file_bytes,
        filename=filename,
        session_id=session_id,
        user_id=user_id,
        file_type="pdf",
        process_callback=failing_processor,
    )

    assert res["status"] == "error"
    assert "PDF parse error" in res["message"]

    # Verify document is NOT marked as processed
    doc_hash = res["doc_hash"]
    assert is_already_processed(doc_hash, user_id) is False

    doc_in_db = db.get_document_by_hash(doc_hash, user_id)
    assert doc_in_db["status"] == "failed"


def test_upload_endpoint_dedup_integration(sync_client):
    """Test POST /api/documents/upload deduplication and UI status endpoints."""
    import uuid
    from tests.conftest import get_auth_headers
    run_id = uuid.uuid4().hex[:8]
    headers = get_auth_headers(sync_client, username=f"user_{run_id}", password="secretpassword123")
    
    file_content = f"%PDF-1.4 Mock PDF Content For Deduplication Integration Test {run_id}".encode("utf-8")
    files = {"file": (f"Calculus_Notes_{run_id}.pdf", file_content, "application/pdf")}
    
    # 1. First upload in session_1
    resp1 = sync_client.post(
        "/api/documents/upload",
        files=files,
        data={"section_id": f"math_session_1_{run_id}", "topic_id": f"math_session_1_{run_id}"},
        headers=headers,
    )
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["status"] in ("processed", "indexing")
    doc_hash = data1["doc_hash"]
    doc_id = data1["id"]

    # Mark document indexed/completed in db to simulate indexing finish
    db.update_document_stats(doc_id=doc_id, indexed=True, entity_count=5, chunk_count=10, status="completed")

    # 2. Second upload of the EXACT same file in session_2
    files2 = {"file": (f"Calculus_Notes_{run_id}.pdf", file_content, "application/pdf")}
    resp2 = sync_client.post(
        "/api/documents/upload",
        files=files2,
        data={"section_id": f"math_session_2_{run_id}", "topic_id": f"math_session_2_{run_id}"},
        headers=headers,
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["status"] == "already_processed"
    assert data2["doc_hash"] == doc_hash
    assert data2["chunks_created"] == 0

    # 3. Check UI status endpoint
    status_resp = sync_client.get(f"/api/documents/session/math_session_1_{run_id}/status", headers=headers)
    assert status_resp.status_code == 200
    stats = status_resp.json()
    assert any(s["doc_hash"] == doc_hash and s["linked_sessions"] >= 2 for s in stats)
