"""
Intelligent Tutoring System (ITS) API Endpoints.

Exposes the end-to-end ITS pipeline:
- Curriculum Knowledge Map Generation & DAG Resolution
- Personalized Multi-Session Study Planning
- 5-Dimensional Conceptual Teaching Engine (Visuals, History, Analogies, Examples, Theory)
- Formative Assessment & Practice
- Diagnostic Student Response Evaluation (UNDERSTAND? decision)
- Adaptive Remediation (5 Levers: Alt Expl, Simpler Analogy, Visuals, Hint, Breakdown)
- Live Mastery Progress Tracking & Exam Readiness Gatekeeper
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.auth import get_current_user
from app.tutoring.models import (
    CourseInput,
    FormativeQuestion,
    RemediationLever,
)
from app.tutoring.orchestrator import tutoring_orchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tutoring", tags=["Intelligent Tutoring System"])


# ─── Pydantic Request & Response Schemas ─────────────────────────────────────


class CurriculumBuildRequest(BaseModel):
    course_id: str
    subject: str
    course_info: Optional[str] = ""
    learning_objectives: Optional[List[str]] = []
    assessment_criteria: Optional[str] = ""
    material_text: Optional[str] = ""
    session_id_or_doc_id: Optional[str] = None


class StudyPlanCreateRequest(BaseModel):
    course_id: str
    target_date: Optional[str] = ""
    daily_minutes: Optional[int] = 45
    goal_level: Optional[str] = "Undergraduate"
    learning_pace: Optional[str] = "standard"
    prior_knowledge: Optional[str] = "intermediate"


class ConceptTeachRequest(BaseModel):
    course_id: str
    concept_id: str
    context_text: Optional[str] = ""


class PracticeQuestionRequest(BaseModel):
    course_id: str
    concept_id: str
    question_type: Optional[str] = "conceptual"


class PracticeSubmitRequest(BaseModel):
    course_id: str
    concept_id: str
    question: Dict[str, Any]
    student_answer: str
    consecutive_failures: Optional[int] = 1


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.post("/curriculum/build")
async def build_curriculum_endpoint(
    body: CurriculumBuildRequest,
    user: dict = Depends(get_current_user),
):
    """Generates the hierarchical Curriculum Knowledge Map from course materials."""
    course_input = CourseInput(
        course_id=body.course_id,
        course_info=body.course_info or body.subject,
        learning_objectives=body.learning_objectives or [],
        assessment_criteria=body.assessment_criteria or "",
        subject=body.subject,
    )
    km = await tutoring_orchestrator.build_curriculum(
        course_input=course_input,
        material_text=body.material_text or "",
        session_id_or_doc_id=body.session_id_or_doc_id,
    )
    return {
        "course_id": km.course_id,
        "title": km.title,
        "subject": km.subject,
        "topics": [
            {
                "topic_id": t.topic_id,
                "title": t.title,
                "summary": t.summary,
                "subtopics": [
                    {
                        "subtopic_id": st.subtopic_id,
                        "title": st.title,
                        "concepts": [
                            {
                                "concept_id": c.concept_id,
                                "title": c.title,
                                "description": c.description,
                                "difficulty": c.difficulty,
                                "prerequisites": c.prerequisites,
                                "key_terms": c.key_terms,
                                "knowledge_box_ids": c.knowledge_box_ids,
                            }
                            for c in st.concepts
                        ],
                    }
                    for st in t.subtopics
                ],
            }
            for t in km.topics
        ],
        "dependency_graph": km.dependency_graph,
    }


@router.get("/curriculum/{course_id}")
async def get_curriculum_endpoint(
    course_id: str,
    user: dict = Depends(get_current_user),
):
    """Retrieves cached or generated Curriculum Knowledge Map."""
    km = tutoring_orchestrator.get_curriculum(course_id)
    if not km:
        raise HTTPException(status_code=404, detail=f"Curriculum not found for course '{course_id}'.")
    return {
        "course_id": km.course_id,
        "title": km.title,
        "subject": km.subject,
        "topics": [
            {
                "topic_id": t.topic_id,
                "title": t.title,
                "summary": t.summary,
                "subtopics": [
                    {
                        "subtopic_id": st.subtopic_id,
                        "title": st.title,
                        "concepts": [
                            {
                                "concept_id": c.concept_id,
                                "title": c.title,
                                "description": c.description,
                                "difficulty": c.difficulty,
                                "prerequisites": c.prerequisites,
                                "key_terms": c.key_terms,
                                "knowledge_box_ids": c.knowledge_box_ids,
                            }
                            for c in st.concepts
                        ],
                    }
                    for st in t.subtopics
                ],
            }
            for t in km.topics
        ],
        "dependency_graph": km.dependency_graph,
    }


@router.post("/plan/create")
async def create_study_plan_endpoint(
    body: StudyPlanCreateRequest,
    user: dict = Depends(get_current_user),
):
    """Generates an individualized, sequenced multi-session study plan."""
    tutoring_orchestrator.get_or_create_student(
        user_id=user["id"],
        goal_level=body.goal_level,
        learning_pace=body.learning_pace,
        prior_knowledge=body.prior_knowledge,
    )

    try:
        plan = tutoring_orchestrator.create_study_plan(
            user_id=user["id"],
            course_id=body.course_id,
            target_date=body.target_date or "",
            daily_minutes=body.daily_minutes or 45,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "plan_id": plan.plan_id,
        "student_id": plan.student_id,
        "course_id": plan.course_id,
        "target_date": plan.target_date,
        "sessions": [
            {
                "session_number": s.session_number,
                "title": s.title,
                "target_concepts": s.target_concepts,
                "estimated_minutes": s.estimated_minutes,
                "status": s.status,
            }
            for s in plan.sessions
        ],
        "is_exam_ready": plan.is_exam_ready,
    }


@router.post("/teach")
async def teach_concept_endpoint(
    body: ConceptTeachRequest,
    user: dict = Depends(get_current_user),
):
    """Produces 5-dimensional pedagogical explanation for the target concept."""
    dimensions = await tutoring_orchestrator.teach_concept(
        user_id=user["id"],
        course_id=body.course_id,
        concept_id=body.concept_id,
        context_text=body.context_text or "",
    )
    return {
        "concept_id": dimensions.concept_id,
        "concept_title": dimensions.concept_title,
        "visual_description": dimensions.visual_description,
        "historical_context": dimensions.historical_context,
        "analogy": dimensions.analogy,
        "examples": dimensions.examples,
        "detail_theory": dimensions.detail_theory,
        "figures": dimensions.figures,
        "tables": dimensions.tables,
        "formulas": dimensions.formulas,
    }


@router.post("/practice/generate")
async def generate_practice_endpoint(
    body: PracticeQuestionRequest,
    user: dict = Depends(get_current_user),
):
    """Generates formative diagnostic question testing core principles and traps."""
    q = await tutoring_orchestrator.generate_formative_question(
        user_id=user["id"],
        course_id=body.course_id,
        concept_id=body.concept_id,
        question_type=body.question_type or "conceptual",
    )
    return {
        "question_id": q.question_id,
        "concept_id": q.concept_id,
        "prompt": q.prompt,
        "question_type": q.question_type,
        "rubric": q.rubric,
        "common_pitfalls": q.common_pitfalls,
        "hints": q.hints,
    }


@router.post("/practice/submit")
async def submit_practice_endpoint(
    body: PracticeSubmitRequest,
    user: dict = Depends(get_current_user),
):
    """
    Evaluates student answer, makes the UNDERSTAND? decision,
    and returns adaptive remediation or updated mastery progress snapshot.
    """
    q_data = body.question
    question = FormativeQuestion(
        question_id=q_data.get("question_id", "q_temp"),
        concept_id=body.concept_id,
        prompt=q_data.get("prompt", ""),
        question_type=q_data.get("question_type", "conceptual"),
        rubric=q_data.get("rubric", ""),
        common_pitfalls=q_data.get("common_pitfalls", []),
        hints=q_data.get("hints", []),
    )

    eval_result, remediation_pkg, snapshot = await tutoring_orchestrator.process_student_response(
        user_id=user["id"],
        course_id=body.course_id,
        concept_id=body.concept_id,
        question=question,
        student_answer=body.student_answer,
        consecutive_failures=body.consecutive_failures or 1,
    )

    return {
        "evaluation": {
            "is_understood": eval_result.is_understood,
            "score": eval_result.score,
            "diagnosed_gap": eval_result.diagnosed_gap,
            "misconception": eval_result.misconception,
            "feedback": eval_result.feedback,
            "next_action": eval_result.next_action,
        },
        "remediation": (
            {
                "lever_used": remediation_pkg.lever_used.value,
                "content": remediation_pkg.content,
                "scaffolding_step": remediation_pkg.scaffolding_step,
                "suggested_follow_up": remediation_pkg.suggested_follow_up,
            }
            if remediation_pkg
            else None
        ),
        "progress_snapshot": (
            {
                "retained": snapshot.retained,
                "in_progress": snapshot.in_progress,
                "weak_areas": snapshot.weak_areas,
                "strengths": snapshot.strengths,
                "recommendations": snapshot.recommendations,
            }
            if snapshot
            else None
        ),
    }


@router.get("/exam-readiness/{course_id}")
async def get_exam_readiness_endpoint(
    course_id: str,
    user: dict = Depends(get_current_user),
):
    """Assesses overall curriculum mastery and evaluates 'Ready for Exam?'."""
    result = tutoring_orchestrator.check_exam_readiness(
        user_id=user["id"],
        course_id=course_id,
    )
    return {
        "is_ready": result.is_ready,
        "readiness_score": result.readiness_score,
        "weak_areas_to_review": result.weak_areas_to_review,
        "recommendation_summary": result.recommendation_summary,
    }
