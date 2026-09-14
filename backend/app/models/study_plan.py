import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Float, DateTime, ForeignKey, JSON
)
from sqlalchemy.orm import relationship
from app.core.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class StudyPlan(Base):
    """
    Study Plan model representing an AI-generated, day-by-day learning roadmap
    tailored to a student's course materials, target exam date, and daily hours.
    """
    __tablename__ = "study_plans"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), default="default_user", index=True, nullable=False)
    topic_id = Column(String(128), nullable=True)
    session_id = Column(String(36), ForeignKey("study_sessions.id", ondelete="SET NULL"), nullable=True, index=True)

    title = Column(String(255), nullable=False, default="Custom Study Plan")
    target_date = Column(String(32), nullable=False)
    total_days = Column(Integer, default=10, nullable=False)
    hours_per_day = Column(Float, default=2.0, nullable=False)

    # List of daily schedule milestones
    # [{ day: 1, phase: "Phase 1: ...", topic: "...", focus: "...", estimated_hours: 2, recommended_action: "...", key_concepts: [...], study_notes: "..." }]
    schedule = Column(JSON, default=list, nullable=False)

    # List of integer day numbers completed e.g. [1, 2, 4]
    completed_days = Column(JSON, default=list, nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    # Relationship to StudySession if linked
    session = relationship("StudySession")
