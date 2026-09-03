"""
Documents API — file upload + SQLite FTS indexing + Topic Extraction.
"""
import os
import asyncio
import json
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends, BackgroundTasks
from pydantic import BaseModel
from app.api.auth import get_current_user
from app.core import database as db
from app.core.config import get_settings
from app.rag.doc_processor import doc_processor
from app.rag.topic_extractor import topic_extractor
from app.rag.ollama_client import ollama
from app.rag.sqlite_fts_store import get_session_store
from app.rag.document_dedup import get_file_hash, is_already_processed, link_document_to_session

settings = get_settings()
router = APIRouter(prefix="/documents", tags=["documents"])

_indexing_status: dict = {}
_concept_cache: dict = {}


class ConceptExplainRequest(BaseModel):
    concept: str
    topic_id: Optional[str] = "general"


@router.get("")
async def list_user_documents(
    topic_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    docs = (
        db.get_documents_for_user_and_topic(user["id"], topic_id)
        if topic_id
        else db.get_documents_for_user(user["id"])
    )
    for doc in docs:
        topics = doc.get("key_topics") or []
        subject_marker = next((topic for topic in topics if str(topic).startswith("__subject__:")), "")
        doc["detected_subject"] = subject_marker.removeprefix("__subject__:").strip()
        doc["key_topics"] = [topic for topic in topics if not str(topic).startswith("__subject__:")]
        status = _indexing_status.get(doc["id"])
        doc["index_status"] = status.get("status") if status else ("done" if doc.get("indexed") else "pending")
        doc["index_progress"] = status.get("progress", 0) if status else (100 if doc.get("indexed") else 0)
        doc["index_stats"] = status.get("stats", {}) if status else {}
    return docs


async def _run_indexing(doc_id: str, section_id: str, file_path: str, user_id: str, file_name: str):
    _indexing_status[doc_id] = {"status": "indexing", "progress": 20, "stats": {}}
    try:
        # Ingest into SQLite FTS store
        doc_record = await doc_processor.ingest_document(
            file_path=file_path,
            doc_id=doc_id,
            file_name=file_name,
            subject=section_id,
            session_id=section_id,
        )
        _indexing_status[doc_id]["progress"] = 60

        # Extract topics
        extracted = await topic_extractor.extract_topics(file_path=file_path, subject=section_id)
        raw_topics = extracted.get("topics", [])
        topic_titles = [t.get("title", "") for t in raw_topics if t.get("title")]

        detected_subject = extracted.get("title") or section_id or "General Studies"

        stats = {
            "chunks_indexed": len(doc_record.chunks) if doc_record else 0,
            "entities_extracted": len(topic_titles),
            "detected_subject": detected_subject,
        }
        _indexing_status[doc_id] = {"status": "done", "progress": 100, "stats": stats}

        db.update_document_stats(
            doc_id=doc_id,
            indexed=True,
            entity_count=len(topic_titles),
            chunk_count=len(doc_record.chunks) if doc_record else 0,
            key_topics=[f"__subject__:{detected_subject}", *topic_titles],
            status="completed",
        )

        # Dispatch Background Path: Stage 2 (Table) & Stage 3 (Image/VLM) Enrichment
        asyncio.create_task(doc_processor.run_background_enrichment(doc_id))
    except Exception as e:
        print(f"[documents] Indexing error for {doc_id}: {e}")
        _indexing_status[doc_id] = {"status": "error", "progress": 0, "error": str(e), "stats": {}}
        db.update_document_stats(
            doc_id=doc_id,
            indexed=False,
            entity_count=0,
            chunk_count=0,
            status="failed",
            error_message=str(e),
        )


@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    section_id: Optional[str] = Form(None),
    topic_id: str = Form("general"),
    user: dict = Depends(get_current_user),
):
    allowed_exts = {
        ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif",
        ".docx", ".doc", ".csv", ".xlsx", ".xls", ".pptx", ".ppt",
        ".html", ".htm", ".json", ".txt", ".md", ".rst", ".log", ".py", ".js", ".ts"
    }
    ext = Path(file.filename).suffix.lower()
    if ext not in allowed_exts:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(list(allowed_exts)))}"
        )

    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    section_id = (section_id or topic_id or "general").strip() or "general"

    # Fast Content Hash Deduplication
    doc_hash = get_file_hash(content)
    if is_already_processed(doc_hash, user["id"], db=db):
        link_document_to_session(doc_hash, section_id, user["id"], db=db)
        existing_doc = db.get_document_by_hash(doc_hash, user["id"])
        return {
            "status": "already_processed",
            "id": existing_doc.get("id") if existing_doc else None,
            "doc_hash": doc_hash,
            "file_name": file.filename,
            "filename": file.filename,
            "file_type": ext.lstrip("."),
            "chunks_created": 0,
            "size_mb": round(size_mb, 2),
            "topic_id": topic_id,
            "message": "Document already exists, linked to this session instantly",
        }

    upload_dir = Path(settings.UPLOAD_DIR) / user["id"] / section_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = str(upload_dir / file.filename)
    with open(file_path, "wb") as f:
        f.write(content)

    doc = db.create_document(
        user_id=user["id"],
        topic_id=section_id,
        file_name=file.filename,
        file_path=file_path,
        file_type=ext.lstrip("."),
        doc_hash=doc_hash,
        status="processing",
    )
    link_document_to_session(doc_hash, section_id, user["id"], db=db)

    db.delete_flashcards_for_topic(section_id)
    background_tasks.add_task(_run_indexing, doc["id"], section_id, file_path, user["id"], file.filename)

    return {
        "status": "processed",
        "id": doc["id"],
        "doc_hash": doc_hash,
        "file_name": file.filename,
        "filename": file.filename,
        "file_type": ext.lstrip("."),
        "size_mb": round(size_mb, 2),
        "topic_id": topic_id,
        "chunks_created": 0,
        "message": f"✅ {file.filename} uploaded and indexing started.",
    }


