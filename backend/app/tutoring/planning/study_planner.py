"""
Personalized Study Planner.

Constructs an adaptive, sequenced study schedule (Session 1 .. Session N)
tailored to the student's learning pace, target deadlines, prior knowledge,
and diagnosed weaknesses, adhering to prerequisite DAG constraints.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.tutoring.curriculum.knowledge_map import knowledge_map_resolver
from app.tutoring.models import (
    ConceptNode,
    CurriculumKnowledgeMap,
    PersonalizedStudyPlan,
    SessionPlan,
    StudentModel,
    StudentProfile,
)

logger = logging.getLogger(__name__)


class StudyPlanner:
    """Generates and manages individualized session-by-session study plans."""

    def __init__(self) -> None:
        self.resolver = knowledge_map_resolver

    def generate_plan(
        self,
        student_profile: StudentProfile,
        student_model: StudentModel,
        curriculum: CurriculumKnowledgeMap,
        target_date: str = "",
        daily_minutes: int = 45,
    ) -> PersonalizedStudyPlan:
        """
        Creates a new PersonalizedStudyPlan with sequenced SessionPlans.
        Filters out concepts already mastered (> 0.85 mastery) unless flagged as weak.
        """
        # 1. Obtain topographically sorted sequence of concepts
        sorted_concepts = self.resolver.get_topological_sequence(curriculum)

        # 2. Determine concepts to cover
        concepts_to_study: List[ConceptNode] = []
        mastered_threshold = 0.85

        for c in sorted_concepts:
            mastery = student_model.concept_mastery.get(c.concept_id, 0.0)
            is_weak = any(w.get("concept_id") == c.concept_id for w in student_model.weaknesses)
            if mastery < mastered_threshold or is_weak:
                concepts_to_study.append(c)

        # If all were mastered, retain at least all concepts for comprehensive review
        if not concepts_to_study:
            concepts_to_study = sorted_concepts

        # 3. Determine concepts per session based on pace
        pace = student_profile.learning_pace.lower()
        if pace == "accelerated":
            concepts_per_session = 3
            session_duration = max(daily_minutes, 60)
        elif pace == "thorough":
            concepts_per_session = 1
            session_duration = min(daily_minutes, 30)
        else:  # standard
            concepts_per_session = 2
            session_duration = daily_minutes or 45

        # 4. Group into sessions
        sessions: List[SessionPlan] = []
        session_idx = 1

        for i in range(0, len(concepts_to_study), concepts_per_session):
            chunk = concepts_to_study[i : i + concepts_per_session]
            c_ids = [c.concept_id for c in chunk]
            c_titles = [c.title for c in chunk]

            title = f"Session {session_idx}: {', '.join(c_titles[:2])}"
            if len(c_titles) > 2:
                title += f" (+{len(c_titles) - 2} more)"

            sessions.append(
                SessionPlan(
                    session_number=session_idx,
                    title=title,
                    target_concepts=c_ids,
                    estimated_minutes=session_duration,
                    status="pending" if session_idx > 1 else "in_progress",
                )
            )
            session_idx += 1

        plan_id = f"plan_{student_profile.user_id}_{curriculum.course_id}_{uuid.uuid4().hex[:8]}"

        return PersonalizedStudyPlan(
            plan_id=plan_id,
            student_id=student_profile.user_id,
            course_id=curriculum.course_id,
            sessions=sessions,
            target_date=target_date,
            is_exam_ready=False,
        )

    def get_current_session(
        self, plan: PersonalizedStudyPlan
    ) -> Optional[SessionPlan]:
        """Returns the active (in_progress) session, or first pending session."""
        for s in plan.sessions:
            if s.status == "in_progress":
                return s
        for s in plan.sessions:
            if s.status == "pending":
                s.status = "in_progress"
                return s
        return None

    def mark_session_completed(
        self, plan: PersonalizedStudyPlan, session_number: int
    ) -> Optional[SessionPlan]:
        """
        Marks specified session as completed and advances the next pending session to in_progress.
        Returns the next session or None if plan is complete.
        """
        next_session: Optional[SessionPlan] = None
        for i, s in enumerate(plan.sessions):
            if s.session_number == session_number:
                s.status = "completed"
                s.completed_at = datetime.now(timezone.utc)
                # Next session becomes in_progress
                if i + 1 < len(plan.sessions):
                    plan.sessions[i + 1].status = "in_progress"
                    next_session = plan.sessions[i + 1]
                break

        # Check if all sessions are completed
        all_completed = all(s.status == "completed" for s in plan.sessions)
        if all_completed:
            plan.is_exam_ready = True

        return next_session


study_planner = StudyPlanner()
