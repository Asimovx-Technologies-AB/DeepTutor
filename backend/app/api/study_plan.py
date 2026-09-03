import json
import re
from datetime import datetime, date
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from app.api.auth import get_current_user
from app.core import database as db
from app.rag.ollama_client import ollama

router = APIRouter(prefix="/study-plan", tags=["study-plan"])


class GenerateStudyPlanRequest(BaseModel):
    session_id: Optional[str] = None
    topic_id: Optional[str] = None
    target_date: str  # YYYY-MM-DD
    hours_per_day: Optional[float] = 2.0


class ToggleDayRequest(BaseModel):
    day_number: int


class DayNotesRequest(BaseModel):
    plan_id: Optional[str] = None
    day_number: Optional[int] = None
    topic_id: Optional[str] = "general"
    day_topic: str
    key_concepts: Optional[List[str]] = []
    force_regenerate: Optional[bool] = False


async def _generate_day_study_notes(day_topic: str, key_concepts: List[str]) -> str:
    prompt = f"""You are DeepTutor, an elite academic AI tutor.
Write comprehensive, authoritative master study notes for the topic: "{day_topic}".
Key concepts to cover: {", ".join(key_concepts) if key_concepts else "Core principles"}.

FORMAT REQUIREMENTS:
- Use clean Markdown with headers (# and ##).
- Clean human-readable mathematics (e.g. y = mx + c, F = m * a).
- Include:
  1. The Big Picture & Foundational Purpose
  2. Core Governing Principles & Mathematical Framework
  3. Step-by-step Problem-Solving Mechanism
  4. Common Pitfalls & High-Yield Exam Traps
- Zero emojis. Maintain an articulate, elite academic tone.
"""
    notes = await ollama.chat([{"role": "user", "content": prompt}], temperature=0.2)
    return notes.strip()


async def _generate_study_plan(user_id: str, topic_id: str, target_date: str, hours_per_day: float) -> dict:
    try:
        t_date = datetime.strptime(target_date, "%Y-%m-%d").date()
        today = date.today()
        days_diff = (t_date - today).days
        total_days = max(3, min(days_diff, 14))
    except Exception:
        total_days = 7

    prompt = f"""You are an elite academic curriculum planner.
Create a structured {total_days}-day study roadmap for the subject/topic: "{topic_id}".
Student can study {hours_per_day} hours per day.

Return ONLY a valid JSON list of day objects with this exact structure:
[
  {{
    "day": 1,
    "topic": "Foundational Principles of ...",
    "key_concepts": ["Concept 1", "Concept 2"],
    "estimated_hours": {hours_per_day}
  }}
]
JSON OUTPUT:"""

    raw = await ollama.chat([{"role": "user", "content": prompt}], temperature=0.2)
    cleaned = raw.strip().removeprefix("```json").removesuffix("```").strip()

    try:
        schedule_data = json.loads(cleaned)
        if not isinstance(schedule_data, list):
            schedule_data = schedule_data.get("schedule") or []
    except Exception:
        schedule_data = [
            {"day": i + 1, "topic": f"Module {i + 1}: Core Concepts", "key_concepts": ["Foundations", "Application"], "estimated_hours": hours_per_day}
            for i in range(total_days)
        ]

    schedule = []
    for item in schedule_data:
        schedule.append({
            "day": item.get("day", len(schedule) + 1),
            "topic": item.get("topic", "Core Concepts"),
            "key_concepts": item.get("key_concepts", []),
            "estimated_hours": item.get("estimated_hours", hours_per_day),
            "completed": False,
            "study_notes": "",
        })

    plan = db.create_study_plan(
        user_id=user_id,
        topic_id=topic_id,
        title=f"{topic_id.title()} {total_days}-Day Study Roadmap",
        target_date=target_date,
        total_days=len(schedule),
        hours_per_day=hours_per_day,
        schedule=schedule,
    )
    return plan


@router.post("/day-notes")
async def get_day_notes(
    body: DayNotesRequest,
    user: dict = Depends(get_current_user),
):
    if not body.force_regenerate and body.plan_id and body.day_number is not None:
        try:
            plan = db.get_study_plan(body.plan_id)
            if plan and plan.get("schedule"):
                for item in plan["schedule"]:
                    if item.get("day") == body.day_number:
                        saved_notes = item.get("study_notes")
                        if saved_notes and len(saved_notes.strip()) > 150:
                            return {"day_topic": body.day_topic, "notes": saved_notes, "cached": True}
        except Exception:
            pass

    notes = await _generate_day_study_notes(body.day_topic, body.key_concepts or [])
    if body.plan_id and body.day_number is not None:
        try:
            db.save_study_plan_day_notes(body.plan_id, body.day_number, notes)
        except Exception:
            pass

    return {"day_topic": body.day_topic, "notes": notes, "cached": False}


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

    section_id = section_id or "general"
    plan = await _generate_study_plan(
        user_id=user["id"],
        topic_id=section_id,
        target_date=body.target_date,
        hours_per_day=body.hours_per_day or 2.0,
    )
    return plan


@router.get("/topic/{topic_id}")
async def get_plan(
    topic_id: str,
    user: dict = Depends(get_current_user),
):
    plan = db.get_study_plan_by_topic(user["id"], topic_id)
    return plan


@router.get("/my-plans")
async def get_my_plans(user: dict = Depends(get_current_user)):
    """Fetch all study plans belonging to the current user."""
    plans = db.get_study_plans_for_user(user["id"])
    return plans


@router.get("/{plan_id}")
async def get_plan_by_id(
    plan_id: str,
    user: dict = Depends(get_current_user),
):
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
async def delete_plan(
    plan_id: str,
    user: dict = Depends(get_current_user),
):
    ok = db.delete_study_plan(plan_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Study plan not found")
    return {"ok": True}
