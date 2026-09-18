import pytest
from unittest.mock import MagicMock
from app.tutoring.exam.engine import is_exam_report_intent, ExamSessionManager
from app.tutoring.flashcards.intent import FlashcardQuizIntentDetector
from app.tutoring.analyzer.feedback_classifier import UserMessageContextClassifier
from app.tutoring.orchestrator import TutoringQueryOrchestrator


def test_exam_report_intent_detection():
    """Verify all required user queries match EXAM_REPORT deterministic regex."""
    positive_queries = [
        "analyze my response",
        "give me a report",
        "give me my exam report",
        "show my exam report",
        "analyze my exam",
        "how did I perform?",
        "show my performance",
        "give me my exam result",
        "what is my score?",
        "my exam report",
        "i want my exam report",
    ]
    for q in positive_queries:
        assert is_exam_report_intent(q), f"Query failed to match exam report intent: '{q}'"

    negative_queries = [
        "what is photosynthesis?",
        "teach me SVM",
        "give me 5 practice questions on biology",
        "create a study plan for tomorrow",
        "summarize chapter 3",
        "that is wrong",
    ]
    for q in negative_queries:
        assert not is_exam_report_intent(q), f"Query falsely identified as exam report: '{q}'"


def test_flashcard_intent_excludes_exam_report():
    """Verify FlashcardQuizIntentDetector does NOT trigger for exam report queries."""
    report_queries = [
        "give me a report",
        "give me my exam report",
        "analyze my exam",
        "what is my score?",
    ]
    for q in report_queries:
        intent = FlashcardQuizIntentDetector.detect(q)
        assert not intent.is_flashcard_quiz, f"Flashcard detector falsely triggered for: '{q}'"


def test_feedback_classifier_handles_exam_report():
    """Verify feedback classifier routes exam report requests as is_exam_report=True."""
    res = UserMessageContextClassifier.classify_message("give me my exam report")
    assert res.is_exam_report is True
    assert res.confidence == 0.99


def test_exam_session_manager_lifecycle():
    """Test full exam session creation, answer submission, and report generation."""
    mock_db = MagicMock()
    session_id = "test-sess-123"

    # In-memory session mock
    stored_metadata = {}
    mock_session_row = MagicMock()
    mock_session_row.id = session_id
    mock_session_row.session_metadata = stored_metadata

    def fake_filter(*args, **kwargs):
        return MagicMock(first=lambda: mock_session_row)

    mock_db.query.return_value.filter = fake_filter

    # 1. Create exam session
    questions = [
        {
            "question": "What is the capital of France?",
            "options": ["London", "Paris", "Berlin", "Madrid"],
            "correct_answer": "Paris",
            "topic": "Geography",
            "max_marks": 2,
        },
        {
            "question": "What is 2 + 2?",
            "options": ["3", "4", "5", "6"],
            "correct_answer": "4",
            "topic": "Math",
            "max_marks": 1,
        }
    ]
    created = ExamSessionManager.create_exam_session(
        db=mock_db,
        session_id=session_id,
        subject="General Knowledge",
        topic="Trivia",
        questions=questions,
    )
    assert created["total_questions"] == 2
    assert created["status"] == "in_progress"
    assert created["total_marks"] == 3

    # Update session_metadata in mock
    mock_session_row.session_metadata = {"exam_session": created}

    # 2. Submit correct answer for Q1
    ans1 = ExamSessionManager.submit_answer(mock_db, session_id, "Paris")
    assert ans1["is_correct"] is True
    assert ans1["marks"] == 2
    assert ans1["exam_status"] == "in_progress"
    assert ans1["next_question"] is not None
    assert ans1["next_question"]["question_index"] == 2

    # Update session_metadata in mock with updated exam
    exam_after_q1 = mock_session_row.session_metadata["exam_session"]

    # 3. Submit incorrect answer for Q2 (e.g. "3" or "A")
    ans2 = ExamSessionManager.submit_answer(mock_db, session_id, "3")
    assert ans2["is_correct"] is False
    assert ans2["marks"] == 0
    assert ans2["exam_status"] == "completed"

    # 4. Generate exam report from state
    completed_exam = mock_session_row.session_metadata["exam_session"]
    report = ExamSessionManager.generate_exam_report(completed_exam)

    assert "# 📊 Exam Report: Trivia" in report
    assert "## Overall Performance" in report
    assert "Score**: 2 / 3" in report
    assert "Questions Attempted**: 2 / 2" in report
    assert "Correct**: ✅ 1" in report
    assert "Incorrect**: ❌ 1" in report
    assert "## Topic-wise Performance" in report
    assert "## Mistake Analysis" in report
    assert "## Recommended Revision" in report


