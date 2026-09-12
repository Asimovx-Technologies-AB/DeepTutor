"""
Knowledge Gap Identifier.

Analyzes assessment failures and diagnostic traces to pinpoint the exact root
cause of a student's lack of understanding:
- Missing or unmastered prerequisite concepts
- Core conceptual misunderstandings / flawed mental models
- Procedural or execution slips
- Misinterpreted problem parameters
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.tutoring.curriculum.knowledge_map import knowledge_map_resolver
from app.tutoring.models import (
    ConceptNode,
    CurriculumKnowledgeMap,
    EvaluationResult,
    RemediationLever,
    StudentModel,
)

logger = logging.getLogger(__name__)


class GapIdentifier:
    """Diagnoses root causes of student misunderstanding and selects remediation levers."""

    def __init__(self) -> None:
        self.resolver = knowledge_map_resolver

    def diagnose_gap(
        self,
        concept: ConceptNode,
        eval_result: EvaluationResult,
        student_model: StudentModel,
        curriculum: Optional[CurriculumKnowledgeMap] = None,
        consecutive_failures: int = 1,
    ) -> Dict[str, Any]:
        """
        Pinpoints the gap and determines the recommended remediation lever.
        """
        # 1. Check if unmastered prerequisites are contributing
        unmastered_prereqs: List[str] = []
        if curriculum:
            prereqs = self.resolver.get_prerequisites(curriculum, concept.concept_id)
            for p in prereqs:
                mastery = student_model.concept_mastery.get(p.concept_id, 0.0)
                if mastery < 0.65:
                    unmastered_prereqs.append(p.title)

        diagnosed_gap = eval_result.diagnosed_gap or "Inability to apply governing principles."
        misconception = eval_result.misconception

        # 2. Select remediation lever based on consecutive attempts and diagnosis
        if unmastered_prereqs:
            lever = RemediationLever.BREAKDOWN
            gap_summary = (
                f"Missing foundational prerequisite(s): {', '.join(unmastered_prereqs)}. "
                f"Requires structural breakdown."
            )
        elif consecutive_failures >= 3:
            lever = RemediationLever.BREAKDOWN
            gap_summary = f"Persistent difficulty: {diagnosed_gap}. Breaking down into micro-steps."
        elif consecutive_failures == 2:
            lever = RemediationLever.ALTERNATIVE_EXPLANATION
            gap_summary = f"Conceptual block: {diagnosed_gap}. Reframing from an alternative angle."
        elif misconception:
            lever = RemediationLever.SIMPLER_ANALOGY
            gap_summary = f"Misconception identified: '{misconception}'. Resolving via grounded analogy."
        else:
            lever = RemediationLever.HINT
            gap_summary = f"Minor gap: {diagnosed_gap}. Providing targeted scaffolding hint."

        return {
            "concept_id": concept.concept_id,
            "gap_summary": gap_summary,
            "diagnosed_gap": diagnosed_gap,
            "misconception": misconception,
            "unmastered_prereqs": unmastered_prereqs,
            "recommended_lever": lever,
            "consecutive_failures": consecutive_failures,
        }


gap_identifier = GapIdentifier()
