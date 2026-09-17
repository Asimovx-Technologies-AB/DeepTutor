import json
import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.core.database import get_db, SessionLocal
from app.models.session import StudySession, ChatMessage
from app.models.relationship import KnowledgeRelationship
from app.tutoring.orchestrator import TutoringQueryOrchestrator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["Chat Interface"])


@router.get("/sessions")
def list_chat_sessions(
    scope: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Lists chat sessions."""
    sessions = db.query(StudySession).order_by(StudySession.last_active.desc()).all()
    return [
        {
            "id": s.id,
            "session_title": s.title,
            "topic_id": (s.session_metadata or {}).get("topic_id") or s.id,
            "document_id": s.document_id,
            "document_name": s.document_name,
            "created_at": s.created_at.isoformat(),
            "updated_at": s.last_active.isoformat() if s.last_active else s.created_at.isoformat(),
            "message_count": s.message_count or 0,
        }
        for s in sessions
    ]


@router.post("/sessions")
def create_chat_session(
    payload: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """Creates a new chat session."""
    topic_id = payload.get("topic_id")
    title = payload.get("session_title", "General Tutoring")
    metadata = {"topic_id": topic_id} if topic_id else {}

    doc_id = None
    doc_name = None
    if topic_id:
        from app.models.document import Document
        doc = db.query(Document).filter(Document.id == topic_id).first()
        if doc:
            doc_id = doc.id
            doc_name = doc.title or doc.filename
    
    sess = StudySession(
        title=title,
        subject=title,
        document_id=doc_id,
        document_name=doc_name,
        session_metadata=metadata,
        status="active"
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return {
        "id": sess.id,
        "session_title": sess.title,
        "topic_id": topic_id or sess.id,
        "document_name": sess.document_name,
        "created_at": sess.created_at.isoformat(),
        "updated_at": sess.last_active.isoformat() if sess.last_active else sess.created_at.isoformat(),
        "message_count": sess.message_count or 0,
    }


@router.get("/sessions/{session_id}")
def get_chat_session(
    session_id: str,
    db: Session = Depends(get_db)
):
    """Gets details of a single chat session."""
    sess = db.query(StudySession).filter(StudySession.id == session_id).first()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found.")
    return {
        "id": sess.id,
        "session_title": sess.title,
        "topic_id": (sess.session_metadata or {}).get("topic_id") or sess.id,
        "document_name": sess.document_name,
        "created_at": sess.created_at.isoformat(),
        "updated_at": sess.last_active.isoformat() if sess.last_active else sess.created_at.isoformat(),
        "message_count": sess.message_count or 0,
    }


@router.delete("/sessions/{session_id}")
def delete_chat_session(
    session_id: str,
    db: Session = Depends(get_db)
):
    """Deletes a chat session."""
    sess = db.query(StudySession).filter(StudySession.id == session_id).first()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found.")
    db.delete(sess)
    db.commit()
    return {"status": "success"}


@router.get("/sessions/{session_id}/messages")
def get_chat_messages(
    session_id: str,
    db: Session = Depends(get_db)
):
    """Retrieves conversation history for chat interface."""
    msgs = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at).all()
    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "citations": m.citations or [],
            "sources": m.citations or [],
            "metadata": {"sources": m.citations or []},
            "grounding_score": m.grounding_score or 1.0,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in msgs
    ]


# ─── Chat Streaming Endpoint (SSE) ──────────────────────────────────────────

@router.get("/sessions/{session_id}/message/stream")
def stream_chat_message(
    session_id: str,
    content: Optional[str] = Query(None),
    query: Optional[str] = Query(None),
    language: str = Query("english"),
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Server-Sent Events (SSE) streaming endpoint consumed by streamChatMessage
    in frontend/src/services/api.ts.
    Yields token, sources, graph_context, grounding, done.
    """
    prompt = content or query or "Hello"
    # Fetch connected graph relationships for graph_context event
    sess = db.query(StudySession).filter(StudySession.id == session_id).first()
    graph_data = []
    if sess and sess.document_id:
        rels = db.query(KnowledgeRelationship).filter(KnowledgeRelationship.document_id == sess.document_id).limit(10).all()
        graph_data = [
            {
                "source": r.source_chunk_id,
                "target": r.target_chunk_id,
                "relation": r.relation_type,
                "weight": r.weight
            }
            for r in rels
        ]

    def event_generator():
        # Emit graph_context event early
        yield f"data: {json.dumps({'type': 'graph_context', 'data': graph_data})}\n\n"

        # Dedicated session ensures active DB connection throughout stream completion
        with SessionLocal() as stream_db:
            for event in TutoringQueryOrchestrator.stream_query_response(
                session=stream_db,
                raw_query=prompt,
                session_id=session_id
            ):
                evt_type = event.get("type")
                if evt_type == "token":
                    token_str = event.get("data") or event.get("token") or ""
                    yield f"data: {json.dumps({'type': 'token', 'data': token_str})}\n\n"
                elif evt_type in ("sources", "grounding", "done", "phase_start", "phase_end", "flashcard_quiz", "suggestions", "teacher_state", "checkpoint"):
                    yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/sessions/{session_id}/message")
def send_chat_message(
    session_id: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """Non-streaming chat message endpoint."""
    content = payload.get("content", "")
    result = TutoringQueryOrchestrator.process_query(
        session=db,
        raw_query=content,
        session_id=session_id
    )
    return {
        "role": "assistant",
        "content": result["content"],
        "type": result.get("type", "chat_message"),
        "flashcard_quiz": result.get("flashcard_quiz"),
        "citations": result.get("citations", []),
        "grounding_score": result.get("grounding_score", 1.0),
    }
