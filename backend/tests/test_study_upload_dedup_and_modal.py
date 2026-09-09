"""
test_study_upload_dedup_and_modal.py
====================================
Tests for:
1. Fast-path hash deduplication in /api/study/upload
2. Grouped unique material cards with linked_sessions in GET /api/documents
3. Linking existing material to new study sessions
"""

import uuid
import pytest
import pymupdf
from unittest.mock import patch, AsyncMock
from app.core import database as db
from tests.conftest import get_auth_headers


def _make_valid_pdf_bytes(title: str, text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), f"{title}\n\n{text}")
    data = doc.tobytes()
    doc.close()
    return data


def test_study_upload_dedup_fast_path(sync_client):
    """Uploading the same document twice in different sessions reuses the processed content."""
    run_id = uuid.uuid4().hex[:8]
    headers = get_auth_headers(sync_client, username=f"dedup_user_{run_id}", password="TestPassword123!")

    session_1 = f"study_sess_1_{run_id}"
    session_2 = f"study_sess_2_{run_id}"

    pdf_bytes = _make_valid_pdf_bytes(
        f"Quantum Mechanics {run_id}",
        "Quantum mechanics describes the physical properties of nature at the scale of atoms and subatomic particles.",
    )
    files_1 = {"file": (f"Quantum_Mechanics_{run_id}.pdf", pdf_bytes, "application/pdf")}

    mock_topics = (
        True,
        "Valid academic study material",
        [
            {"id": "t1", "title": "Wave-Particle Duality", "document_name": f"Quantum_Mechanics_{run_id}.pdf"},
            {"id": "t2", "title": "Schrodinger Equation", "document_name": f"Quantum_Mechanics_{run_id}.pdf"},
        ],
    )

    # 1. First upload in session_1 (with mocked topic extractor)
    with patch("app.api.study.extract_topics_and_validate", new=AsyncMock(return_value=mock_topics)):
        resp1 = sync_client.post(
            f"/api/study/upload?subject=Physics&session_id={session_1}",
            files=files_1,
            headers=headers,
        )
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["status"] == "text_ready"
    doc_hash = data1.get("doc_hash")
    assert doc_hash and len(doc_hash) == 64

    # 2. Second upload of the EXACT same PDF in session_2 (should hit fast path without calling topic extractor)
    files_2 = {"file": (f"Quantum_Mechanics_{run_id}.pdf", pdf_bytes, "application/pdf")}
    resp2 = sync_client.post(
        f"/api/study/upload?subject=Physics&session_id={session_2}",
        files=files_2,
        headers=headers,
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["status"] == "text_ready"
    assert data2["reused"] is True
    assert data2["doc_hash"] == doc_hash
    assert data2["session_id"] == session_2

    # 3. Verify GET /api/documents returns EXACTLY 1 unique card for this PDF
    docs_resp = sync_client.get("/api/documents", headers=headers)
    assert docs_resp.status_code == 200
    materials = docs_resp.json()

    matching_cards = [
        m for m in materials
        if m.get("doc_hash") == doc_hash or f"Quantum_Mechanics_{run_id}" in m.get("file_name", "")
    ]
    assert len(matching_cards) == 1, f"Expected 1 unique card, found {len(matching_cards)}"

    card = matching_cards[0]
    assert card["doc_hash"] == doc_hash
    assert "linked_sessions" in card
    linked_ids = [s["id"] for s in card.get("linked_sessions", [])]
    assert session_1 in linked_ids or session_2 in linked_ids
    assert card.get("session_count", 0) >= 1


def test_link_existing_material_to_new_session(sync_client):
    """Test linking an existing document to a third session via /api/documents/link-to-session."""
    run_id = uuid.uuid4().hex[:8]
    headers = get_auth_headers(sync_client, username=f"link_user_{run_id}", password="TestPassword123!")

    session_orig = f"orig_sess_{run_id}"
    session_new = f"new_sess_{run_id}"

    pdf_bytes = _make_valid_pdf_bytes(
        f"Organic Chemistry {run_id}",
        "Organic chemistry is the study of the structure, properties, composition, reactions, and preparation of carbon-containing compounds.",
    )
    files = {"file": (f"Organic_Chem_{run_id}.pdf", pdf_bytes, "application/pdf")}

    mock_topics = (
        True,
        "Valid academic study material",
        [{"id": "t1", "title": "Alkanes and Alkenes", "document_name": f"Organic_Chem_{run_id}.pdf"}],
    )

    # Upload first
    with patch("app.api.study.extract_topics_and_validate", new=AsyncMock(return_value=mock_topics)):
        resp = sync_client.post(
            f"/api/study/upload?subject=Chemistry&session_id={session_orig}",
            files=files,
            headers=headers,
        )
    assert resp.status_code == 200
    doc_hash = resp.json()["doc_hash"]

    # Link to new session
    link_resp = sync_client.post(
        "/api/documents/link-to-session",
        json={
            "session_id": session_new,
            "doc_hash": doc_hash,
            "filename": f"Organic_Chem_{run_id}.pdf",
        },
        headers=headers,
    )
    assert link_resp.status_code == 200
    link_data = link_resp.json()
    assert link_data["ok"] is True
    assert any(
        d.get("doc_hash") == doc_hash or d.get("filename") == f"Organic_Chem_{run_id}.pdf"
        for d in link_data["documents"]
    )
