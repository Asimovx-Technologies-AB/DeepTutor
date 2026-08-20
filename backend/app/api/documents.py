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
from app.rag.storage import active_vector_store, active_graph_store
from app.rag.graph_store import graph_store
from app.rag.vector_store import vector_store
from app.rag.cache import query_result_cache
from app.rag.section_scope import get_section_collection_id
from app.rag.storage.s3_store import s3_store


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
        if pct >= 100:
            _indexing_status[doc_id]["status"] = "done"

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
            key_topics=stats.get("extracted_topics", []),
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

    # Read uploaded file content
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)

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

    # Upload to AWS S3 Cloud Storage
    s3_key = f"documents/{user['id']}/{section_id}/{file.filename}"
    if s3_store.is_configured():
        background_tasks.add_task(s3_store.upload_file, file_path, s3_key, file.content_type)

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
        "s3_stored": s3_store.is_configured(),
        "status": "indexing",
        "message": f"✅ {file.filename} uploaded to AWS S3 & GraphRAG indexing started in background.",
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


from pydantic import BaseModel
from app.rag.topic_sanitizer import is_valid_academic_topic, clean_and_format_topic
from app.rag.ollama_client import ollama
from app.rag.entity_extractor import _extract_json


class ConceptExplainRequest(BaseModel):
    concept: str
    topic_id: Optional[str] = "general"


@router.post("/concept-explain")
async def explain_concept(req: ConceptExplainRequest, user: dict = Depends(get_current_user)):
    """Return a concise, high-yield academic explanation of a Knowledge Graph concept."""
    concept = req.concept.strip()
    if not concept:
        raise HTTPException(status_code=400, detail="Concept name required.")

    # 1. Search vector store for grounded context from user's document
    grounding_text = ""
    try:
        coll_id = _user_section_collection_id(user["id"], req.topic_id or "general")
        results = await vector_store.search(query=concept, collection_id=coll_id, top_k=2)
        if results:
            grounding_text = "\n".join([r.get("text", "")[:400] for r in results if r.get("text")])
    except Exception:
        pass

    prompt = f"""You are DeepTutor, an elite academic AI tutor.
Provide a concise, crystal-clear conceptual breakdown for the academic concept: "{concept}".

Textbook Reference (if relevant):
{grounding_text}

Return ONLY valid JSON in this exact structure:
{{
  "definition": "A precise, easy-to-understand 2-sentence explanation of {concept}.",
  "key_takeaway": "The core formula, governing law, or key takeaway.",
  "application": "Where or how this concept is applied in practice or problem-solving.",
  "exam_tip": "High-yield exam tip or common mistake to avoid."
}}

JSON:"""

    try:
        messages = [
            {"role": "system", "content": "You are a precise academic assistant. Respond with valid JSON only."},
            {"role": "user", "content": prompt}
        ]
        resp = await ollama.chat(messages, temperature=0.1)
        data = _extract_json(resp)
        if data and data.get("definition"):
            return {
                "concept": concept,
                "definition": data.get("definition", ""),
                "key_takeaway": data.get("key_takeaway", ""),
                "application": data.get("application", ""),
                "exam_tip": data.get("exam_tip", ""),
            }
    except Exception as e:
        print(f"[EXPLAIN CONCEPT ERROR] {e}")

    return {
        "concept": concept,
        "definition": f"{concept} is a fundamental concept in this chapter, essential for theoretical understanding and problem-solving.",
        "key_takeaway": f"Review key definitions and core formulas relating to {concept}.",
        "application": "Used extensively across standard exercises and real-world systems.",
        "exam_tip": "Focus on step-by-step derivations and standard problem patterns."
    }


