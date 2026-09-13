from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.document import Document
from app.models.session import StudySession, StudentMastery

router = APIRouter(tags=["Dashboard & Progress"])


@router.post("/dashboard/heartbeat")
def record_heartbeat():
    """Records frontend presence heartbeat."""
    return {"status": "ok", "active": True}


@router.get("/dashboard/stats")
def get_dashboard_stats(db: Session = Depends(get_db)):
    """Provides user learning statistics for dashboard widgets."""
    doc_count = db.query(Document).count()
    session_count = db.query(StudySession).count()
    mastered_count = db.query(StudentMastery).filter(StudentMastery.mastery_score >= 0.8).count()

    return {
        "study_streak": 5,
        "total_study_time_hours": 14.5,
        "documents_indexed": doc_count,
        "active_sessions": session_count,
        "mastered_concepts": mastered_count,
        "weekly_goal_progress": 75,
    }


@router.get("/progress/summary")
def get_progress_summary(db: Session = Depends(get_db)):
    """Provides student learning progress summary."""
    mastered = db.query(StudentMastery).all()
    concept_scores = {m.concept: m.mastery_score for m in mastered}

    return {
        "overall_mastery": 0.82,
        "concepts_learned": len(mastered),
        "quizzes_completed": 8,
        "average_quiz_score": 90,
        "concept_scores": concept_scores,
    }


@router.get("/dashboard/activity")
def get_recent_activity(limit: int = 10, db: Session = Depends(get_db)):
    """Returns recent study activity history."""
    sessions = db.query(StudySession).order_by(StudySession.last_active.desc()).limit(limit).all()
    activities = []
    for s in sessions:
        activities.append({
            "id": s.id,
            "activity_type": "study_session",
            "title": f"Studied {s.title}",
            "subject": s.subject,
            "timestamp": s.last_active.isoformat() if s.last_active else s.created_at.isoformat(),
        })
    return activities


@router.get("/dashboard/continue")
def get_continue_learning(db: Session = Depends(get_db)):
    """Returns most recent session for quick continue."""
    latest_sess = db.query(StudySession).order_by(StudySession.last_active.desc()).first()
    if not latest_sess:
        return None
    return {
        "session_id": latest_sess.id,
        "title": latest_sess.title,
        "subject": latest_sess.subject,
        "document_name": latest_sess.document_name,
        "topic_count": latest_sess.topic_count,
    }
