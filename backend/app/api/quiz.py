import re
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, List, Optional
from app.api.auth import get_current_user
from app.core import database as db
from app.rag.quiz_generator import generate_quiz_for_section
from app.rag.section_scope import get_section_collection_id

router = APIRouter(prefix="/quiz", tags=["quiz"])


class GenerateQuizRequest(BaseModel):
    session_id: Optional[str] = None
    topic_id: Optional[str] = None
    focus_topic: Optional[str] = None
    custom_topic: Optional[str] = None
    difficulty: Optional[str] = "medium"
    time_limit_mins: Optional[int] = 10
    num_questions: Optional[int] = 5


class SubmitQuizRequest(BaseModel):
    answers: Dict[str, str]  # question_id -> option_letter (A/B/C/D)


@router.get("/suggestions")
async def get_topic_suggestions(
    topic_id: Optional[str] = None,
    session_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """
    Extract clean, high-value AI-suggested concepts directly from uploaded PDF documents.
    Filters out author names, page reference strings, locations, and metadata headers.
    """
    suggestions = set()

    target_tid = topic_id
    if session_id:
        sess = db.get_session(session_id)
        if sess:
            target_tid = sess.get("topic_id") or sess.get("id")

    target_tid = (target_tid or "general").strip() or "general"
    namespaced_topic = get_section_collection_id(user['id'], target_tid)

    # Fetch text content for this section to strictly verify suggestion relevance
    section_text_lower = ""
    try:
        from app.rag.vector_store import vector_store
        col = vector_store._collection(namespaced_topic)
        docs_data = col.get(include=["documents"]).get("documents") or []
        section_text_lower = " ".join(docs_data).lower()
    except Exception:
        pass

    # Noisy words & metadata headers to ignore
    STOP_TOPICS = {
        "institution", "keywords plus", "author", "editor",
        "volume", "issue", "pages", "journal", "abstract", "introduction", "conclusion",
        "references", "figure", "table", "index"
    }

    # 1. Extract concept/algorithm/method entities from NetworkX Knowledge Graph
    try:
        from app.rag.graph_store import graph_store
        graph = graph_store.get_full_graph(namespaced_topic)
        nodes = graph.get("nodes", [])
        for n in nodes:
            name = n.get("name") or n.get("id")
            ent_type = (n.get("type") or "").lower()

            # Skip metadata nodes
            if ent_type in {"metadata"}:
                continue

            if name and 4 <= len(name) <= 45:
                name_clean = name.strip()
                name_lower = name_clean.lower()

                # Filter out page strings (e.g. 'ml algorithams.pdf p.8')
                if ".pdf" in name_lower or "p." in name_lower or "page" in name_lower:
                    continue

                # Ensure candidate concept actually exists in the current section's document text
                if section_text_lower and name_lower not in section_text_lower:
                    continue

                if name_lower not in STOP_TOPICS and not any(stop in name_lower for stop in ["http", "doi:", "isbn"]):
                    # Fix common OCR typos
                    if name_lower == "cikit-learn":
                        name_clean = "Scikit-Learn"
                    suggestions.add(name_clean)
    except Exception:
        pass

    # Filter candidates
    clean_list = []
    for s in suggestions:
        s_lower = s.lower()
        if (
            len(s) >= 4
            and s_lower not in STOP_TOPICS
            and not re.search(r'\.pdf|\bp\.\d+|\bpages?\b', s_lower)
            and not re.match(r'^[A-Z]\.\s*[A-Z]\.', s)  # Initials like H. T. Abbas
        ):
            clean_list.append(s)

    # Provide high-value AI fallback concepts if list is short
    if len(clean_list) < 6:
        fallbacks = [
            "Key Themes",
            "Main Ideas",
            "Important Entities",
            "Major Events",
            "Summary Overview",
            "Core Concepts",
            "Important Details"
        ]
        for f in fallbacks:
            if f not in clean_list and len(clean_list) < 15:
                clean_list.append(f)

    return {"suggestions": clean_list[:15]}


@router.post("/generate")
async def generate_quiz(
    body: GenerateQuizRequest,
    user: dict = Depends(get_current_user),
):
    section_id = body.topic_id
    if body.session_id:
        session = db.get_session(body.session_id)
        if session:
            section_id = session.get("topic_id") or session.get("id") or "general"

    if not section_id:
        section_id = "general"

    effective_focus = body.focus_topic or body.custom_topic

    quiz = await generate_quiz_for_section(
        section_id=section_id,
        user_id=user["id"],
        focus_topic=effective_focus,
        difficulty=body.difficulty,
        time_limit_mins=body.time_limit_mins,
        num_questions=body.num_questions or 5,
        topic_id=section_id,
    )
    if not quiz:
        raise HTTPException(
            status_code=500,
            detail="Failed to generate quiz. Make sure documents are uploaded and Ollama is online."
        )
    return quiz


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
    return db.get_quizzes_by_topic(topic_id)


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

    # Calculate score
    score = 0
    total = len(questions)
    for q in questions:
        q_id = q["id"]
        user_ans = body.answers.get(q_id, "").strip().upper()
        if user_ans == q["correct_answer"].strip().upper():
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
