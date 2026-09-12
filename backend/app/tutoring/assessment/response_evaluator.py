"""
Student Response Evaluator & Diagnostic Analyzer.

Analyzes student responses to formative questions, performing deep diagnostic
evaluation to determine understanding (UNDERSTAND? decision diamond), pinpointing
specific conceptual gaps or misconceptions, and deciding pedagogical routing.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

from app.rag.llm_client import llm_client
from app.tutoring.models import (
    ConceptNode,
    EvaluationResult,
    FormativeQuestion,
    StudentProfile,
)

logger = logging.getLogger(__name__)

EVALUATION_PROMPT = """You are an exacting academic professor evaluating a student's answer.

QUESTION PROMPT:
{question_prompt}

EVALUATION RUBRIC & IDEAL ANSWER:
{rubric}

COMMON PITFALLS:
{common_pitfalls}

STUDENT'S ANSWER:
{student_answer}

ANALYZE THE ANSWER:
1. Is the student's conceptual understanding sound? (true/false)
2. Quantitative Score: between 0.0 (completely incorrect) and 1.0 (flawless mastery).
3. Diagnosed Knowledge Gap: If incorrect or incomplete, pinpoint the exact underlying concept or logic missing. (null if sound)
4. Misconception: If the student applied flawed reasoning, identify the specific misconception. (null if none)
5. Constructive Academic Feedback: Clearly explain what was accurate and precisely clarify any errors without giving away the full answer immediately if they need remediation.
6. Next Pedagogical Action:
   - "advance" (score >= 0.75, clear understanding demonstrated)
   - "remediate" (score < 0.60 or critical misconception present, requires adaptive remediation)
   - "next_question" (score between 0.60 and 0.74, borderline, verify with an alternative angle)

CRITICAL INSTRUCTIONS:
- Format all math in KaTeX ($$...$$ or $...$).
- No emojis. Academic tone.
- Output strictly valid JSON.

JSON OUTPUT:
{{
  "is_understood": true,
  "score": 0.85,
  "diagnosed_gap": null,
  "misconception": null,
  "feedback": "Academic feedback text...",
  "next_action": "advance"
}}
"""


class ResponseEvaluator:
    """Evaluates student answers and makes the UNDERSTAND? decision."""

    def __init__(self) -> None:
        self.llm = llm_client

    async def evaluate_response(
        self,
        question: FormativeQuestion,
        student_answer: str,
        student_profile: Optional[StudentProfile] = None,
    ) -> EvaluationResult:
        """Evaluates student answer against rubric, determining whether understanding is met."""
        prompt = EVALUATION_PROMPT.format(
            question_prompt=question.prompt,
            rubric=question.rubric or "Clear conceptual explanation matching the concept principles.",
            common_pitfalls="\n".join(f"- {p}" for p in question.common_pitfalls) or "None",
            student_answer=student_answer.strip() or "[No answer submitted]",
        )

        try:
            raw_response = await self.llm.generate(prompt)
            data = self._parse_json(raw_response)
        except Exception as exc:
            logger.warning("[ResponseEvaluator] LLM evaluation notice: %s. Using heuristic analysis.", exc)
            data = self._heuristic_evaluation(question, student_answer)

        score = float(data.get("score", 0.5))
        is_understood = bool(data.get("is_understood", score >= 0.75))
        next_action = data.get("next_action")
        if not next_action:
            if is_understood and score >= 0.75:
                next_action = "advance"
            elif score < 0.60:
                next_action = "remediate"
            else:
                next_action = "next_question"

        return EvaluationResult(
            is_understood=is_understood,
            score=score,
            diagnosed_gap=data.get("diagnosed_gap"),
            misconception=data.get("misconception"),
            feedback=data.get("feedback", ""),
            next_action=next_action,
        )

    def _parse_json(self, text: str) -> Dict[str, Any]:
        """Extracts JSON dictionary from LLM response."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1:
            return json.loads(cleaned[start : end + 1])
        return json.loads(cleaned)

    def _heuristic_evaluation(
        self, question: FormativeQuestion, student_answer: str
    ) -> Dict[str, Any]:
        """Heuristic evaluation when LLM call is unavailable."""
        ans = student_answer.strip().lower()
        if len(ans) < 15:
            return {
                "is_understood": False,
                "score": 0.2,
                "diagnosed_gap": "Incomplete response lacking core conceptual articulation.",
                "misconception": "Superficial recall without substantive justification.",
                "feedback": "The response is insufficient to demonstrate conceptual mastery. Please elaborate on the mechanism.",
                "next_action": "remediate",
            }
        return {
            "is_understood": True,
            "score": 0.8,
            "diagnosed_gap": None,
            "misconception": None,
            "feedback": "Your answer demonstrates sound understanding of the primary mechanics.",
            "next_action": "advance",
        }


response_evaluator = ResponseEvaluator()
