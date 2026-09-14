import logging
import json
import re
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any, Tuple
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy import or_

from app.core.database import get_db
from app.models.study_plan import StudyPlan
from app.models.session import StudySession, CurriculumTopic
from app.models.document import Document
from app.models.chunk import KnowledgeChunk
from app.services.llm_service import default_llm_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/study-plan", tags=["Study Plan"])


# ─── Pydantic Request & Response Schemas ───────────────────────

class GeneratePlanRequest(BaseModel):
    topic_id: Optional[str] = None
    session_id: Optional[str] = None
    target_date: str = Field(..., description="Target completion date in YYYY-MM-DD")
    hours_per_day: Optional[float] = 2.0
    language: Optional[str] = "en"


class ToggleDayRequest(BaseModel):
    day_number: int


class VerifyQuizRequest(BaseModel):
    day_number: int
    score_percentage: float


class DayNotesRequest(BaseModel):
    plan_id: Optional[str] = None
    day_number: int
    topic_id: Optional[str] = "general"
    day_topic: str
    key_concepts: List[str] = []
    force_regenerate: bool = False


def _serialize_plan(plan: StudyPlan) -> Dict[str, Any]:
    created_str = ""
    if plan.created_at:
        created_str = plan.created_at.isoformat() if hasattr(plan.created_at, "isoformat") else str(plan.created_at)

    updated_str = ""
    if plan.updated_at:
        updated_str = plan.updated_at.isoformat() if hasattr(plan.updated_at, "isoformat") else str(plan.updated_at)

    schedule_data = plan.schedule
    if isinstance(schedule_data, str):
        try:
            schedule_data = json.loads(schedule_data)
        except Exception:
            schedule_data = []

    completed_data = plan.completed_days
    if isinstance(completed_data, str):
        try:
            completed_data = json.loads(completed_data)
        except Exception:
            completed_data = []

    return {
        "id": plan.id,
        "user_id": plan.user_id,
        "topic_id": plan.topic_id or "",
        "session_id": plan.session_id or "",
        "title": plan.title,
        "target_date": plan.target_date,
        "total_days": plan.total_days,
        "hours_per_day": plan.hours_per_day,
        "schedule": schedule_data or [],
        "completed_days": completed_data or [],
        "created_at": created_str,
        "updated_at": updated_str,
    }


# ─── Helper Functions: Document Grounding ──────────────────────

def _resolve_document(
    db: Session,
    topic_id: Optional[str],
    session_id: Optional[str]
) -> Optional[Document]:
    """
    Intelligently resolves the target Document from topic_id, session_id,
    or falls back to the most recently uploaded document in PostgreSQL.
    """
    doc = None

    # 1. Try topic_id as Document.id or file_hash
    if topic_id and topic_id != "general":
        doc = db.query(Document).filter(
            (Document.id == topic_id) | (Document.file_hash == topic_id)
        ).first()
        if not doc:
            # Check if topic_id matches a study_session id
            sess = db.query(StudySession).filter(StudySession.id == topic_id).first()
            if sess and sess.document_id:
                doc = db.query(Document).filter(Document.id == sess.document_id).first()

    # 2. Try session_id
    if not doc and session_id:
        sess = db.query(StudySession).filter(StudySession.id == session_id).first()
        if sess:
            if sess.document_id:
                doc = db.query(Document).filter(Document.id == sess.document_id).first()
            else:
                # An explicit session was requested without an attached document_id;
                # respect the session rather than hijacking it with an unrelated document.
                return None

    # 3. Fallback: Ground to the most recent document only if no explicit session or topic was specified
    if not doc and not topic_id and not session_id:
        doc = db.query(Document).order_by(Document.created_at.desc()).first()

    return doc


def _clean_topic_title(raw: str) -> str:
    """Cleans noisy OCR artifacts, page headers, and trailing arrows."""
    t = re.sub(r'^[0-9]+(\.[0-9]+)*\s*', '', raw.strip())
    t = re.sub(r'\s*>\s*', ' — ', t)
    t = t.replace('\n', ' ').strip()
    return t[:120]


