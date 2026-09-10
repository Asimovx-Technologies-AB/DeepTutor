import os
import shutil
from pathlib import Path
import asyncio
import json
import re
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends, Query, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.api.auth import get_current_user, decode_token, get_user_from_token, get_user_from_header_or_query
from app.core import database as db
from app.core.config import get_settings
from app.rag.llm_client import llm_client
from app.rag.query_analyzer import query_analyzer
from app.rag.decision_agent import decision_agent
from app.rag.doc_processor import doc_processor
from app.rag.sqlite_fts_store import get_session_store
from app.rag.session_manager import session_manager
from app.rag.user_memory import user_memory_store

settings = get_settings()
router = APIRouter(prefix="/chat", tags=["chat"])

# High-performance in-memory semantic / exact query response cache (<20ms response)
_response_cache: Dict[str, Dict[str, Any]] = {}


def _make_cache_key(session_id: str, query: str) -> str:
    norm = re.sub(r"\s+", " ", query.lower().strip())
    return f"{session_id}:{norm}"


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
    session = await asyncio.to_thread(
        db.create_session,
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
    sessions = await asyncio.to_thread(db.get_sessions_for_user, user["id"])
    return sessions


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    user: dict = Depends(get_current_user),
):
    session = await asyncio.to_thread(db.get_session, session_id)
    if not session or session.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/sessions/{session_id}/messages")
async def get_messages(
    session_id: str,
    user: dict = Depends(get_current_user),
):
    session = await asyncio.to_thread(db.get_session, session_id)
    if not session or session.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = await asyncio.to_thread(db.get_messages, session_id)
    return messages


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    user: dict = Depends(get_current_user),
):
    user_id = user["id"]
    del_result = await asyncio.to_thread(db.delete_session, session_id, user_id=user_id)
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


