import pytest
from unittest.mock import MagicMock
from app.tutoring.exam.engine import (
    is_exam_start_intent,
    extract_exam_params,
    ExamQuestionGenerator,
    ExamSessionManager,
)


def test_written_exam_intent_detection():
    """Verify natural language requests for written / subjective exams are recognized."""
    test_queries = [
        "i dont want quiz i want a written exam",
        "I don't want a quiz, give me a written exam on self attention",
        "give me a written exam on self attention, 3 questions",
        "theory exam on transformers with 5 questions",
        "subjective exam on operating systems",
        "descriptive exam on neural networks",
        "i want a written exam",
    ]
    for q in test_queries:
        assert is_exam_start_intent(q) is True, f"Failed for query: {q}"
        params = extract_exam_params(q, default_topic="General")
        assert params["exam_type"] == "written", f"Expected exam_type 'written' for: {q}"


def test_mcq_exam_intent_default():
    """Standard exam prompts without 'written' or 'theory' default to mcq."""
    params = extract_exam_params("make a exam on self attention , 3 questions", default_topic="General")
    assert params["exam_type"] == "mcq"
    assert params["question_count"] == 3


def test_written_question_generation_structure():
    """Ensure written questions have empty options, reference answers, and rubric points."""
    questions = ExamQuestionGenerator.generate_written("self attention", [], question_count=3)
    assert len(questions) == 3
    for q in questions:
        assert q["question_type"] == "written"
        assert q["options"] == []
        assert "reference_answer" in q and len(q["reference_answer"]) > 10
        assert "rubric_points" in q and len(q["rubric_points"]) >= 1
        assert q["max_marks"] == 5


def test_written_exam_session_and_answer_lifecycle():
    """Test full cycle: session creation, written answer evaluation, and exam report."""
    mock_db = MagicMock()
    mock_session_row = MagicMock()
    mock_session_row.session_metadata = {}
    mock_db.query.return_value.filter.return_value.first.return_value = mock_session_row

    questions = [
        {
            "question": "Explain how scaled dot-product attention works.",
            "options": [],
            "correct_answer": "Queries and keys are multiplied, scaled by sqrt(d_k), passed through softmax, and multiplied by values.",
            "reference_answer": "Queries and keys are multiplied, scaled by sqrt(d_k), passed through softmax, and multiplied by values.",
            "rubric_points": ["Dot product of Q and K", "Scaling factor sqrt(d_k)", "Softmax normalization", "Weighted sum of values V"],
            "topic": "Self Attention",
            "max_marks": 5,
            "question_type": "written",
        },
        {
            "question": "Why is multi-head attention superior to single-head attention?",
            "options": [],
            "correct_answer": "It allows the model to jointly attend to information from different representation subspaces at different positions.",
            "reference_answer": "It allows the model to jointly attend to information from different representation subspaces at different positions.",
            "rubric_points": ["Different representation subspaces", "Different positions attended jointly", "Linear projections"],
            "topic": "Transformers",
            "max_marks": 5,
            "question_type": "written",
        }
    ]

    session_id = "test-written-session"
    created = ExamSessionManager.create_exam_session(
        db=mock_db,
        session_id=session_id,
        subject="Deep Learning",
        topic="Self Attention",
        questions=questions,
        exam_type="written",
    )

    assert created["exam_type"] == "written"
    assert created["total_questions"] == 2
    assert created["total_marks"] == 10
    mock_session_row.session_metadata = {"exam_session": created}

    # Answer Q1 with good explanation (> 200 chars to test long answer capability)
    student_ans_q1 = (
        "In scaled dot-product attention, we compute the dot product of queries Q and keys K. "
        "We divide the result by the scaling factor square root of d_k to prevent gradient vanishing in large dimensions. "
        "Next, softmax normalization is applied to get the attention weights, which are then used to compute the weighted sum of values V."
    )
    ans1 = ExamSessionManager.submit_answer(mock_db, session_id, student_ans_q1)
    assert ans1["question_type"] == "written"
    assert ans1["is_correct"] is True
    assert ans1["marks"] >= 3
    assert ans1["feedback"] is not None
    assert ans1["next_question"] is not None

    # Answer Q2 with minimal/empty answer
    ans2 = ExamSessionManager.submit_answer(mock_db, session_id, "I do not know.")
    assert ans2["exam_status"] == "completed"

    # Verify Written Exam Report
    completed = mock_session_row.session_metadata["exam_session"]
    report = ExamSessionManager.generate_exam_report(completed)
    assert "# 📊 Written Exam Report: Self Attention" in report
    assert "Your Written Answer" in report
    assert "Model Reference Answer" in report
    assert "Marks Awarded" in report
    assert "Mistake Analysis" in report
