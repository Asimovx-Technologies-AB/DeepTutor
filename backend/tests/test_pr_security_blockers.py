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


def test_register_or_update_session_with_null_subject():
    """Verify that register_or_update_session handles null and empty subjects without violating NOT NULL constraints."""
    user_test = "user_null_subj_test"
    sid = "session_null_subj_123"

    # 1. Test with subject=None
    res1 = register_or_update_session(session_id=sid, user_id=user_test, subject=None, title="Null Subject Test")
    assert res1 is not None
    assert res1["subject"] == "General Study"

    # 2. Test with subject=""
    res2 = register_or_update_session(session_id=sid, user_id=user_test, subject="", title="Empty Subject Test")
    assert res2 is not None
    assert res2["subject"] == "General Study"

    # 3. Test with subject="   "
    res3 = register_or_update_session(session_id=sid, user_id=user_test, subject="   ", title="Whitespace Subject Test")
    assert res3 is not None
    assert res3["subject"] == "General Study"

    # Cleanup
    delete_registry_session(sid, user_id=user_test)


def test_clean_llm_response_noise_removal():
    """Verify that clean_llm_response sanitizes noisy conversational preambles, wrapper fences, and misplaced math delimiters."""
    from app.rag.llm_client import clean_llm_response

    # Test 1: Preamble and outer markdown wrap
    raw_1 = "```markdown\nCertainly! Here are the study notes:\n# Machine Learning\nThis is the content.\n```"
    cleaned_1 = clean_llm_response(raw_1)
    assert not cleaned_1.startswith("```")
    assert not cleaned_1.endswith("```")
    assert "Certainly" not in cleaned_1
    assert cleaned_1.startswith("# Machine Learning")

    # Test 2: Inline double dollars ($$) to single dollars ($)
    raw_2 = "Formally, given a dataset $$ \\mathcal{D} $$ where $$ x_i $$ represents input and $$ y_i $$ represents output:"
    cleaned_2 = clean_llm_response(raw_2)
    assert "$$ \\mathcal{D} $$" not in cleaned_2
    assert "$\\mathcal{D}$" in cleaned_2
    assert "$x_i$" in cleaned_2
    assert "$y_i$" in cleaned_2

    # Test 3: Display math block preservation
    raw_3 = "The optimal model is:\n$$\nf^* = \\arg\\min L(y, f(x))\n$$\nwhere $L$ is loss."
    cleaned_3 = clean_llm_response(raw_3)
    assert "$$\nf^* = \\arg\\min L(y, f(x))\n$$" in cleaned_3

    # Test 4: Unbulleted paradigm lists
    raw_4 = "\nSupervised Learning: Learn from labeled data.\nUnsupervised Learning: Learn from unlabeled data."
    cleaned_4 = clean_llm_response(raw_4)
    assert "- **Supervised Learning**: Learn from labeled data." in cleaned_4
    assert "- **Unsupervised Learning**: Learn from unlabeled data." in cleaned_4


