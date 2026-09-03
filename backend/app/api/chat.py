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
from app.rag.ollama_client import ollama
from app.rag.query_analyzer import query_analyzer
from app.rag.decision_agent import decision_agent
from app.rag.doc_processor import doc_processor
from app.rag.sqlite_fts_store import get_session_store
from app.rag.session_manager import session_manager

settings = get_settings()
router = APIRouter(prefix="/chat", tags=["chat"])


class CreateSessionRequest(BaseModel):
    topic_id: Optional[str] = ""
    session_title: str = "New Chat Session"


class MessageRequest(BaseModel):
    content: str
    language: Optional[str] = "english"


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
    try:
        session_manager.create_session(
            subject=body.session_title,
            title=body.session_title,
            user_id=user["id"]
        )
    except Exception:
        pass
    return session


@router.get("/sessions")
async def list_sessions(
    scope: Optional[str] = Query(None),
    user: dict = Depends(get_current_user)
):
    sessions = db.get_sessions_for_user(user["id"])
    return sessions


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    user: dict = Depends(get_current_user),
):
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/sessions/{session_id}/messages")
async def get_messages(
    session_id: str,
    user: dict = Depends(get_current_user),
):
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = db.get_messages(session_id)
    return messages


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    user: dict = Depends(get_current_user),
):
    user_id = user["id"]
    del_result = db.delete_session(session_id, user_id=user_id)
    if not del_result.get("deleted"):
        raise HTTPException(status_code=404, detail="Session not found or access denied")

    try:
        session_manager.delete_session(session_id)
    except Exception:
        pass

    # Clean up uploaded physical files
    deleted_docs = del_result.get("deleted_docs", [])
    for doc in deleted_docs:
        file_path = doc.get("file_path")
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
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

    if not await ollama.is_available():
        msg = (
            "⚠️ **Gemini API key is not configured or rate limited.**\n\n"
            "Please ensure `GEMINI_API_KEY` is set in `backend/.env`."
        )
        return db.add_message(session_id, "assistant", msg)

    # 1. Retrieve context
    context, status_note, meta = doc_processor.retrieve_context(doc_id=session_id, query=body.content)
    if not context:
        store = get_session_store(session_id)
        results = store.search(body.content, limit=4)
        if results:
            context = "\n\n".join([f"[{r.get('source_type', 'text')} page {r.get('page', 1)}]\n{r.get('content', '')}" for r in results])

    # 2. Plan reasoning
    plan = await query_analyzer.analyze_query(
        message=body.content,
        current_subject=session.get("title") or session.get("topic_id"),
        history=[{"role": m.get("role", ""), "content": m.get("content", "")} for m in history[:-1]],
    )

    # 3. Generate grounded response
    res = await decision_agent.analyze_and_respond(
        message=body.content,
        current_subject=session.get("title"),
        history=[{"role": m.get("role", ""), "content": m.get("content", "")} for m in history[:-1]],
        context=context,
        doc_status_note=status_note,
        user_id=str(user["id"]),
        query_analysis=plan,
    )

    reply_text = res.get("reply", "")
    sources = [{"source": session.get("title", "Study Material"), "page": 1, "text": context[:300]}] if context else []
    response_format = res.get("response_format", "conceptual")
    export_ready = res.get("export_ready", False)

    graph_context = {
        "thought_process": res.get("thought_process", ""),
        "concepts": res.get("concepts_covered", []),
        "response_format": response_format,
        "export_ready": export_ready,
    }

    msg = db.add_message(
        session_id, "assistant", reply_text,
        metadata={
            "sources": sources,
            "graph_context": graph_context,
            "response_format": response_format,
            "export_ready": export_ready,
        },
    )
    if isinstance(msg, dict):
        msg["response_format"] = response_format
        msg["export_ready"] = export_ready
    return msg


# ─── SSE Streaming message ──────────────────────────────────────────────────────
@router.get("/sessions/{session_id}/message/stream")
async def stream_message(
    session_id: str,
    content: str = Query(...),
    token: str = Query(""),
    language: str = Query("english"),
):
    session = db.get_session(session_id)
    if not session:
        async def not_found():
            yield f"data: {json.dumps({'type': 'token', 'data': '⚠️ Session not found.'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return StreamingResponse(not_found(), media_type="text/event-stream")

    user_id = session.get("user_id", "")
    db.add_message(session_id, "user", content)
    history = db.get_messages(session_id, last_n=10)

    async def event_generator():
        if not await ollama.is_available():
            msg = "⚠️ **AI Service unavailable.** Please check `GEMINI_API_KEY` in `backend/.env`."
            for char in msg:
                yield f"data: {json.dumps({'type': 'token', 'data': char})}\n\n"
            db.add_message(session_id, "assistant", msg)
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        # 1. Retrieve context
        context, status_note, meta = doc_processor.retrieve_context(doc_id=session_id, query=content)
        if not context:
            store = get_session_store(session_id)
            results = store.search(content, limit=4)
            if results:
                context = "\n\n".join([f"[{r.get('source_type', 'text')} page {r.get('page', 1)}]\n{r.get('content', '')}" for r in results])

        sources = [{"source": session.get("title", "Study Material"), "page": 1, "text": context[:300]}] if context else []
        yield f"data: {json.dumps({'type': 'sources', 'data': sources})}\n\n"
        yield f"data: {json.dumps({'type': 'graph_context', 'data': {'retrieved': len(sources)}})}\n\n"

        # 2. Build streaming prompt
        messages = [
            {
                "role": "system",
                "content": (
                    "You are DeepTutor, an elite academic AI tutor. "
                    "Explain the concept clearly, intuitively, and rigorously based on the context below. "
                    "Use clean human-readable mathematics. Strictly ZERO emojis.\n\n"
                    f"STUDY CONTEXT:\n{context or 'General course topic'}"
                )
            }
        ]
        for m in history[:-1]:
            messages.append({"role": m.get("role", "user"), "content": m.get("content", "")})
        messages.append({"role": "user", "content": content})

        full_response = ""
        try:
            async for token_str in ollama.chat_stream(messages):
                full_response += token_str
                yield f"data: {json.dumps({'type': 'token', 'data': token_str})}\n\n"
        except Exception as e:
            err = f"\n\n⚠️ Error during response generation: {e}"
            full_response += err
            yield f"data: {json.dumps({'type': 'token', 'data': err})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

        if full_response:
            db.add_message(
                session_id, "assistant", full_response,
                metadata={"sources": sources, "graph_context": {"context_length": len(context)}},
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
