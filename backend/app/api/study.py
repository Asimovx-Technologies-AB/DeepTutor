"""
DeepTutor — AI Study Room & GraphRAG API Router (/api/study).

Endpoints:
- POST /upload: Zero-wait parallel ingestion & curriculum roadmap generation
- POST /agent/message: Two-agent reasoning chat (Planner -> Executor)
- POST /topic/core-idea: Normal Mode 4-phase concept breakdown
- POST /topic/doubt: Grounded topic-specific doubt resolution
- GET  /topic/teach/stream: Real-time SSE university lecture stream
- POST /topic/exam: Mixed 3-format exam generator (Written, MCQ, Fill-in-the-blank)
- POST /topic/evaluate: Automated rubric evaluation & grading engine
- POST /export/notes-md: Direct Markdown (.md) attachment download
- GET/POST/DELETE /sessions/*: Physical SQLite session lifecycle management
- GET/POST/DELETE /memory/*: Student episodic memory & learning profile
"""

import os
import uuid
import re
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query, Response, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.config import get_settings
from app.api.auth import get_current_user
from app.services.study_storage import (
    init_session_db,
    save_session_message,
    get_session_messages,
    save_session_topics,
    get_session_topics,
    get_session_documents,
    list_registry_sessions,
    get_registry_session,
    register_or_update_session,
    delete_registry_session,
    get_student_memory,
    add_student_memory_fact,
    reset_student_memory,
)
from app.services.study_doc_processor import doc_processor
from app.services.study_curriculum import extract_topics_and_validate
from app.services.study_agents import (
    planner_agent,
    executor_agent,
    generate_core_idea,
    resolve_topic_doubt,
    stream_teacher_lecture,
    generate_mixed_exam,
    evaluate_exam_submission,
)

router = APIRouter(prefix="/study", tags=["Study Room"])


# ─── Pydantic Request Models ────────────────────────────────────────────────

class AgentMessageRequest(BaseModel):
    message: str
    session_id: str
    user_id: Optional[str] = "default-user"
    subject: Optional[str] = "General Study"
    difficulty: Optional[str] = "Intermediate"
    history: Optional[List[Dict[str, Any]]] = None


class CoreIdeaRequest(BaseModel):
    session_id: str
    topic_id: str
    topic_title: str
    topic_summary: Optional[str] = ""


class TopicDoubtRequest(BaseModel):
    session_id: str
    topic_id: str
    topic_title: str
    question: str
    history: Optional[List[Dict[str, Any]]] = None


class TopicExamRequest(BaseModel):
    session_id: str
    topic_id: str
    topic_title: str


class ExamEvaluationRequest(BaseModel):
    session_id: str
    topic_id: str
    questions: List[Dict[str, Any]]
    answers: Dict[str, str]


class ExportMarkdownRequest(BaseModel):
    markdown: str
    title: Optional[str] = "study_notes"


class CreateSessionRequest(BaseModel):
    subject: Optional[str] = "General Study"
    title: Optional[str] = "New Study Session"


class AddMemoryFactRequest(BaseModel):
    fact: Optional[str] = None
    learning_style: Optional[str] = None
    goal: Optional[str] = None
    weakness: Optional[str] = None
    studied_topic: Optional[str] = None


