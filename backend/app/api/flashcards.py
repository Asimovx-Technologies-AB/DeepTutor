from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from app.api.auth import get_current_user
from app.core import database as db
from app.rag.flashcard_generator import generate_flashcards_for_topic

router = APIRouter(prefix="/flashcards", tags=["flashcards"])


class GenerateFlashcardsRequest(BaseModel):
    session_id: Optional[str] = None
    topic_id: Optional[str] = None
    focus_topic: Optional[str] = None


class ReviewFlashcardRequest(BaseModel):
    mastered: bool


@router.post("/generate")
async def generate_flashcards(
    body: GenerateFlashcardsRequest,
    user: dict = Depends(get_current_user),
):
    topic_id = body.topic_id
    if body.session_id:
        session = db.get_session(body.session_id)
        if session:
            topic_id = session.get("topic_id") or "general"
            
    if not topic_id:
        topic_id = "general"

    cards = await generate_flashcards_for_topic(
        topic_id=topic_id,
        focus_topic=body.focus_topic,
        user_id=user["id"]
    )
    if not cards:
        raise HTTPException(
            status_code=500,
            detail="Failed to generate flashcards from your uploaded documents. Please upload a PDF document first."
        )
    return cards


@router.get("/session/{session_id}")
async def list_session_flashcards(
    session_id: str,
    user: dict = Depends(get_current_user),
):
    session = db.get_session(session_id)
    topic_id = session.get("topic_id") if session else "general"
    cards = db.get_flashcards_by_topic(topic_id or "general")
    if not cards:
        cards = await generate_flashcards_for_topic(topic_id or "general", user_id=user["id"])
    return cards


@router.get("/topic/{topic_id}")
async def list_flashcards(
    topic_id: str,
    user: dict = Depends(get_current_user),
):
    cards = db.get_flashcards_by_topic(topic_id)
    if not cards:
        cards = await generate_flashcards_for_topic(topic_id, user_id=user["id"])
    return cards


@router.post("/{topic_id}/cards/{card_id}/review")
async def review_flashcard(
    topic_id: str,
    card_id: str,
    body: ReviewFlashcardRequest,
    user: dict = Depends(get_current_user),
):
    ok = db.update_flashcard_status(topic_id, card_id, body.mastered)
    if not ok:
        raise HTTPException(status_code=404, detail="Flashcard not found")
    return {"ok": True}