@router.get("/topic/{topic_id}")
async def list_documents(topic_id: str, user: dict = Depends(get_current_user)):
    docs = [d for d in db.get_documents_for_topic(topic_id) if d["user_id"] == user["id"]]
    for doc in docs:
        status = _indexing_status.get(doc["id"], {})
        doc["index_status"] = status.get("status", "pending")
        doc["index_progress"] = status.get("progress", 0)
        doc["index_stats"] = status.get("stats", {})
    return docs


@router.get("/{doc_id}/status")
async def indexing_status(doc_id: str, user: dict = Depends(get_current_user)):
    if not any(d["id"] == doc_id for d in db.get_documents_for_user(user["id"])):
        raise HTTPException(status_code=404, detail="Document not found")
    status = _indexing_status.get(doc_id, {"status": "pending", "progress": 0})
    return status


@router.post("/concept-explain")
async def explain_concept(req: ConceptExplainRequest, user: dict = Depends(get_current_user)):
    concept = req.concept.strip()
    if not concept:
        raise HTTPException(status_code=400, detail="Concept name required.")

    cache_key = f"{concept.lower()}_{req.topic_id or 'general'}"
    if cache_key in _concept_cache:
        return _concept_cache[cache_key]

    prompt = f"""You are DeepTutor, an elite academic AI tutor.
Provide a concise, crystal-clear conceptual breakdown for: "{concept}".
Return JSON matching:
{{
  "concept": "{concept}",
  "definition": "...",
  "key_takeaway": "...",
  "application": "...",
  "exam_tip": "..."
}}
JSON OUTPUT:"""
    try:
        raw = await ollama.chat([{"role": "user", "content": prompt}], temperature=0.2)
        cleaned = raw.strip().removeprefix("```json").removesuffix("```").strip()
        parsed = json.loads(cleaned)
        _concept_cache[cache_key] = parsed
        return parsed
    except Exception:
        fallback = {
            "concept": concept,
            "definition": f"{concept} is a foundational concept essential for theoretical mastery and problem-solving.",
            "key_takeaway": f"Review key definitions and core mechanisms governing {concept}.",
            "application": "Used extensively across standard exercises and real-world implementations.",
            "exam_tip": "Focus on step-by-step formulations and definitions."
        }
        _concept_cache[cache_key] = fallback
        return fallback


