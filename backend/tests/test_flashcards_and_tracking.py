"""
Flashcard, Quiz & Tracking Agent Unit Tests
===========================================
Validates intent detection, generator schema adherence, single-card grounding repair,
and tracking agent event ingestion with gamification XP updates.
"""

import pytest
from datetime import datetime, timezone
from app.tutoring.flashcards.intent import FlashcardQuizIntentDetector
from app.tutoring.flashcards.schemas import (
    OptionSchema,
    QuestionCardSchema,
    FlashcardQuizPayload
)
from app.tutoring.flashcards.grounding import GroundingValidator
from app.tutoring.flashcards.generator import FlashcardQuizGenerator
from app.tutoring.tracking.agent import TrackingAgent
from app.tutoring.tracking.schemas import AnswerEventSchema


def test_flashcard_intent_detection():
    # 1. Standard quiz request
    res1 = FlashcardQuizIntentDetector.detect("Quiz me on Neural Networks please")
    assert res1.is_flashcard_quiz is True
    assert res1.target_topic == "Neural Networks"
    assert res1.question_count == 5
    assert res1.preferred_mode == "quiz"

    # 2. Flashcard request with explicit count
    res2 = FlashcardQuizIntentDetector.detect("Make 4 flashcards for Cellular Respiration")
    assert res2.is_flashcard_quiz is True
    assert res2.target_topic == "Cellular Respiration"
    assert res2.question_count == 4
    assert res2.preferred_mode == "flashcards"

    # 3. Practice questions with default topic fallback
    res3 = FlashcardQuizIntentDetector.detect("Practice questions", default_topic="Organic Chemistry")
    assert res3.is_flashcard_quiz is True
    assert res3.target_topic == "Organic Chemistry"
    assert res3.question_count == 5

    # 4. Normal conceptual query (should NOT trigger quiz)
    res4 = FlashcardQuizIntentDetector.detect("How does backpropagation work in deep learning?")
    assert res4.is_flashcard_quiz is False

    # 5. User query with typo "flshcard" and target "svm"
    res5 = FlashcardQuizIntentDetector.detect("make a flshcard for svm")
    assert res5.is_flashcard_quiz is True
    assert res5.target_topic == "svm"
    assert res5.preferred_mode == "flashcards"


def test_grounding_validator_and_targeted_repair():
    chunks = [
        {
            "id": "chunk-1",
            "content": "Superposition allows a quantum qubit to exist simultaneously in linear combinations of basis states |0> and |1>.",
            "topic": "Quantum Computing",
            "chapter_section": "Chapter 1"
        }
    ]

    # Grounded card
    grounded_card = QuestionCardSchema(
        id="card_1",
        prompt="What allows a quantum qubit to exist in combinations of basis states?",
        options=[
            OptionSchema(id="opt_a", text="Superposition of basis states"),
            OptionSchema(id="opt_b", text="Classical bit parity")
        ],
        correct_option_id="opt_a",
        explanation="Superposition allows a quantum qubit to exist in linear combinations of basis states.",
        hint="Consider quantum linear combinations."
    )
    is_valid, score, _ = GroundingValidator.evaluate_card_grounding(grounded_card, chunks)
    assert is_valid is True

    # Ungrounded card (completely invented topics)
    ungrounded_card = QuestionCardSchema(
        id="card_2",
        prompt="How do steam locomotives generate propulsion?",
        options=[
            OptionSchema(id="opt_a", text="High-pressure coal boiler"),
            OptionSchema(id="opt_b", text="Diesel rotary generator")
        ],
        correct_option_id="opt_a",
        explanation="High-pressure steam expands cylinders driving the locomotive wheels.",
        hint="Boiler propulsion mechanics."
    )
    is_valid2, score2, _ = GroundingValidator.evaluate_card_grounding(ungrounded_card, chunks)
    assert is_valid2 is False

    # Targeted repair: should repair ONLY card_2 while preserving card_1
    repaired = GroundingValidator.verify_and_repair_cards([grounded_card, ungrounded_card], "Quantum Computing", chunks)
    assert len(repaired) == 2
    assert repaired[0].id == "card_1"
    assert repaired[0].prompt == grounded_card.prompt
    assert repaired[1].id == "card_2"
    # Repaired card 2 now uses the source chunks
    assert "Superposition" in repaired[1].explanation or "quantum" in repaired[1].explanation.lower()


