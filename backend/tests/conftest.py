"""
conftest.py — Shared fixtures for the DeepTutor backend test suite.
"""
import os
import sys
import tempfile
import pytest
import pytest_asyncio
from pathlib import Path

# ── Ensure backend is on the path ──────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# ── Force test-safe environment overrides BEFORE any app import ────────────
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_deep_tutor.db")
os.environ.setdefault("LLM_PROVIDER", "gemini")
os.environ.setdefault("ALLOW_SQLITE_FALLBACK", "true")
os.environ.setdefault("SECRET_KEY", "test-secret-key-do-not-use-in-production")

# ── App imports (after env setup) ─────────────────────────────────────────
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport


@pytest.fixture(scope="session")
def sample_pdf_path(tmp_path_factory) -> Path:
    """Creates a minimal valid .pdf-like text file for upload tests."""
    tmp = tmp_path_factory.mktemp("docs")
    p = tmp / "sample_ml_doc.txt"
    p.write_text(
        "Introduction to Machine Learning\n\n"
        "Machine learning is a branch of artificial intelligence. "
        "Supervised learning uses labelled training data to learn a mapping from inputs to outputs. "
        "Support Vector Machines (SVM) find the optimal hyperplane to separate classes. "
        "Neural networks are composed of layers of neurons that perform linear transformations followed by activations. "
        "Gradient descent minimises the loss function by adjusting model weights. "
        "Overfitting occurs when a model learns noise instead of the underlying pattern. "
        "Regularisation techniques such as L1 and L2 help mitigate overfitting.\n\n"
        "Key Concepts Table:\n"
        "| Algorithm | Type         | Key Strength |\n"
        "|-----------|-------------|---------------|\n"
        "| SVM       | Supervised  | High-dim data |\n"
        "| k-NN      | Supervised  | Simplicity    |\n"
        "| k-Means   | Unsupervised| Clustering    |\n",
        encoding="utf-8",
    )
    return p


@pytest.fixture(scope="session")
def sample_txt_path(tmp_path_factory) -> Path:
    """A plain .txt file for FTS indexing tests."""
    tmp = tmp_path_factory.mktemp("docs")
    p = tmp / "fts_test.txt"
    p.write_text(
        "The mitochondria is the powerhouse of the cell. "
        "ATP synthesis occurs in the inner mitochondrial membrane. "
        "Cellular respiration converts glucose into usable energy.",
        encoding="utf-8",
    )
    return p


@pytest.fixture(scope="session")
def temp_db_path(tmp_path_factory) -> Path:
    """An isolated temporary SQLite path for FTS tests."""
    return tmp_path_factory.mktemp("db") / "test_fts.db"


@pytest.fixture(scope="session")
def app():
    """Create the FastAPI app instance once per test session."""
    from app.main import app as fastapi_app
    return fastapi_app


@pytest.fixture(scope="session")
def sync_client(app):
    """Synchronous TestClient for non-async endpoint tests."""
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest_asyncio.fixture
async def async_client(app):
    """Async HTTPX client for async endpoint tests."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ── Auth helpers ───────────────────────────────────────────────────────────

def get_auth_headers(client: TestClient, username="testuser", password="testpassword") -> dict:
    """Register + login a test user, return Bearer auth headers."""
    email = f"{username}@test.com"
    client.post("/api/auth/register", json={"username": username, "password": password, "email": email})
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    if resp.status_code == 200:
        token = resp.json().get("access_token", "")
        return {"Authorization": f"Bearer {token}"}
    return {}
