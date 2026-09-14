"""
Flashcard & Quiz Intent Detector
================================
Detects whether a student's chat query is asking for an interactive quiz or flashcards,
extracting the target topic, optional question count, and preferred mode.
"""

import re
from typing import Optional
from app.tutoring.flashcards.schemas import FlashcardQuizIntent


class FlashcardQuizIntentDetector:
    """
    Analyzes student message to determine if they are requesting on-demand
    flashcards or a practice quiz.
    """

    TRIGGER_PATTERNS = [
        # Explicit quiz & exam requests
        re.compile(r"\b(?:quiz\s+me|give\s+me\s+a\s+quiz|generate\s+a\s+quiz|create\s+a\s+quiz|test\s+me|test\s+my\s+knowledge|practice\s+quiz|practice\s+questions|conduct\s+(?:me\s+)?(?:an?\s+)?exam|exam\b|take\s+(?:an?\s+)?exam)\b", re.IGNORECASE),
        # Explicit flashcard requests & common variations/typos
        re.compile(r"\b(?:make|create|generate|give\s+me|show\s+me|build)?\s*(?:a\s+|an\s+|some\s+)?(?:\d+\s+)?(?:fl+a*sh[\s-]*cards?|study[\s-]*cards?)\b", re.IGNORECASE),
        re.compile(r"\b(?:fl+a*sh[\s-]*cards?|study[\s-]*cards?)\b", re.IGNORECASE),
        # Explicit MCQs / multiple choice
        re.compile(r"\b(?:\d+\s+)?(?:mcqs?|multiple\s+choice)\b", re.IGNORECASE),
        # Numbered quiz / exam requests (e.g. "5 quiz questions", "10 flashcards on Y")
        re.compile(r"\b(?:\d+)\s*(?:quiz\s+questions?|exam\s+questions?|mcqs?|flashcards?|flshcards?)\b", re.IGNORECASE),
    ]

    COUNT_PATTERN = re.compile(r"\b(\d+)\s*(?:questions?|quiz\s+questions?|exam\s+questions?|mcqs?|flashcards?|flshcards?|cards?|items?)\b", re.IGNORECASE)

    TOPIC_EXTRACTORS = [
        re.compile(r"\b(?:quiz\s+me|test\s+me|test\s+my\s+knowledge|conduct\s+(?:me\s+)?(?:an?\s+)?exam)\s+(?:on|about|for|regarding|in)\s+(.+)$", re.IGNORECASE),
        re.compile(r"\b(?:make|create|generate|give\s+me|show\s+me|build)?\s*(?:a\s+|an\s+|some\s+)?(?:\d+\s+)?(?:fl+a*sh[\s-]*cards?|study[\s-]*cards?|quiz|mcqs?|exam)\s+(?:on|for|about|regarding|in)\s+(.+)$", re.IGNORECASE),
        re.compile(r"\b(?:fl+a*sh[\s-]*cards?|study[\s-]*cards?|practice\s+quiz|practice\s+questions)\s+(?:on|for|about|regarding|in)\s+(.+)$", re.IGNORECASE),
        re.compile(r"\b(?:for|on|about)\s+([a-zA-Z0-9_\s-]+)$", re.IGNORECASE),
    ]

    @classmethod
    def detect(cls, query: str, default_topic: Optional[str] = None) -> FlashcardQuizIntent:
        """
        Evaluates the query and returns a FlashcardQuizIntent object.
        """
        cleaned = query.strip()
        is_match = any(pat.search(cleaned) for pat in cls.TRIGGER_PATTERNS)

        if not is_match:
            return FlashcardQuizIntent(is_flashcard_quiz=False)

        # 1. Determine preferred mode
        is_flashcard = bool(re.search(r"\b(?:fl+a*sh[\s-]*cards?|study[\s-]*cards?)\b", cleaned, re.IGNORECASE))
        preferred_mode = "flashcards" if is_flashcard else "quiz"

        # 2. Extract question count (defaults to 5; if user specifies a count, honor it)
        question_count = 5
        count_match = cls.COUNT_PATTERN.search(cleaned)
        if count_match:
            try:
                val = int(count_match.group(1))
                question_count = max(1, min(val, 25))
            except (ValueError, IndexError):
                question_count = 5

        # 3. Extract target topic
        target_topic = None
        for extractor in cls.TOPIC_EXTRACTORS:
            m = extractor.search(cleaned)
            if m and m.group(1):
                extracted = m.group(1).strip()
                # Clean trailing punctuation or polite phrases
                extracted = re.sub(r"[?!.,;]+$", "", extracted).strip()
                extracted = re.sub(r"\b(?:please|pls|now|quick|fast|thanks)\b", "", extracted, flags=re.IGNORECASE).strip()
                if extracted and extracted.lower() not in ("this", "this topic", "the material", "here", "it"):
                    target_topic = extracted
                break

        if not target_topic and default_topic:
            target_topic = default_topic

        return FlashcardQuizIntent(
            is_flashcard_quiz=True,
            target_topic=target_topic,
            question_count=question_count,
            preferred_mode=preferred_mode,
        )
