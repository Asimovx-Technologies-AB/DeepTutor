"""
Chat API with GraphRAG-powered streaming.
SSE stream emits multi-type events: token | sources | graph_context | done

Each user's documents are stored in their own ChromaDB collection, namespaced as:
  {user_id}_{topic_id}
"""
import asyncio
import json
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.api.auth import get_current_user, decode_token
from app.core import database as db
from app.rag.graph_rag import graph_rag
from app.rag.ollama_client import ollama
from app.rag.section_scope import get_section_collection_id

router = APIRouter(prefix="/chat", tags=["chat"])


class CreateSessionRequest(BaseModel):
    topic_id: Optional[str] = ""
    session_title: str = "New Chat Session"


class MessageRequest(BaseModel):
    content: str


def _user_section_collection_id(user_id: str, topic_id: str, session_id: str = "") -> str:
    """Build a per-user section collection id — isolates data by user and session section."""
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
async def list_sessions(user: dict = Depends(get_current_user)):
    sessions = db.get_sessions_for_user(user["id"])
    return sorted(sessions, key=lambda s: s["started_at"], reverse=True)


@router.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str, user: dict = Depends(get_current_user)):
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return db.get_messages(session_id)


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, user: dict = Depends(get_current_user)):
    db.delete_session(session_id)
    return {"ok": True}


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
        # If Ollama not available, send helpful error
        if not await ollama.is_available():
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
