import pytest
from unittest.mock import patch, MagicMock

from app.schemas.tutoring import TeacherTurnActionEnum, UserMessageClassificationEnum
from app.tutoring.analyzer.feedback_classifier import (
    UserMessageContextClassifier,
    UserMessageClassificationResult,
)
from app.tutoring.teaching.correction_handler import TeachingCorrectionHandler
from app.tutoring.teaching.interactive_teacher import InteractiveTeacherEngine, TeacherSessionState


def test_classify_short_corrections_as_feedback():
    short_corrections = [
        "wrong",
        "wrong answer",
        "that's wrong",
        "incorrect",
        "no",
        "not correct",
        "this is wrong",
        "you made a mistake",
        "that is not right",
    ]
    history = [
        {"role": "user", "content": "What is the capital of Australia?"},
        {"role": "assistant", "content": "The capital of Australia is Sydney."},
    ]

    for phrase in short_corrections:
        result = UserMessageContextClassifier.classify_message(
            raw_query=phrase,
            conversation_history=history,
            current_topic="Geography",
        )
        assert result.category == UserMessageClassificationEnum.FEEDBACK_CORRECTION, (
            f"Expected {phrase} to be classified as FEEDBACK_CORRECTION, got {result.category}"
        )


def test_classify_declarative_factual_statements():
    statements = [
        "Leaf nodes split the data in a decision tree",
        "Mitochondria are the powerhouse of the cell",
        "Photosynthesis produces glucose and oxygen",
        "Binary search has an O(n) runtime complexity",
    ]
    history = [
        {"role": "user", "content": "Let's study decision trees."},
        {"role": "assistant", "content": "Decision trees are tree-structured models."},
    ]

    for stmt in statements:
        result = UserMessageContextClassifier.classify_message(
            raw_query=stmt,
            conversation_history=history,
            current_topic="Machine Learning",
        )
        assert result.category == UserMessageClassificationEnum.STATEMENT_EVALUATION, (
            f"Expected '{stmt}' to be classified as STATEMENT_EVALUATION, got {result.category}"
        )


def test_classify_questions_and_continuations():
    questions = [
        "What is gradient descent?",
        "Can you explain backpropagation?",
        "Why is the sky blue?",
    ]
    for q in questions:
        result = UserMessageContextClassifier.classify_message(raw_query=q)
        assert result.category == UserMessageClassificationEnum.NEW_QUESTION_REQUEST

    continuations = [
        "continue",
        "next please",
        "proceed",
        "go ahead",
    ]
    for c in continuations:
        result = UserMessageContextClassifier.classify_message(raw_query=c)
        assert result.category == UserMessageClassificationEnum.CLARIFICATION_CONTINUATION


def test_interactive_teacher_turn_action_for_feedback():
    state = TeacherSessionState(
        session_id="test_session_1",
        topic="Decision Trees",
        main_topic="Decision Trees",
        subtopics=["Root Nodes", "Splitting Rules", "Leaf Nodes"],
        current_subtopic_index=0,
        current_subtopic="Root Nodes",
        awaiting_user_confirmation=True,
    )

    correction_inputs = [
        "wrong",
        "wrong answer",
        "that's wrong",
        "incorrect",
        "no",
        "not correct",
        "this is wrong",
    ]

    for inp in correction_inputs:
        action = InteractiveTeacherEngine.classify_turn_action(raw_query=inp, state=state)
        assert action == TeacherTurnActionEnum.FEEDBACK_CORRECTION, (
            f"Expected '{inp}' to yield FEEDBACK_CORRECTION, got {action}"
        )


def test_interactive_teacher_turn_action_for_factual_statement():
    state = TeacherSessionState(
        session_id="test_session_2",
        topic="Cell Biology",
        main_topic="Cell Biology",
        subtopics=["Mitochondria", "Ribosomes", "Nucleus"],
        current_subtopic_index=0,
        current_subtopic="Mitochondria",
        awaiting_user_confirmation=True,
    )

    action = InteractiveTeacherEngine.classify_turn_action(
        raw_query="Mitochondria are where cellular respiration occurs and ATP is produced",
        state=state,
    )
    assert action == TeacherTurnActionEnum.STATEMENT_EVALUATION


def test_teaching_correction_handler_output():
    history = [
        {"role": "user", "content": "What is the capital of Australia?"},
        {"role": "assistant", "content": "The capital of Australia is Sydney."},
    ]

    with patch("app.tutoring.teaching.correction_handler.default_llm_service.generate") as mock_gen:
        mock_gen.return_value = (
            "The previous explanation had an error. Here is the corrected version: "
            "The capital of Australia is Canberra, not Sydney."
        )

        response = TeachingCorrectionHandler.handle_user_correction(
            user_feedback="wrong",
            conversation_history=history,
            current_topic="Geography",
            current_subtopic="Capitals",
            is_teacher_mode=True,
        )

        assert "The previous explanation had an error" in response
        assert "Would you like me to continue to the next subtopic?" in response


def test_teaching_statement_evaluation_handler_output():
    history = [
        {"role": "user", "content": "Explain decision trees."},
        {"role": "assistant", "content": "A decision tree is composed of internal nodes and leaf nodes."},
    ]

    with patch("app.tutoring.teaching.correction_handler.default_llm_service.generate") as mock_gen:
        mock_gen.return_value = (
            "That is not correct. The correct answer is: Leaf nodes do not split data; "
            "internal decision nodes split the data while leaf nodes provide the final class prediction."
        )

        response = TeachingCorrectionHandler.handle_statement_evaluation(
            user_statement="Leaf nodes split the data in a decision tree",
            conversation_history=history,
            current_topic="Decision Trees",
            current_subtopic="Leaf Nodes",
            is_teacher_mode=True,
        )

        assert "That is not correct" in response
        assert "Would you like me to continue to the next subtopic?" in response
