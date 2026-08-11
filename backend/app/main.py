"""
FastAPI main application.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os
from pathlib import Path
from app.core.config import get_settings
from app.api import auth, chat, documents, quiz, flashcards, progress, study_plan, leaderboard, mcp

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create required directories
    for dir_path in [settings.UPLOAD_DIR, settings.CHROMA_PERSIST_DIR, settings.GRAPH_DATA_DIR]:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
    print(f"[START] {settings.APP_NAME} v{settings.APP_VERSION} started")
    print(f"[OLLAMA] Base URL: {settings.OLLAMA_BASE_URL} | Model: {settings.OLLAMA_CHAT_MODEL}")
    print(f"[GRAPHRAG] ChromaDB @ {settings.CHROMA_PERSIST_DIR} | Graph @ {settings.GRAPH_DATA_DIR}")
    # Backend reloaded with explicit CUDA Device 0 binding for Docling & Ollama (100% GPU)
    try:
        from app.rag.document_processor import get_parser_info
        info = get_parser_info()
        primary = info.get("primary", "pdfplumber").upper()
        ocr = info.get("ocr_enabled", False)
        version = info.get("docling_version") or ""
        print(f"[PARSER] Primary={primary} {version} | OCR={ocr} | Chunking={info.get('chunking_strategy')}")
    except Exception:
        pass
    print(f"[MCP] FastMCP Server & Client Manager initialized")
    yield
    print("[STOP] Shutting down...")


app = FastAPI(
    title="Deep Tutor API",
    description="AI Tutor backend with GraphRAG + Local LLM + MCP",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(quiz.router, prefix="/api")
app.include_router(flashcards.router, prefix="/api")
app.include_router(progress.router, prefix="/api")
app.include_router(study_plan.router, prefix="/api")
app.include_router(leaderboard.router, prefix="/api")
app.include_router(mcp.router)


@app.get("/")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs",
    }


@app.get("/api/health")
async def health():
    from app.rag.ollama_client import ollama
    from app.rag.document_processor import get_parser_info
    from app.rag.cache import embedding_cache, query_result_cache
    ollama_ok = await ollama.is_available()
    parser_info = get_parser_info()
    return {
        "api": "ok",
        "ollama": "connected" if ollama_ok else "disconnected",
        "ollama_url": settings.OLLAMA_BASE_URL,
        "model": settings.OLLAMA_CHAT_MODEL,
        "parser": parser_info,
        "cache": {
            "embedding": embedding_cache.stats(),
            "query": query_result_cache.stats(),
        },
    }