@router.get("/topic/{topic_id}/graph")
async def get_knowledge_graph(topic_id: str, user: dict = Depends(get_current_user)):
    docs = db.get_documents_for_user_and_topic(user["id"], topic_id)
    if not docs and topic_id == "general":
        docs = db.get_documents_for_user(user["id"])

    primary_doc_name = docs[0].get("file_name", "") if docs else ""
    doc_node_id = f"doc_{topic_id}"
    root_label = f"Knowledge Base ({primary_doc_name})" if primary_doc_name else "Document Knowledge Base"

    nodes = [{
        "id": doc_node_id,
        "name": root_label,
        "type": "document",
        "description": f"Knowledge base synthesized from {len(docs)} uploaded document(s)"
    }]
    edges = []
    seen = set()

    for doc in docs:
        for kt in doc.get("key_topics", []):
            if str(kt).startswith("__subject__:"):
                continue
            kt_clean = str(kt).strip()
            if kt_clean and kt_clean.lower() not in seen:
                seen.add(kt_clean.lower())
                nid = f"concept_{len(seen)}"
                nodes.append({
                    "id": nid,
                    "name": kt_clean,
                    "type": "concept",
                    "description": f"Concept from {doc.get('file_name', 'uploaded material')}"
                })
                edges.append({
                    "source": doc_node_id,
                    "target": nid,
                    "type": "contains_concept",
                    "description": "Topic concept extracted from document"
                })

    return {
        "topic_id": topic_id,
        "stats": {"node_count": len(nodes), "edge_count": len(edges)},
        "graph": {"nodes": nodes, "edges": edges},
    }


@router.get("/{doc_id}/markdown")
async def get_document_markdown(doc_id: str, user: dict = Depends(get_current_user)):
    with db.DBContext() as database:
        doc = database.query(db.Document).filter(db.Document.id == doc_id).first()
        if not doc or doc.user_id != user["id"]:
            raise HTTPException(status_code=404, detail="Document not found.")
        file_path = doc.file_path
        file_name = doc.file_name

    text = doc_processor.get_document_text(doc_id)
    if not text and Path(file_path).exists():
        try:
            import pypdf
            reader = pypdf.PdfReader(file_path)
            text = "\n\n".join([p.extract_text() or "" for p in reader.pages[:20]])
        except Exception:
            text = "Unable to preview document content."

    return {
        "doc_id": doc_id,
        "file_name": file_name,
        "chunk_count": 1,
        "markdown": f"# {file_name}\n\n{text}",
    }


@router.delete("/section/{section_id}")
async def delete_section_documents(section_id: str, user: dict = Depends(get_current_user)):
    user_id = user["id"]
    del_result = db.delete_section_all_data(user_id=user_id, topic_id=section_id)
    deleted_docs = del_result.get("deleted_docs", [])

    for doc in deleted_docs:
        file_path = doc.get("file_path")
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

    for base_p in [
        Path(settings.UPLOAD_DIR) / user_id / section_id,
        Path(settings.UPLOAD_DIR) / section_id,
    ]:
        if base_p.exists():
            try:
                import shutil
                shutil.rmtree(base_p, ignore_errors=True)
            except Exception:
                pass

    return {
        "ok": True,
        "section_id": section_id,
        "deleted_count": len(deleted_docs),
        "details": del_result,
        "message": f"Successfully deleted section '{section_id}' and all associated files."
    }


@router.delete("/{doc_id}")
async def delete_document(doc_id: str, user: dict = Depends(get_current_user)):
    user_id = user["id"]
    doc = db.delete_document(doc_id=doc_id, user_id=user_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found or access denied.")

    file_path = doc.get("file_path")
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception:
            pass

    _indexing_status.pop(doc_id, None)
    return {
        "ok": True,
        "doc_id": doc_id,
        "file_name": doc["file_name"],
        "message": f"Deleted document '{doc['file_name']}'."
    }


@router.get("/session/{session_id}/status")
async def session_documents_status(session_id: str, user: dict = Depends(get_current_user)):
    """Returns UI status signals for documents in this session including cross-session reuse count."""
    return db.get_document_status_for_ui(session_id, user["id"])


@router.get("/session/{session_id}")
async def session_documents_list(session_id: str, user: dict = Depends(get_current_user)):
    """Returns all documents linked to the specified session."""
    return db.get_session_documents(session_id, user["id"])