def test_orchestrator_exam_report_no_session_fallback():
    """Verify fallback message is returned when no exam session exists."""
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    result = TutoringQueryOrchestrator.process_query(
        session=mock_db,
        raw_query="give me my exam report",
        session_id="empty-sess",
    )
    assert result["type"] == "exam_report"
    assert result["intent"] == "EXAM_REPORT"
    assert "I don't have an exam attempt to analyze yet" in result["content"]
    assert "Start or complete an exam first" in result["content"]


def test_exam_start_intent_detection():
    """Verify exact user phrases match EXAM_START deterministic regex."""
    from app.tutoring.exam.engine import is_exam_start_intent, extract_exam_params

    exact_user_query = "make a exam for me give me 3 question in one by one , after answer one question give next question and it was not a quiz"
    assert is_exam_start_intent(exact_user_query)

    params = extract_exam_params(exact_user_query)
    assert params["question_count"] == 3

    other_exam_queries = [
        "make an exam for me",
        "create an exam on Transformer Architecture",
        "start exam on neural networks",
        "conduct an exam with 5 questions",
        "give me 4 questions in one by one exam",
        "take an exam",
    ]
    for q in other_exam_queries:
        assert is_exam_start_intent(q), f"Query failed to match exam start intent: '{q}'"


def test_flashcard_intent_excludes_exam_start():
    """Verify FlashcardQuizIntentDetector ignores exam start queries and 'not a quiz' queries."""
    exact_user_query = "make a exam for me give me 3 question in one by one , after answer one question give next question and it was not a quiz"
    intent = FlashcardQuizIntentDetector.detect(exact_user_query)
    assert not intent.is_flashcard_quiz, "Flashcard detector falsely triggered for explicit 'not a quiz' exam request!"

    exam_queries = [
        "make an exam for me",
        "start an exam",
        "conduct an exam on biology",
    ]
    for q in exam_queries:
        intent = FlashcardQuizIntentDetector.detect(q)
        assert not intent.is_flashcard_quiz, f"Flashcard detector falsely triggered for: '{q}'"


