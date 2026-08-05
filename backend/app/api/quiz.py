from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, List, Optional
from app.api.auth import get_current_user
from app.core import database as db
from app.rag.quiz_generator import generate_quiz_for_topic

router = APIRouter(prefix="/quiz", tags=["quiz"])


class GenerateQuizRequest(BaseModel):
    session_id: Optional[str] = None
    topic_id: Optional[str] = None
    focus_topic: Optional[str] = None
    difficulty: Optional[str] = "medium"
    time_limit_mins: Optional[int] = 10
    num_questions: Optional[int] = 5


class SubmitQuizRequest(BaseModel):
    answers: Dict[str, str]  # question_id -> option_letter (A/B/C/D)


@router.post("/generate")
async def generate_quiz(
    body: GenerateQuizRequest,
    user: dict = Depends(get_current_user),
):
    topic_id = body.topic_id
    if body.session_id:
        session = db.get_session(body.session_id)
        if session:
            topic_id = session.get("topic_id") or "general"
    
    if not topic_id:
        topic_id = "general"

    quiz = await generate_quiz_for_topic(
        topic_id=topic_id,
        focus_topic=body.focus_topic,
        difficulty=body.difficulty,
        time_limit_mins=body.time_limit_mins,
        num_questions=body.num_questions or 5,
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
    topic_id = session.get("topic_id") if session else "general"
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
