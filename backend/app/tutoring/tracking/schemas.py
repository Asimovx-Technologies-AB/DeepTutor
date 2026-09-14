"""
Tracking Agent Schemas
======================
Data contracts for learning events, student mastery updates, and gamification metrics.
"""

from typing import List, Dict, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class AnswerEventSchema(BaseModel):
    topic: str = Field(..., description="Target academic topic or concept")
    is_correct: bool = Field(..., description="Whether the student answered correctly")
    timestamp: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))
    student_id: str = Field(default="default_user", description="Identifier of the student")
    question_id: Optional[str] = Field(None, description="Optional question/card identifier")
    mode: Optional[str] = Field("quiz", description="'quiz' or 'flashcards'")


class TopicMasteryInfo(BaseModel):
    topic: str
    mastery_score: float
    practice_attempts: int
    successful_attempts: int
    is_weak_topic: bool


class MasteryReportSchema(BaseModel):
    student_id: str
    total_xp: int
    streak_days: int
    weak_topics: List[str]
    topic_masteries: List[TopicMasteryInfo]
