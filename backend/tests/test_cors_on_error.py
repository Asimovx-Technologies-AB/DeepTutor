"""
A 500 must still carry CORS headers.

Starlette's ServerErrorMiddleware sits outside every middleware the app
registers, so an unhandled exception used to produce a bare 500 that never
passed back out through CORSMiddleware. In the browser that response has no
Access-Control-Allow-Origin, so a crashing endpoint is reported as a CORS
failure — which is how the dashboard 500s presented, indistinguishable from an
origin that had never been allowed.
"""
import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from app.main import CORSSafeErrorMiddleware

ORIGIN = "https://indie-tutor.com"


@pytest.fixture
def client():
    app = FastAPI()
    # Same order as app.main: registered before CORSMiddleware, so CORS ends up
    # outermost and sees the response this produces.
    app.add_middleware(CORSSafeErrorMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[ORIGIN],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/boom")
    async def boom():
        raise RuntimeError("UndefinedColumn: documents.doc_hash")

    @app.get("/stream")
    async def stream():
        async def gen():
            yield b"chunk"

        return StreamingResponse(gen(), media_type="text/plain")

    return TestClient(app, raise_server_exceptions=False)


def test_unhandled_error_still_returns_cors_header(client):
    r = client.get("/boom", headers={"Origin": ORIGIN})
    assert r.status_code == 500
    # Without this the browser reports a CORS error and the real failure is lost.
    assert r.headers.get("access-control-allow-origin") == ORIGIN


def test_error_body_does_not_leak_the_exception(client):
    r = client.get("/boom", headers={"Origin": ORIGIN})
    assert r.json() == {"detail": "Internal Server Error"}
    assert "UndefinedColumn" not in r.text


def test_disallowed_origin_gets_no_header_on_error(client):
    r = client.get("/boom", headers={"Origin": "https://evil.example"})
    assert r.status_code == 500
    assert r.headers.get("access-control-allow-origin") is None


def test_streaming_responses_pass_through(client):
    r = client.get("/stream", headers={"Origin": ORIGIN})
    assert r.status_code == 200
    assert r.text == "chunk"
    assert r.headers.get("access-control-allow-origin") == ORIGIN