@router.get("/topic/{topic_id}/graph")
async def get_knowledge_graph(topic_id: str, user: dict = Depends(get_current_user)):
    """Return full knowledge graph for visualization — scoped to the current user section."""
    namespaced_topic = _user_section_collection_id(user["id"], topic_id)
    raw_graph = graph_store.get_full_graph(namespaced_topic)
    stats = graph_store.get_graph_stats(namespaced_topic)

    # Fallback 1: check un-namespaced topic_id if present
    if not raw_graph.get("nodes"):
        fallback_graph = graph_store.get_full_graph(topic_id)
        if fallback_graph.get("nodes"):
            raw_graph = fallback_graph
            stats = graph_store.get_graph_stats(topic_id)

    # Fallback 2: construct concept graph from document key_topics if graph store has no nodes
    docs = db.get_documents_for_user_and_topic(user["id"], topic_id)
    if not docs:
        docs = db.get_documents_for_user(user["id"]) if topic_id == "general" else []

    primary_doc_name = docs[0].get("file_name", "") if docs else ""

    if not raw_graph.get("nodes"):
        nodes = []
        edges = []
        seen_nodes = set()
        for doc in docs:
            key_topics = doc.get("key_topics", [])
            for kt in key_topics:
                clean_kt = clean_and_format_topic(str(kt))
                if clean_kt and is_valid_academic_topic(clean_kt):
                    node_id = clean_kt.lower().strip()
                    if node_id and node_id not in seen_nodes:
                        seen_nodes.add(node_id)
                        nodes.append({
                            "id": node_id,
                            "name": clean_kt,
                            "type": "concept",
                            "description": f"Core academic concept from {doc.get('file_name', 'uploaded material')}"
                        })
        if nodes:
            doc_node_id = f"doc_{topic_id}"
            root_label = f"Knowledge Base ({primary_doc_name})" if primary_doc_name else "Document Knowledge Base"
            nodes.insert(0, {
                "id": doc_node_id,
                "name": root_label,
                "type": "document",
                "description": f"Knowledge base synthesized from {len(docs)} uploaded document(s)"
            })
            for n in nodes[1:]:
                edges.append({
                    "source": doc_node_id,
                    "target": n["id"],
                    "type": "contains_concept",
                    "description": "Topic concept extracted from document"
                })
            raw_graph = {"nodes": nodes, "edges": edges}

    # Strict filtering: keep only valid, high-yield academic concepts (omit boilerplate / metadata)
    clean_nodes = []
    valid_node_ids = set()
    for node in raw_graph.get("nodes", []):
        n_name = node.get("name", node.get("id", ""))
        n_type = node.get("type", "concept")
        
        # Clean root document node name so it never shows raw UUIDs
        if n_type == "document":
            if any(char.isdigit() for char in n_name) and len(n_name) > 20:
                node["name"] = f"Knowledge Base ({primary_doc_name})" if primary_doc_name else "Document Knowledge Base"
            clean_nodes.append(node)
            valid_node_ids.add(node.get("id", ""))
            continue

        if is_valid_academic_topic(n_name) and clean_and_format_topic(n_name):
            clean_name = clean_and_format_topic(n_name) or n_name
            node["name"] = clean_name
            clean_nodes.append(node)
            valid_node_ids.add(node.get("id", clean_name.lower().strip()))

    clean_edges = []
    for edge in raw_graph.get("edges", []):
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        if src in valid_node_ids and tgt in valid_node_ids:
            clean_edges.append(edge)

    graph = {"nodes": clean_nodes, "edges": clean_edges}
    stats = {"node_count": len(clean_nodes), "edge_count": len(clean_edges)}

    return {"topic_id": topic_id, "stats": stats, "graph": graph}



@router.get("/{doc_id}/markdown")
async def get_document_markdown(doc_id: str, user: dict = Depends(get_current_user)):
    """Export and return full structured Markdown content for an uploaded document."""
    from app.rag.document_processor import process_document
    with db.DBContext() as database:
        doc = database.query(db.Document).filter(db.Document.id == doc_id).first()
        if not doc or doc.user_id != user["id"]:
            raise HTTPException(status_code=404, detail="Document not found.")
        file_path = doc.file_path

    if not Path(file_path).exists():
        raise HTTPException(status_code=404, detail="Source file not found on server.")

    chunks = await asyncio.to_thread(process_document, file_path)
    md_lines = [f"# {doc.file_name}\n"]
    for c in chunks:
        title = c.get("metadata", {}).get("section_title")
        if title:
            md_lines.append(f"\n## {title}\n")
        md_lines.append(c["text"])

    return {
        "doc_id": doc_id,
        "file_name": doc.file_name,
        "chunk_count": len(chunks),
        "markdown": "\n\n".join(md_lines),
    }


