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


def test_meta_referential_query_detection():
    from app.services.study_agents import is_meta_referential_query
    assert is_meta_referential_query("make a flashcard on above module you gave me") is True
    assert is_meta_referential_query("make flashcards on the above module") is True
    assert is_meta_referential_query("create flashcards from what you just explained") is True
    assert is_meta_referential_query("quiz me on previous response") is True
    assert is_meta_referential_query("make flashcards on this") is True
    assert is_meta_referential_query("what is photosythesis") is False


@pytest.mark.asyncio
async def test_meta_referential_flashcard_agent_execution():
    from app.services.study_agents import QueryAnalyzerAgent, DecisionAgent
    planner = QueryAnalyzerAgent()
    executor = DecisionAgent()

    history = [
        {"role": "user", "content": "Explain Scaled Dot-Product Attention in Transformers"},
        {"role": "assistant", "content": "# Scaled Dot-Product Attention\n\nScaled Dot-Product Attention computes attention weights by taking the dot product of queries with keys, scaling by $\\sqrt{d_k}$, and applying a softmax function to obtain weights for values:\n$$\\text{Attention}(Q, K, V) = \\text{softmax}\\left(\\frac{QK^T}{\\sqrt{d_k}}\\right)V$$"}
    ]

    # 1. Planner should identify meta-referential query and resolve the topic
    plan = await planner.plan("make a flashcard on above module you gave me", subject="Attention All U Need", history=history)
    assert plan["is_meta_referential"] is True
    assert "Scaled Dot-Product Attention" in plan["resolved_topic"] or "Attention" in plan["resolved_topic"]

    # 2. Decision agent should generate flashcards directly grounded in the previous module rather than rejecting as out-of-scope
    mock_deck = {
        "title": "Scaled Dot-Product Attention",
        "description": "Flashcards on Scaled Dot-Product Attention",
        "initial_mode": "flashcards",
        "questions": [
            {
                "id": "q1",
                "prompt": "What scaling factor is used in Scaled Dot-Product Attention?",
                "options": [
                    {"id": "a", "text": "$\\sqrt{d_k}$"},
                    {"id": "b", "text": "$d_k^2$"},
                    {"id": "c", "text": "$1/d_k$"},
                    {"id": "d", "text": "$d_k$"}
                ],
                "correct_option_id": "a",
                "explanation": "The dot product is divided by $\\sqrt{d_k}$ to prevent softmax gradients from becoming extremely small."
            }
        ]
    }
    with patch("app.services.study_quiz_engine.generate_flashcard_deck", new=AsyncMock(return_value=mock_deck)):
        result = await executor.execute(
            session_id="test_sess_meta",
            user_query="make a flashcard on above module you gave me",
            subject="Attention All U Need",
            plan=plan,
            history=history
        )
        assert result["format"] == "flashcard"
        assert result["quiz_data"] is not None
        assert "out of the scope" not in result["response"]
        assert "Scaled Dot-Product Attention" in result["response"]

