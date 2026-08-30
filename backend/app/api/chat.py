import os
import shutil
from pathlib import Path
import asyncio
import json
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.api.auth import get_current_user, decode_token
from app.core import database as db
from app.core.config import get_settings
from app.rag.graph_rag import graph_rag
from app.rag.ollama_client import ollama
from app.rag.section_scope import get_section_collection_id
from app.rag.storage import active_vector_store, active_graph_store
from app.rag.vector_store import vector_store
from app.rag.graph_store import graph_store
from app.rag.cache import query_result_cache
from app.rag.storage.s3_store import s3_store

settings = get_settings()
router = APIRouter(prefix="/chat", tags=["chat"])


class CreateSessionRequest(BaseModel):
    topic_id: Optional[str] = ""
    session_title: str = "New Chat Session"


class MessageRequest(BaseModel):
    content: str
    language: Optional[str] = "english"


def _user_section_collection_id(user_id: str, topic_id: str, session_id: str = "") -> str:
    """Build a collection id scoped to the authenticated user's upload."""
    section_id = topic_id or session_id or "general"
    return get_section_collection_id(user_id, section_id)


# ─── Sessions ──────────────────────────────────────────────────────────────────
@router.post("/sessions")
async def create_session(
    body: CreateSessionRequest,
    user: dict = Depends(get_current_user),
):
    session = db.create_session(
        user_id=user["id"],
        topic_id=body.topic_id or "",
        title=body.session_title,
    )
    return session


@router.get("/sessions")
async def list_sessions(
    scope: Optional[str] = Query(None),
    user: dict = Depends(get_current_user)
):
    sessions = db.get_sessions_for_user(user["id"])
    if scope == "learn":
        # All learning sessions are based on the user's own materials.
        pass
    elif scope == "subjects":
        # The legacy curriculum catalogue no longer has a separate scope.
        sessions = []
        
    return sorted(sessions, key=lambda s: s["started_at"], reverse=True)


@router.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str, user: dict = Depends(get_current_user)):
    session = db.get_session(session_id)
    if not session or session.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Session not found")
    return db.get_messages(session_id)


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, user: dict = Depends(get_current_user)):
    user_id = user["id"]
    session = db.get_session(session_id)
    if session and session.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session:
        # Also clean up any possible leftover session id data
        db.delete_session(session_id)
        db.delete_section_all_data(user_id=user_id, topic_id=session_id)
        return {"ok": True, "session_id": session_id}

    topic_id = session.get("topic_id") or ""

    # 1. Delete SQL database records for this session & its topic
    db.delete_session(session_id)
    del_result = db.delete_section_all_data(user_id=user_id, topic_id=session_id)
    if topic_id and topic_id != "general" and topic_id != session_id:
        db.delete_section_all_data(user_id=user_id, topic_id=topic_id)

    # 2. Clean up uploaded physical files & AWS S3
    deleted_docs = del_result.get("deleted_docs", [])
    for doc in deleted_docs:
        file_path = doc.get("file_path")
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

        if s3_store.is_configured() and doc.get("file_name"):
            s3_key = f"documents/{user_id}/{doc.get('topic_id', session_id)}/{doc.get('file_name')}"
            s3_store.delete_file(s3_key)

    for tid in [session_id, topic_id]:
        if not tid or tid == "general":
            continue
        for base_p in [
            Path(settings.UPLOAD_DIR) / user_id / tid,
            Path(settings.UPLOAD_DIR) / tid,
        ]:
            if base_p.exists():
                try:
                    shutil.rmtree(base_p, ignore_errors=True)
                except Exception:
                    pass

    # 3. Clean up FAISS, JSON-KV, ChromaDB, NetworkX
    target_ids = [session_id]
    if topic_id and topic_id != "general" and topic_id != session_id:
        target_ids.append(topic_id)

    for tid in target_ids:
        namespaced_topic = _user_section_collection_id(user_id, tid, session_id=session_id)
        for t in [namespaced_topic, tid]:
            try:
                active_vector_store.delete_collection(t)
                vector_store.delete_collection(t)
            except Exception:
                pass
            try:
                active_graph_store.delete_graph(t)
                graph_store.delete_graph(t)
            except Exception:
                pass
            try:
                await query_result_cache.invalidate(t)
            except Exception:
                pass

    return {"ok": True, "session_id": session_id}