# ─── 1. Document Upload & Concurrent Ingestion ──────────────────────────────

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    subject: str = Form("General Study"),
    session_id: Optional[str] = Form(None),
    user: dict = Depends(get_current_user)
):
    """
    Zero-wait parallel ingestion:
    - Runs text extraction / VLM OCR and Topic Extraction concurrently via asyncio.gather
    - Intercepts non-academic documents with guardrails
    - Dispatches background table & diagram workers
    """
    settings = get_settings()
    study_id = session_id or str(uuid.uuid4())
    init_session_db(study_id)

    # Save uploaded file to disk
    upload_dir = Path(settings.UPLOAD_DIR) / study_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = str(upload_dir / file.filename)

    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    doc_id = f"doc_{int(uuid.uuid4().int % 10000000)}"

    # Concurrent Execution: Ingestion + Fast Curriculum Reasoning
    async def _safe_extract_topics(sample_text: str):
        return await extract_topics_and_validate(sample_text, subject=subject, filename=file.filename)

    # 1. First run fast-path ingestion
    ingest_result = await doc_processor.ingest_document(
        doc_id=doc_id,
        file_path=file_path,
        file_name=file.filename,
        subject=subject,
        session_id=study_id,
    )

    # 2. Concurrently classify and extract curriculum roadmap
    sample_text = ingest_result.get("sample_text", "")
    is_study_material, message, topics = await _safe_extract_topics(sample_text)

    if not is_study_material:
        raise HTTPException(
            status_code=400,
            detail=f"Relevance Guardrail: {message}"
        )

    # Persist topics to session database
    if topics:
        save_session_topics(study_id, topics)

    # Update global registry with user isolation
    clean_title = Path(file.filename).stem.replace("_", " ").title()
    register_or_update_session(
        session_id=study_id,
        subject=subject,
        title=f"{clean_title} Study Room",
        status="text_ready",
        document_name=file.filename,
        user_id=user["id"]
    )

    # Dispatch Stage 2 & 3 Non-blocking Background Enrichment Workers
    asyncio.create_task(
        doc_processor.run_background_enrichment(study_id, doc_id, file_path)
    )

    return {
        "status": "text_ready",
        "session_id": study_id,
        "doc_id": doc_id,
        "filename": file.filename,
        "page_count": ingest_result.get("page_count", 1),
        "chunk_count": ingest_result.get("chunk_count", 0),
        "topics": topics,
        "message": "Document indexed successfully. Chat and Study Map are now active."
    }


# ─── 2. Two-Agent Reasoning Chat (Planner -> Executor) ───────────────────────

@router.post("/agent/message")
async def send_agent_message(body: AgentMessageRequest):
    """
    Planner-Executor two-agent chat endpoint with FTS5 BM25 retrieval and memory.
    """
    init_session_db(body.session_id)

    # Retrieve previous conversation history before adding new message
    history = body.history
    if not history:
        prev_msgs = get_session_messages(body.session_id, limit=6)
        history = [{"role": m.get("role", "user"), "text": m.get("text", "")} for m in prev_msgs]

    # Record student message in SQLite
    user_msg_id = str(uuid.uuid4())
    save_session_message(
        session_id=body.session_id,
        message_id=user_msg_id,
        role="user",
        text=body.message
    )

    # Agent 1: Planner Agent
    plan = await planner_agent.plan(
        user_query=body.message,
        subject=body.subject or "General Study",
        history=history
    )

    # Agent 2: Executor Agent
    exec_result = await executor_agent.execute(
        user_query=body.message,
        plan=plan,
        session_id=body.session_id,
        user_id=body.user_id or "default-user",
        subject=body.subject or "General Study",
        history=history
    )

    # Record assistant message in SQLite
    assistant_msg_id = str(uuid.uuid4())
    save_session_message(
        session_id=body.session_id,
        message_id=assistant_msg_id,
        role="assistant",
        text=exec_result["response"],
        thought_process=exec_result.get("thought_process", ""),
        quiz_data=exec_result.get("quiz_data"),
        is_explanation=True
    )

    return {
        "id": assistant_msg_id,
        "role": "assistant",
        "text": exec_result["response"],
        "thought_process": exec_result.get("thought_process", ""),
        "sources": exec_result.get("sources", []),
        "quiz_data": exec_result.get("quiz_data"),
        "format": exec_result.get("format", "conceptual"),
        "response_format": exec_result.get("response_format", exec_result.get("format", "conceptual")),
        "export_ready": exec_result.get("export_ready", False),
        "confidence": plan.get("confidence", 0.9)
    }


# ─── 3. Normal Mode: 4-Step Core Idea ───────────────────────────────────────

@router.post("/topic/core-idea")
async def get_topic_core_idea(body: CoreIdeaRequest):
    """Returns 4-step structured breakdown for Normal Mode."""
    return await generate_core_idea(
        session_id=body.session_id,
        topic_id=body.topic_id,
        topic_title=body.topic_title,
        topic_summary=body.topic_summary or ""
    )


# ─── 4. Topic Doubt Resolution ──────────────────────────────────────────────

@router.post("/topic/doubt")
async def post_topic_doubt(body: TopicDoubtRequest):
    """Resolves topic-specific doubts with grounded context."""
    return await resolve_topic_doubt(
        session_id=body.session_id,
        topic_id=body.topic_id,
        topic_title=body.topic_title,
        question=body.question,
        history=body.history
    )


