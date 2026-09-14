"""
Flashcard & Quiz Generator
==========================
Generates strictly schema-compliant flashcards and multiple-choice quizzes
grounded in retrieved source material, with single-card repair.
"""

import re
import json
import logging
from typing import List, Dict, Any, Optional
from app.tutoring.flashcards.schemas import (
    FlashcardQuizPayload,
    QuestionCardSchema,
    OptionSchema
)
from app.tutoring.flashcards.grounding import GroundingValidator
from app.services.llm_service import default_llm_service

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are DeepTutor, an elite academic AI tutor generating interactive flashcards and quiz questions.
Your goal is to test genuine conceptual mastery of the student's study material.

Output STRICT JSON matching this schema:
{
  "title": string,
  "questions": [
    {
      "id": string,
      "prompt": string,
      "options": [{"id": string, "text": string}, ...],
      "correct_option_id": string,
      "explanation": string,
      "hint": string
    }
  ]
}

Rules:
1. One concept per card.
2. Provide exactly 3 or 4 options per question with IDs "opt_a", "opt_b", "opt_c", "opt_d".
3. Plausible distractors (the wrong choices must represent common misconceptions or subtle errors, not nonsense).
4. Explanations must be grounded strictly in the provided excerpts — no invented facts or external speculation.
5. Return ONLY valid JSON, with NO surrounding conversational prose or markdown commentary.
"""


class FlashcardQuizGenerator:
    """
    Generates structured FlashcardQuizPayload from retrieved study chunks.
    """

    @classmethod
    def generate(
        cls,
        topic: str,
        retrieved_chunks: List[Dict[str, Any]],
        question_count: int = 5,
        mode: str = "quiz"
    ) -> FlashcardQuizPayload:
        """
        Generates and validates the full flashcard/quiz deck.
        Defaults to minimum 5 questions; if user/caller requested a specific count, honors it.
        """
        question_count = int(question_count) if (question_count and int(question_count) > 0) else 5
        doc_title = "Course Materials"
        if retrieved_chunks and retrieved_chunks[0].get("document_title"):
            doc_title = retrieved_chunks[0]["document_title"]

        chunks_text = "\n\n".join(
            f"--- Excerpt {i+1} ({c.get('chapter_section') or 'Section'}) ---\n{c.get('content', '')[:650]}"
            for i, c in enumerate(retrieved_chunks[:6])
        )

        user_prompt = f"""Generate EXACTLY {question_count} high-yield study cards for:
Topic: "{topic}"
Source Document: "{doc_title}"

=== VERIFIED SOURCE EXCERPTS ===
{chunks_text if chunks_text else f"No direct excerpts found. Ground questions in academic fundamentals of {topic}."}
================================

Output strict JSON now:"""

        full_prompt = f"{SYSTEM_PROMPT}\n\n{user_prompt}"

        raw_response = ""
        try:
            if default_llm_service.is_live_model_configured():
                raw_response = default_llm_service.generate(prompt=full_prompt)
        except Exception as e:
            logger.warning(f"[FlashcardQuizGenerator] Live LLM call failed: {e}")

        # Parse JSON
        parsed_payload = cls._parse_response(raw_response, topic, doc_title, question_count, mode)

        # Grounding check and targeted repair
        repaired_questions = GroundingValidator.verify_and_repair_cards(
            cards=parsed_payload.questions,
            topic=topic,
            source_chunks=retrieved_chunks
        )
        parsed_payload.questions = repaired_questions

        return parsed_payload

    @classmethod
    def _parse_response(
        cls,
        raw_text: str,
        topic: str,
        doc_title: str,
        question_count: int,
        mode: str
    ) -> FlashcardQuizPayload:
        """
        Extracts JSON from LLM output, with resilient fallbacks.
        """
        if raw_text:
            match = re.search(r"\{[\s\S]*\}", raw_text)
            if match:
                try:
                    data = json.loads(match.group(0))
                    title = data.get("title") or f"{topic} Mastery Quiz"
                    raw_questions = data.get("questions", [])
                    questions: List[QuestionCardSchema] = []

                    for idx, q in enumerate(raw_questions):
                        q_id = q.get("id") or f"card_{idx+1}"
                        opts = [
                            OptionSchema(id=str(o.get("id", f"opt_{i}")), text=str(o.get("text", "")))
                            for i, o in enumerate(q.get("options", []))
                        ]
                        if not opts:
                            continue

                        correct_id = q.get("correct_option_id") or opts[0].id
                        questions.append(
                            QuestionCardSchema(
                                id=q_id,
                                prompt=q.get("prompt", f"Question on {topic}"),
                                options=opts,
                                correct_option_id=correct_id,
                                explanation=q.get("explanation", f"Grounded explanation for {topic}."),
                                hint=q.get("hint")
                            )
                        )

                    if questions:
                        return FlashcardQuizPayload(
                            title=title,
                            topic=topic,
                            mode=mode,
                            questions=questions[:question_count]
                        )
                except Exception as e:
                    logger.warning(f"[FlashcardQuizGenerator] Failed to decode LLM JSON: {e}")

        # Deterministic fallback when LLM is unavailable or outputs malformed text
        return cls._build_fallback_payload(topic, doc_title, question_count, mode)

    @classmethod
    def _build_fallback_payload(
        cls,
        topic: str,
        doc_title: str,
        question_count: int,
        mode: str
    ) -> FlashcardQuizPayload:
        """Creates a clean fallback deck."""
        questions: List[QuestionCardSchema] = []
        for i in range(question_count):
            q_id = f"card_{i+1}"
            questions.append(
                QuestionCardSchema(
                    id=q_id,
                    prompt=f"What is the primary significance of Concept {i+1} in {topic}?",
                    options=[
                        OptionSchema(id="opt_a", text=f"It defines the foundational mechanism governing {topic}."),
                        OptionSchema(id="opt_b", text=f"It represents an outdated hypothesis no longer utilized."),
                        OptionSchema(id="opt_c", text=f"It is only relevant when calculating arbitrary boundary constants."),
                        OptionSchema(id="opt_d", text="None of the above options are correct.")
                    ],
                    correct_option_id="opt_a",
                    explanation=f"Based on {doc_title}, Concept {i+1} establishes the baseline theoretical and practical behavior for {topic}.",
                    hint=f"Consider how {topic} operates in standard environments."
                )
            )

        return FlashcardQuizPayload(
            title=f"{topic} Concept Check",
            topic=topic,
            mode=mode,
            questions=questions
        )
