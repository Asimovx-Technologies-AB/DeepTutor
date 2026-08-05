"""
FastAPI main application.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os
from pathlib import Path
from app.core.config import get_settings
from app.api import auth, chat, documents, quiz, flashcards, progress, study_plan

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create required directories
    for dir_path in [settings.UPLOAD_DIR, settings.CHROMA_PERSIST_DIR, settings.GRAPH_DATA_DIR]:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
    print(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} started")
    print(f"📡 Ollama: {settings.OLLAMA_BASE_URL} | Model: {settings.OLLAMA_CHAT_MODEL}")
    print(f"🧠 GraphRAG: ChromaDB @ {settings.CHROMA_PERSIST_DIR} | Graph @ {settings.GRAPH_DATA_DIR}")
    yield
    print("👋 Shutting down...")


app = FastAPI(
    title="Deep Tutor API",
    description="AI Tutor backend with GraphRAG + Local LLM",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "*"],
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
    ollama_ok = await ollama.is_available()
    return {
        "api": "ok",
        "ollama": "connected" if ollama_ok else "disconnected",
        "ollama_url": settings.OLLAMA_BASE_URL,
        "model": settings.OLLAMA_CHAT_MODEL,
    }
