"""
Negative unit tests for cross-user deletion authorization and sandbox escapes.
Verifies fixes for the four PR security/correctness blockers.
"""
import pytest
import asyncio
from app.services.study_storage import delete_registry_session, delete_session_document, register_or_update_session, save_session_document
from app.mcp_client import mcp_client_manager, _validate_safe_code


def test_cross_user_session_deletion_fail_closed():
    """Verify that delete_registry_session fails closed when user_id is mismatched, null, or missing."""
    user_a = "user_alpha_123"
    user_b = "user_beta_456"

    # Create session owned by User A
    sid = "session_alpha_123"
    register_or_update_session(session_id=sid, user_id=user_a, subject="Security", title="User A Private Session")

    # Attempt cross-user deletion by User B -> Must return False
    res_b = delete_registry_session(sid, user_id=user_b)
    assert res_b is False

    # Attempt deletion with invalid/non-existent user ID -> Must return False
    res_fake = delete_registry_session(sid, user_id="fake_user_999")
    assert res_fake is False

    # Attempt deletion of non-existent session ID -> Must return False
    res_nonexistent = delete_registry_session("non_existent_session_id_9999", user_id=user_a)
    assert res_nonexistent is False

    # Legitimate deletion by User A -> Must return True
    res_a = delete_registry_session(sid, user_id=user_a)
    assert res_a is True


def test_cross_user_document_chunk_deletion():
    """Verify that chunks and session_documents cannot be purged by an unauthorized user."""
    user_a = "user_owner_789"
    user_attacker = "user_attacker_000"

    sid = "session_docs_789"
    register_or_update_session(session_id=sid, user_id=user_a, subject="Math", title="User A Study Room")

    # Save a document linked to User A
    save_session_document(sid, filename="private_lecture.pdf", doc_hash="hash_secret_123", user_id=user_a)

    # Attacker tries to delete User A's document chunks -> Must return False
    stolen = delete_session_document(sid, "private_lecture.pdf", user_id=user_attacker)
    assert stolen is False

    # Legitimate owner deletes document -> Must return True
    success = delete_session_document(sid, "private_lecture.pdf", user_id=user_a)
    assert success is True

    # Cleanup session
    delete_registry_session(sid, user_id=user_a)


def test_python_sandbox_unapproved_module_escape_blocked():
    """Verify AST validator blocks unapproved modules and dunder introspection."""
    escapes = [
        "import io\nio.open('/tmp/test', 'w')",
        "import sqlite3\nconn = sqlite3.connect(':memory:')",
        "import socket\ns = socket.socket()",
        "import os\nos.system('whoami')",
        "import sys\nprint(sys.path)",
        "import pathlib\np = pathlib.Path('.')",
        "eval('1 + 1')",
        "open('/etc/passwd', 'r')",
        "globals()['__builtins__']",
    ]

    for code in escapes:
        with pytest.raises(ValueError) as exc_info:
            _validate_safe_code(code)
        assert "prohibited" in str(exc_info.value).lower() or "unapproved" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_sympy_code_injection_blocked():
    """Verify math solver rejects code execution attempts and forbidden syntax."""
    malicious_exprs = [
        "__import__('os').system('whoami')",
        "eval('1+1')",
        "open('/etc/passwd')",
        "import(os)",
    ]

    for expr in malicious_exprs:
        res = await mcp_client_manager.execute_tool("solve_math_expression", {"expression": expr})
        assert res["status"] == "error"
        assert "Notice" in res["output"] or "Forbidden" in res["output"] or "Notice" in res["output"]
