"""
Tracking & Gamification API Router
==================================
Provides HTTP endpoints to ingest student question answer events and
retrieve student mastery profiles and weak-topic analytics.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.tutoring.tracking.schemas import AnswerEventSchema, MasteryReportSchema
from app.tutoring.tracking.agent import TrackingAgent

router = APIRouter(prefix="/tracking", tags=["Tracking & Gamification"])


@router.post("/events")
def record_learning_event(
    event: AnswerEventSchema,
    db: Session = Depends(get_db)
):
    """
    Ingests an answer attempt event from the flashcard/quiz UI hook,
    updates topic mastery in PostgreSQL, and awards gamification XP.
    """
    return TrackingAgent.record_answer_event(event=event, db=db)


@router.get("/summary/{student_id}", response_model=MasteryReportSchema)
def get_student_mastery_summary(
    student_id: str,
    db: Session = Depends(get_db)
):
    """
    Returns the comprehensive mastery snapshot, weak topics, and streak status.
    """
    return TrackingAgent.get_student_summary(student_id=student_id, db=db)
