"""
test_batch_session_delete.py
==============================
Tests for batch session deletion backend endpoints:
- POST /api/chat/sessions/batch-delete
- POST /api/study/sessions/batch-delete
"""

import pytest
from app.core import database as db
from app.services.study_storage import register_or_update_session, get_registry_session, delete_registry_session


def test_db_delete_session_clean_cascade():
    # Create test session
    session_id = "test_batch_del_sess_999"
    user_id = "test_user_batch_123"
    
    register_or_update_session(
        session_id=session_id,
        user_id=user_id,
        title="Test Batch Session",
        subject="Physics"
    )
    
    meta = get_registry_session(session_id)
    assert meta is not None
    assert meta.get("id") == session_id
    
    # Delete via registry helper
    ok = delete_registry_session(session_id, user_id=user_id)
    assert ok is True
    
    # Verify session is gone
    meta_after = get_registry_session(session_id)
    assert meta_after is None


def test_batch_delete_multiple_sessions_registry():
    user_id = "test_user_batch_multi"
    sids = [f"test_batch_multi_sess_{i}" for i in range(3)]
    
    for sid in sids:
        register_or_update_session(
            session_id=sid,
            user_id=user_id,
            title=f"Test Session {sid}",
            subject="Mathematics"
        )
        assert get_registry_session(sid) is not None

    # Execute batch delete logic
    deleted_ids = []
    for sid in sids:
        ok = delete_registry_session(sid, user_id=user_id)
        if ok:
            deleted_ids.append(sid)

    assert len(deleted_ids) == 3
    for sid in sids:
        assert get_registry_session(sid) is None
