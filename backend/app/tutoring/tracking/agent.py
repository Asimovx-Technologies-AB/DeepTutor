"""
Tracking Agent
==============
Ingests fine-grained learning events (quiz & flashcard answers), updates concept
mastery models, generates weak-topic diagnostics, and manages gamification state.
"""

from datetime import datetime, timezone
import logging
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.session import StudentMastery, StudentProfile
from app.tutoring.tracking.schemas import AnswerEventSchema, MasteryReportSchema, TopicMasteryInfo

logger = logging.getLogger(__name__)


class TrackingAgent:
    """
    Tracking Agent monitoring student performance, mastery progression, and gamification rewards.
    """

    XP_CORRECT = 15
    XP_ATTEMPT = 5

    @classmethod
    def record_answer_event(
        cls,
        event: AnswerEventSchema,
        db: Session
    ) -> Dict[str, Any]:
        """
        Processes a single question or card interaction.
        Updates mastery in PostgreSQL and returns instant gamification delta.
        """
        student_id = event.student_id or "default_user"
        topic_name = event.topic.strip() or "General Knowledge"
        now = event.timestamp or datetime.now(timezone.utc)

        # 1. Update or create StudentMastery
        mastery = (
            db.query(StudentMastery)
            .filter(
                StudentMastery.user_id == student_id,
                StudentMastery.concept == topic_name
            )
            .first()
        )

        if not mastery:
            mastery = StudentMastery(
                user_id=student_id,
                concept=topic_name,
                mastery_score=0.5,
                practice_attempts=0,
                successful_attempts=0,
                last_practiced=now
            )
            db.add(mastery)
            db.flush()

        mastery.practice_attempts += 1
        if event.is_correct:
            mastery.successful_attempts += 1

        # Calculate updated rolling mastery score (0.0 to 1.0)
        success_ratio = mastery.successful_attempts / max(1, mastery.practice_attempts)
        immediate_bonus = 1.0 if event.is_correct else 0.0
        # 80% weight on cumulative ratio, 20% on latest answer
        mastery.mastery_score = round(min(1.0, max(0.0, (success_ratio * 0.8) + (immediate_bonus * 0.2))), 3)
        mastery.last_practiced = now

        # 2. Update StudentProfile for gamification (XP & streak)
        profile = db.query(StudentProfile).filter(StudentProfile.user_id == student_id).first()
        if not profile:
            profile = StudentProfile(
                user_id=student_id,
                preferred_difficulty="Intermediate",
                learning_goals=["Concept Mastery"],
                mastery_summary={
                    "total_xp": 0,
                    "streak_days": 1,
                    "last_active_date": now.strftime("%Y-%m-%d"),
                    "total_questions_answered": 0,
                }
            )
            db.add(profile)
            db.flush()

        summary = profile.mastery_summary or {}
        xp_earned = cls.XP_CORRECT if event.is_correct else cls.XP_ATTEMPT
        current_xp = summary.get("total_xp", 0) + xp_earned
        total_answered = summary.get("total_questions_answered", 0) + 1

        today_str = now.strftime("%Y-%m-%d")
        last_date = summary.get("last_active_date")
        streak = summary.get("streak_days", 1)
        if last_date != today_str:
            streak += 1

        summary["total_xp"] = current_xp
        summary["total_questions_answered"] = total_answered
        summary["streak_days"] = streak
        summary["last_active_date"] = today_str
        profile.mastery_summary = summary
        flag_modified(profile, "mastery_summary")

        db.commit()

        is_weak = mastery.mastery_score < 0.6
        return {
            "status": "recorded",
            "topic": topic_name,
            "is_correct": event.is_correct,
            "xp_earned": xp_earned,
            "total_xp": current_xp,
            "streak_days": streak,
            "mastery_score": mastery.mastery_score,
            "is_weak_topic": is_weak
        }

    @classmethod
    def get_student_summary(
        cls,
        student_id: str,
        db: Session
    ) -> MasteryReportSchema:
        """
        Retrieves complete student mastery, weak topics, and gamification snapshot.
        """
        profile = db.query(StudentProfile).filter(StudentProfile.user_id == student_id).first()
        summary = profile.mastery_summary if profile and profile.mastery_summary else {}
        total_xp = summary.get("total_xp", 0)
        streak_days = summary.get("streak_days", 1)

        masteries = db.query(StudentMastery).filter(StudentMastery.user_id == student_id).all()
        topic_info_list: List[TopicMasteryInfo] = []
        weak_topics: List[str] = []

        for m in masteries:
            is_weak = m.mastery_score < 0.6
            if is_weak:
                weak_topics.append(m.concept)
            topic_info_list.append(
                TopicMasteryInfo(
                    topic=m.concept,
                    mastery_score=m.mastery_score,
                    practice_attempts=m.practice_attempts,
                    successful_attempts=m.successful_attempts,
                    is_weak_topic=is_weak
                )
            )

        return MasteryReportSchema(
            student_id=student_id,
            total_xp=total_xp,
            streak_days=streak_days,
            weak_topics=weak_topics,
            topic_masteries=topic_info_list
        )
