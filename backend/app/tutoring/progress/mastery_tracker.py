"""
Student Mastery Tracker & Progress Snapshot Engine.

Maintains live cognitive state, updates mastery scores via Bayesian Knowledge
Tracing (BKT) heuristics, categorizes concepts into Retained, In Progress, Weak
Areas, Strengths, and Recommendations, and evaluates the ASSESSMENT PASS? decision.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.tutoring.models import (
    ConceptNode,
    CurriculumKnowledgeMap,
    EvaluationResult,
    ProgressSnapshot,
    StudentModel,
)
from app.tutoring.student.student_model import student_model_manager

logger = logging.getLogger(__name__)

PASS_MASTERY_THRESHOLD = 0.75


class MasteryTracker:
    """Tracks concept mastery, computes progress snapshots, and decides assessment passes."""

    def __init__(self) -> None:
        self.model_manager = student_model_manager

    def record_attempt(
        self,
        student_model: StudentModel,
        concept: ConceptNode,
        eval_result: EvaluationResult,
    ) -> StudentModel:
        """
        Updates student model after an assessment response.
        Updates BKT mastery and registers strengths, weaknesses, or misconceptions.
        """
        # Update concept mastery via model manager
        student_model = self.model_manager.update_mastery(
            model=student_model,
            concept_id=concept.concept_id,
            is_correct=eval_result.is_understood,
            score=eval_result.score,
        )

        current_mastery = student_model.concept_mastery.get(concept.concept_id, 0.5)

        if eval_result.is_understood and eval_result.score >= 0.85:
            # Register as strength if not already present
            existing_s = [s for s in student_model.strengths if s.get("concept_id") == concept.concept_id]
            if not existing_s:
                student_model.strengths.append(
                    {
                        "concept_id": concept.concept_id,
                        "title": concept.title,
                        "score": eval_result.score,
                        "mastered_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
            # Remove from weaknesses if previously flagged and now resolved
            student_model.weaknesses = [
                w for w in student_model.weaknesses if w.get("concept_id") != concept.concept_id
            ]

        elif not eval_result.is_understood:
            # Register weakness
            gap = eval_result.diagnosed_gap or "General conceptual deficiency"
            existing_w = next(
                (w for w in student_model.weaknesses if w.get("concept_id") == concept.concept_id),
                None,
            )
            if existing_w:
                existing_w["frequency"] = existing_w.get("frequency", 1) + 1
                existing_w["last_error"] = gap
            else:
                student_model.weaknesses.append(
                    {
                        "concept_id": concept.concept_id,
                        "title": concept.title,
                        "gap": gap,
                        "frequency": 1,
                        "flagged_at": datetime.now(timezone.utc).isoformat(),
                    }
                )

            # Register misconception if diagnosed
            if eval_result.misconception:
                student_model.misconceptions.append(
                    {
                        "concept_id": concept.concept_id,
                        "title": concept.title,
                        "misconception": eval_result.misconception,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )

        return student_model

    def check_assessment_pass(
        self,
        student_model: StudentModel,
        concept_id: str,
    ) -> bool:
        """
        ASSESSMENT PASS? decision diamond.
        Returns True if the student's mastery for this concept meets or exceeds the pass threshold.
        """
        mastery = student_model.concept_mastery.get(concept_id, 0.0)
        return mastery >= PASS_MASTERY_THRESHOLD

    def get_progress_snapshot(
        self,
        student_model: StudentModel,
        curriculum: CurriculumKnowledgeMap,
    ) -> ProgressSnapshot:
        """
        Aggregates live state into Retained, In Progress, Weak Areas, Strengths, and Recommendations.
        """
        retained: List[Dict[str, Any]] = []
        in_progress: List[Dict[str, Any]] = []
        weak_areas: List[Dict[str, Any]] = list(student_model.weaknesses)
        strengths: List[Dict[str, Any]] = list(student_model.strengths)
        recommendations: List[str] = []

        # Scan all curriculum concepts
        for topic in curriculum.topics:
            for subtopic in topic.subtopics:
                for concept in subtopic.concepts:
                    cid = concept.concept_id
                    mastery = student_model.concept_mastery.get(cid, 0.0)

                    entry = {
                        "concept_id": cid,
                        "title": concept.title,
                        "mastery": round(mastery, 2),
                        "difficulty": concept.difficulty,
                    }

                    if mastery >= 0.80:
                        retained.append(entry)
                    elif mastery > 0.10:
                        in_progress.append(entry)

        # Formulate intelligent pedagogical recommendations
        if weak_areas:
            top_weak = weak_areas[0]
            recommendations.append(
                f"Prioritize targeted review for '{top_weak.get('title', top_weak.get('concept_id'))}' "
                f"to resolve persistent gap: {top_weak.get('gap', 'unmastered mechanics')}."
            )

        if in_progress:
            curr = in_progress[0]
            recommendations.append(
                f"Continue active practice on '{curr.get('title')}' (current mastery: {int(curr.get('mastery', 0)*100)}%)."
            )
        elif not weak_areas:
            recommendations.append("All in-progress units mastered. Proceed to next syllabus module or final exam readiness review.")

        return ProgressSnapshot(
            retained=retained,
            in_progress=in_progress,
            weak_areas=weak_areas,
            strengths=strengths,
            recommendations=recommendations,
        )


mastery_tracker = MasteryTracker()