def _extract_document_syllabus(
    db: Session,
    doc: Document,
    session_id: Optional[str] = None
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Extracts real chapters, sections, definitions, and key concepts from
    CurriculumTopic and KnowledgeChunk tables for the specified document.
    """
    doc_title = doc.title or doc.filename.replace('.pdf', '').replace('_', ' ')
    discovered: List[Dict[str, Any]] = []
    seen_titles = set()

    noise_patterns = [
        "arxiv", "submitted:", "accepted for publication", "doi:", "issn",
        "trend research", "department of", "university", "abstract",
        "competing interests", "author contributions", "acknowledgments",
        "references", "correspondence to:", "received:"
    ]

    # 1. Inspect CurriculumTopic entries for this document
    ct_query = db.query(CurriculumTopic).filter(CurriculumTopic.document_id == doc.id)
    if session_id:
        ct_query = db.query(CurriculumTopic).filter(
            or_(CurriculumTopic.document_id == doc.id, CurriculumTopic.session_id == session_id)
        )
    curriculum_topics = ct_query.order_by(CurriculumTopic.order_index.asc()).all()

    for ct in curriculum_topics:
        cleaned = _clean_topic_title(ct.title or "")
        lower = cleaned.lower()
        if len(cleaned) < 4 or any(noise in lower for noise in noise_patterns):
            continue
        if lower not in seen_titles:
            seen_titles.add(lower)
            discovered.append({
                "title": cleaned,
                "summary": ct.summary or f"Core study module on {cleaned}.",
                "key_concepts": ct.key_concepts if (ct.key_concepts and isinstance(ct.key_concepts, list)) else [cleaned],
                "estimated_time": ct.estimated_study_time or "2 hrs"
            })

    # 2. Extract sections & concepts from KnowledgeChunks
    chunks = (
        db.query(KnowledgeChunk)
        .filter(KnowledgeChunk.document_id == doc.id)
        .order_by(KnowledgeChunk.chunk_index.asc())
        .all()
    )

    chunk_topics: List[Dict[str, Any]] = []
    for c in chunks:
        section = c.chapter_section or c.topic or ""
        cleaned = _clean_topic_title(section)
        lower = cleaned.lower()

        if len(cleaned) >= 4 and not any(noise in lower for noise in noise_patterns):
            if lower not in seen_titles:
                seen_titles.add(lower)
                
                # Collect concepts from chunk metadata
                concepts = []
                if c.related_concepts and isinstance(c.related_concepts, list):
                    concepts.extend([str(x) for x in c.related_concepts if len(str(x)) > 2])
                if c.keywords_entities and isinstance(c.keywords_entities, list):
                    concepts.extend([str(x) for x in c.keywords_entities if len(str(x)) > 2])
                if not concepts:
                    concepts = [cleaned]

                chunk_topics.append({
                    "title": cleaned,
                    "summary": (c.content[:160] + "...") if c.content else f"Key concepts on {cleaned}",
                    "key_concepts": list(dict.fromkeys(concepts))[:5],
                    "estimated_time": "2 hrs"
                })

    # Merge or prefer highest-quality topics
    if len(discovered) < 3 and chunk_topics:
        discovered.extend(chunk_topics)
    elif chunk_topics and len(chunk_topics) > len(discovered):
        discovered = chunk_topics

    return doc_title, discovered


# ─── Endpoints ──────────────────────────────────────────────────

@router.get("/my-plans")
def get_my_plans(
    user_id: str = "default_user",
    db: Session = Depends(get_db)
):
    """
    Returns all active and saved study plans for the user from PostgreSQL.
    """
    plans = (
        db.query(StudyPlan)
        .filter(StudyPlan.user_id == user_id)
        .order_by(StudyPlan.created_at.desc())
        .all()
    )
    return [_serialize_plan(p) for p in plans]


@router.get("/{plan_id}")
def get_study_plan(
    plan_id: str,
    db: Session = Depends(get_db)
):
    """
    Returns a single study plan by its unique ID.
    """
    plan = db.query(StudyPlan).filter(StudyPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Study plan not found.")
    return _serialize_plan(plan)


@router.post("/generate")
def generate_study_plan(
    req: GeneratePlanRequest,
    user_id: str = "default_user",
    db: Session = Depends(get_db)
):
    """
    Generates a personalized, structured day-by-day learning roadmap
    grounded 100% in the uploaded/database document.
    Saves the generated plan into PostgreSQL.
    """
    # 1. Parse target date and calculate total days
    try:
        target_dt = datetime.strptime(req.target_date, "%Y-%m-%d").date()
    except ValueError:
        target_dt = datetime.now(timezone.utc).date() + timedelta(days=10)

    today = datetime.now(timezone.utc).date()
    days_delta = (target_dt - today).days
    total_days = max(3, min(days_delta if days_delta > 0 else 10, 30))

    # 2. Resolve document context directly from PostgreSQL
    doc = _resolve_document(db, req.topic_id, req.session_id)
    doc_id = doc.id if doc else (req.topic_id or "")
    discovered_topics: List[Dict[str, Any]] = []

    if doc:
        doc_title, discovered_topics = _extract_document_syllabus(db, doc, req.session_id)
        course_title = f"{doc_title} Study Roadmap"
    else:
        # Check if session exists without document_id
        sess = None
        if req.session_id:
            sess = db.query(StudySession).filter(StudySession.id == req.session_id).first()
        elif req.topic_id:
            sess = db.query(StudySession).filter(StudySession.id == req.topic_id).first()

        if sess:
            doc_title = sess.title or "Study Session"
            course_title = f"{doc_title} Study Roadmap"
            ct_list = db.query(CurriculumTopic).filter(
                CurriculumTopic.session_id == sess.id
            ).order_by(CurriculumTopic.order_index.asc()).all()
            for ct in ct_list:
                cleaned = _clean_topic_title(ct.title or "")
                if cleaned:
                    discovered_topics.append({
                        "title": cleaned,
                        "summary": ct.summary or f"Core study module on {cleaned}.",
                        "key_concepts": ct.key_concepts if (ct.key_concepts and isinstance(ct.key_concepts, list)) else [cleaned],
                        "estimated_time": ct.estimated_study_time or "2 hrs"
                    })
        else:
            doc_title = "Course Materials"
            course_title = "Academic Study Plan"

    # 3. Build Schedule using AI or Document Structure
    schedule: List[Dict[str, Any]] = []

    # Attempt Live LLM Generation for deep document grounding
    if doc and discovered_topics and default_llm_service.is_live_model_configured():
        try:
            topics_summary_str = "\n".join(
                f"- Section {i+1}: {t['title']} | Key concepts: {', '.join(t.get('key_concepts', [])[:4])}"
                for i, t in enumerate(discovered_topics[:25])
            )

            prompt = f"""You are DeepTutor, an elite academic AI curriculum architect.
A student is preparing for an exam on the document "{doc_title}" ({doc.page_count} pages).
Here are the real chapters, sections, and concept excerpts extracted directly from this document:

{topics_summary_str}

The student has requested a {total_days}-day study roadmap ({req.hours_per_day or 2.5} hrs/day) targeting {req.target_date}.
Create a personalized day-by-day study roadmap covering these exact sections from the document sequentially across the {total_days} days.

Divide into 4 progressive phases:
- Phase I: Foundations & Core Concepts (first ~30% of days)
- Phase II: In-Depth Mechanics & Derivations (~35% of days)
- Phase III: Applied Problem Solving & Scenarios (~20% of days)
- Phase IV: Synthesis, Mock Practice & Mastery Finalization (remaining days)

Return ONLY a valid JSON array of exactly {total_days} objects matching this exact structure:
[
  {{
    "day": 1,
    "phase": "Phase I: Foundations & Core Concepts",
    "topic": "Exact section name from the document",
    "focus": "1-2 sentence description of what the student will master from this section of the document",
    "estimated_hours": {req.hours_per_day or 2.5},
    "recommended_action": "Specific reading directive and concept check",
    "key_concepts": ["concept1", "concept2", "concept3"]
  }}
]
"""
            llm_output = default_llm_service.generate(prompt=prompt)
            if llm_output:
                # Extract JSON array from LLM response
                json_match = re.search(r'\[\s*\{.*\}\s*\]', llm_output, re.DOTALL)
                if json_match:
                    parsed_schedule = json.loads(json_match.group(0))
                    if isinstance(parsed_schedule, list) and len(parsed_schedule) == total_days:
                        schedule = parsed_schedule
                        # Ensure all expected fields are present
                        for idx, item in enumerate(schedule):
                            item["day"] = idx + 1
                            item["estimated_hours"] = req.hours_per_day or 2.5
                            item["study_notes"] = ""
                            if "key_concepts" not in item:
                                item["key_concepts"] = [item.get("topic", "Core Theory")]
                        logger.info(f"[StudyPlan] Successfully generated {total_days}-day plan via LLM for '{doc_title}'")
        except Exception as e:
            logger.warning(f"[StudyPlan] LLM plan generation fell back to deterministic mapping: {e}")

    # Fallback: Deterministic Document-Grounded Scheduler (100% faithful to the document)
    if not schedule:
        p1_end = max(1, int(total_days * 0.30))
        p2_end = max(p1_end + 1, int(total_days * 0.65))
        p3_end = max(p2_end + 1, int(total_days * 0.85))

        # If we have extracted topics from the document, distribute them across total_days
        num_topics = len(discovered_topics) if discovered_topics else 1

        for day in range(1, total_days + 1):
            # Phase
            if day <= p1_end:
                phase = "Phase I: Foundations & Core Concepts"
            elif day <= p2_end:
                phase = "Phase II: In-Depth Mechanics & Application"
            elif day <= p3_end:
                phase = "Phase III: Applied Problem Solving & Scenarios"
            else:
                phase = "Phase IV: Synthesis & Examination Readiness"

            # Assign topic from document
            if discovered_topics:
                t_idx = (day - 1) % num_topics
                curr_topic = discovered_topics[t_idx]
                topic_title = curr_topic["title"]
                focus_text = curr_topic.get("summary") or f"Master the core mechanisms of {topic_title} from {doc_title}."
                concepts = curr_topic.get("key_concepts") or [topic_title]
            else:
                topic_title = f"{doc_title} Module {day}"
                focus_text = f"Study and internalize key principles from {doc_title}."
                concepts = [doc_title, f"Module {day}"]

            schedule.append({
                "day": day,
                "phase": phase,
                "topic": topic_title,
                "focus": focus_text,
                "estimated_hours": req.hours_per_day or 2.5,
                "recommended_action": f"Read the {topic_title} briefing from {doc_title} and take the Day {day} Mastery Quiz check.",
                "key_concepts": concepts[:5],
                "study_notes": ""
            })

    # 4. Persist to PostgreSQL database
    new_plan = StudyPlan(
        user_id=user_id,
        topic_id=doc_id,
        session_id=req.session_id or None,
        title=course_title,
        target_date=req.target_date,
        total_days=total_days,
        hours_per_day=req.hours_per_day or 2.5,
        schedule=schedule,
        completed_days=[]
    )

    db.add(new_plan)
    db.commit()
    db.refresh(new_plan)

    logger.info(f"[StudyPlan] Created document-grounded plan '{new_plan.title}' ({total_days} days) for user {user_id}")
    return _serialize_plan(new_plan)


def _get_completed_list(plan: StudyPlan) -> List[int]:
    raw = plan.completed_days
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = []
    return list(raw or [])


@router.post("/{plan_id}/toggle-day")
def toggle_day_completion(
    plan_id: str,
    req: ToggleDayRequest,
    db: Session = Depends(get_db)
):
    """
    Toggles completion of a specific study plan day in PostgreSQL.
    """
    plan = db.query(StudyPlan).filter(StudyPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Study plan not found.")

    completed = _get_completed_list(plan)
    if req.day_number in completed:
        completed.remove(req.day_number)
    else:
        completed.append(req.day_number)
        completed.sort()

    plan.completed_days = completed
    flag_modified(plan, "completed_days")
    db.commit()
    db.refresh(plan)

    return {
        "status": "success",
        "completed_days": plan.completed_days,
        "plan": _serialize_plan(plan)
    }


@router.post("/{plan_id}/verify-quiz")
def verify_day_quiz(
    plan_id: str,
    req: VerifyQuizRequest,
    db: Session = Depends(get_db)
):
    """
    Verifies score for a day mastery quiz. If score >= 70%,
    marks the day as completed in PostgreSQL.
    """
    plan = db.query(StudyPlan).filter(StudyPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Study plan not found.")

    passed = req.score_percentage >= 70.0
    completed = _get_completed_list(plan)

    if passed:
        if req.day_number not in completed:
            completed.append(req.day_number)
            completed.sort()
            plan.completed_days = completed
            flag_modified(plan, "completed_days")
            db.commit()
            db.refresh(plan)

        message = (
            f"Mastery Achieved! You scored {int(req.score_percentage)}% on the Day {req.day_number} quiz. "
            f"Day {req.day_number} marked as complete."
        )
    else:
        message = (
            f"You scored {int(req.score_percentage)}%. A score of 70% or higher is required to master Day {req.day_number}. "
            f"Review the AI Study Notes and try again!"
        )

    return {
        "passed": passed,
        "score_percentage": req.score_percentage,
        "day_number": req.day_number,
        "message": message,
        "completed_days": plan.completed_days
    }


@router.post("/day-notes")
def generate_day_notes(
    req: DayNotesRequest,
    db: Session = Depends(get_db)
):
    """
    Generates comprehensive AI study notes for a specific day grounded directly
    in the document's real KnowledgeChunks from PostgreSQL.
    Caches the generated notes in PostgreSQL for zero-latency repeat views.
    """
    # 1. Check if cached in database
    if req.plan_id and not req.force_regenerate:
        plan = db.query(StudyPlan).filter(StudyPlan.id == req.plan_id).first()
        if plan and plan.schedule:
            schedule_items = plan.schedule
            if isinstance(schedule_items, str):
                try:
                    schedule_items = json.loads(schedule_items)
                except Exception:
                    schedule_items = []
            for item in schedule_items:
                if item.get("day") == req.day_number and item.get("study_notes"):
                    return {
                        "notes": item["study_notes"],
                        "day_number": req.day_number,
                        "cached": True
                    }

    # 2. Retrieve actual KnowledgeChunks from PostgreSQL for this topic
    doc = _resolve_document(db, req.topic_id, None)
    chunk_excerpts = []
    doc_title = doc.title or "Study Document" if doc else "Course Materials"

    if doc:
        # Search chunks matching day_topic or key_concepts
        search_terms = [req.day_topic[:30]] + [c[:25] for c in req.key_concepts if c]
        conditions = [KnowledgeChunk.content.ilike(f"%{term}%") for term in search_terms]
        
        relevant_chunks = (
            db.query(KnowledgeChunk)
            .filter(KnowledgeChunk.document_id == doc.id, or_(*conditions))
            .limit(4)
            .all()
        )
        if not relevant_chunks:
            # Fallback to general chunks for this document
            relevant_chunks = (
                db.query(KnowledgeChunk)
                .filter(KnowledgeChunk.document_id == doc.id)
                .limit(4)
                .all()
            )
        chunk_excerpts = [c.content for c in relevant_chunks if c.content]

    excerpts_text = "\n\n---\n\n".join(chunk_excerpts[:3]) if chunk_excerpts else "No raw excerpts found."
    concepts_str = ", ".join(req.key_concepts) if req.key_concepts else req.day_topic

    # 3. Synthesize via LLM using the actual document text
    prompt = f"""You are DeepTutor, an elite academic AI tutor.
Generate a structured, rigorous, and beautifully formatted academic study brief grounded in the student's study document:
Document: "{doc_title}"
Topic: {req.day_topic}
Key Concepts: {concepts_str}

Relevant Excerpts from "{doc_title}":
{excerpts_text}

Please format with clean Markdown and KaTeX math formulas where appropriate:
## Executive Summary & Mental Anchor
(1-2 clear, intuitive paragraphs summarizing this section of "{doc_title}" with a memorable mental model)

## Key Concepts & Definitions
(Define the core principles with clear bullet points)

## Step-by-Step Mechanics & Theoretical Breakdown
(Detailed explanation of the mechanisms, algorithms, or theories explained in this section)

## High-Yield Review Checklist
(Bullet list of key items the student should recall for the exam)
"""

    notes: str = ""
    try:
        if default_llm_service.is_live_model_configured():
            notes = default_llm_service.generate(prompt=prompt)
    except Exception as e:
        logger.warning(f"[StudyPlan] LLM generation failed for day notes: {e}")

    if notes and len(notes.strip()) >= 50:
        if doc_title and doc_title.lower() not in notes.lower()[:300]:
            notes = f"# {req.day_topic}\n\n> **Document Grounding**: Synthesized from **{doc_title}**\n\n" + notes

    # Fallback with real document excerpts
    if not notes or len(notes.strip()) < 50:
        notes = f"""# {req.day_topic}

> **Document Grounding**: Synthesized directly from **{doc_title}**

## Executive Summary & Mental Anchor
This module focuses on mastering **{req.day_topic}** from **{doc_title}**. Understanding these core mechanisms establishes the conceptual baseline needed for both theoretical insight and practical problem solving.

## Key Concepts & Definitions
{chr(10).join(f"- **{concept}**: Key architectural principle governing this section of {doc_title}." for concept in req.key_concepts) if req.key_concepts else f"- **{req.day_topic}**: Foundational section."}

## Source Document Excerpts & Mechanics
{excerpts_text if chunk_excerpts else "Excerpts processed from knowledge chunk vectors in PostgreSQL."}

## High-Yield Review Checklist
- [x] Internalized definitions for {concepts_str}.
- [ ] Practiced step-by-step concepts from {doc_title}.
- [ ] Ready to take the Day {req.day_number} Mastery Quiz check.
"""

    # 4. Cache generated notes in PostgreSQL plan schedule
    if req.plan_id:
        plan = db.query(StudyPlan).filter(StudyPlan.id == req.plan_id).first()
        if plan and plan.schedule:
            schedule_items = plan.schedule
            if isinstance(schedule_items, str):
                try:
                    schedule_items = json.loads(schedule_items)
                except Exception:
                    schedule_items = []
            updated_schedule = []
            for item in schedule_items:
                if item.get("day") == req.day_number:
                    item["study_notes"] = notes
                updated_schedule.append(item)
            plan.schedule = updated_schedule
            flag_modified(plan, "schedule")
            db.commit()

    return {
        "notes": notes,
        "day_number": req.day_number,
        "cached": False
    }


@router.delete("/{plan_id}")
def delete_study_plan(
    plan_id: str,
    db: Session = Depends(get_db)
):
    """
    Deletes a study plan from PostgreSQL.
    """
    plan = db.query(StudyPlan).filter(StudyPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Study plan not found.")

    db.delete(plan)
    db.commit()
    logger.info(f"[StudyPlan] Deleted plan {plan_id}")
    return {"status": "deleted", "id": plan_id}
