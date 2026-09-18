import pytest
import io
import time
from fastapi import HTTPException
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    get_current_user_id,
)
from app.core.rate_limiter import InMemoryRateLimiter
from app.storage.local_storage import LocalObjectStorage
from app.models.user import User
from app.models.session import StudySession
from app.api.auth import register, login, get_current_user
from app.api.study import (
    create_study_session,
    delete_study_session,
    batch_delete_sessions,
    get_student_memory,
    add_student_memory_fact,
    clear_student_memory,
    generate_topic_exam,
)


def test_password_hashing_and_verification():
    """Verify bcrypt password hashing and verification."""
    password = "SuperSecretPassword123!"
    hashed = hash_password(password)

    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_jwt_token_generation_and_validation():
    """Verify JWT token signing, claims verification, and expiration handling."""
    claims = {"sub": "user-test-uuid", "email": "test@deeptutor.org", "role": "student"}
    token = create_access_token(claims)

    decoded = decode_access_token(token)
    assert decoded is not None
    assert decoded["sub"] == "user-test-uuid"
    assert decoded["email"] == "test@deeptutor.org"
    assert "exp" in decoded

    # Tampered token test
    tampered = token[:-4] + "abcd"
    assert decode_access_token(tampered) is None


def test_auth_register_and_login_flow(db_session):
    """Verify end-to-end user registration and login issuing signed JWT tokens."""
    email = f"student_{int(time.time())}@deeptutor.org"
    password = "ValidPassword123"

    # 1. Register new user
    reg_response = register(
        payload={"username": "Alice Learner", "email": email, "password": password},
        db=db_session
    )
    assert "access_token" in reg_response
    assert reg_response["token_type"] == "bearer"
    assert reg_response["user"]["email"] == email
    user_id = reg_response["user"]["id"]

    # 2. Duplicate registration rejected
    with pytest.raises(HTTPException) as exc_info:
        register(
            payload={"username": "Alice Learner", "email": email, "password": password},
            db=db_session
        )
    assert exc_info.value.status_code == 400

    # 3. Login with correct password
    login_response = login(
        payload={"email": email, "password": password},
        db=db_session
    )
    assert "access_token" in login_response
    assert login_response["user"]["id"] == user_id

    # 4. Login with invalid password rejected with 401
    with pytest.raises(HTTPException) as exc_info:
        login(
            payload={"email": email, "password": "WrongPassword123"},
            db=db_session
        )
    assert exc_info.value.status_code == 401


def test_idor_session_deletion_protection(db_session):
    """Verify that users cannot delete sessions belonging to other users (IDOR prevention)."""
    # Create session owned by User A
    sess_a = StudySession(
        id="session-owned-by-user-a",
        title="User A Session",
        user_id="user-a-123",
        status="active"
    )
    db_session.add(sess_a)
    db_session.commit()

    # User B attempts to delete User A's session -> Must be rejected with 403
    with pytest.raises(HTTPException) as exc_info:
        delete_study_session(
            session_id="session-owned-by-user-a",
            current_user_id="user-b-456",
            db=db_session
        )
    assert exc_info.value.status_code == 403

    # User A deletes their own session -> Allowed
    result = delete_study_session(
        session_id="session-owned-by-user-a",
        current_user_id="user-a-123",
        db=db_session
    )
    assert result["status"] == "success"


def test_batch_delete_idor_protection(db_session):
    """Verify batch delete only deletes sessions owned by the authenticated caller."""
    sess_1 = StudySession(id="batch-sess-1", title="Sess 1", user_id="user-x", status="active")
    sess_2 = StudySession(id="batch-sess-2", title="Sess 2", user_id="user-y", status="active")
    db_session.add_all([sess_1, sess_2])
    db_session.commit()

    # User X requests deletion of both Sess 1 and Sess 2
    res = batch_delete_sessions(
        payload={"session_ids": ["batch-sess-1", "batch-sess-2"]},
        current_user_id="user-x",
        db=db_session
    )
    # Only 1 session (user-x's own session) should be deleted
    assert res["deleted_count"] == 1

    # Verify Sess 2 still exists in DB
    remaining = db_session.query(StudySession).filter(StudySession.id == "batch-sess-2").first()
    assert remaining is not None


def test_path_traversal_rejection(tmp_path):
    """Verify that LocalObjectStorage rejects directory traversal attempts."""
    storage = LocalObjectStorage(root_dir=str(tmp_path))

    # Test path escaping storage root
    with pytest.raises(PermissionError):
        storage.retrieve_file("../../sensitive_file.txt")

    with pytest.raises(PermissionError):
        storage.delete_file("../outside_file.txt")

    assert storage.file_exists("../../some_file.txt") is False

    # Normal storage operations should succeed
    stored_path = storage.store_file(b"Safe content", "safe_doc.pdf")
    assert storage.file_exists(stored_path) is True
    assert storage.retrieve_file(stored_path) == b"Safe content"


def test_rate_limiter_enforcement():
    """Verify sliding-window rate limiter blocks requests exceeding threshold."""
    limiter = InMemoryRateLimiter(requests_limit=3, window_seconds=10)
    client_ip = "192.168.1.100"

    # 3 allowed requests
    assert limiter.is_rate_limited(client_ip)[0] is False
    assert limiter.is_rate_limited(client_ip)[0] is False
    assert limiter.is_rate_limited(client_ip)[0] is False

    # 4th request must be rate limited
    is_limited, retry_after = limiter.is_rate_limited(client_ip)
    assert is_limited is True
    assert retry_after > 0


def test_persistent_student_memory(db_session):
    """Verify student memory facts persist across requests and isolate per user."""
    user_id_1 = "student-alpha"
    user_id_2 = "student-beta"

    # Add facts for User 1
    add_student_memory_fact(
        user_id=user_id_1,
        fact_data={"fact": "Prefers visual graph explanations"},
        db=db_session
    )

    # Retrieve memory for User 1
    mem_1 = get_student_memory(user_id=user_id_1, db=db_session)
    assert "Prefers visual graph explanations" in mem_1["facts"]

    # User 2 memory should remain independent and not contain User 1's facts
    mem_2 = get_student_memory(user_id=user_id_2, db=db_session)
    assert "Prefers visual graph explanations" not in mem_2["facts"]

    # Clear memory for User 1
    clear_student_memory(user_id=user_id_1, db=db_session)
    mem_1_cleared = get_student_memory(user_id=user_id_1, db=db_session)
    assert "Prefers visual graph explanations" not in mem_1_cleared["facts"]


@pytest.mark.asyncio
async def test_upload_security_validation(db_session):
    """Verify document upload rejects non-PDFs and fake PDFs without magic bytes."""
    from fastapi.datastructures import UploadFile
    from fastapi import BackgroundTasks
    from app.api.documents import upload_and_process_document
    bg = BackgroundTasks()

    # 1. Non-pdf extension rejected
    bad_ext_file = UploadFile(filename="malicious.exe", file=io.BytesIO(b"binary data"))
    with pytest.raises(HTTPException) as exc_info:
        await upload_and_process_document(background_tasks=bg, file=bad_ext_file, db=db_session)
    assert exc_info.value.status_code == 400

    # 2. PDF extension with spoofed content (missing %PDF- magic bytes) rejected
    fake_pdf = UploadFile(filename="spoofed.pdf", file=io.BytesIO(b"NOT A REAL PDF DOCUMENT CONTENT"))
    with pytest.raises(HTTPException) as exc_info:
        await upload_and_process_document(background_tasks=bg, file=fake_pdf, db=db_session)
    assert exc_info.value.status_code == 400