# ─── Non-streaming message ─────────────────────────────────────────────────────
@router.post("/sessions/{session_id}/message")
async def send_message(
    session_id: str,
    body: MessageRequest,
    user: dict = Depends(get_current_user),
):
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Save user message
    db.add_message(session_id, "user", body.content)
    history = db.get_messages(session_id, last_n=10)

    # Use per-user and per-session namespaced section for ChromaDB/graph lookup
    topic_id = _user_section_collection_id(user["id"], session.get("topic_id") or "", session_id=session_id)

    if not await ollama.is_available():
        provider = getattr(settings, "LLM_PROVIDER", "gemini").lower()
        if provider == "azure_openai":
            response_text = (
                "⚠️ **Azure OpenAI is not configured.** Set `AZURE_OPENAI_ENDPOINT` "
                "and grant the application identity access to the deployment."
            )
        elif provider == "gemini":
            response_text = (
                "⚠️ **Gemini API key is not configured.**\n\n"
                "Please add your Gemini API key in `backend/.env`:\n"
                "```env\nLLM_PROVIDER=gemini\nGEMINI_API_KEY=your_actual_key\n```"
            )
        else:
            response_text = (
                "⚠️ **Ollama is not running.** Please start it with `ollama serve` "
                "and make sure you have pulled a model: `ollama pull llama3.1`"
            )
        msg = db.add_message(session_id, "assistant", response_text)
        return msg

    # GraphRAG query — scoped to this user's & session's vector collection
    result = await graph_rag.simple_query(
        topic_id=topic_id,
        question=body.content,
        session_messages=history[:-1],  # Exclude current message
        language=body.language or "english",
    )

    msg = db.add_message(
        session_id, "assistant", result["content"],
        metadata={"sources": result["sources"], "graph_context": result["graph_context"]},
    )
    return msg


# ─── SSE Streaming message ──────────────────────────────────────────────────────
@router.get("/sessions/{session_id}/message/stream")
async def stream_message(
    session_id: str,
    content: str = Query(...),
    token: str = Query(""),
    language: str = Query("english"),
):
    """
    Server-Sent Events endpoint.
    Emits events:
      data: {"type": "sources", "data": [...]}
      data: {"type": "graph_context", "data": {...}}
      data: {"type": "token", "data": "..."}
      data: {"type": "done"}
    """
    session = db.get_session(session_id)
    if not session:
        async def not_found():
            yield f"data: {json.dumps({'type': 'token', 'data': '⚠️ Session not found.'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return StreamingResponse(not_found(), media_type="text/event-stream")

    # Resolve user_id from session (stored when session was created)
    user_id = session.get("user_id", "")

    # Save user message
    db.add_message(session_id, "user", content)
    history = db.get_messages(session_id, last_n=10)

    # Per-user & per-session namespaced topic for ChromaDB/Graph isolation
    topic_id = _user_section_collection_id(user_id, session.get("topic_id") or "", session_id=session_id)

    async def event_generator():
        # If LLM not available, send helpful provider-specific error
        if not await ollama.is_available():
            provider = getattr(settings, "LLM_PROVIDER", "gemini").lower()
            if provider == "azure_openai":
                msg = (
                    "⚠️ **Azure OpenAI is not configured.** Set `AZURE_OPENAI_ENDPOINT` "
                    "and grant the application identity access to the deployment."
                )
            elif provider == "gemini":
                msg = (
                    "⚠️ **Gemini API key is not configured.**\n\n"
                    "Please add your Gemini API key in `backend/.env`:\n"
                    "```env\nLLM_PROVIDER=gemini\nGEMINI_API_KEY=your_actual_key\n```"
                )
            else:
                msg = (
                    "⚠️ **Ollama is not running.**\n\n"
                    "To start the local LLM:\n"
                    "```bash\nollama serve\n```\n"
                    "Then pull a model:\n"
                    "```bash\nollama pull llama3.1\n```"
                )
            for char in msg:
                yield f"data: {json.dumps({'type': 'token', 'data': char})}\n\n"
            db.add_message(session_id, "assistant", msg)
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        full_response = ""
        sources_saved = []
        graph_saved = {}

        try:
            async for event_line in graph_rag.query_stream(
                topic_id=topic_id,
                question=content,
                session_messages=history[:-1],
                language=language,
            ):
                yield event_line
                # Parse to collect data for saving
                if event_line.startswith("data: "):
                    try:
                        evt = json.loads(event_line[6:])
                        if evt["type"] == "token":
                            full_response += evt["data"]
                        elif evt["type"] == "sources":
                            sources_saved = evt["data"]
                        elif evt["type"] == "graph_context":
                            graph_saved = evt["data"]
                    except Exception:
                        pass

        except Exception as e:
            error_msg = f"⚠️ Error: {str(e)}"
            yield f"data: {json.dumps({'type': 'token', 'data': error_msg})}\n\n"
            full_response = error_msg
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        # Persist assistant message after stream completes
        if full_response:
            db.add_message(
                session_id, "assistant", full_response,
                metadata={"sources": sources_saved, "graph_context": graph_saved},
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
