"""
Documents API — file upload + SQLite FTS indexing + Topic Extraction.
"""
import os
import asyncio
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends, BackgroundTasks
from pydantic import BaseModel
from app.api.auth import get_current_user
from app.core import database as db
from app.core.config import get_settings
from app.rag.doc_processor import doc_processor
from app.rag.topic_extractor import topic_extractor
from app.rag.llm_client import llm_client
from app.rag.sqlite_fts_store import get_session_store
from app.rag.document_dedup import get_file_hash, is_already_processed, link_document_to_session

settings = get_settings()
logger = logging.getLogger(__name__)
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
    from app.services.study_storage import list_registry_sessions, get_session_topics
    
    docs = []
    try:
        docs = (
            db.get_documents_for_user_and_topic(user["id"], topic_id)
            if topic_id
            else db.get_documents_for_user(user["id"])
        )
    except Exception as e:
        logger.warning(f"[documents.list] DB fetch error: {e}")
        docs = []

    # Fetch all user sessions from registry to compute session links
    sessions_by_id = {}
    try:
        user_sessions = list_registry_sessions(user_id=user["id"])
        for s in user_sessions:
            if s.get("id"):
                sessions_by_id[s["id"]] = s
    except Exception as e:
        logger.warning(f"[documents.list] Session registry error: {e}")
        user_sessions = []

    # Map each document with indexing status and subjects
    for doc in docs:
        topics = doc.get("key_topics") or []
        subject_marker = next((topic for topic in topics if str(topic).startswith("__subject__:")), "")
        doc["detected_subject"] = subject_marker.removeprefix("__subject__:").strip()
        doc["key_topics"] = [topic for topic in topics if not str(topic).startswith("__subject__:")]
        status = _indexing_status.get(doc["id"])
        db_status = doc.get("status") or ("done" if doc.get("indexed") else "pending")
        if db_status == "completed":
            db_status = "done"

        doc["index_status"] = status.get("status") if status else db_status
        doc["index_progress"] = status.get("progress", 100 if db_status == "done" else (0 if db_status == "failed" else 20)) if status else (100 if db_status == "done" else 0)
        doc["index_stats"] = status.get("stats", {}) if status else {}

    # Track existing filenames to prevent duplicate document cards
    existing_filenames = {
        str(d.get("file_name") or "").strip().lower()
        for d in docs if d.get("file_name")
    }

    # Merge session materials not yet captured in documents table
    for s in user_sessions:
        sid = s.get("id")
        if not sid:
            continue
        doc_names = s.get("documents") or ([s.get("document_name")] if s.get("document_name") else [])
        if not doc_names:
            continue

        # Identify documents not yet present in docs before querying database
        new_docs = [
            fn for fn in doc_names
            if fn and fn.strip().lower() not in existing_filenames
        ]
        if not new_docs:
            continue

        # Lazy query for topics only when new documents actually exist
        session_topics = get_session_topics(sid, user_id=user["id"])
        topic_titles = [t.get("title", "") for t in session_topics if t.get("title")]

        for fn in new_docs:
            clean_fn = fn.strip()
            existing_filenames.add(clean_fn.lower())
            clean_title = Path(clean_fn).stem.replace("_", " ").title()
            subject_name = s.get("subject") or clean_title

            candidate_path = Path(settings.UPLOAD_DIR) / user["id"] / sid / clean_fn
            if not candidate_path.exists():
                candidate_path = Path(settings.UPLOAD_DIR) / sid / clean_fn

            docs.append({
                "id": f"{sid}_{clean_fn}",
                "user_id": s.get("user_id", user["id"]),
                "topic_id": sid,
                "file_name": clean_fn,
                "file_path": str(candidate_path),
                "file_type": Path(clean_fn).suffix.lower().lstrip(".") or "pdf",
                "indexed": True,
                "entity_count": len(topic_titles),
                "chunk_count": s.get("topic_count", 0),
                "detected_subject": subject_name,
                "key_topics": topic_titles,
                "index_status": "done",
                "index_progress": 100,
                "index_stats": {},
                "created_at": s.get("created_at"),
            })

    # Deduplication & Session Linking: Group by doc_hash or normalized file_name
    deduped_map: Dict[str, Dict[str, Any]] = {}
    for doc in docs:
        key = str(doc.get("doc_hash") or "").strip().lower()
        if not key or len(key) < 16:
            key = f"fn_{str(doc.get('file_name', '')).strip().lower()}"

        if key not in deduped_map:
            doc_copy = dict(doc)
            doc_copy["linked_sessions"] = []
            deduped_map[key] = doc_copy
        else:
            # Merge key_topics if current doc has more details
            existing = deduped_map[key]
            if not existing.get("key_topics") and doc.get("key_topics"):
                existing["key_topics"] = doc.get("key_topics")
            if not existing.get("detected_subject") and doc.get("detected_subject"):
                existing["detected_subject"] = doc.get("detected_subject")

    # Match linked sessions for each deduplicated document
    for key, doc in deduped_map.items():
        doc_fn = str(doc.get("file_name", "")).strip().lower()
        matched_sessions = []
        for sid, s in sessions_by_id.items():
            s_docs = [str(name).strip().lower() for name in (s.get("documents") or ([s.get("document_name")] if s.get("document_name") else []))]
            if doc_fn in s_docs or sid == doc.get("topic_id"):
                matched_sessions.append({
                    "id": sid,
                    "title": s.get("title") or f"{doc.get('detected_subject') or 'Study'} Room",
                    "subject": s.get("subject") or doc.get("detected_subject"),
                    "created_at": s.get("created_at"),
                })
        doc["linked_sessions"] = matched_sessions
        doc["session_count"] = len(matched_sessions)
        if matched_sessions and not doc.get("topic_id"):
            doc["topic_id"] = matched_sessions[0]["id"]

    results = list(deduped_map.values())
    if topic_id:
        results = [
            d for d in results
            if d.get("topic_id") == topic_id or any(s["id"] == topic_id for s in d.get("linked_sessions", []))
        ]
    return results


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

        try:
            from app.services.study_storage import update_document_status
            update_document_status(section_id, doc_id, "completed")
        except Exception as err:
            logger.debug(f"[documents._run_indexing] update_document_status completed: {err}")

        # Invalidate existing flashcards only after successful re-indexing
        try:
            db.delete_flashcards_for_topic(section_id)
        except Exception as err:
            logger.debug(f"[documents._run_indexing] delete_flashcards_for_topic: {err}")

        # Dispatch Background Path: Stage 2 (Table) & Stage 3 (Image/VLM) Enrichment
        asyncio.create_task(doc_processor.run_background_enrichment(doc_id))
    except Exception as e:
        logger.error(f"[documents] Indexing error for {doc_id}: {e}")
        _indexing_status[doc_id] = {"status": "error", "progress": 0, "error": str(e), "stats": {}}
        db.update_document_stats(
            doc_id=doc_id,
            indexed=False,
            entity_count=0,
            chunk_count=0,
            status="failed",
            error_message=str(e),
        )
        try:
            from app.services.study_storage import update_document_status
            update_document_status(section_id, doc_id, "failed")
        except Exception as err:
            logger.debug(f"[documents._run_indexing] update_document_status failed: {err}")


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

    safe_filename = os.path.basename(file.filename).strip()
    if not safe_filename or safe_filename.startswith("."):
        safe_filename = f"upload_{db.new_id()[:8]}{ext}"

    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    max_allowed_mb = user.get("max_upload_size_mb", 100 if user.get("is_premium") else 10)
    if size_mb > max_allowed_mb:
        raise HTTPException(
            status_code=413,
            detail=f"File size ({size_mb:.1f} MB) exceeds maximum permitted limit of {max_allowed_mb} MB."
        )

    section_id = (section_id or topic_id or "general").strip() or "general"

    # Fast Content Hash Deduplication
    doc_hash = get_file_hash(content)
    if is_already_processed(doc_hash, user["id"], db=db):
        link_document_to_session(doc_hash, section_id, user["id"], db=db)
        existing_doc = db.get_document_by_hash(doc_hash, user["id"])
        if existing_doc:
            try:
                from app.rag.pg_fts_store import pg_fts_store
                pg_fts_store.clone_document_chunks_to_session(
                    target_session_id=section_id,
                    source_doc_id=existing_doc.get("id"),
                    doc_hash=doc_hash,
                    user_id=user["id"],
                )
            except Exception as e:
                logger.error(f"[documents.upload] Failed to clone document chunks: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to clone document chunks to session: {e}")
        return {
            "status": "already_processed",
            "id": existing_doc.get("id") if existing_doc else None,
            "doc_hash": doc_hash,
            "file_name": safe_filename,
            "filename": safe_filename,
            "file_type": ext.lstrip("."),
            "chunks_created": 0,
            "size_mb": round(size_mb, 2),
            "topic_id": section_id,
            "section_id": section_id,
            "message": "Document already exists, linked to this session instantly",
        }

    upload_dir = (Path(settings.UPLOAD_DIR) / user["id"] / section_id).resolve()
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest_path = (upload_dir / safe_filename).resolve()
    if not str(dest_path).startswith(str(upload_dir)):
        raise HTTPException(status_code=400, detail="Invalid filename path traversal attempt.")
    file_path = str(dest_path)

    await asyncio.to_thread(dest_path.write_bytes, content)

    doc = db.create_document(
        user_id=user["id"],
        topic_id=section_id,
        file_name=safe_filename,
        file_path=file_path,
        file_type=ext.lstrip("."),
        doc_hash=doc_hash,
        status="processing",
    )
    link_document_to_session(doc_hash, section_id, user["id"], db=db)
    try:
        from app.services.study_storage import save_session_document
        save_session_document(
            session_id=section_id,
            doc_id=doc["id"],
            filename=safe_filename,
            file_path=file_path,
            status="processing",
            user_id=user["id"],
            doc_hash=doc_hash,
        )
    except Exception as e:
        logger.warning(f"[documents.upload] save_session_document warning: {e}")

    background_tasks.add_task(_run_indexing, doc["id"], section_id, file_path, user["id"], safe_filename)

    return {
        "status": "processed",
        "id": doc["id"],
        "doc_hash": doc_hash,
        "file_name": safe_filename,
        "filename": safe_filename,
        "file_type": ext.lstrip("."),
        "size_mb": round(size_mb, 2),
        "topic_id": section_id,
        "section_id": section_id,
        "chunks_created": 0,
        "message": f"✅ {safe_filename} uploaded and indexing started.",
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
        raw = await llm_client.chat([{"role": "user", "content": prompt}], temperature=0.2)
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
    from app.services.study_storage import delete_registry_session, delete_session_document, get_registry_session

    # 1. Try deleting standard user Document record
    doc = db.delete_document(doc_id=doc_id, user_id=user_id)
    if doc:
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
            "file_name": doc.get("file_name", doc_id),
            "message": f"Deleted document '{doc.get('file_name', doc_id)}'."
        }

    # 2. Check if doc_id is a composite session-material key "{sid}_{filename}"
    if "_" in doc_id:
        for candidate_sid in [doc_id.split("_", 1)[0], "_".join(doc_id.split("_")[:2])]:
            s_meta = get_registry_session(candidate_sid)
            if s_meta:
                candidate_fn = doc_id[len(candidate_sid) + 1:]
                if delete_session_document(candidate_sid, candidate_fn, user_id=user_id):
                    return {
                        "ok": True,
                        "doc_id": doc_id,
                        "file_name": candidate_fn,
                        "message": f"Deleted session material '{candidate_fn}'."
                    }

    # 3. Check if doc_id matches a session_document directly by hash, ID, or filename
    with db.DBContext() as session_db:
        s_docs = session_db.query(db.SessionDocument).filter(
            db.SessionDocument.user_id == user_id,
            (db.SessionDocument.doc_hash == doc_id) | (db.SessionDocument.filename == doc_id) | (db.SessionDocument.id == doc_id)
        ).all()
        if s_docs:
            for sd in s_docs:
                delete_session_document(sd.session_id, doc_id, user_id=user_id)
            return {
                "ok": True,
                "doc_id": doc_id,
                "file_name": doc_id,
                "message": f"Detached and deleted material '{doc_id}' from sessions."
            }

    return {"ok": True, "doc_id": doc_id, "file_name": doc_id, "message": f"Material '{doc_id}' deleted or already unlinked."}


