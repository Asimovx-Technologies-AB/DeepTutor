import pytest
from app.rag.section_scope import get_section_collection_id, user_owns_section
from app.rag.quiz_generator import _validate_questions, _parse_quiz_json

def test_parse_quiz_json():
    raw_json = """
    ```json
    {
      "title": "Sample Quiz",
      "questions": [
        {
          "question_text": "What is 2+2?",
          "options": ["3", "4", "5", "6"],
          "correct_answer": "B",
          "explanation": "2+2=4"
        }
      ]
    }
    ```
    """
    parsed = _parse_quiz_json(raw_json)
    assert parsed is not None
    assert parsed.get("title") == "Sample Quiz"
    valid = _validate_questions(parsed.get("questions", []))
    assert len(valid) == 1
    assert valid[0]["correct_answer"] == "B"

def test_section_collection_id():
    col_id = get_section_collection_id("user123", "general")
    assert col_id == "sec_user123_general"