@router.delete("/section/{section_id}")
async def delete_section_documents(section_id: str, user: dict = Depends(get_current_user)):
    """
    Comprehensively delete all documents/PDFs, FAISS vectors, JSON-KV graphs,
    quizzes, flashcards, study plans, chat sessions, and physical files
    for a specific section/topic for the current user.
    """
    user_id = user["id"]
    namespaced_topic = _user_section_collection_id(user_id, section_id)

    # 1. Delete all SQL database records (documents, flashcards, quizzes, study plans, chat sessions)
    del_result = db.delete_section_all_data(user_id=user_id, topic_id=section_id)
    deleted_docs = del_result.get("deleted_docs", [])

    # 2. Remove physical PDF / document files from disk & AWS S3
    for doc in deleted_docs:
        file_path = doc.get("file_path")
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"[documents] Failed to remove file {file_path}: {e}")

        # Delete from AWS S3
        if s3_store.is_configured() and doc.get("file_name"):
            s3_key = f"documents/{user_id}/{section_id}/{doc.get('file_name')}"
            s3_store.delete_file(s3_key)

    # Also clean up the section upload directories if present
    for base_p in [
        Path(settings.UPLOAD_DIR) / user_id / section_id,
        Path(settings.UPLOAD_DIR) / section_id,
    ]:
        if base_p.exists():
            try:
                import shutil
                shutil.rmtree(base_p, ignore_errors=True)
            except Exception as e:
                print(f"[documents] Failed to remove upload_dir {base_p}: {e}")

    # 3. Delete active FAISS vector store + fallback ChromaDB
    try:
        active_vector_store.delete_collection(namespaced_topic)
        active_vector_store.delete_collection(section_id)
        vector_store.delete_collection(namespaced_topic)
        vector_store.delete_collection(section_id)
    except Exception as e:
        print(f"[documents] Vector store delete note: {e}")

    # 4. Delete active JSON-KV graph store + fallback NetworkX
    try:
        active_graph_store.delete_graph(namespaced_topic)
        active_graph_store.delete_graph(section_id)
        graph_store.delete_graph(namespaced_topic)
        graph_store.delete_graph(section_id)
    except Exception as e:
        print(f"[documents] Graph store delete note: {e}")

    # 5. Invalidate query cache for this section
    try:
        await query_result_cache.invalidate(namespaced_topic)
        await query_result_cache.invalidate(section_id)
    except Exception:
        pass

    return {
        "ok": True,
        "section_id": section_id,
        "deleted_count": len(deleted_docs),
        "details": del_result,
        "message": f"Successfully deleted section '{section_id}' and all associated database records, files, vectors, and graph data."
    }


@router.delete("/{doc_id}")
async def delete_document(doc_id: str, user: dict = Depends(get_current_user)):
    """
    Delete a single document by ID.
    If no remaining documents exist for the section, cleans up the section's vector and graph data.
    """
    user_id = user["id"]
    doc = db.delete_document(doc_id=doc_id, user_id=user_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found or access denied.")

    section_id = doc["topic_id"]
    file_path = doc.get("file_path")

    # Remove physical file from disk
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            print(f"[documents] Failed to remove file {file_path}: {e}")

    # Remove from indexing status cache if present
    _indexing_status.pop(doc_id, None)

    # Check remaining documents in section for this user
    remaining = db.get_documents_for_user_and_topic(user_id, section_id)
    namespaced_topic = _user_section_collection_id(user_id, section_id)

    if not remaining:
        # No documents left for this section — delete vector store, graph store, flashcards
        try:
            active_vector_store.delete_collection(namespaced_topic)
            active_vector_store.delete_collection(section_id)
            vector_store.delete_collection(namespaced_topic)
            vector_store.delete_collection(section_id)
        except Exception:
            pass

        try:
            active_graph_store.delete_graph(namespaced_topic)
            active_graph_store.delete_graph(section_id)
            graph_store.delete_graph(namespaced_topic)
            graph_store.delete_graph(section_id)
        except Exception:
            pass

        db.delete_flashcards_for_topic(section_id)
        try:
            await query_result_cache.invalidate(namespaced_topic)
            await query_result_cache.invalidate(section_id)
        except Exception:
            pass

    return {
        "ok": True,
        "doc_id": doc_id,
        "file_name": doc["file_name"],
        "message": f"Deleted document '{doc['file_name']}'."
    }

