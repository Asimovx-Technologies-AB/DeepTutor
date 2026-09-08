"""
FastAPI main application — DeepTutor v2 (4-Stage RAG Pipeline).
"""
import asyncio
import os
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pathlib import Path
from app.core.config import get_settings
from app.api import auth, chat, documents, quiz, flashcards, progress, study_plan, leaderboard, mcp, notes, dashboard, study
from app.api.endpoints import images
from app.services.study_storage import ensure_data_directories, check_and_restore_s3_backups

settings = get_settings()


def _run_migrations_in_background():
    """Apply backend/migrations/*.sql off the startup path."""
    try:
        # backend/ is the image's WORKDIR, but add it explicitly so the runner
        # is importable however the process was launched.
        backend_dir = str(Path(__file__).resolve().parent.parent)
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)
        from migrations.run_migrations import safe_run_migrations
        safe_run_migrations()
    except Exception as e:
        print(f"[MIGRATION] Warning: migration runner unavailable: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema migrations run ALONGSIDE serving, never ahead of it.
    #
    # importing app.core.database has already run Base.metadata.create_all(),
    # which covers the ORM models only. The study/lecture/task-queue tables and
    # the canonical document_chunks shape live in backend/migrations/*.sql, and
    # nothing else in the deployment runs them: the Container App starts the
    # image directly, with no init container or release step.
    #
    # Awaiting them here is what broke every deploy after 775fe08. Gunicorn's
    # master binds :8000 immediately, so the Container Apps readiness probe
    # connects and then waits on GET / for a response no worker can give while
    # it is still blocked in startup. The probe runs every 15s with a
    # 3-failure threshold, so a boot slower than ~45s is killed and back-off
    # looped — "Readiness probe failed: context deadline exceeded ... awaiting
    # headers", then ContainerBackOff, then ActivationFailed, with traffic
    # stranded on the previous revision. On 0.5 vCPU, psycopg2.connect() and
    # pg_advisory_lock() with no timeouts never stood a chance.
    #
    # safe_run_migrations() already swallows and logs its own failures, so
    # nothing here depends on the result.
    app.state.migration_task = asyncio.create_task(
        asyncio.to_thread(_run_migrations_in_background)
    )

    # Startup: create all required directories
    ensure_data_directories()
    check_and_restore_s3_backups()

    dirs = [
        settings.UPLOAD_DIR,
        settings.IMAGE_SEARCH_CACHE_DIR,
    ]
    for dir_path in dirs:
        Path(dir_path).mkdir(parents=True, exist_ok=True)

    llm_model = (
        settings.OPENAI_CHAT_MODEL if settings.LLM_PROVIDER == "openai"
        else settings.AZURE_OPENAI_CHAT_DEPLOYMENT if settings.LLM_PROVIDER == "azure_openai"
        else settings.GEMINI_MODEL
    )
    embed_model = (
        settings.OPENAI_EMBED_MODEL if settings.EMBEDDING_PROVIDER == "openai"
        else settings.AZURE_OPENAI_EMBED_DEPLOYMENT if settings.EMBEDDING_PROVIDER == "azure_openai"
        else settings.GEMINI_EMBED_MODEL
    )
    vlm_provider = getattr(settings, "VLM_PROVIDER", "openai").upper()
    vlm_model = (
        settings.OPENAI_VLM_MODEL if vlm_provider in ("OPENAI", "AZURE_OPENAI")
        else settings.GEMINI_VLM_MODEL
    )
    print(f"[START] {settings.APP_NAME} v{settings.APP_VERSION}")
    print(f"[LLM]   Provider: {settings.LLM_PROVIDER.upper()} | Model: {llm_model}")
    print(f"[VLM]   Provider: {vlm_provider} | Model: {vlm_model}")
    print(f"[EMBED] Provider: {settings.EMBEDDING_PROVIDER.upper()} | Model: {embed_model} ({settings.PGVECTOR_DIMENSIONS}d)")

    # Say plainly at boot whether vision will work. Without this the only
    # symptom of a missing key is documents that silently transcribe to nothing.
    try:
        from app.rag.vlm_client import vlm_client
        if vlm_client.is_configured():
            print(f"[VLM]   Credentials OK — scanned pages and images will be transcribed.")
        else:
            print(
                "[VLM]   WARNING: no usable credentials "
                f"(LLM_PROVIDER={settings.LLM_PROVIDER}). Scanned PDFs and images "
                "will yield no text. Set OPENAI_API_KEY, or AZURE_OPENAI_ENDPOINT "
                "with LLM_PROVIDER=azure_openai."
            )
    except Exception as e:
        print(f"[VLM]   WARNING: could not verify VLM configuration: {e}")

    # Report active parser
    try:
        from app.rag.pipeline.parser import document_parser
        print(f"[PARSER] Primary: {settings.PRIMARY_PARSER.upper()} | Docling: {settings.ENABLE_DOCLING}")
    except Exception:
        pass

    print("[MCP] FastMCP Server & Client Manager initialized")

    # Start durable PostgreSQL task queue worker
    try:
        from app.services.task_queue import task_worker
        await task_worker.start()
        print("[TASK_QUEUE] Background task worker started.")
    except Exception as e:
        print(f"[TASK_QUEUE] Warning: could not start task worker: {e}")

    yield

    # Shutdown
    try:
        from app.services.task_queue import task_worker
        await task_worker.stop()
    except Exception:
        pass

    print("[STOP] Shutting down...")


app = FastAPI(
    title="Deep Tutor API",
    description="AI Tutor — 4-Stage RAG Pipeline: PyMuPDF + FAISS HNSW + LightRAG JSON-KV + Hybrid Search",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# CORS. The deployed environment exports CORS_ALLOWED_ORIGINS (comma-separated)
# so the API can be pinned to the Static Web App origin; an empty value keeps
# the permissive default that local development relies on.
_cors_origins = [o.strip() for o in settings.CORS_ALLOWED_ORIGINS.split(",") if o.strip()] or ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    # Auth travels in the Authorization header, not cookies, so credentials stay
    # off — which is also what lets "*" remain a legal origin list.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers (supports both /api/path and /path)
all_routers = [
    auth.router,
    chat.router,
    documents.router,
    quiz.router,
    flashcards.router,
    progress.router,
    study_plan.router,
    leaderboard.router,
    notes.router,
    dashboard.router,
    study.router,
]
for r in all_routers:
    app.include_router(r, prefix="/api")
    app.include_router(r)

app.include_router(images.router, prefix="/api/images", tags=["Images"])
app.include_router(images.router, prefix="/images", tags=["Images"])

app.include_router(mcp.router)


@app.get("/")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "architecture": "4-Stage RAG Pipeline",
        "docs": "/docs",
    }


@app.get("/health")
@app.get("/api/health")
async def health():
    from app.core.database import get_db_pool_status
    pool_metrics = get_db_pool_status()

    return {
        "api": "ok",
        "version": settings.APP_VERSION,
        # The commit this image was built from, injected by the deploy workflow.
        # Without it the pipeline can only prove that *something* answered, not
        # that the build it just shipped is the one serving.
        "build": os.getenv("GIT_SHA", "unknown"),
        "database": pool_metrics,
        "pipeline": {
            "status": "active",
            "vector_store": settings.VECTOR_STORE_BACKEND,
            "dimensions": settings.PGVECTOR_DIMENSIONS,
        },
    }


@app.get("/api/health/db")
async def health_db():
    """Detailed endpoint for database connection pool monitoring and latency probing."""
    from app.core.database import get_db_pool_status
    return get_db_pool_status()
