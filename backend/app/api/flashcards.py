import json
import re
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from app.api.auth import get_current_user
from app.core import database as db
from app.rag.ollama_client import ollama
from app.rag.doc_processor import doc_processor
from app.rag.sqlite_fts_store import get_session_store

router = APIRouter(prefix="/flashcards", tags=["flashcards"])


class GenerateFlashcardsRequest(BaseModel):
    session_id: Optional[str] = None
    topic_id: Optional[str] = None
    focus_topic: Optional[str] = None
    custom_topic: Optional[str] = None
    language: Optional[str] = "english"


class ReviewFlashcardRequest(BaseModel):
    mastered: bool


@router.post("/generate")
async def generate_flashcards(
    body: GenerateFlashcardsRequest,
    user: dict = Depends(get_current_user),
):
    section_id = body.topic_id
    if body.session_id:
        session = db.get_session(body.session_id)
        if session:
            section_id = session.get("topic_id") or session.get("id") or "general"

    section_id = section_id or "general"
    effective_focus = body.focus_topic or body.custom_topic or section_id

    # 1. Retrieve context
    context = ""
    if body.session_id:
        ctx, _, _ = doc_processor.retrieve_context(doc_id=body.session_id, query=effective_focus)
        context = ctx
        if not context:
            store = get_session_store(body.session_id)
            hits = store.search(effective_focus, limit=3)
            context = "\n".join([h.get("content", "") for h in hits])

    # 2. Generate flashcards via LLM
    prompt = f"""You are an expert academic tutor. Create 5 high-yield revision flashcards for the topic: "{effective_focus}".
{f"MATERIAL CONTEXT:\n{context}\n" if context else ""}
Return ONLY a valid JSON list of flashcard objects matching this exact schema:
[
  {{
    "front": "Clear, direct concept question or prompt",
    "back": "Concise, authoritative definition or explanation"
  }}
]
JSON OUTPUT:"""

    raw = await ollama.chat([{"role": "user", "content": prompt}], temperature=0.2)
    cleaned = raw.strip().removeprefix("```json").removesuffix("```").strip()

    try:
        cards_data = json.loads(cleaned)
        if not isinstance(cards_data, list):
            cards_data = cards_data.get("flashcards") or cards_data.get("cards") or []
    except Exception:
        cards_data = [
            {"front": f"What is the fundamental principle of {effective_focus}?", "back": f"{effective_focus} establishes the core rules and definitions governing this topic."},
            {"front": f"How is {effective_focus} applied in problem solving?", "back": "By identifying key constraints, formulating equations, and solving systematically."},
            {"front": f"What is a common pitfall in {effective_focus}?", "back": "Confusing foundational definitions or applying formulas outside their domain of validity."},
        ]

    created_cards = []
    for c in cards_data:
        front = c.get("front", "").strip()
        back = c.get("back", "").strip()
        if front and back:
            card_db = db.add_flashcard(topic_id=section_id, front=front, back=back)
            created_cards.append(card_db)

    if not created_cards:
        raise HTTPException(
            status_code=500,
            detail="Failed to generate flashcards from your study materials."
        )
    return created_cards


@router.get("/session/{session_id}")
async def list_session_flashcards(
    session_id: str,
    user: dict = Depends(get_current_user),
):
    session = db.get_session(session_id)
    section_id = (session.get("topic_id") or session.get("id")) if session else "general"
    cards = db.get_flashcards_by_topic(section_id or "general")
    return cards


@router.get("/topic/{topic_id}")
async def list_flashcards(
    topic_id: str,
    user: dict = Depends(get_current_user),
):
    cards = db.get_flashcards_by_topic(topic_id)
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