def test_flashcard_quiz_generator_schema():
    chunks = [
        {
            "id": "c1",
            "content": "Attention mechanisms compute a weighted sum of values based on query and key compatibility.",
            "topic": "Transformers",
            "chapter_section": "Attention Is All You Need",
            "document_title": "Attention Is All You Need"
        }
    ]

    payload = FlashcardQuizGenerator.generate(
        topic="Attention Mechanisms",
        retrieved_chunks=chunks,
        question_count=3,
        mode="quiz"
    )

    assert isinstance(payload, FlashcardQuizPayload)
    assert payload.topic == "Attention Mechanisms"
    assert len(payload.questions) == 3
    for q in payload.questions:
        assert q.id is not None
        assert len(q.prompt) > 5
        assert len(q.options) >= 2
        assert any(o.id == q.correct_option_id for o in q.options)
        assert len(q.explanation) > 5


def test_tracking_agent_and_gamification(db_session):
    student = "student_test_gamma"
    topic = "Thermodynamics"

    # 1. Submit correct answer event
    evt1 = AnswerEventSchema(
        topic=topic,
        is_correct=True,
        student_id=student,
        question_id="card_1",
        mode="quiz"
    )
    res1 = TrackingAgent.record_answer_event(evt1, db_session)
    assert res1["status"] == "recorded"
    assert res1["is_correct"] is True
    assert res1["xp_earned"] == 15
    assert res1["total_xp"] >= 15
    assert res1["mastery_score"] > 0.7

    # 2. Submit incorrect answer event
    evt2 = AnswerEventSchema(
        topic=topic,
        is_correct=False,
        student_id=student,
        question_id="card_2",
        mode="quiz"
    )
    res2 = TrackingAgent.record_answer_event(evt2, db_session)
    assert res2["is_correct"] is False
    assert res2["xp_earned"] == 5
    assert res2["total_xp"] >= 20

    # 3. Retrieve student summary
    summary = TrackingAgent.get_student_summary(student, db_session)
    assert summary.student_id == student
    assert summary.total_xp >= 20
    assert any(m.topic == topic for m in summary.topic_masteries)


def test_quiz_non_streaming_orchestrator_response(db_session):
    """Verify non-streaming quiz orchestration assigns content & latency without NameError."""
    from app.tutoring.orchestrator import TutoringQueryOrchestrator
    from unittest.mock import patch
    from app.tutoring.flashcards.schemas import FlashcardQuizPayload, QuestionCardSchema, OptionSchema

    fake_payload = FlashcardQuizPayload(
        topic="Transformers",
        title="Transformers Quiz",
        mode="quiz",
        questions=[
            QuestionCardSchema(
                id="q1",
                prompt="What is self-attention?",
                options=[OptionSchema(id="o1", text="Mechanism"), OptionSchema(id="o2", text="Layer")],
                correct_option_id="o1",
                explanation="Grounded in materials"
            )
        ]
    )

    with patch("app.tutoring.teaching.agent.TeachingAgent.generate_flashcards_or_quiz", return_value=fake_payload):
        resp = TutoringQueryOrchestrator.process_query(
            session=db_session,
            raw_query="Give me a quiz on Transformers",
            session_id=None
        )

    assert resp["type"] == "flashcard_quiz"
    assert resp["intent"] == "QUIZ"
    assert "content" in resp
    assert "latency_ms" in resp
    assert isinstance(resp["content"], str)
    assert "```flashcard_quiz" in resp["content"]
    assert resp["latency_ms"] >= 0


def test_streaming_reference_resolver_receives_session(db_session):
    """Verify streaming query response passes db_session and session_id to ReferenceResolver."""
    from app.tutoring.orchestrator import TutoringQueryOrchestrator
    from unittest.mock import patch

    with patch("app.tutoring.analyzer.resolver.ReferenceResolver.resolve_references") as mock_resolve:
        mock_resolve.return_value = ("hello", {"is_follow_up": False})
        list(TutoringQueryOrchestrator.stream_query_response(
            session=db_session,
            raw_query="hello",
            session_id="test-stream-sess-123"
        ))

        mock_resolve.assert_called_once()
        _, kwargs = mock_resolve.call_args
        assert kwargs.get("db_session") == db_session
        assert kwargs.get("session_id") == "test-stream-sess-123"

