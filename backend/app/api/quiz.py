import re
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, List, Optional
from app.api.auth import get_current_user
from app.core import database as db
from app.rag.ollama_client import ollama
from app.rag.exam_generator import exam_generator
from app.rag.doc_processor import doc_processor
from app.rag.sqlite_fts_store import get_session_store

router = APIRouter(prefix="/quiz", tags=["quiz"])


class GenerateQuizRequest(BaseModel):
    session_id: Optional[str] = None
    topic_id: Optional[str] = None
    note_id: Optional[str] = None
    note_content: Optional[str] = None
    focus_topic: Optional[str] = None
    custom_topic: Optional[str] = None
    difficulty: Optional[str] = "medium"
    time_limit_mins: Optional[int] = 10
    num_questions: Optional[int] = 5
    language: Optional[str] = "english"


class SubmitQuizRequest(BaseModel):
    answers: Dict[str, str]


@router.get("/suggestions")
async def get_topic_suggestions(
    topic_id: Optional[str] = None,
    session_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    target_tid = topic_id
    if session_id:
        sess = db.get_session(session_id)
        if sess:
            target_tid = sess.get("topic_id") or sess.get("id")

    target_tid = (target_tid or "general").strip() or "general"
    clean_list: List[str] = []

    db_extracted_topics = db.get_key_topics_for_user_section(user['id'], target_tid)
    for kt in db_extracted_topics:
        if kt and str(kt).strip() and not str(kt).startswith("__subject__:"):
            clean_list.append(str(kt).strip())

    if not clean_list:
        clean_list = ["Core Foundations", "Primary Principles", "Applied Problem Solving", "Exam Synthesis"]

    return {"suggestions": clean_list[:15]}


@router.post("/generate")
async def generate_quiz(
    body: GenerateQuizRequest,
    user: dict = Depends(get_current_user),
):
    section_id = (body.topic_id or "").strip()
    if not section_id and body.session_id:
        session = db.get_session(body.session_id)
        if session:
            section_id = session.get("topic_id") or session.get("id") or "general"

    section_id = section_id or "general"
    topic_title = body.focus_topic or body.custom_topic or section_id

    # Retrieve context
    context = ""
    if body.note_content:
        context = body.note_content
    elif body.session_id:
        ctx, _, _ = doc_processor.retrieve_context(doc_id=body.session_id, query=topic_title)
        context = ctx
        if not context:
            store = get_session_store(body.session_id)
            hits = store.search(topic_title, limit=3)
            context = "\n".join([h.get("content", "") for h in hits])

    # Generate exam via exam_generator
    exam_data = await exam_generator.generate_exam(topic_title=topic_title, context=context)
    questions = exam_data.get("questions", [])

    # Create quiz in database
    quiz_obj = db.create_quiz(
        topic_id=section_id,
        title=exam_data.get("title", f"{topic_title} Quiz"),
        difficulty=body.difficulty or "medium",
        time_limit=body.time_limit_mins or 10,
    )

    created_questions = []
    for q in questions:
        q_prompt = q.get("prompt", "")
        q_type = q.get("type", "multiple_choice")
        options = q.get("options", ["A", "B", "C", "D"])
        correct = str(q.get("correct_answer", "A"))
        explanation = q.get("explanation", "")

        q_db = db.add_question(
            quiz_id=quiz_obj["id"],
            question_text=q_prompt,
            question_type=q_type,
            options=options,
            correct_answer=correct,
            explanation=explanation,
        )
        created_questions.append({
            "id": q_db["id"],
            "question_text": q_prompt,
            "question_type": q_type,
            "options": options,
            "correct_answer": correct,
            "explanation": explanation,
        })

    quiz_obj["questions"] = created_questions
    return quiz_obj


@router.get("/session/{session_id}")
async def list_session_quizzes(
    session_id: str,
    user: dict = Depends(get_current_user),
):
    session = db.get_session(session_id)
    topic_id = (session.get("topic_id") or session.get("id")) if session else "general"
    return db.get_quizzes_by_topic(topic_id or "general")


@router.get("/topic/{topic_id}")
async def list_quizzes(
    topic_id: str,
    user: dict = Depends(get_current_user),
):
    quizzes = db.get_quizzes_by_topic(topic_id)
    return quizzes


@router.get("/{quiz_id}")
async def get_quiz(
    quiz_id: str,
    user: dict = Depends(get_current_user),
):
    quiz = db.get_quiz(quiz_id)
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    return quiz


@router.post("/{quiz_id}/submit")
async def submit_quiz(
    quiz_id: str,
    body: SubmitQuizRequest,
    user: dict = Depends(get_current_user),
):
    quiz = db.get_quiz(quiz_id)
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")

    questions = quiz.get("questions", [])
    if not questions:
        raise HTTPException(status_code=400, detail="Quiz has no questions")

    score = 0
    total = len(questions)
    for q in questions:
        q_id = q["id"]
        user_ans = str(body.answers.get(q_id, "")).strip().upper()
        correct_ans = str(q.get("correct_answer", "A")).strip().upper()
        options = q.get("options") or []

        if user_ans == correct_ans:
            score += 1
        elif user_ans:
            match = re.search(r'[A-D]', correct_ans)
            if match:
                opt_idx = ord(match.group()) - ord('A')
                if 0 <= opt_idx < len(options):
                    opt_text = str(options[opt_idx]).strip().upper()
                    if user_ans == opt_text or user_ans in opt_text:
                        score += 1

    percentage = round((score / total) * 100, 2) if total > 0 else 0.0

    attempt = db.create_attempt(
        user_id=user["id"],
        quiz_id=quiz_id,
        score=score,
        total=total,
        percentage=percentage,
        answers=body.answers,
    )
    return attempt


@router.get("/my-attempts")
async def get_my_attempts(
    user: dict = Depends(get_current_user),
):
    return db.get_attempts_for_user(user["id"])
