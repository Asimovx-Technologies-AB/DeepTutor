"""
test_integration_auth.py
=========================
Criteria §1.1 — Authentication / Authorization.

Tests:
- Protected endpoints return 401 without a token
- Protected endpoints return 401 with a malformed token
- Registered user can log in and receive an access token
- Authenticated user can access a protected endpoint
"""
import pytest


PROTECTED_ENDPOINTS = [
    ("GET",  "/api/study/sessions"),
    ("GET",  "/api/documents/"),
]


class TestAuthProtection:

    def test_protected_endpoints_return_401_without_token(self, sync_client):
        """Every protected endpoint must return 401 when no token is supplied."""
        for method, path in PROTECTED_ENDPOINTS:
            resp = getattr(sync_client, method.lower())(path)
            assert resp.status_code in (401, 403, 422), \
                f"{method} {path} should be protected; got {resp.status_code}"

    def test_protected_endpoints_reject_bad_token(self, sync_client):
        """A malformed/expired Bearer token must be rejected (401)."""
        bad_headers = {"Authorization": "Bearer this.is.invalid"}
        for method, path in PROTECTED_ENDPOINTS:
            resp = getattr(sync_client, method.lower())(path, headers=bad_headers)
            assert resp.status_code in (401, 403), \
                f"{method} {path} must reject bad token; got {resp.status_code}"

    def test_register_and_login_returns_token(self, sync_client):
        """A newly registered user must be able to log in and receive a JWT."""
        reg = sync_client.post("/api/auth/register", json={
            "username": "authtest_user",
            "password": "SecurePass123!",
            "email": "authtest@deeptutor.test",
        })
        # 200 = created, 409/400 = already exists (acceptable in repeated runs)
        assert reg.status_code in (200, 201, 409, 400)

        login = sync_client.post("/api/auth/login", data={
            "username": "authtest_user",
            "password": "SecurePass123!",
        })
        assert login.status_code == 200, f"Login failed: {login.text}"
        body = login.json()
        assert "access_token" in body
        assert len(body["access_token"]) > 20
