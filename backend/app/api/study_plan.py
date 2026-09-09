import json
import re
import logging
from datetime import datetime, date
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from app.api.auth import get_current_user
from app.core import database as db
from app.rag.llm_client import llm_client

logger = logging.getLogger(__name__)

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


def clean_study_notes_markdown(text: str) -> str:
    """Cleans LaTeX math syntax, converts misplaced inline double-dollars to single dollars, and normalizes bullet lists."""
    if not text:
        return ""

    import re
    cleaned = text.strip()

    # 1. Strip outer markdown code block wrap if wrapped in ```markdown ... ```
    if cleaned.startswith("```markdown") and cleaned.endswith("```"):
        cleaned = cleaned[len("```markdown"): -3].strip()
    elif cleaned.startswith("```") and cleaned.endswith("```") and cleaned.count("```") == 2:
        lines = cleaned.splitlines()
        if len(lines) > 2 and lines[0].strip() in ("```", "```md", "```text"):
            cleaned = "\n".join(lines[1:-1]).strip()

    # 2. Convert standalone single-line formulas wrapped in $...$ into display math $$\n...\n$$
    cleaned = re.sub(
        r'^\s*\$(?!\$)([^\$\n]{5,})\$\s*$',
        r'$$\n\1\n$$',
        cleaned,
        flags=re.MULTILINE
    )

    # 3. Convert inline double dollars ($$ var $$) on the same line to single dollars ($var$)
    def _replace_inline_double_dollars(match):
        content = match.group(1).strip()
        if "\n" not in content:
            return f"${content}$"
        return f"\n$$\n{content}\n$$\n"

    cleaned = re.sub(r'(?<!\$)\$\$\s*([^\$\n]+?)\s*\$\$(?!\$)', _replace_inline_double_dollars, cleaned)

    # 4. Ensure display math blocks have newlines around them
    cleaned = re.sub(r'([^\n])\s*\$\$\s*\n', r'\1\n\n$$\n', cleaned)
    cleaned = re.sub(r'\n\s*\$\$\s*([^\n])', r'\n$$\n\n\1', cleaned)

    # 5. Clean up un-bulleted paradigm lists like "Supervised Learning: ..." or "Reinforcement Learning (RL): ..." into "- **...**: ..."
    cleaned = re.sub(
        r'^(?!(?:[-*#>]|\d+\.))\s*([A-Za-z0-9\s()/\-]{3,45}):\s+([A-Z])',
        r'- **\1**: \2',
        cleaned,
        flags=re.MULTILINE
    )

    # 6. Consolidate excessive blank lines
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)

    return cleaned.strip()


async def _generate_day_study_notes(day_topic: str, key_concepts: List[str], topic_id: Optional[str] = "general") -> str:
    material_context = ""
    if topic_id and topic_id != "general":
        try:
            from app.rag.pg_fts_store import pg_fts_store
            chunks = pg_fts_store.search_chunks(topic_id, day_topic, limit=3)
            if chunks:
                material_context = "\n\nEXCERPTS FROM UPLOADED MATERIAL:\n" + "\n---\n".join([c.get("content", "") for c in chunks])
                logger.info(f"[_generate_day_study_notes] Retrieved {len(chunks)} contextual chunks for topic '{day_topic}'.")
            else:
                logger.info(f"[_generate_day_study_notes] No chunks found for topic '{day_topic}' in session '{topic_id}'.")
        except Exception as e:
            logger.warning(f"[_generate_day_study_notes] search_chunks failed for topic_id={topic_id}: {e}")

    prompt = f"""You are DeepTutor, an elite academic AI tutor.
Write comprehensive, authoritative, beautifully structured master study notes for the topic: "{day_topic}".
Key concepts to cover: {", ".join(key_concepts) if key_concepts else "Core principles"}.
{material_context}

FORMAT REQUIREMENTS & QUALITY GUIDELINES:
1. LaTeX Math Formatting:
   - For inline variables, symbols, and short formulas inside sentences, always use single dollar signs: `$x_i$`, `$y_i$`, `$f(x)$`, `$P$`, `$L$`, `$\\mathcal{{D}}$`.
   - For major display equations, place them on dedicated separate lines enclosed by double dollar signs:
     $$
     f^* = \\arg\\min_f \\mathbb{{E}}_{{(x,y) \\sim P}} \\left[ L(y, f(x)) \\right]
     $$
2. Structured Bullet Lists:
   - Always format definitions, paradigms, steps, and sub-points as clean Markdown bullet points (`- **Term / Principle**: Clear explanation`).
   - Never write run-on wall-of-text paragraphs.
3. Zero Emojis: Maintain an articulate, pristine academic tone.
4. Structure:
   - # {day_topic} — Study Notes
   - > **TL;DR / Summary**: 3-5 line high-density essence box.
   - ## Core Governing Principles & Mathematical Framework
   - ## Step-by-Step Problem-Solving & Concrete Examples
   - ## Comparison & Trade-Offs (Use a clean Markdown comparison table)
   - ## High-Yield Gotchas & Common Pitfalls
   - ## Self-Check Active Recall (5-8 testable questions labeled [High-yield], with answers in `<details><summary>Click to reveal answers</summary>...</details>`)
   - ## Quick-Reference Glossary (Two-column Markdown table of key terms and concise definitions)
   - **Next Topic to Explore:** (1 line suggestion)
"""
    notes = await llm_client.chat([{"role": "user", "content": prompt}], temperature=0.2)
    return clean_study_notes_markdown(notes)


