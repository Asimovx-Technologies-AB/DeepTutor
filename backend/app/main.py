"""
FastAPI main application — DeepTutor v2 (4-Stage RAG Pipeline).
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pathlib import Path
from app.core.config import get_settings
from app.api import auth, chat, documents, quiz, flashcards, progress, study_plan, leaderboard, mcp

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create all required directories
    dirs = [
        settings.UPLOAD_DIR,
        settings.FAISS_DATA_DIR,
        settings.LIGHTRAG_DATA_DIR,
        settings.CHROMA_PERSIST_DIR,  # keep for legacy fallback
        settings.GRAPH_DATA_DIR,       # keep for legacy fallback
    ]
    for dir_path in dirs:
        Path(dir_path).mkdir(parents=True, exist_ok=True)

    print(f"[START] {settings.APP_NAME} v{settings.APP_VERSION}")
    print(f"[LLM]   Ollama @ {settings.OLLAMA_BASE_URL} | Chat: {settings.OLLAMA_CHAT_MODEL}")
    print(f"[EMBED] Provider: {settings.EMBEDDING_PROVIDER.upper()} | Model: {settings.OLLAMA_EMBED_MODEL}")
    print(f"[STORE] Vector: {settings.VECTOR_STORE_BACKEND.upper()} @ {settings.FAISS_DATA_DIR}")
    print(f"[STORE] Graph:  {settings.GRAPH_STORE_BACKEND.upper()} @ {settings.LIGHTRAG_DATA_DIR}")
    print(f"[CHUNK] Semantic chunker: {settings.CHUNK_MIN_WORDS}–{settings.CHUNK_MAX_WORDS} words/chunk")

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
        "architecture": "4-Stage RAG Pipeline",
        "docs": "/docs",
    }


@app.get("/api/health")
async def health():
    from app.rag.ollama_client import ollama
    from app.rag.cache import embedding_cache, query_result_cache
    from app.rag.storage import active_vector_store, active_graph_store

    ollama_ok = await ollama.is_available()

    # Vector store stats
    try:
        vs_stats = active_vector_store.cache_stats()
    except Exception:
        vs_stats = {"backend": settings.VECTOR_STORE_BACKEND}

    # Graph store stats
    try:
        gs_stats = {"backend": settings.GRAPH_STORE_BACKEND, "data_dir": settings.LIGHTRAG_DATA_DIR}
    except Exception:
        gs_stats = {"backend": settings.GRAPH_STORE_BACKEND}

    return {
        "api": "ok",
        "version": settings.APP_VERSION,
        "pipeline": {
            "stage1_parser": settings.PRIMARY_PARSER,
            "stage1_chunker": f"semantic_{settings.CHUNK_MIN_WORDS}_{settings.CHUNK_MAX_WORDS}w",
            "stage2_embedder": settings.EMBEDDING_PROVIDER,
            "stage3_vector_store": settings.VECTOR_STORE_BACKEND,
            "stage3_graph_store": settings.GRAPH_STORE_BACKEND,
        },
        "ollama": {
            "status": "connected" if ollama_ok else "disconnected",
            "url": settings.OLLAMA_BASE_URL,
            "chat_model": settings.OLLAMA_CHAT_MODEL,
            "embed_model": settings.OLLAMA_EMBED_MODEL,
        },
        "vector_store": vs_stats,
        "graph_store": gs_stats,
        "cache": {
            "embedding": embedding_cache.stats(),
            "query": query_result_cache.stats(),
        },
    }
