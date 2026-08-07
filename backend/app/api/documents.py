"""
Documents API — file upload + async GraphRAG indexing.
Each user gets their own isolated ChromaDB collection and knowledge graph,
namespaced as: {user_id}_{topic_id}
"""
import os
import asyncio
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends, BackgroundTasks
from app.api.auth import get_current_user
from app.core import database as db
from app.core.config import get_settings
from app.rag.graph_rag import graph_rag
from app.rag.graph_store import graph_store
from app.rag.section_scope import get_section_collection_id

settings = get_settings()
router = APIRouter(prefix="/documents", tags=["documents"])

# Track indexing progress
_indexing_status: dict = {}  # doc_id → {status, progress, stats}


def _user_section_collection_id(user_id: str, section_id: str) -> str:
    """Build the consistent per-user section collection id for ChromaDB + graph store."""
    return get_section_collection_id(user_id, section_id)


async def _run_indexing(doc_id: str, section_id: str, file_path: str, user_id: str):
    """Background task: run GraphRAG indexing and update status."""
    _indexing_status[doc_id] = {"status": "indexing", "progress": 0, "stats": {}}

    async def progress_cb(stage: str, pct: int):
        _indexing_status[doc_id]["progress"] = pct
        _indexing_status[doc_id]["stage"] = stage

    # Use user-section-scoped collection so each user's uploaded section is isolated
    namespaced_topic = _user_section_collection_id(user_id, section_id)

    try:
        stats = await graph_rag.index_document(namespaced_topic, file_path, progress_callback=progress_cb)
        _indexing_status[doc_id] = {"status": "done", "progress": 100, "stats": stats}
        db.update_document_stats(
            doc_id=doc_id,
            indexed=True,
            entity_count=stats.get("entities_extracted", 0),
            chunk_count=stats.get("chunks_indexed", 0),
        )
    except Exception as e:
        _indexing_status[doc_id] = {"status": "error", "progress": 0, "error": str(e), "stats": {}}


@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    section_id: Optional[str] = Form(None),
    topic_id: str = Form("general"),
    user: dict = Depends(get_current_user),
):
    # Validate file type
    allowed_exts = {".pdf", ".txt", ".md"}
    ext = Path(file.filename).suffix.lower()
    if ext not in allowed_exts:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(allowed_exts)}"
        )

    # Check file size
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > settings.MAX_UPLOAD_SIZE_MB:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({size_mb:.1f}MB). Max: {settings.MAX_UPLOAD_SIZE_MB}MB"
        )

    # Choose the section label for this upload.
    section_id = (section_id or topic_id or "general").strip() or "general"

    # Save to disk under user-specific section directory
    upload_dir = Path(settings.UPLOAD_DIR) / user["id"] / section_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = str(upload_dir / file.filename)
    with open(file_path, "wb") as f:
        f.write(content)

    # Register in DB using the section identifier as the document topic/section key
    doc = db.create_document(
        user_id=user["id"],
        topic_id=section_id,
        file_name=file.filename,
        file_path=file_path,
        file_type=ext.lstrip("."),
    )

    # Clear any stale flashcards for this same section so generated cards stay aligned with the latest PDF.
    db.delete_flashcards_for_topic(section_id)

    # Start background indexing — pass user_id and section id for per-user section namespacing
    background_tasks.add_task(_run_indexing, doc["id"], section_id, file_path, user["id"])

    return {
        "id": doc["id"],
        "file_name": file.filename,
        "file_type": ext.lstrip("."),
        "size_mb": round(size_mb, 2),
        "topic_id": topic_id,
        "status": "indexing",
        "message": f"✅ {file.filename} uploaded. GraphRAG indexing started in background.",
    }


@router.get("/topic/{topic_id}")
async def list_documents(topic_id: str, user: dict = Depends(get_current_user)):
    # Only return documents belonging to the current user
    docs = [d for d in db.get_documents_for_topic(topic_id) if d["user_id"] == user["id"]]
    for doc in docs:
        status = _indexing_status.get(doc["id"], {})
        doc["index_status"] = status.get("status", "pending")
        doc["index_progress"] = status.get("progress", 0)
        doc["index_stats"] = status.get("stats", {})
    return docs


@router.get("/{doc_id}/status")
async def indexing_status(doc_id: str, user: dict = Depends(get_current_user)):
    """Poll indexing progress for a document."""
    status = _indexing_status.get(doc_id, {"status": "pending", "progress": 0})
    return status


@router.get("/topic/{topic_id}/graph")
async def get_knowledge_graph(topic_id: str, user: dict = Depends(get_current_user)):
    """Return full knowledge graph for visualization — scoped to the current user section."""
    namespaced_topic = _user_section_collection_id(user["id"], topic_id)
    graph = graph_store.get_full_graph(namespaced_topic)
    stats = graph_store.get_graph_stats(namespaced_topic)
    return {"topic_id": topic_id, "stats": stats, "graph": graph}