async def _generate_study_plan(user_id: str, topic_id: str, target_date: str, hours_per_day: float) -> dict:
    try:
        t_date = datetime.strptime(target_date, "%Y-%m-%d").date()
        today = date.today()
        days_diff = (t_date - today).days
        total_days = max(3, min(days_diff, 14))
    except Exception:
        total_days = 7

    # Gather all uploaded materials and extracted topics for this user & topic/session
    material_names: List[str] = []
    syllabus_topics: List[str] = []

    # 1. From Study Storage (session_documents & session_topics)
    try:
        from app.services.study_storage import get_session_documents, get_session_topics
        s_docs = get_session_documents(topic_id, user_id=user_id)
        material_names.extend([d["filename"] for d in s_docs if d.get("filename")])
        s_topics = get_session_topics(topic_id)
        for t in s_topics:
            if t.get("title"):
                kc = ", ".join(t.get("key_concepts", []))
                syllabus_topics.append(f"- {t.get('title')}: {t.get('summary', '')} (Key concepts: {kc})")
    except Exception:
        pass

    # 2. From core database Documents
    try:
        core_docs = db.get_documents_for_user_and_topic(user_id, topic_id)
        if not core_docs and topic_id.startswith("plan_"):
            core_docs = db.get_documents_for_user(user_id)
        for cd in core_docs:
            fn = cd.get("file_name")
            if fn and fn not in material_names:
                material_names.append(fn)
            for kt in cd.get("key_topics", []):
                if kt and not str(kt).startswith("__subject__:") and kt not in syllabus_topics:
                    syllabus_topics.append(f"- {kt}")
    except Exception:
        pass

    materials_context = ""
    if material_names or syllabus_topics:
        materials_context = f"""
STUDENT'S UPLOADED STUDY MATERIALS & SYLLABUS OUTLINE:
- Uploaded Document(s): {', '.join(material_names) if material_names else 'Course Material PDF'}
- Extracted Syllabus Chapters & Modules:
{chr(10).join(syllabus_topics[:12]) if syllabus_topics else '- Comprehensive coverage of ' + topic_id}
"""

    prompt = f"""You are an elite academic curriculum planner.
Create a structured, highly actionable {total_days}-day study roadmap for: "{topic_id}".
Student can study {hours_per_day} hours per day.

{materials_context}

CRITICAL REQUIREMENTS:
- Map and distribute the uploaded materials and chapters logically across the {total_days} days.
- Ensure every day focuses on clear, concrete subtopics and chapters from the material.
- Provide 2-4 key concepts for each day.

Return ONLY a valid JSON list of day objects with this exact structure:
[
  {{
    "day": 1,
    "topic": "Module 1: Foundational Principles of ...",
    "key_concepts": ["Concept 1", "Concept 2", "Concept 3"],
    "estimated_hours": {hours_per_day}
  }}
]
JSON OUTPUT:"""

    raw = await llm_client.chat([{"role": "user", "content": prompt}], temperature=0.2)
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

    title_source = material_names[0] if material_names else topic_id.replace('_', ' ').title()
    clean_title = f"{title_source} {len(schedule)}-Day Study Plan"

    plan = db.create_study_plan(
        user_id=user_id,
        topic_id=topic_id,
        title=clean_title,
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

    notes = await _generate_day_study_notes(body.day_topic, body.key_concepts or [], topic_id=body.topic_id)
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
    plan = db.get_study_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Study plan not found")
    if plan.get("user_id") and plan.get("user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized to delete this study plan")
    ok = db.delete_study_plan(plan_id, user_id=user["id"])
    if not ok:
        raise HTTPException(status_code=404, detail="Study plan not found")
    return {"ok": True}


class VerifyQuizRequest(BaseModel):
    day_number: int
    score_percentage: float


@router.post("/{plan_id}/verify-quiz")
async def verify_quiz(
    plan_id: str,
    body: VerifyQuizRequest,
    user: dict = Depends(get_current_user),
):
    plan = db.get_study_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Study plan not found")
    if plan.get("user_id") and plan.get("user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized to verify quiz for this study plan")
    passed = body.score_percentage >= 70.0
    if passed:
        db.set_study_plan_day_completed(plan_id, body.day_number, True)
    return {
        "ok": True,
        "plan_id": plan_id,
        "day_number": body.day_number,
        "score_percentage": body.score_percentage,
        "passed": passed,
    }
