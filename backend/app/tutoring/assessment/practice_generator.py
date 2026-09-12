"""
Formative Practice & Question Generator.

Constructs targeted practice questions, problems, and conceptual checks
designed to probe deep understanding, test edge cases, and expose common misconceptions.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional

from app.rag.llm_client import llm_client
from app.tutoring.models import (
    ConceptNode,
    FormativeQuestion,
    StudentModel,
    StudentProfile,
)

logger = logging.getLogger(__name__)

QUESTION_GEN_PROMPT = """You are an academic examiner and tutor specializing in {concept_title}.
Generate a rigorous formative practice problem to test student understanding.

CONCEPT DETAILS:
Title: {concept_title}
Description: {concept_description}
Difficulty: {difficulty}
Key Terms: {key_terms}

STUDENT PROFILE:
Level: {goal_level}
Pace: {pace}

DIAGNOSED STUDENT WEAKNESSES (if any):
{weaknesses}

QUESTION SPECIFICATIONS:
- Type: {question_type} (e.g. conceptual, application, step_problem)
- Focus: Assess deep comprehension of governing principles and test whether the student can apply it to a novel scenario. Avoid trivial recall.
- Math: KaTeX notation ($$...$$ and $...$).
- No emojis. Academic tone.

Output strictly valid JSON:
{{
  "prompt": "The complete problem statement or question.",
  "question_type": "{question_type}",
  "rubric": "Precise criteria for an ideal answer, listing core points that must be articulated.",
  "common_pitfalls": ["Pitfall 1: e.g. confusing X with Y", "Pitfall 2: e.g. forgetting boundary condition"],
  "hints": ["First gentle scaffolding hint", "Second more direct hint"]
}}
"""


class PracticeGenerator:
    """Generates formative assessment questions tailored to concept and student level."""

    def __init__(self) -> None:
        self.llm = llm_client

    async def generate_question(
        self,
        concept: ConceptNode,
        student_profile: StudentProfile,
        student_model: Optional[StudentModel] = None,
        question_type: str = "conceptual",
    ) -> FormativeQuestion:
        """Generates a targeted FormativeQuestion for the given concept."""
        weaknesses_str = "None noted."
        if student_model and student_model.weaknesses:
            weaknesses_str = "\n".join(
                f"- {w.get('topic', w.get('concept_id', ''))}: {w.get('detail', '')}"
                for w in student_model.weaknesses[:3]
            )

        prompt = QUESTION_GEN_PROMPT.format(
            concept_title=concept.title,
            concept_description=concept.description,
            difficulty=concept.difficulty,
            key_terms=", ".join(concept.key_terms),
            goal_level=student_profile.goal_level,
            pace=student_profile.learning_pace,
            weaknesses=weaknesses_str,
            question_type=question_type,
        )

        try:
            raw_response = await self.llm.generate(prompt)
            data = self._parse_json(raw_response)
        except Exception as exc:
            logger.warning("[PracticeGenerator] LLM question generation notice: %s. Using fallback.", exc)
            data = self._heuristic_question(concept, question_type)

        qid = f"q_{concept.concept_id}_{uuid.uuid4().hex[:8]}"

        return FormativeQuestion(
            question_id=qid,
            concept_id=concept.concept_id,
            prompt=data.get("prompt", f"Explain the governing mechanism of {concept.title}."),
            question_type=data.get("question_type", question_type),
            rubric=data.get("rubric", ""),
            common_pitfalls=data.get("common_pitfalls", []),
            hints=data.get("hints", []),
        )

    def _parse_json(self, text: str) -> Dict[str, Any]:
        """Robustly extracts JSON dictionary from LLM output."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1:
            return json.loads(cleaned[start : end + 1])
        return json.loads(cleaned)

    def _heuristic_question(self, concept: ConceptNode, question_type: str) -> Dict[str, Any]:
        """Heuristic fallback question."""
        return {
            "prompt": f"Explain the fundamental mechanism governing {concept.title}. Specifically, describe how its key parameters influence the final outcome and what assumptions must hold.",
            "question_type": question_type,
            "rubric": f"Student must identify {concept.title}'s core principle, state at least two governing variables, and explain the boundary condition.",
            "common_pitfalls": [
                f"Confusing {concept.title} with related basic definitions",
                "Overlooking boundary constraints or initial assumptions",
            ],
            "hints": [
                f"Think about the primary definition of {concept.title}.",
                "Consider how the outputs change if the primary input variable is doubled.",
            ],
        }


practice_generator = PracticeGenerator()
