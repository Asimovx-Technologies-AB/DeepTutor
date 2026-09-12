"""
Exam Readiness Evaluator.

Acts as the terminal gatekeeper in the Intelligent Tutoring System pipeline:
- Assesses comprehensive curriculum mastery across all units.
- Decision Diamond: "Ready for Exam?"
  - If NO: Pinpoints specific unmastered topics/concepts to route back for targeted review.
  - If YES: Confirms mastery criteria met and awards "EXAM READY" status.
"""
from __future__ import annotations

import logging
from typing import Dict, List

from app.tutoring.curriculum.knowledge_map import knowledge_map_resolver
from app.tutoring.models import (
    CurriculumKnowledgeMap,
    ExamReadinessResult,
    PersonalizedStudyPlan,
    StudentModel,
)

logger = logging.getLogger(__name__)

READINESS_THRESHOLD_SCORE = 80.0  # 80% weighted coverage and mastery


class ExamReadinessEvaluator:
    """Evaluates whether a student is ready to take their milestone exam."""

    def __init__(self) -> None:
        self.resolver = knowledge_map_resolver

    def evaluate_readiness(
        self,
        curriculum: CurriculumKnowledgeMap,
        student_model: StudentModel,
        study_plan: PersonalizedStudyPlan,
    ) -> ExamReadinessResult:
        """
        Evaluates exam readiness across the curriculum.
        Calculates curriculum-wide mastery score and checks for unresolved weaknesses.
        """
        all_concepts = self.resolver.get_all_concepts(curriculum)
        total_concepts = len(all_concepts)

        if total_concepts == 0:
            return ExamReadinessResult(
                is_ready=True,
                readiness_score=100.0,
                weak_areas_to_review=[],
                recommendation_summary="No concepts found in curriculum. Exam ready.",
            )

        mastery_sum = 0.0
        weak_areas: List[str] = []

        for cid, concept in all_concepts.items():
            mastery = student_model.concept_mastery.get(cid, 0.0)
            mastery_sum += mastery

            # Flag if mastery is below passing threshold
            if mastery < 0.70:
                weak_areas.append(f"{concept.title} (Mastery: {int(mastery * 100)}%)")

        readiness_score = round((mastery_sum / total_concepts) * 100.0, 1)

        # Student is ready if score >= threshold AND no critical weak areas (< 50% mastery)
        has_critical_weakness = any(
            student_model.concept_mastery.get(cid, 0.0) < 0.50 for cid in all_concepts
        )

        is_ready = (readiness_score >= READINESS_THRESHOLD_SCORE) and not has_critical_weakness

        if is_ready:
            summary = (
                f"EXAM READY: Congratulations! Your curriculum readiness score is {readiness_score}%. "
                f"You have demonstrated thorough mastery across all {total_concepts} core concepts."
            )
        else:
            summary = (
                f"NOT READY FOR EXAM: Current readiness score is {readiness_score}% (Target: {READINESS_THRESHOLD_SCORE}%). "
                f"Review the {len(weak_areas)} flagged weak area(s) before attempting the examination."
            )

        return ExamReadinessResult(
            is_ready=is_ready,
            readiness_score=readiness_score,
            weak_areas_to_review=weak_areas,
            recommendation_summary=summary,
        )


exam_readiness_evaluator = ExamReadinessEvaluator()
