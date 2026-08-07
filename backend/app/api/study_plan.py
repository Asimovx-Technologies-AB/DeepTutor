from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from app.api.auth import get_current_user
from app.core import database as db
from app.rag.study_plan_generator import generate_study_plan, generate_day_study_notes

router = APIRouter(prefix="/study-plan", tags=["study-plan"])


class GenerateStudyPlanRequest(BaseModel):
    session_id: Optional[str] = None
    topic_id: Optional[str] = None
    target_date: str  # YYYY-MM-DD
    hours_per_day: Optional[float] = 2.0


class ToggleDayRequest(BaseModel):
    day_number: int


class DayNotesRequest(BaseModel):
    topic_id: Optional[str] = "general"
    day_topic: str
    key_concepts: Optional[List[str]] = []


@router.post("/day-notes")
async def get_day_notes(
    body: DayNotesRequest,
    user: dict = Depends(get_current_user),
):
    notes = await generate_day_study_notes(
        topic_id=body.topic_id or "general",
        day_topic=body.day_topic,
        key_concepts=body.key_concepts or [],
        user_id=user["id"],
    )
    return {"day_topic": body.day_topic, "notes": notes}


@router.post("/generate")
async def generate_plan(
    body: GenerateStudyPlanRequest,
    user: dict = Depends(get_current_user),
):
    section_id = body.topic_id
    if body.session_id:
        session = db.get_session(body.session_id)
        if session:
            section_id = session.get("topic_id") or session.get("id") or body.session_id
        else:
            section_id = body.session_id

    if not section_id:
        section_id = "general"

    plan = await generate_study_plan(
        user_id=user["id"],
        topic_id=section_id,
        target_date=body.target_date,
        hours_per_day=body.hours_per_day or 2.0,
    )
    if not plan:
        raise HTTPException(
            status_code=500,
            detail="Failed to generate study plan. Make sure documents are uploaded for this topic and Ollama is online."
        )
    return plan


@router.get("/my-plans")
async def list_my_plans(user: dict = Depends(get_current_user)):
    return db.get_study_plans_for_user(user["id"])


@router.get("/{plan_id}")
async def get_plan(plan_id: str, user: dict = Depends(get_current_user)):
    plan = db.get_study_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Study plan not found")
    return plan


@router.post("/{plan_id}/toggle-day")
async def toggle_day(
    plan_id: str,
    body: ToggleDayRequest,
    user: dict = Depends(get_current_user),
):
    plan = db.toggle_study_plan_day(plan_id, body.day_number)
    if not plan:
        raise HTTPException(status_code=404, detail="Study plan not found")
    return plan


@router.delete("/{plan_id}")
async def delete_plan(plan_id: str, user: dict = Depends(get_current_user)):
    ok = db.delete_study_plan(plan_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Study plan not found")
    return {"ok": True}