def test_orchestrator_interactive_1_by_1_exam_flow():
    """Verify end-to-end interactive 1-by-1 exam: start -> answer -> next -> complete -> report."""
    mock_db = MagicMock()
    session_id = "exam-interactive-sess"

    stored_metadata = {}
    mock_session_row = MagicMock()
    mock_session_row.id = session_id
    mock_session_row.session_metadata = stored_metadata

    def fake_filter(*args, **kwargs):
        return MagicMock(first=lambda: mock_session_row)

    mock_db.query.return_value.filter = fake_filter

    # Step 1: User requests exam
    start_result = TutoringQueryOrchestrator.process_query(
        session=mock_db,
        raw_query="make a exam for me give me 3 question in one by one , after answer one question give next question and it was not a quiz",
        session_id=session_id,
        topic_title="Transformer Architecture"
    )

    assert start_result["type"] == "exam_question"
    assert start_result["intent"] == "EXAM_START"
    assert "Question 1 of 3" in start_result["content"]
    assert start_result["suggested_questions"] == ["A", "B", "C", "D"]

    # Step 2: User answers Question 1
    q1_ans_result = TutoringQueryOrchestrator.process_query(
        session=mock_db,
        raw_query="A",
        session_id=session_id,
    )
    assert q1_ans_result["type"] == "exam_answer"
    assert "Question 2 of 3" in q1_ans_result["content"]
    assert "Score so far" in q1_ans_result["content"]

    # Step 3: User answers Question 2
    q2_ans_result = TutoringQueryOrchestrator.process_query(
        session=mock_db,
        raw_query="B",
        session_id=session_id,
    )
    assert q2_ans_result["type"] == "exam_answer"
    assert "Question 3 of 3" in q2_ans_result["content"]

    # Step 4: User answers Question 3 (final question)
    q3_ans_result = TutoringQueryOrchestrator.process_query(
        session=mock_db,
        raw_query="C",
        session_id=session_id,
    )
    assert q3_ans_result["type"] == "exam_answer"
    assert "🎉 **Exam completed!**" in q3_ans_result["content"]
    assert "show my exam report" in q3_ans_result["content"]

    # Step 5: User requests exam report
    report_result = TutoringQueryOrchestrator.process_query(
        session=mock_db,
        raw_query="show my exam report",
        session_id=session_id,
    )
    assert report_result["type"] == "exam_report"
    assert report_result["intent"] == "EXAM_REPORT"
    assert "# 📊 Exam Report:" in report_result["content"]
    assert "## Overall Performance" in report_result["content"]
    assert "## Question-wise Analysis" in report_result["content"]
    assert "## Topic-wise Performance" in report_result["content"]


def test_exam_start_on_3_questions_query_detection():
    """Verify 'make a exam on 3 questions' extracts 3 questions and topic falls back to default."""
    from app.tutoring.exam.engine import is_exam_start_intent, extract_exam_params

    query = "make a exam on 3 questions"
    assert is_exam_start_intent(query)
    params = extract_exam_params(query, default_topic="Encoder-Decoder Architecture Overview")
    assert params["question_count"] == 3
    assert params["topic"] == "Encoder-Decoder Architecture Overview"


def test_orchestrator_streaming_interactive_1_by_1_exam_flow():
    """Verify streaming SSE generator handles interactive exam 1-by-1 and pauses teacher mode."""
    mock_db = MagicMock()
    session_id = "exam-streaming-sess"

    stored_metadata = {
        "teacher_state": {
            "mode": "teacher",
            "topic": "Transformers",
            "paused": False
        }
    }
    mock_session_row = MagicMock()
    mock_session_row.id = session_id
    mock_session_row.session_metadata = stored_metadata

    def fake_filter(*args, **kwargs):
        return MagicMock(first=lambda: mock_session_row)

    mock_db.query.return_value.filter = fake_filter

    # Step 1: User requests exam via streaming SSE
    events = list(TutoringQueryOrchestrator.stream_query_response(
        session=mock_db,
        raw_query="make a exam on 3 questions",
        session_id=session_id,
        topic_title="Encoder-Decoder Architecture Overview"
    ))

    # Verify teacher mode got paused
    assert stored_metadata["teacher_state"]["paused"] is True

    # Check token text contains Question 1 of 3
    token_events = [e for e in events if e.get("type") == "token"]
    assert len(token_events) > 0
    full_text = "".join(e.get("token", "") for e in token_events)
    assert "Question 1 of 3" in full_text
    assert "📝 Exam:" in full_text
    assert "Encoder-Decoder Architecture Overview" in full_text

    # Step 2: Answer Question 1 via streaming
    ans_events = list(TutoringQueryOrchestrator.stream_query_response(
        session=mock_db,
        raw_query="A",
        session_id=session_id,
    ))
    ans_text = "".join(e.get("token", "") for e in ans_events if e.get("type") == "token")
    assert "Question 2 of 3" in ans_text
    assert "Score so far" in ans_text