# ─── Non-streaming message (Speculatively Parallelized) ─────────────────────────
@router.post("/sessions/{session_id}/message")
async def send_message(
    session_id: str,
    body: MessageRequest,
    user: dict = Depends(get_current_user),
):
    session = await asyncio.to_thread(db.get_session, session_id)
    if not session or session.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Session not found")

    cache_key = _make_cache_key(session_id, body.content)
    if cache_key in _response_cache:
        cached = _response_cache[cache_key]
        # Return instant cached response in <1ms
        return cached

    # Save user message
    await asyncio.to_thread(db.add_message, session_id, "user", body.content)

    if not await llm_client.is_available():
        msg = (
            "⚠️ **OpenAI API key is not configured or rate limited.**\n\n"
            "Please ensure `OPENAI_API_KEY` is set in `backend/.env`."
        )
        return await asyncio.to_thread(db.add_message, session_id, "assistant", msg)

    # ── Fetch history first to supply conversation context to query planner ──
    subject_title = session.get("title") or session.get("topic_id")
    history = await asyncio.to_thread(db.get_messages, session_id, last_n=10)
    hist_messages = [{"role": m.get("role", ""), "content": m.get("content", "")} for m in (history[:-1] if history else [])]

    # ── Extract pending_followup from the last assistant message's metadata ──
    prev_followup = None
    for h in reversed(history[:-1] if history else []):
        if h.get("role") == "assistant":
            h_meta = h.get("metadata") or {}
            prev_followup = h_meta.get("pending_followup")
            break

    async def _fetch_context():
        ctx, status_note, meta = await asyncio.to_thread(doc_processor.retrieve_context, doc_id=session_id, query=body.content)
        if not ctx:
            store = get_session_store(session_id)
            results = await asyncio.to_thread(store.search, body.content, limit=4)
            if results:
                ctx = "\n\n".join([f"[{r.get('source_type', 'text')} page {r.get('page', 1)}]\n{r.get('content', '')}" for r in results])
        return ctx, status_note, meta

    async def _fetch_plan():
        return await query_analyzer.analyze_query(
            message=body.content,
            current_subject=subject_title,
            history=hist_messages,
            pending_followup=prev_followup,
        )

    (context, status_note, meta), plan = await asyncio.gather(
        _fetch_context(),
        _fetch_plan(),
    )

    # Generate grounded response via Decision Agent
    res = await decision_agent.analyze_and_respond(
        message=body.content,
        current_subject=session.get("title"),
        history=[{"role": m.get("role", ""), "content": m.get("content", "")} for m in history[:-1]],
        context=context,
        doc_status_note=status_note,
        user_id=str(user["id"]),
        query_analysis=plan,
        pending_followup=prev_followup,
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

    msg = await asyncio.to_thread(
        db.add_message,
        session_id, "assistant", reply_text,
        metadata={
            "sources": sources,
            "graph_context": graph_context,
            "response_format": response_format,
            "export_ready": export_ready,
            "pending_followup": res.get("pending_followup"),
        },
    )
    if isinstance(msg, dict):
        msg["response_format"] = response_format
        msg["export_ready"] = export_ready

    # Cache response (bounded to 1000 items)
    if len(_response_cache) < 1000:
        _response_cache[cache_key] = msg

    return msg


# ─── SSE Streaming message (High-Speed Turbo Stream) ────────────────────────────
@router.get("/sessions/{session_id}/message/stream")
async def stream_message(
    session_id: str,
    content: str = Query(...),
    token: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
    language: str = Query("english"),
):
    user = get_user_from_header_or_query(authorization=authorization, token=token)
    session = await asyncio.to_thread(db.get_session, session_id)
    if not session or session.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Session not found")

    user_id = str(session.get("user_id", user["id"]))
    await asyncio.to_thread(db.add_message, session_id, "user", content)

    # ── Fetch history first to supply conversation context to query planner ──
    subject_title = session.get("title") or session.get("topic_id")
    history = await asyncio.to_thread(db.get_messages, session_id, last_n=10)
    hist_messages = [{"role": m.get("role", ""), "content": m.get("content", "")} for m in (history[:-1] if history else [])]

    # ── Extract pending_followup from the last assistant message's metadata ──
    prev_followup = None
    for h in reversed(history[:-1] if history else []):
        if h.get("role") == "assistant":
            h_meta = h.get("metadata") or {}
            prev_followup = h_meta.get("pending_followup")
            break

    async def _fetch_context():
        ctx, status_note, meta = await asyncio.to_thread(doc_processor.retrieve_context, doc_id=session_id, query=content)
        if not ctx:
            store = get_session_store(session_id)
            results = await asyncio.to_thread(store.search, content, limit=4)
            if results:
                ctx = "\n\n".join([f"[{r.get('source_type', 'text')} page {r.get('page', 1)}]\n{r.get('content', '')}" for r in results])
        return ctx, status_note, meta

    async def _fetch_plan():
        return await query_analyzer.analyze_query(
            message=content,
            current_subject=subject_title,
            history=hist_messages,
            pending_followup=prev_followup,
        )

    (context, status_note, meta), plan = await asyncio.gather(
        _fetch_context(),
        _fetch_plan(),
    )

    # Async trigger memory extraction in background
    asyncio.create_task(user_memory_store.auto_extract_and_update(user_id, content, history))

    async def event_generator():
        if not await llm_client.is_available():
            msg = "⚠️ **AI Service unavailable.** Please check `OPENAI_API_KEY` in `backend/.env`."
            for char in msg:
                yield f"data: {json.dumps({'type': 'token', 'data': char})}\n\n"
            await asyncio.to_thread(db.add_message, session_id, "assistant", msg)
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        sources = [{"source": session.get("title", "Study Material"), "page": 1, "text": context[:300]}] if context else []
        resp_fmt = plan.get("response_format", "conceptual")

        yield f"data: {json.dumps({'type': 'sources', 'data': sources})}\n\n"
        yield f"data: {json.dumps({'type': 'graph_context', 'data': {'retrieved': len(sources), 'response_format': resp_fmt}})}\n\n"

        # Build concise, high-speed streaming prompt
        followup_note = ""
        if prev_followup:
            followup_note = (
                f"\n\nPREVIOUS OFFER: Your previous message offered: {json.dumps(prev_followup)}. "
                "If the student says 'yes' or agrees, you MUST fulfill that offer in addition to anything else they ask."
            )

        system_instruction = (
            "You are DeepTutor, an elite academic AI tutor. "
            "Explain concepts clearly, intuitively, and rigorously grounded strictly in the provided study context. "
            "When the student asks to 'create an image', 'draw an image/diagram', 'show a flowchart', or 'visualize' a concept, NEVER state that you cannot generate images; instead, immediately generate a rich, clean Mermaid diagram in a fenced ```mermaid ... ``` code block to visually represent it in the Markdown viewer! "
            "Always wrap mathematical formulas and equations in standalone LaTeX blocks `$$ ... $$` or inline `$ ... $`. "
            "Present comparisons in clean Markdown tables. Strictly zero emojis.\n\n"
            f"STUDY CONTEXT:\n{context or 'General course material'}\n\n"
            f"RECOMMENDED FORMAT: {resp_fmt}"
            f"{followup_note}"
        )

        messages = [{"role": "system", "content": system_instruction}]
        for m in history[:-1]:
            messages.append({"role": m.get("role", "user"), "content": m.get("content", "")})
        messages.append({"role": "user", "content": content})

        full_response = ""
        try:
            async for token_str in llm_client.chat_stream(messages, max_tokens=1500):
                full_response += token_str
                yield f"data: {json.dumps({'type': 'token', 'data': token_str})}\n\n"
        except Exception as e:
            err = f"\n\n⚠️ Error during response generation: {e}"
            full_response += err
            yield f"data: {json.dumps({'type': 'token', 'data': err})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

        if full_response:
            await asyncio.to_thread(
                db.add_message,
                session_id, "assistant", full_response,
                metadata={
                    "sources": sources,
                    "graph_context": {"context_length": len(context), "response_format": resp_fmt},
                },
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
