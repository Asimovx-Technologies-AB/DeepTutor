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


from app.rag.topic_sanitizer import is_valid_academic_topic, clean_and_format_topic, deduplicate_and_rank_topics
from app.rag.storage import active_graph_store


@router.get("/suggestions")
async def get_topic_suggestions(
    topic_id: Optional[str] = None,
    session_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """
    Extract clean, high-value AI-suggested concepts directly from uploaded PDF documents.
    Filters out author names, page reference strings, table noise, citations, and boilerplate.
    """
    target_tid = topic_id
    if session_id:
        sess = db.get_session(session_id)
        if sess:
            target_tid = sess.get("topic_id") or sess.get("id")

    target_tid = (target_tid or "general").strip() or "general"
    namespaced_topic = get_section_collection_id(user['id'], target_tid)

    raw_candidates: List[str] = []

    # 1. Fetch DB key topics extracted during document vectorization
    db_extracted_topics = db.get_key_topics_for_user_section(user['id'], target_tid)
    for kt in db_extracted_topics:
        if kt:
            raw_candidates.append(kt)

    # 2. Extract concept/algorithm/method entities from LightRAG JSON-KV Knowledge Graph
    try:
        lightrag_entities = active_graph_store.get_entities(namespaced_topic)
        for ent in lightrag_entities:
            name = ent.get("name")
            ent_type = (ent.get("type") or "").lower()
            if name and ent_type not in {"metadata"}:
                raw_candidates.append(name)
    except Exception:
        pass

    # 3. Fallback: NetworkX graph store entities
    try:
        from app.rag.graph_store import graph_store
        graph = graph_store.get_full_graph(namespaced_topic)
        nodes = graph.get("nodes", [])
        for n in nodes:
            name = n.get("name") or n.get("id")
            ent_type = (n.get("type") or "").lower()
            if name and ent_type not in {"metadata"}:
                raw_candidates.append(name)
    except Exception:
        pass

    # 4. Clean, format, and deduplicate with topic sanitizer
    clean_list = deduplicate_and_rank_topics(raw_candidates, max_topics=15)

    # Provide high-yield pedagogical fallback concepts if list is short
    if len(clean_list) < 4:
        fallbacks = [
            "Core Principles & Definitions",
            "Key Algorithms & Methods",
            "Theoretical Frameworks",
            "Comparative Analysis",
            "Practical Applications",
            "Important Case Studies"
        ]
        for f in fallbacks:
            if f not in clean_list and len(clean_list) < 10:
                clean_list.append(f)

    return {"suggestions": clean_list[:15]}


from app.rag.ollama_client import ollama


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
        user_docs = db.get_documents_for_user(user["id"])
        if not user_docs:
            raise HTTPException(
                status_code=400,
                detail="No uploaded documents found. Please upload a PDF document before generating a quiz."
            )

        llm_online = await ollama.is_available()
        if not llm_online:
            raise HTTPException(
                status_code=503,
                detail="AI service is offline or unconfigured. Please configure GEMINI_API_KEY in backend/.env or ensure Ollama is running."
            )

        raise HTTPException(
            status_code=500,
            detail="Failed to generate quiz from document text. Please try again with a different focus topic."
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
    quizzes = db.get_quizzes_by_topic(topic_id)
    if not quizzes and topic_id.startswith(("sslc-", "math-10-", "phys-10-", "chem-10-", "math-", "phys-", "chem-", "textbook")):
        # Auto-generate a fresh quiz on-demand from the textbook index
        try:
            quiz = await generate_quiz_for_section(
                section_id=topic_id,
                user_id=user["id"],
                topic_id=topic_id,
                difficulty="medium",
                num_questions=5,
            )
            if quiz:
                return [quiz]
        except Exception as e:
            print(f"[quiz] Auto-generate failed for {topic_id}: {e}")
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

    # Calculate score
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
