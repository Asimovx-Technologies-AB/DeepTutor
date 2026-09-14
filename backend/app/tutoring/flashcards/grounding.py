"""
Grounding Verification & Targeted Single-Card Regeneration
=========================================================
Verifies that each generated card's explanation and question are strictly
supported by the source document chunks. If any card fails verification,
regenerates ONLY that specific card without discarding the rest of the set.
"""

import re
import json
import logging
from typing import List, Dict, Any, Tuple
from app.tutoring.flashcards.schemas import QuestionCardSchema, OptionSchema
from app.services.llm_service import default_llm_service

logger = logging.getLogger(__name__)


class GroundingValidator:
    """
    Validates source grounding per card and triggers targeted single-card regeneration.
    """

    @classmethod
    def evaluate_card_grounding(
        cls,
        card: QuestionCardSchema,
        source_chunks: List[Dict[str, Any]]
    ) -> Tuple[bool, float, str]:
        """
        Evaluates whether a card's explanation is supported by the source chunks.
        Returns: (is_valid, support_score, reason)
        """
        if not source_chunks:
            return True, 1.0, "No source chunks provided, passing by default"

        combined_source = " ".join(c.get("content", "") for c in source_chunks).lower()
        explanation_lower = card.explanation.lower()

        # Extract substantive terms (words >= 4 chars, excluding stop words)
        stop_words = {
            "this", "that", "with", "from", "have", "were", "what", "when", "which",
            "their", "there", "these", "those", "about", "above", "after", "because",
            "could", "should", "would", "other", "where", "while", "being", "under"
        }
        exp_words = [
            w for w in re.findall(r"\b[a-z]{4,}\b", explanation_lower)
            if w not in stop_words
        ]

        if not exp_words:
            return True, 1.0, "Short explanation passed"

        # Check fraction of substantive explanation words occurring in source text
        matched_words = [w for w in exp_words if w in combined_source]
        overlap_ratio = len(matched_words) / len(exp_words)

        # Also check if correct option or prompt keywords exist in source
        prompt_words = [
            w for w in re.findall(r"\b[a-z]{4,}\b", card.prompt.lower())
            if w not in stop_words
        ]
        prompt_overlap = sum(1 for w in prompt_words if w in combined_source) / max(1, len(prompt_words))

        composite_score = (overlap_ratio * 0.7) + (prompt_overlap * 0.3)

        if composite_score >= 0.25:
            return True, composite_score, "Adequately grounded"
        else:
            return False, composite_score, f"Insufficient grounding overlap ({composite_score:.2f} < 0.25)"

    @classmethod
    def regenerate_single_card(
        cls,
        card_id: str,
        topic: str,
        source_chunks: List[Dict[str, Any]],
        existing_prompts: List[str]
    ) -> QuestionCardSchema:
        """
        Regenerates a single question card using the verified source chunks.
        """
        chunks_text = "\n\n".join(
            f"--- Excerpt {i+1} ---\n{c.get('content', '')[:600]}"
            for i, c in enumerate(source_chunks[:4])
        )

        avoid_prompt_str = "\n".join(f"- Avoid duplicating: {p}" for p in existing_prompts if p)

        prompt = f"""You are DeepTutor's assessment generator.
Create a SINGLE high-quality multiple-choice question card grounded STRICTLY in the provided text excerpts.

Topic: {topic}
Existing questions to avoid duplicating:
{avoid_prompt_str}

=== VERIFIED SOURCE EXCERPTS ===
{chunks_text}
================================

Rules:
1. One core concept only.
2. 3-4 plausible options.
3. The explanation MUST be directly supported by the excerpt above.
4. Output ONLY valid JSON matching this exact structure:
{{
  "id": "{card_id}",
  "prompt": "Clear question here?",
  "options": [
    {{"id": "opt_a", "text": "Option A"}},
    {{"id": "opt_b", "text": "Option B"}},
    {{"id": "opt_c", "text": "Option C"}},
    {{"id": "opt_d", "text": "Option D"}}
  ],
  "correct_option_id": "opt_a",
  "explanation": "Explanation grounded strictly in the excerpt.",
  "hint": "Brief intuitive hint"
}}"""

        try:
            raw = default_llm_service.generate(prompt=prompt)
            # Extract JSON block
            match = re.search(r"\{[\s\S]*\}", raw)
            if match:
                data = json.loads(match.group(0))
                options = [OptionSchema(id=o["id"], text=o["text"]) for o in data.get("options", [])]
                return QuestionCardSchema(
                    id=data.get("id", card_id),
                    prompt=data.get("prompt", f"Core question on {topic}"),
                    options=options,
                    correct_option_id=data.get("correct_option_id", options[0].id if options else "opt_a"),
                    explanation=data.get("explanation", f"Grounded explanation for {topic}."),
                    hint=data.get("hint")
                )
        except Exception as e:
            logger.warning(f"[GroundingValidator] Single-card regeneration fallback triggered: {e}")

        # Fallback card using source chunk directly
        fallback_chunk = source_chunks[0].get("content", f"{topic} is a core academic principle.") if source_chunks else topic
        first_sentence = fallback_chunk.split(".")[0].strip()
        return QuestionCardSchema(
            id=card_id,
            prompt=f"Which statement accurately describes {topic} based on the study material?",
            options=[
                OptionSchema(id="opt_a", text=first_sentence if len(first_sentence) < 140 else first_sentence[:137] + "..."),
                OptionSchema(id="opt_b", text=f"{topic} applies exclusively under classical assumptions without variance."),
                OptionSchema(id="opt_c", text=f"{topic} is superseded and unused in modern architectures."),
                OptionSchema(id="opt_d", text="None of the provided options are consistent with the text.")
            ],
            correct_option_id="opt_a",
            explanation=f"According to the source material: {first_sentence}.",
            hint=f"Focus on the primary definition of {topic}."
        )

    @classmethod
    def verify_and_repair_cards(
        cls,
        cards: List[QuestionCardSchema],
        topic: str,
        source_chunks: List[Dict[str, Any]]
    ) -> List[QuestionCardSchema]:
        """
        Loops through all cards. If any card fails grounding, regenerates ONLY that card.
        """
        repaired_cards: List[QuestionCardSchema] = []
        for card in cards:
            is_valid, score, reason = cls.evaluate_card_grounding(card, source_chunks)
            if not is_valid:
                logger.info(f"[GroundingValidator] Card {card.id} failed grounding check ({reason}). Regenerating just this card...")
                other_prompts = [c.prompt for c in cards if c.id != card.id]
                new_card = cls.regenerate_single_card(
                    card_id=card.id,
                    topic=topic,
                    source_chunks=source_chunks,
                    existing_prompts=other_prompts
                )
                repaired_cards.append(new_card)
            else:
                repaired_cards.append(card)

        return repaired_cards
