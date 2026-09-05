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

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query, Response, Depends, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.config import get_settings
from app.api.auth import get_current_user, get_user_from_token, get_user_from_header_or_query


def verify_session_ownership(session_id: str, user_id: str) -> dict:
    """Verify session exists and belongs to the authenticated user. Raise 403 on ownership violation."""
    from app.services.study_storage import get_registry_session
    meta = get_registry_session(session_id)
    if meta:
        if meta.get("user_id") and meta.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="Access denied: session belongs to another user")
        return meta

    try:
        from app.core import database as db
        s = db.get_session(session_id)
        if s:
            if s.get("user_id") and s.get("user_id") != user_id:
                raise HTTPException(status_code=403, detail="Access denied: session belongs to another user")
            return s
    except Exception:
        pass

    return {}

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
    generate_lecture_diagnostic,
    evaluate_lecture_diagnostic,
    generate_phase_checkpoint,
    evaluate_checkpoint_response,
    handle_lecture_pause_ask,
    generate_teach_back_prompt,
    evaluate_teach_back_submission,
    generate_mixed_exam,
    evaluate_exam_submission,
)
from app.services.study_storage import (
    get_lecture_session,
    get_lecture_checkpoints,
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
    upload_root = Path(settings.UPLOAD_DIR).resolve()

    if session_id:
        clean_sid = session_id.strip()
        if not re.match(r"^[a-zA-Z0-9_\-]{1,64}$", clean_sid) or ".." in clean_sid:
            raise HTTPException(status_code=400, detail="Invalid session_id format")
        study_id = clean_sid
        verify_session_ownership(study_id, user["id"])
    else:
        study_id = str(uuid.uuid4())

    init_session_db(study_id)

    # Sanitize filename and check path traversal
    safe_filename = Path(file.filename).name
    if not safe_filename or ".." in safe_filename or "/" in safe_filename or "\\" in safe_filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    upload_dir = (upload_root / study_id).resolve()
    file_path_obj = (upload_dir / safe_filename).resolve()

    if not str(file_path_obj).startswith(str(upload_root)):
        raise HTTPException(status_code=400, detail="Path traversal attempt detected")

    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = str(file_path_obj)

    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    doc_id = f"doc_{int(uuid.uuid4().int % 10000000)}"
    clean_title = Path(safe_filename).stem.replace("_", " ").title()
    effective_subject = subject.strip() if (subject and subject.strip() and subject.strip() != "General Study") else clean_title

    # Concurrent Execution: Ingestion + Fast Curriculum Reasoning
    async def _safe_extract_topics(sample_text: str):
        return await extract_topics_and_validate(sample_text, subject=effective_subject, filename=file.filename)

    # Check if session already has documents
    existing_docs = get_session_documents(study_id)
    is_existing_session = bool(existing_docs and len(existing_docs) > 0)

    # 1. First run fast-path ingestion
    ingest_result = await doc_processor.ingest_document(
        doc_id=doc_id,
        file_path=file_path,
        file_name=file.filename,
        subject=effective_subject,
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

    # Persist topics to session database - merge if existing session
    all_session_topics = topics
    if topics:
        for t in topics:
            t["document_name"] = file.filename
        all_session_topics = save_session_topics(study_id, topics, append=is_existing_session, document_name=file.filename)

    # Update global registry with user isolation & multi-material tracking
    existing_reg = get_registry_session(study_id)
    prev_title = existing_reg.get("title") if existing_reg else None
    is_generic_title = not prev_title or prev_title in ("New Study Workspace", "New Course Workspace", "Study Room Session", "Default Study Room")
    session_title = f"{clean_title} Study Room" if is_generic_title else prev_title

    register_or_update_session(
        session_id=study_id,
        subject=effective_subject,
        title=session_title,
        status="text_ready",
        document_name=file.filename,
        user_id=user["id"]
    )

    # Record in main database so it persists in the global study materials library
    try:
        from app.core import database as db
        from app.rag.document_dedup import get_file_hash, link_document_to_session
        doc_hash = get_file_hash(content)
        ext = Path(file.filename).suffix.lower().lstrip(".")
        db_doc = db.create_document(
            user_id=user["id"],
            topic_id=study_id,
            file_name=file.filename,
            file_path=file_path,
            file_type=ext,
            doc_hash=doc_hash,
            status="completed",
        )
        link_document_to_session(doc_hash, study_id, user["id"], db=db)
        topic_titles = [t.get("title", "") for t in (all_session_topics or topics) if t.get("title")]
        db.update_document_stats(
            doc_id=db_doc["id"],
            indexed=True,
            entity_count=len(topic_titles),
            chunk_count=ingest_result.get("chunk_count", 0),
            key_topics=[f"__subject__:{effective_subject}", *topic_titles],
            status="completed",
        )
    except Exception as e:
        print(f"[study.upload] Warning: failed to save document to main db: {e}")

    # Dispatch Stage 2 & 3 Non-blocking Background Enrichment Workers
    asyncio.create_task(
        doc_processor.run_background_enrichment(study_id, doc_id, file_path)
    )

    all_docs = get_session_documents(study_id)
    return {
        "status": "text_ready",
        "session_id": study_id,
        "doc_id": doc_id,
        "filename": file.filename,
        "documents": all_docs,
        "document_count": len(all_docs),
        "page_count": ingest_result.get("page_count", 1),
        "chunk_count": ingest_result.get("chunk_count", 0),
        "topics": all_session_topics or topics,
        "message": f"'{file.filename}' added to workspace ({len(all_docs)} total material{'s' if len(all_docs) > 1 else ''}). Chat and Study Map are now active."
    }


# ─── 2. Two-Agent Reasoning Chat (Planner -> Executor) ───────────────────────

@router.post("/agent/message")
async def send_agent_message(
    body: AgentMessageRequest,
    user: dict = Depends(get_current_user)
):
    """
    Planner-Executor two-agent chat endpoint with FTS5 BM25 retrieval and memory.
    """
    verify_session_ownership(body.session_id, user["id"])
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
        user_id=user["id"],
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
        "is_synthetic_textbook": exec_result.get("is_synthetic_textbook", False),
        "level": exec_result.get("level"),
        "level_name": exec_result.get("level_name"),
        "confidence": plan.get("confidence", 0.9)
    }


# ─── 3. Normal Mode: 4-Step Core Idea ───────────────────────────────────────

@router.post("/topic/core-idea")
async def get_topic_core_idea(
    body: CoreIdeaRequest,
    user: dict = Depends(get_current_user)
):
    """Returns 4-step structured breakdown for Normal Mode."""
    verify_session_ownership(body.session_id, user["id"])
    return await generate_core_idea(
        session_id=body.session_id,
        topic_id=body.topic_id,
        topic_title=body.topic_title,
        topic_summary=body.topic_summary or ""
    )


# ─── 4. Topic Doubt Resolution ──────────────────────────────────────────────

@router.post("/topic/doubt")
async def post_topic_doubt(
    body: TopicDoubtRequest,
    user: dict = Depends(get_current_user)
):
    """Resolves topic-specific doubts with grounded context."""
    verify_session_ownership(body.session_id, user["id"])
    return await resolve_topic_doubt(
        session_id=body.session_id,
        topic_id=body.topic_id,
        topic_title=body.topic_title,
        question=body.question,
        history=body.history
    )


# ─── 5. Teacher Mode: Interactive Masterclass Lecture Engine ─────────────────

class DiagnosticStartRequest(BaseModel):
    session_id: str
    topic_id: str
    topic_title: str


@router.post("/topic/teach/diagnostic/start")
async def start_diagnostic_endpoint(
    body: DiagnosticStartRequest,
    user: dict = Depends(get_current_user)
):
    """Requirement 1: Generates 1-question diagnostic probe and initializes lecture session."""
    verify_session_ownership(body.session_id, user["id"])
    return await generate_lecture_diagnostic(
        session_id=body.session_id,
        topic_id=body.topic_id,
        topic_title=body.topic_title
    )


class DiagnosticSubmitRequest(BaseModel):
    session_id: str
    topic_id: str
    topic_title: str
    question: str
    student_answer: str
    lecture_id: Optional[str] = None


@router.post("/topic/teach/diagnostic/submit")
async def submit_diagnostic_endpoint(
    body: DiagnosticSubmitRequest,
    user: dict = Depends(get_current_user)
):
    """Requirement 1: Evaluates diagnostic answer and branches lecture level (novice/standard/advanced)."""
    verify_session_ownership(body.session_id, user["id"])
    return await evaluate_lecture_diagnostic(
        session_id=body.session_id,
        topic_id=body.topic_id,
        topic_title=body.topic_title,
        question=body.question,
        student_answer=body.student_answer,
        lecture_id=body.lecture_id
    )


@router.get("/topic/teach/stream")
async def get_teacher_stream(
    session_id: str = Query(...),
    topic_id: str = Query(...),
    topic_title: str = Query(...),
    override_syllabus: bool = Query(False),
    diagnostic_level: str = Query("standard"),
    lecture_id: Optional[str] = Query(None),
    token: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
):
    """Real-time SSE lecture stream across 4 enforced pedagogical phases with continuity and KaTeX math."""
    user = get_user_from_header_or_query(authorization=authorization, token=token)
    verify_session_ownership(session_id, user["id"])
    return StreamingResponse(
        stream_teacher_lecture(
            session_id=session_id,
            topic_id=topic_id,
            topic_title=topic_title,
            override_syllabus=override_syllabus,
            diagnostic_level=diagnostic_level,
            lecture_id=lecture_id
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


class CheckpointGenerateRequest(BaseModel):
    session_id: str
    topic_title: str
    phase_name: str
    phase_content: str
    lecture_id: Optional[str] = None


@router.post("/topic/teach/checkpoint/generate")
async def generate_checkpoint_endpoint(
    body: CheckpointGenerateRequest,
    user: dict = Depends(get_current_user)
):
    """Requirement 3: Generates an active-recall checkpoint question for the phase."""
    verify_session_ownership(body.session_id, user["id"])
    return await generate_phase_checkpoint(
        session_id=body.session_id,
        topic_title=body.topic_title,
        phase_name=body.phase_name,
        phase_content=body.phase_content,
        lecture_id=body.lecture_id
    )


class CheckpointSubmitRequest(BaseModel):
    session_id: str
    topic_title: str
    phase_name: str
    question_prompt: str
    correct_answer: str
    student_response: str
    checkpoint_id: Optional[str] = None


@router.post("/topic/teach/checkpoint/submit")
async def submit_checkpoint_endpoint(
    body: CheckpointSubmitRequest,
    user: dict = Depends(get_current_user)
):
    """Requirement 3: Evaluates checkpoint response and provides modal remediation if incorrect."""
    verify_session_ownership(body.session_id, user["id"])
    return await evaluate_checkpoint_response(
        session_id=body.session_id,
        topic_title=body.topic_title,
        phase_name=body.phase_name,
        question_prompt=body.question_prompt,
        correct_answer=body.correct_answer,
        student_response=body.student_response,
        checkpoint_id=body.checkpoint_id
    )


class PauseAskRequest(BaseModel):
    session_id: str
    topic_title: str
    current_phase: str
    accumulated_context: str
    student_question: str
    lecture_id: Optional[str] = None
    token_offset: Optional[int] = 0


@router.post("/topic/teach/pause/ask")
async def pause_ask_endpoint(
    body: PauseAskRequest,
    user: dict = Depends(get_current_user)
):
    """Requirement 4: In-line Pause & Ask without losing lecture context or resetting stream."""
    verify_session_ownership(body.session_id, user["id"])
    return await handle_lecture_pause_ask(
        session_id=body.session_id,
        topic_title=body.topic_title,
        current_phase=body.current_phase,
        accumulated_context=body.accumulated_context,
        student_question=body.student_question,
        lecture_id=body.lecture_id,
        token_offset=body.token_offset or 0
    )


class TeachBackPromptRequest(BaseModel):
    session_id: str
    topic_id: str
    topic_title: str
    lecture_id: Optional[str] = None


@router.post("/topic/teach/teach-back/prompt")
async def teach_back_prompt_endpoint(
    body: TeachBackPromptRequest,
    user: dict = Depends(get_current_user)
):
    """Requirement 5: Prompts student for Feynman-technique teach-back."""
    verify_session_ownership(body.session_id, user["id"])
    return await generate_teach_back_prompt(
        session_id=body.session_id,
        topic_id=body.topic_id,
        topic_title=body.topic_title,
        lecture_id=body.lecture_id
    )


class TeachBackSubmitRequest(BaseModel):
    session_id: str
    topic_id: str
    topic_title: str
    submission_text: str
    lecture_id: Optional[str] = None


@router.post("/topic/teach/teach-back/submit")
async def teach_back_submit_endpoint(
    body: TeachBackSubmitRequest,
    user: dict = Depends(get_current_user)
):
    """Requirement 5 & 7: Evaluates teach-back, grades mastery, and outputs final smart notes summary."""
    verify_session_ownership(body.session_id, user["id"])
    return await evaluate_teach_back_submission(
        session_id=body.session_id,
        topic_id=body.topic_id,
        topic_title=body.topic_title,
        submission_text=body.submission_text,
        lecture_id=body.lecture_id
    )


@router.get("/topic/teach/session/{session_id}/{lecture_id}")
async def get_lecture_session_endpoint(
    session_id: str,
    lecture_id: str,
    user: dict = Depends(get_current_user)
):
    """Retrieves full durable lecture session state, checkpoints, and notes."""
    verify_session_ownership(session_id, user["id"])
    session = get_lecture_session(session_id, lecture_id)
    if not session:
        raise HTTPException(status_code=404, detail="Lecture session not found")
    checkpoints = get_lecture_checkpoints(session_id, lecture_id)
    return {
        "session": session,
        "checkpoints": checkpoints
    }


class FlashcardDeckRequest(BaseModel):
    session_id: str
    topic_id: str
    topic_title: str
    subject: Optional[str] = "General Study"
    num_cards: Optional[int] = 8
    explanation_level: Optional[str] = "standard"
    initial_mode: Optional[str] = "flashcards"


@router.post("/flashcard-deck")
async def get_flashcard_deck_endpoint(
    body: FlashcardDeckRequest,
    user: dict = Depends(get_current_user)
):
    """Generates grounded dual-mode flashcard/quiz deck for a topic."""
    verify_session_ownership(body.session_id, user["id"])
    from app.services.study_quiz_engine import generate_flashcard_deck
    return await generate_flashcard_deck(
        session_id=body.session_id,
        topic_id=body.topic_id,
        topic_title=body.topic_title,
        subject=body.subject or "General Study",
        num_cards=body.num_cards or 8,
        explanation_level=body.explanation_level or "standard",
        initial_mode=body.initial_mode or "flashcards"
    )


# ─── 6. Mixed-Format Topic Mastery Examination Engine ───────────────────────

@router.post("/topic/exam")
async def get_topic_exam(
    body: TopicExamRequest,
    user: dict = Depends(get_current_user)
):
    """Generates 3-format mixed exam (Written, MCQ, Fill-in-the-blank)."""
    verify_session_ownership(body.session_id, user["id"])
    return await generate_mixed_exam(
        session_id=body.session_id,
        topic_id=body.topic_id,
        topic_title=body.topic_title
    )


@router.post("/topic/evaluate")
async def evaluate_topic_exam(
    body: ExamEvaluationRequest,
    user: dict = Depends(get_current_user)
):
    """Evaluates and scores student exam answers with rubrics."""
    verify_session_ownership(body.session_id, user["id"])
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
async def export_notes_markdown(
    body: ExportMarkdownRequest,
    user: dict = Depends(get_current_user)
):
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
    from app.core import database as db
    meta = get_registry_session(session_id)
    s = db.get_session(session_id)

    if meta and meta.get("user_id") and meta.get("user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Access denied: session belongs to another user")
    if s and s.get("user_id") and s.get("user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Access denied: session belongs to another user")

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
async def delete_study_session(
    session_id: str,
    user: dict = Depends(get_current_user)
):
    """Permanently deletes session, registry entry, and physical SQLite .db."""
    from app.core import database as db
    meta = get_registry_session(session_id)
    s = db.get_session(session_id)

    if meta and meta.get("user_id") and meta.get("user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Access denied: session belongs to another user")
    if s and s.get("user_id") and s.get("user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Access denied: session belongs to another user")

    if not meta and not s:
        raise HTTPException(status_code=404, detail="Session not found")

    ok_reg = delete_registry_session(session_id, user_id=user["id"])
    del_res = db.delete_session(session_id, user_id=user["id"])
    ok = ok_reg or del_res.get("deleted", False)

    return {"success": ok, "session_id": session_id}


@router.delete("/sessions/{session_id}/documents/{doc_name_or_id:path}")
async def delete_session_document_endpoint(
    session_id: str,
    doc_name_or_id: str,
    user: dict = Depends(get_current_user)
):
    """Deletes a specific material document from a study room session."""
    verify_session_ownership(session_id, user["id"])
    from app.services.study_storage import delete_session_document
    ok = delete_session_document(session_id, doc_name_or_id)
    return {"success": ok, "session_id": session_id, "deleted_material": doc_name_or_id}


# ─── 9. Student Episodic Memory ─────────────────────────────────────────────

@router.get("/memory/{user_id}")
async def fetch_student_memory(
    user_id: str,
    user: dict = Depends(get_current_user)
):
    """Fetches student learning profile, goals, weaknesses, and facts."""
    if user_id != user["id"]:
        raise HTTPException(status_code=403, detail="Access denied: cannot access another student's memory")
    return get_student_memory(user_id)


@router.post("/memory/{user_id}/fact")
async def update_student_memory_fact(
    user_id: str,
    body: AddMemoryFactRequest,
    user: dict = Depends(get_current_user)
):
    """Adds or updates student goal, preference, or struggle area."""
    if user_id != user["id"]:
        raise HTTPException(status_code=403, detail="Access denied: cannot modify another student's memory")
    return add_student_memory_fact(
        user_id=user["id"],
        fact=body.fact,
        learning_style=body.learning_style,
        goal=body.goal,
        weakness=body.weakness,
        studied_topic=body.studied_topic
    )


@router.delete("/memory/{user_id}")
async def clear_student_memory(
    user_id: str,
    user: dict = Depends(get_current_user)
):
    """Resets memory for a specific student."""
    if user_id != user["id"]:
        raise HTTPException(status_code=403, detail="Access denied: cannot delete another student's memory")
    return {"success": reset_student_memory(user["id"])}

