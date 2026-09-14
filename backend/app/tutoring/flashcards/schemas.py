"""
Flashcard & Quiz Schemas
========================
Defines strict Pydantic schemas for options, question cards, the full quiz payload,
and intent extraction.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class OptionSchema(BaseModel):
    id: str = Field(..., description="Unique option identifier, e.g., 'opt_a', 'A'")
    text: str = Field(..., description="Text content of the option")


class QuestionCardSchema(BaseModel):
    id: str = Field(..., description="Unique question/card ID, e.g., 'card_1'")
    prompt: str = Field(..., description="The question prompt or flashcard front")
    options: List[OptionSchema] = Field(..., description="List of 3-4 multiple-choice options")
    correct_option_id: str = Field(..., description="ID of the single correct option")
    explanation: str = Field(..., description="Detailed explanation grounded in study material")
    hint: Optional[str] = Field(None, description="Optional conceptual hint for the student")


class FlashcardQuizPayload(BaseModel):
    title: str = Field(..., description="Title of the quiz/flashcard deck")
    topic: str = Field(..., description="Target academic topic")
    mode: str = Field(default="quiz", description="Default view mode: 'quiz' or 'flashcards'")
    questions: List[QuestionCardSchema] = Field(..., description="List of question cards")


class FlashcardQuizIntent(BaseModel):
    is_flashcard_quiz: bool = False
    target_topic: Optional[str] = None
    question_count: int = 5
    preferred_mode: str = "quiz"  # "quiz" or "flashcards"
