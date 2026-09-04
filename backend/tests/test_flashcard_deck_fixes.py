import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from app.services.study_quiz_engine import (
    sanitize_topic_title,
    _parse_json_relaxed,
    _extract_question_objects,
    _fallback_deck,
    generate_flashcard_deck
)

def test_sanitize_topic_title():
    raw_1 = "Classification of Forests in India – Exhaustive Master Explanation in Class-10-Geography"
    assert sanitize_topic_title(raw_1) == "Classification of Forests in India"

    raw_2 = "## Support Vector Machines - Master Guide"
    assert sanitize_topic_title(raw_2) == "Support Vector Machines"

    raw_3 = ""
    assert sanitize_topic_title(raw_3) == "Course Material"


def test_fallback_deck_card_count():
    deck = _fallback_deck("Classification of Forests in India", "Geography", "flashcards")
    assert deck["title"] == "Classification of Forests in India"
    assert len(deck["questions"]) >= 6, "Fallback deck must contain at least 6 cards, never 1 single card!"
    assert deck["questions"][0]["prompt"].startswith("What is the foundational concept")


def test_extract_question_objects():
    raw_llm_output = """
    Here are the requested questions:
    {"id": "q1", "prompt": "What is forest classification?", "options": [{"id": "a", "text": "Grouping by traits"}], "correct_option_id": "a", "explanation": "It groups forests by density and climate."}
    {"id": "q2", "prompt": "What is reserved forest?", "options": [{"id": "a", "text": "Protected forest"}], "correct_option_id": "a", "explanation": "Reserved forests are protected."}
    """
    extracted = _extract_question_objects(raw_llm_output)
    assert len(extracted) == 2
    assert extracted[0]["id"] == "q1"
    assert extracted[1]["id"] == "q2"


@pytest.mark.asyncio
async def test_generate_flashcard_deck_fallback_on_error():
    with patch("app.services.study_quiz_engine.call_llm", new=AsyncMock(return_value="")):
        deck = await generate_flashcard_deck(
            session_id="test_sess_123",
            topic_id="t1",
            topic_title="Classification of Forests in India – Exhaustive Master Explanation",
            subject="Geography",
            num_cards=8,
            override_context="Forests in India are classified into Reserved, Protected, and Unclassed forests."
        )
        assert deck["title"] == "Classification of Forests in India"
        assert len(deck["questions"]) >= 6, f"Expected at least 6 cards on fallback, got {len(deck['questions'])}"
