"""
Flashcard & Quiz Module
=======================
Self-contained module for intent detection, pluggable retrieval, grounded generation,
and targeted single-card repair.
"""

from app.tutoring.flashcards.schemas import (
    OptionSchema,
    QuestionCardSchema,
    FlashcardQuizPayload,
    FlashcardQuizIntent
)
from app.tutoring.flashcards.intent import FlashcardQuizIntentDetector
from app.tutoring.flashcards.retriever import (
    BaseStudyMaterialRetriever,
    PostgresStudyMaterialRetriever
)
from app.tutoring.flashcards.grounding import GroundingValidator
from app.tutoring.flashcards.generator import FlashcardQuizGenerator

__all__ = [
    "OptionSchema",
    "QuestionCardSchema",
    "FlashcardQuizPayload",
    "FlashcardQuizIntent",
    "FlashcardQuizIntentDetector",
    "BaseStudyMaterialRetriever",
    "PostgresStudyMaterialRetriever",
    "GroundingValidator",
    "FlashcardQuizGenerator",
]