# ─── 5. Teacher Mode: SSE Streaming Lecture ──────────────────────────────────

@router.get("/topic/teach/stream")
async def get_teacher_stream(
    session_id: str = Query(...),
    topic_id: str = Query(...),
    topic_title: str = Query(...)
):
    """Real-time SSE lecture stream across 4 pedagogical phases."""
    return StreamingResponse(
        stream_teacher_lecture(session_id, topic_id, topic_title),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


# ─── 6. Mixed-Format Topic Mastery Examination Engine ───────────────────────

@router.post("/topic/exam")
async def get_topic_exam(body: TopicExamRequest):
    """Generates 3-format mixed exam (Written, MCQ, Fill-in-the-blank)."""
    return await generate_mixed_exam(
        session_id=body.session_id,
        topic_id=body.topic_id,
        topic_title=body.topic_title
    )


@router.post("/topic/evaluate")
async def evaluate_topic_exam(body: ExamEvaluationRequest):
    """Evaluates and scores student exam answers with rubrics."""
    return await evaluate_topic_exam_submission(body)


async def evaluate_topic_exam_submission(body: ExamEvaluationRequest):
    return await evaluate_exam_submission(
        session_id=body.session_id,
        topic_id=body.topic_id,
        questions=body.questions,
        student_answers=body.answers
    )


# ─── 7. Export Suite: Markdown Attachment Download ──────────────────────────

@router.post("/export/notes-md")
async def export_notes_markdown(body: ExportMarkdownRequest):
    """Returns downloadable Markdown (.md) attachment with Content-Disposition."""
    slug = re.sub(r"[^\w\-_]", "_", body.title or "study_notes").lower()
    return Response(
        content=body.markdown,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'attachment; filename="{slug}.md"'
        }
    )


# ─── 8. Workspace & Multi-Session Management ────────────────────────────────

@router.get("/sessions")
async def list_study_sessions(user: dict = Depends(get_current_user)):
    """Lists all active study workspaces for the current user."""
    return list_registry_sessions(user_id=user["id"])


@router.post("/sessions/new")
async def create_new_session(
    body: CreateSessionRequest,
    user: dict = Depends(get_current_user)
):
    """Creates a fresh workspace and initializes physical SQLite DB."""
    new_id = f"session_{int(uuid.uuid4().int % 10000000000)}"
    meta = register_or_update_session(
        session_id=new_id,
        subject=body.subject or "General Study",
        title=body.title or "New Course Workspace",
        user_id=user["id"]
    )
    return meta


@router.get("/sessions/{session_id}")
async def get_session_details(session_id: str, user: dict = Depends(get_current_user)):
    """Loads persisted conversation, topics, and documents for a session."""
    meta = get_registry_session(session_id)
    if not meta:
        meta = register_or_update_session(session_id, user_id=user["id"])
    messages = get_session_messages(session_id)
    topics = get_session_topics(session_id)
    documents = get_session_documents(session_id)

    return {
        "meta": meta,
        "messages": messages,
        "topics": topics,
        "documents": documents
    }


@router.delete("/sessions/{session_id}")
async def delete_study_session(session_id: str):
    """Permanently deletes session, registry entry, and physical SQLite .db."""
    delete_registry_session(session_id)
    return {"success": True, "session_id": session_id}


# ─── 9. Student Episodic Memory ─────────────────────────────────────────────

@router.get("/memory/{user_id}")
async def fetch_student_memory(user_id: str):
    """Fetches student learning profile, goals, weaknesses, and facts."""
    return get_student_memory(user_id)


@router.post("/memory/{user_id}/fact")
async def update_student_memory_fact(user_id: str, body: AddMemoryFactRequest):
    """Adds or updates student goal, preference, or struggle area."""
    return add_student_memory_fact(
        user_id=user_id,
        fact=body.fact,
        learning_style=body.learning_style,
        goal=body.goal,
        weakness=body.weakness,
        studied_topic=body.studied_topic
    )


@router.delete("/memory/{user_id}")
async def clear_student_memory(user_id: str):
    """Resets memory for a specific student."""
    return {"success": reset_student_memory(user_id)}
