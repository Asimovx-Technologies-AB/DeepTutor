"""
test_hashing_and_dedup_audit.py
=================================
Senior AI Engineer test suite to verify:
1. Cryptographic SHA-256 content hashing (strictly 64 hex characters, no 32-char truncation).
2. save_session_document hash resolution (streaming file hash vs passed hash).
3. link_document_to_session metadata propagation (never leaving filename empty).
4. Cross-session document reuse and zero-material bug prevention.
"""

import pytest
import hashlib
import tempfile
import os
from pathlib import Path
from app.core import database as db
from app.rag.document_dedup import get_file_hash, is_already_processed, link_document_to_session
from app.services.study_storage import save_session_document, get_session_documents


def test_sha256_cryptographic_hash_integrity():
    """Verify SHA-256 is strictly 64 hex characters and deterministic."""
    sample = b"%PDF-1.4 Mock PDF Content with Equations and Vectors"
    h1 = get_file_hash(sample)
    h2 = hashlib.sha256(sample).hexdigest()
    
    assert h1 == h2
    assert len(h1) == 64
    assert isinstance(h1, str)


def test_save_session_document_streaming_hash_from_disk():
    """Verify save_session_document computes full 64-char SHA-256 from disk file when hash omitted."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(b"Physical PDF test bytes for hashing audit")
        tmp_path = tmp.name

    try:
        expected_hash = hashlib.sha256(b"Physical PDF test bytes for hashing audit").hexdigest()
        session_id = "test_sess_hash_disk_01"
        
        doc_id = save_session_document(
            session_id=session_id,
            filename="Physical_Doc.pdf",
            file_path=tmp_path,
            status="completed",
            user_id="test_user_hash"
        )
        assert doc_id is not None
        
        docs = get_session_documents(session_id)
        assert len(docs) == 1
        d = docs[0]
        assert d["filename"] == "Physical_Doc.pdf"
        assert d["doc_hash"] == expected_hash
        assert len(d["doc_hash"]) == 64
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_save_session_document_explicit_doc_hash_priority():
    """Verify explicitly provided doc_hash is preserved and not overridden."""
    session_id = "test_sess_hash_explicit_02"
    explicit_hash = "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
    
    save_session_document(
        session_id=session_id,
        filename="Explicit_Doc.pdf",
        file_path="/tmp/fake_explicit.pdf",
        status="completed",
        doc_hash=explicit_hash,
        user_id="test_user_hash"
    )
    
    docs = get_session_documents(session_id)
    assert len(docs) == 1
    assert docs[0]["doc_hash"] == explicit_hash


def test_link_document_to_session_populates_metadata():
    """Verify link_document_to_session populates filename and status from Document table."""
    user_id = "test_user_metadata_link"
    session_id = "test_sess_link_03"
    content = b"Content for testing session link metadata"
    doc_hash = hashlib.sha256(content).hexdigest()
    
    # Register document in Document table first
    db.create_document(
        user_id=user_id,
        topic_id="original_session",
        file_name="Lecture_Notes.pdf",
        file_path="/tmp/lecture_notes.pdf",
        file_type="pdf",
        doc_hash=doc_hash,
        status="completed"
    )
    
    # Link to new session
    linked = db.link_document_to_session(doc_hash, session_id, user_id)
    assert linked is True
    
    # Verify metadata is populated on SessionDocument
    session_docs = db.get_session_documents(session_id, user_id)
    assert len(session_docs) == 1
    sd = session_docs[0]
    assert sd["filename"] == "Lecture_Notes.pdf"
    assert sd["doc_hash"] == doc_hash
    assert sd["status"] == "completed"
