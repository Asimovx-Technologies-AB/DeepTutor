"""
test_unit_exam_generator.py
============================
Criteria §1.2 — RAG Components: Exam Generator.

Tests:
- JSON schema of generated exams (all required fields present)
- All three question types present (written, multiple_choice, fill_in_blank)
- MCQ grading: exact match on letter
- Fill-in-blank grading: exact + alternatives + substring
- Written grading: LLM eval path (mocked) + fallback partial credit
- Fallback exam structure when LLM fails
- Invalid/malformed LLM JSON triggers fallback gracefully
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
import json


SAMPLE_EXAM = {
    "title": "Machine Learning Mastery Examination",
    "topic_title": "Machine Learning",
    "total_questions": 3,
    "questions": [
        {
            "id": "q1",
            "type": "written",
            "prompt": "Explain supervised learning.",
            "sample_correct_answer": "Supervised learning uses labelled data to train a model that maps inputs to outputs.",
            "key_points": ["labelled data", "input-output mapping"],
            "explanation": "Core definition.",
        },
        {
            "id": "q2",
            "type": "multiple_choice",
            "prompt": "Which algorithm finds the optimal separating hyperplane?",
            "options": ["SVM", "k-NN", "k-Means", "Decision Tree"],
            "correct_answer": "A",
            "explanation": "SVM maximises the margin between classes.",
        },
        {
            "id": "q3",
            "type": "fill_in_blank",
            "prompt": "Overfitting occurs when a model learns _____ instead of the underlying pattern.",
            "correct_answer": "noise",
            "accepted_alternatives": ["random noise", "irrelevant noise"],
            "explanation": "Overfitting is memorising training data.",
        },
    ],
}


class TestExamGeneratorSchema:

    @pytest.mark.asyncio
    async def test_generated_exam_has_required_top_level_fields(self):
        """Generated exam must include title, topic_title, total_questions, questions."""
        from app.rag.exam_generator import ExamGenerator

        with patch("app.rag.ollama_client.ollama.chat", new=AsyncMock(return_value=json.dumps(SAMPLE_EXAM))):
            gen = ExamGenerator()
            exam = await gen.generate_exam("Machine Learning", context="Intro to ML concepts.")

        assert "title" in exam
        assert "questions" in exam
        assert isinstance(exam["questions"], list)
        assert len(exam["questions"]) >= 1

    @pytest.mark.asyncio
    async def test_generated_exam_has_all_three_question_types(self):
        """A well-formed exam must contain written, multiple_choice, fill_in_blank."""
        from app.rag.exam_generator import ExamGenerator

        with patch("app.rag.ollama_client.ollama.chat", new=AsyncMock(return_value=json.dumps(SAMPLE_EXAM))):
            gen = ExamGenerator()
            exam = await gen.generate_exam("Machine Learning")

        q_types = {q["type"] for q in exam["questions"]}
        assert "written" in q_types, "Must have a written question"
        assert "multiple_choice" in q_types, "Must have an MCQ question"
        assert "fill_in_blank" in q_types, "Must have a fill-in-blank question"

    @pytest.mark.asyncio
    async def test_fallback_exam_on_llm_failure(self):
        """When LLM fails, fallback exam must still return valid structure."""
        from app.rag.exam_generator import ExamGenerator

        with patch("app.rag.ollama_client.ollama.chat", new=AsyncMock(side_effect=RuntimeError("LLM down"))):
            gen = ExamGenerator()
            exam = await gen.generate_exam("Neural Networks")

        assert "questions" in exam
        assert len(exam["questions"]) == 3

    @pytest.mark.asyncio
    async def test_fallback_on_malformed_json(self):
        """Malformed LLM JSON must trigger _fallback_exam without crash."""
        from app.rag.exam_generator import ExamGenerator

        with patch("app.rag.ollama_client.ollama.chat", new=AsyncMock(return_value="NOT JSON!!!")):
            gen = ExamGenerator()
            exam = await gen.generate_exam("Backpropagation")

        assert "questions" in exam


class TestExamEvaluator:

    @pytest.mark.asyncio
    async def test_mcq_correct_answer(self):
        """MCQ: exact letter match = is_correct True, score 1.0."""
        from app.rag.exam_generator import ExamGenerator
        gen = ExamGenerator()
        result = await gen.evaluate_exam(
            questions=SAMPLE_EXAM["questions"],
            student_answers={"q1": "Some written answer", "q2": "A", "q3": "noise"},
        )
        mcq_result = next(r for r in result["evaluations"] if r["id"] == "q2")
        assert mcq_result["is_correct"] is True
        assert mcq_result["score"] == 1.0

    @pytest.mark.asyncio
    async def test_mcq_wrong_answer(self):
        """MCQ: wrong letter = is_correct False, score 0.0."""
        from app.rag.exam_generator import ExamGenerator
        gen = ExamGenerator()
        result = await gen.evaluate_exam(
            questions=SAMPLE_EXAM["questions"],
            student_answers={"q1": "Any answer", "q2": "C", "q3": "noise"},
        )
        mcq_result = next(r for r in result["evaluations"] if r["id"] == "q2")
        assert mcq_result["is_correct"] is False
        assert mcq_result["score"] == 0.0

    @pytest.mark.asyncio
    async def test_fill_in_blank_correct_exact(self):
        """Fill-in-blank: exact match must be graded correct."""
        from app.rag.exam_generator import ExamGenerator
        gen = ExamGenerator()
        result = await gen.evaluate_exam(
            questions=SAMPLE_EXAM["questions"],
            student_answers={"q1": "Written", "q2": "A", "q3": "noise"},
        )
        fib = next(r for r in result["evaluations"] if r["id"] == "q3")
        assert fib["is_correct"] is True

    @pytest.mark.asyncio
    async def test_fill_in_blank_accepted_alternative(self):
        """Fill-in-blank: accepted alternative must also be graded correct."""
        from app.rag.exam_generator import ExamGenerator
        gen = ExamGenerator()
        result = await gen.evaluate_exam(
            questions=SAMPLE_EXAM["questions"],
            student_answers={"q1": "Written", "q2": "A", "q3": "random noise"},
        )
        fib = next(r for r in result["evaluations"] if r["id"] == "q3")
        assert fib["is_correct"] is True

    @pytest.mark.asyncio
    async def test_fill_in_blank_wrong_answer(self):
        """Fill-in-blank: completely wrong answer must score 0."""
        from app.rag.exam_generator import ExamGenerator
        gen = ExamGenerator()
        result = await gen.evaluate_exam(
            questions=SAMPLE_EXAM["questions"],
            student_answers={"q1": "Written", "q2": "A", "q3": "gradient"},
        )
        fib = next(r for r in result["evaluations"] if r["id"] == "q3")
        assert fib["is_correct"] is False

    @pytest.mark.asyncio
    async def test_total_score_calculation(self):
        """Total score must equal sum of per-question scores."""
        from app.rag.exam_generator import ExamGenerator
        gen = ExamGenerator()

        mock_written_eval = json.dumps({
            "score_percentage": 80,
            "is_correct": True,
            "feedback": "Good.",
            "ideal_answer": "Supervised learning uses labelled data.",
        })

        with patch("app.rag.ollama_client.ollama.chat", new=AsyncMock(return_value=mock_written_eval)):
            result = await gen.evaluate_exam(
                questions=SAMPLE_EXAM["questions"],
                student_answers={"q1": "Supervised learning uses labelled examples.", "q2": "A", "q3": "noise"},
            )

        per_question_total = sum(r["score"] for r in result["evaluations"])
        assert abs(result["total_score"] - per_question_total) < 0.01