@router.get("/session/{session_id}/status")
async def session_documents_status(session_id: str, user: dict = Depends(get_current_user)):
    """Returns UI status signals for documents in this session including cross-session reuse count."""
    return db.get_document_status_for_ui(session_id, user["id"])


@router.get("/session/{session_id}")
async def session_documents_list(session_id: str, user: dict = Depends(get_current_user)):
    """Returns all documents linked to the specified session."""
    return db.get_session_documents(session_id, user["id"])


class LinkDocumentToSessionRequest(BaseModel):
    session_id: str
    doc_id: Optional[str] = None
    doc_hash: Optional[str] = None
    filename: Optional[str] = None
    file_path: Optional[str] = None


@router.post("/link-to-session")
async def link_document_to_session_endpoint(
    req: LinkDocumentToSessionRequest,
    user: dict = Depends(get_current_user),
):
    """Link a previously uploaded material to a specific study session."""
    user_id = user["id"]
    session_id = (req.session_id or "").strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    from app.services.study_storage import (
        save_session_document,
        get_session_documents,
        save_session_topics,
        get_session_topics,
        register_or_update_session,
        list_registry_sessions,
    )
    from app.rag.document_dedup import link_document_to_session

    doc_id = req.doc_id
    doc_hash = req.doc_hash
    filename = req.filename
    file_path = req.file_path
    doc = None

    # If doc_id was passed, attempt to look it up in the Document database
    if doc_id:
        doc = db.get_document(doc_id, user_id=user_id)
        if doc:
            doc_hash = doc_hash or doc.get("doc_hash")
            filename = filename or doc.get("file_name")
            file_path = file_path or doc.get("file_path")
    elif doc_hash:
        doc = db.get_document_by_hash(doc_hash, user_id=user_id)
        if doc:
            doc_id = doc.get("id")
            filename = filename or doc.get("file_name")
            file_path = file_path or doc.get("file_path")

    if not filename and not doc_id and not doc_hash:
        raise HTTPException(status_code=400, detail="Must provide at least doc_id, filename, or doc_hash")

    effective_filename = filename or f"doc_{doc_id or 'unknown'}"
    effective_file_path = file_path or effective_filename

    # If doc_hash available, record cross-session deduplication link
    if doc_hash:
        try:
            link_document_to_session(doc_hash, session_id, user_id, db=db)
        except Exception as e:
            logger.warning(f"[link_document_to_session] Warning: {e}")

    # Register in session_documents table with fully_processed status
    save_session_document(
        session_id=session_id,
        doc_id=doc_id,
        filename=effective_filename,
        file_path=effective_file_path,
        status="fully_processed",
        user_id=user_id,
        doc_hash=doc_hash or "",
    )

    # Clone document chunks and embeddings into the new session
    try:
        from app.rag.pg_fts_store import pg_fts_store
        pg_fts_store.clone_document_chunks_to_session(
            target_session_id=session_id,
            source_doc_id=doc_id,
            doc_hash=doc_hash,
            user_id=user_id,
        )
    except Exception as e:
        logger.error(f"[link_document_to_session] Error cloning chunks: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clone document chunks to session: {e}")

    # Populate curriculum topics in session for this document
    existing_session_topics = get_session_topics(session_id, user_id=user_id)
    doc_topics_already_present = any(
        t.get("document_name") and t.get("document_name").lower() == effective_filename.lower()
        for t in existing_session_topics
    )

    if not doc_topics_already_present:
        prior_topics = []

        # 1. Try to fetch existing rich topics from the document's original session
        if doc and doc.get("topic_id"):
            try:
                orig_topics = get_session_topics(str(doc["topic_id"]), user_id=user_id)
                if orig_topics:
                    for ot in orig_topics:
                        prior_topics.append({
                            "title": ot.get("title") or "Study Topic",
                            "summary": ot.get("summary") or f"Core study topic from {effective_filename}",
                            "difficulty": ot.get("difficulty") or "Intermediate",
                            "key_concepts": ot.get("key_concepts") or [],
                            "estimated_study_time": ot.get("estimated_study_time") or "15 mins",
                            "document_name": effective_filename,
                        })
            except Exception as e:
                logger.warning(f"[link_document_to_session] Error getting orig topics: {e}")

        # 2. Search other sessions that have this document
        if not prior_topics:
            try:
                from sqlalchemy import text as sql_text
                from app.core.database import engine
                with engine.connect() as conn:
                    rows = conn.execute(
                        sql_text("SELECT session_id FROM session_documents WHERE (doc_hash = :h OR filename = :fn) AND session_id != :sid"),
                        {"h": doc_hash or "", "fn": effective_filename, "sid": session_id}
                    ).fetchall()
                    for r in rows:
                        other_sid = str(r[0])
                        other_topics = get_session_topics(other_sid, user_id=user_id)
                        if other_topics:
                            for ot in other_topics:
                                prior_topics.append({
                                    "title": ot.get("title") or "Study Topic",
                                    "summary": ot.get("summary") or f"Core study topic from {effective_filename}",
                                    "difficulty": ot.get("difficulty") or "Intermediate",
                                    "key_concepts": ot.get("key_concepts") or [],
                                    "estimated_study_time": ot.get("estimated_study_time") or "15 mins",
                                    "document_name": effective_filename,
                                })
                            break
            except Exception as e:
                logger.warning(f"[link_document_to_session] Warning searching other sessions for topics: {e}")

        # 3. Fallback to doc["key_topics"]
        if not prior_topics and doc and doc.get("key_topics"):
            raw_key_topics = doc.get("key_topics") or []
            clean_topics = [t for t in raw_key_topics if not str(t).startswith("__subject__:")]
            for idx, t_title in enumerate(clean_topics):
                prior_topics.append({
                    "title": str(t_title),
                    "summary": f"Core study topic from {effective_filename}",
                    "difficulty": "Intermediate",
                    "key_concepts": [],
                    "estimated_study_time": "15 mins",
                    "document_name": effective_filename,
                })

        # 4. Fallback if still empty: generate at least 1 clean default topic so Focus is never empty
        if not prior_topics:
            clean_topic_title = Path(effective_filename).stem.replace("_", " ").replace("-", " ").title()
            prior_topics.append({
                "title": clean_topic_title,
                "summary": f"Comprehensive progressive curriculum topic for {effective_filename}",
                "difficulty": "Beginner",
                "key_concepts": [],
                "estimated_study_time": "20 mins",
                "document_name": effective_filename,
            })

        if prior_topics:
            try:
                save_session_topics(
                    session_id=session_id,
                    topics=prior_topics,
                    user_id=user_id,
                    append=True,
                    document_name=effective_filename,
                )
            except Exception as e:
                logger.warning(f"[link_document_to_session] Warning saving topics: {e}")

    # Update session registry entry so it displays properly on the page
    clean_title = Path(effective_filename).stem.replace("_", " ").title()
    effective_subject = (doc.get("detected_subject") if doc else None) or "General Study"
    register_or_update_session(
        session_id=session_id,
        subject=effective_subject,
        title=f"{clean_title} Study Room",
        status="fully_processed",
        document_name=effective_filename,
        user_id=user_id,
    )

    # Return the refreshed document list and curriculum topics for this session
    updated_docs = get_session_documents(session_id, user_id)
    updated_topics = get_session_topics(session_id, user_id)
    return {
        "ok": True,
        "message": f"Successfully linked '{effective_filename}' to session.",
        "documents": updated_docs,
        "topics": updated_topics,
    }

