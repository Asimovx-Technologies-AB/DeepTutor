"""
test_ownership_and_security.py
==============================
Validates:
1. Unauthenticated calls to protected routes return 401.
2. Path traversal attempts in upload are rejected with 400.
3. User B cannot access, stream, mutate, or delete User A's sessions, chat, or memory (IDOR protection).
4. User A can access and manage their own resources.
"""
import uuid
import pytest
from fastapi.testclient import TestClient


def create_user_and_login(client: TestClient, username_prefix: str):
    uid = uuid.uuid4().hex[:8]
    username = f"{username_prefix}_{uid}"
    email = f"{username}@securitytest.com"
    password = "SecurePassword123!"

    reg = client.post("/api/auth/register", json={
        "username": username,
        "email": email,
        "password": password
    })
    assert reg.status_code in (200, 201)

    login = client.post("/api/auth/login", json={
        "email": email,
        "password": password
    })
    assert login.status_code == 200
    token = login.json()["access_token"]
    user_data = login.json()["user"]
    headers = {"Authorization": f"Bearer {token}"}
    return user_data, token, headers


class TestSecurityAndOwnership:

    def test_unauthenticated_requests_rejected(self, sync_client):
        """Unauthenticated requests must receive 401 Unauthorized."""
        endpoints = [
            ("GET", "/api/chat/sessions"),
            ("GET", "/api/chat/sessions/nonexistent-session"),
            ("GET", "/api/chat/sessions/nonexistent-session/messages"),
            ("POST", "/api/chat/sessions/nonexistent-session/message", {"content": "hello"}),
            ("DELETE", "/api/chat/sessions/nonexistent-session"),
            ("POST", "/api/study/agent/message", {"session_id": "s1", "message": "hello"}),
            ("POST", "/api/study/topic/core-idea", {"session_id": "s1", "topic_id": "t1", "topic_title": "T1"}),
            ("POST", "/api/study/topic/doubt", {"session_id": "s1", "topic_id": "t1", "topic_title": "T1", "question": "q"}),
            ("GET", "/api/study/sessions"),
            ("GET", "/api/study/sessions/s1"),
            ("DELETE", "/api/study/sessions/s1"),
            ("GET", "/api/study/memory/some-user"),
            ("DELETE", "/api/study/memory/some-user"),
        ]
        for item in endpoints:
            method = item[0]
            path = item[1]
            json_body = item[2] if len(item) > 2 else None
            if method == "GET":
                resp = sync_client.get(path)
            elif method == "POST":
                resp = sync_client.post(path, json=json_body or {})
            elif method == "DELETE":
                resp = sync_client.delete(path)
            assert resp.status_code == 401, f"{method} {path} expected 401, got {resp.status_code}"

    def test_path_traversal_in_upload_rejected(self, sync_client):
        """Path traversal attempts with ../ in filename or session_id must be rejected (400)."""
        _, _, headers = create_user_and_login(sync_client, "traversal_user")

        # 1. Traversal via filename
        files = {"file": ("../../evil_file.txt", b"Hello malicious content", "text/plain")}
        resp = sync_client.post(
            "/api/study/upload",
            files=files,
            data={"subject": "Math"},
            headers=headers
        )
        assert resp.status_code == 400, f"Expected 400 for traversal filename, got {resp.status_code}"

        # 2. Traversal via session_id
        files = {"file": ("normal_file.txt", b"Regular academic content", "text/plain")}
        resp = sync_client.post(
            "/api/study/upload",
            files=files,
            data={"subject": "Math", "session_id": "../../../etc/passwd"},
            headers=headers
        )
        assert resp.status_code == 400, f"Expected 400 for traversal session_id, got {resp.status_code}"

    def test_user_b_cannot_access_or_delete_user_a_session(self, sync_client):
        """Integration test proving User B cannot access, read, message, or delete User A's session."""
        user_a, token_a, headers_a = create_user_and_login(sync_client, "student_a")
        user_b, token_b, headers_b = create_user_and_login(sync_client, "student_b")

        # User A creates a chat session
        create_resp = sync_client.post(
            "/api/chat/sessions",
            json={"session_title": "User A Private Study", "topic_id": "calc-101"},
            headers=headers_a
        )
        assert create_resp.status_code in (200, 201)
        session_a_id = create_resp.json()["id"]

        # User A records a message in their session
        from app.core import database as db
        db.add_message(session_a_id, "user", "Private notes about calculus")

        # --- User B attempts to access User A's session (IDOR) ---
        get_resp = sync_client.get(f"/api/chat/sessions/{session_a_id}", headers=headers_b)
        assert get_resp.status_code in (403, 404), f"User B got access: {get_resp.status_code}"

        # User B attempts to read User A's messages
        msgs_resp = sync_client.get(f"/api/chat/sessions/{session_a_id}/messages", headers=headers_b)
        assert msgs_resp.status_code in (403, 404), f"User B read messages: {msgs_resp.status_code}"

        # User B attempts to append a message to User A's session
        inject_resp = sync_client.post(
            f"/api/chat/sessions/{session_a_id}/message",
            json={"content": "Injected malicious message by User B"},
            headers=headers_b
        )
        assert inject_resp.status_code in (403, 404), f"User B injected message: {inject_resp.status_code}"

        # User B attempts to stream message on User A's session with User B's token
        stream_resp = sync_client.get(
            f"/api/chat/sessions/{session_a_id}/message/stream?content=test&token={token_b}"
        )
        assert stream_resp.status_code in (403, 404), f"User B accessed stream: {stream_resp.status_code}"

        # User B attempts to delete User A's session via /chat/sessions
        del_chat_resp = sync_client.delete(f"/api/chat/sessions/{session_a_id}", headers=headers_b)
        assert del_chat_resp.status_code in (403, 404), f"User B deleted chat session: {del_chat_resp.status_code}"

        # User B attempts to delete User A's session via /study/sessions
        del_study_resp = sync_client.delete(f"/api/study/sessions/{session_a_id}", headers=headers_b)
        assert del_study_resp.status_code in (403, 404), f"User B deleted study session: {del_study_resp.status_code}"

        # User B attempts to read/delete User A's episodic memory
        mem_get_resp = sync_client.get(f"/api/study/memory/{user_a['id']}", headers=headers_b)
        assert mem_get_resp.status_code == 403, f"User B accessed memory: {mem_get_resp.status_code}"

        mem_del_resp = sync_client.delete(f"/api/study/memory/{user_a['id']}", headers=headers_b)
        assert mem_del_resp.status_code == 403, f"User B cleared memory: {mem_del_resp.status_code}"

        # Verify User A's session and messages remain intact
        verify_resp = sync_client.get(f"/api/chat/sessions/{session_a_id}", headers=headers_a)
        assert verify_resp.status_code == 200
        assert verify_resp.json()["id"] == session_a_id

        # User A can delete their own session successfully
        del_owner_resp = sync_client.delete(f"/api/chat/sessions/{session_a_id}", headers=headers_a)
        assert del_owner_resp.status_code == 200
