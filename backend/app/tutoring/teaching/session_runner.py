"""
Learning Session Runner.

Coordinates real-time tutoring sessions:
- Delivers concept explanations across dimensions
- Handles student clarifying questions
- Bridges from interactive instruction into formative practice
"""
from __future__ import annotations

import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from app.rag.llm_client import llm_client
from app.tutoring.curriculum.knowledge_map import knowledge_map_resolver
from app.tutoring.models import (
    ConceptNode,
    ExplanationDimensions,
    SessionPlan,
    StudentModel,
    StudentProfile,
)
from app.tutoring.teaching.explanation_engine import explanation_engine

logger = logging.getLogger(__name__)


class SessionRunner:
    """Manages active interactive teaching sessions."""

    def __init__(self) -> None:
        self.explanation_engine = explanation_engine
        self.resolver = knowledge_map_resolver
        self.llm = llm_client

    async def start_concept_instruction(
        self,
        concept: ConceptNode,
        student_profile: StudentProfile,
        student_model: Optional[StudentModel] = None,
        context_text: str = "",
    ) -> ExplanationDimensions:
        """Generates comprehensive teaching materials for the target concept."""
        return await self.explanation_engine.generate_explanation(
            concept=concept,
            student_profile=student_profile,
            student_model=student_model,
            context_text=context_text,
        )

    async def answer_student_question(
        self,
        question: str,
        current_concept: ConceptNode,
        student_profile: StudentProfile,
        dialogue_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """Addresses a student query during active teaching with academic rigor."""
        history_str = ""
        if dialogue_history:
            history_str = "\n".join(
                f"{msg.get('role', 'user')}: {msg.get('content', '')}"
                for msg in dialogue_history[-4:]
            )

        prompt = f"""You are a master academic professor tutoring a student in '{current_concept.title}'.
The student asks: "{question}"

CONTEXT & RECENT DIALOGUE:
{history_str}

Respond directly to resolve their question:
- Keep the explanation grounded in {current_concept.title}.
- If math is involved, format in KaTeX ($$...$$ or $...$).
- Use clear intuition followed by technical precision.
- No emojis.

Answer:"""
        try:
            return await self.llm.generate(prompt)
        except Exception as exc:
            logger.warning("[SessionRunner] answer_student_question error: %s", exc)
            return f"In the context of {current_concept.title}, {question} relates directly to how the fundamental variables interact within the system constraints."


session_runner = SessionRunner()
