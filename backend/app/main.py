"""
FastAPI main application — DeepTutor v2 (4-Stage RAG Pipeline).
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pathlib import Path
from app.core.config import get_settings
from app.api import auth, chat, documents, quiz, flashcards, progress, study_plan, leaderboard, mcp, notes, dashboard, study
from app.api.endpoints import images
from app.services.study_storage import ensure_data_directories, check_and_restore_s3_backups

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
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

    # Report active parser
    try:
        from app.rag.pipeline.parser import document_parser
        print(f"[PARSER] Primary: {settings.PRIMARY_PARSER.upper()} | Docling: {settings.ENABLE_DOCLING}")
    except Exception:
        pass

    print("[MCP] FastMCP Server & Client Manager initialized")
    yield
    print("[STOP] Shutting down...")


app = FastAPI(
    title="Deep Tutor API",
    description="AI Tutor — 4-Stage RAG Pipeline: PyMuPDF + FAISS HNSW + LightRAG JSON-KV + Hybrid Search",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    from app.rag.ollama_client import ollama

    ollama_ok = await ollama.is_available()

    # Database health check
    db_status = "connected"
    db_type = "Neon PostgreSQL (Cloud)" if "postgres" in settings.DATABASE_URL else "SQLite"
    try:
        from app.core.database import DBContext
        from sqlalchemy import text
        with DBContext() as db_session:
            db_session.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"error: {e}"

    return {
        "api": "ok",
        "version": settings.APP_VERSION,
        "llm_online": ollama_ok,
        "database": {
            "status": db_status,
            "type": db_type,
        },
        "pipeline": {
            "status": "active",
            "storage": "sqlite_fts",
        },
    }
