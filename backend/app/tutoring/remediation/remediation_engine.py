"""
Adaptive Remediation Engine.

Implements the five adaptive pedagogical remediation levers with cognitive scaffolding:
1. Alternative Explanation: Reframing the concept from a completely different formal perspective.
2. Simpler Analogy: Grounding abstract mechanics in intuitive, everyday physical metaphors.
3. Visuals: Mental model diagrams, spatial relationships, and geometric intuitions.
4. Hint: Progressive targeted scaffolding clue without giving away the full answer.
5. Breakdown: Deconstructing the concept or problem into sequential micro-steps.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.rag.llm_client import llm_client
from app.tutoring.models import (
    ConceptNode,
    RemediationLever,
    RemediationPackage,
    StudentProfile,
)
from app.tutoring.teaching.explanation_engine import sanitize_katex_math

logger = logging.getLogger(__name__)

REMEDIATION_PROMPT = """You are an elite diagnostic tutor providing targeted adaptive remediation.

CONCEPT:
Title: {concept_title}
Description: {concept_description}

DIAGNOSED GAP / MISCONCEPTION:
{gap_diagnosis}

REMEDIATION LEVER TO EXECUTE:
{lever_instruction}

STUDENT LEVEL:
{goal_level}

CRITICAL RULES:
1. Focus strictly on repairing the diagnosed gap.
2. Use KaTeX notation ($$...$$ or $...$) for all mathematical expressions.
3. No emojis. Academic, supportive, and intellectually rigorous tone.
4. Conclude with a clear check question or thought prompt to re-engage the student.

Remediation:"""

LEVER_INSTRUCTIONS = {
    RemediationLever.ALTERNATIVE_EXPLANATION: (
        "Deliver an ALTERNATIVE EXPLANATION. Do not repeat the earlier explanation. "
        "Approach the concept from a completely different pedagogical angle (e.g. geometric if algebraic before, "
        "or energy-based if force-based before)."
    ),
    RemediationLever.SIMPLER_ANALOGY: (
        "Deliver a SIMPLER ANALOGY. Craft an intuitive, grounded physical analogy that directly addresses "
        "the misconception, showing why the flawed assumption breaks down in daily life and how the true principle works."
    ),
    RemediationLever.VISUALS: (
        "Deliver a VISUAL / SPATIAL MENTAL MODEL. Describe in vivid detail the visual representation, "
        "coordinates, axes, flows, and transformations that allow the student to 'see' the mechanism working."
    ),
    RemediationLever.HINT: (
        "Provide a TARGETED HINT. Give a subtle, high-leverage clue that points the student toward the key relation "
        "they overlooked, without directly revealing the complete resolution."
    ),
    RemediationLever.BREAKDOWN: (
        "Deliver a STEP-BY-STEP BREAKDOWN. Deconstruct this concept into 3 simple, sequential micro-steps: "
        "Step 1: Foundational premise, Step 2: The transformational mechanism, Step 3: The final result."
    ),
}


class RemediationEngine:
    """Generates remediation packages using the 5 adaptive levers."""

    def __init__(self) -> None:
        self.llm = llm_client

    async def generate_remediation(
        self,
        concept: ConceptNode,
        gap_diagnosis: str,
        lever: RemediationLever,
        student_profile: StudentProfile,
        scaffolding_step: int = 1,
    ) -> RemediationPackage:
        """Constructs an adaptive remediation package using the specified lever."""
        instruction = LEVER_INSTRUCTIONS.get(
            lever, LEVER_INSTRUCTIONS[RemediationLever.ALTERNATIVE_EXPLANATION]
        )

        prompt = REMEDIATION_PROMPT.format(
            concept_title=concept.title,
            concept_description=concept.description,
            gap_diagnosis=gap_diagnosis,
            lever_instruction=instruction,
            goal_level=student_profile.goal_level,
        )

        try:
            content = await self.llm.generate(prompt)
        except Exception as exc:
            logger.debug("[RemediationEngine] LLM remediation notice: %s. Using heuristic fallback.", exc)
            content = self._heuristic_remediation(concept, gap_diagnosis, lever)

        cleaned_content = sanitize_katex_math(content.strip())
        suggested_follow_up = f"Now, reflecting on this, how would you state the primary relationship in {concept.title}?"

        return RemediationPackage(
            lever_used=lever,
            content=cleaned_content,
            scaffolding_step=scaffolding_step,
            suggested_follow_up=suggested_follow_up,
        )

    def _heuristic_remediation(
        self, concept: ConceptNode, gap_diagnosis: str, lever: RemediationLever
    ) -> str:
        """Heuristic fallback for remediation lever content."""
        t = concept.title
        if lever == RemediationLever.SIMPLER_ANALOGY:
            return (
                f"To build intuition for {t}, think of it like balancing a seesaw: "
                f"if you increase the distance on one side, the required force diminishes proportionally. "
                f"The diagnosed issue ({gap_diagnosis}) occurs when we forget both sides must remain in equilibrium."
            )
        elif lever == RemediationLever.HINT:
            return (
                f"Hint for {t}: Focus closely on the primary boundary condition and how the input variables "
                f"interact before applying the general formula."
            )
        elif lever == RemediationLever.BREAKDOWN:
            return (
                f"Let us break {t} into three clear stages:\n\n"
                f"1. **Identify the Core State**: Establish the known parameters and their physical constraints.\n"
                f"2. **Apply the Governing Relation**: Express the relationship mathematically using KaTeX:\n$$\\Delta y = f(x) \\Delta x$$\n"
                f"3. **Verify the Boundary**: Ensure the result adheres to conservation laws."
            )
        elif lever == RemediationLever.VISUALS:
            return (
                f"Visualizing {t}: Imagine a 2D plane with an input vector on the horizontal axis. "
                f"As the governing parameter increases, the vector rotates upward, demonstrating the transformation flow."
            )
        else:
            return (
                f"Alternative perspective on {t}: Rather than looking at it solely through the default formula, "
                f"consider it as a rate of transfer. When inputs vary, the system dynamically adjusts its internal state."
            )


remediation_engine = RemediationEngine()
