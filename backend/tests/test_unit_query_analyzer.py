"""
test_unit_query_analyzer.py
============================
Criteria §1.2 — RAG Components: Query Analyzer.

Tests the QueryAnalyzerAgent deterministic/heuristic path (no real LLM call
required) by mocking the Ollama/Gemini client. Validates:
- Intent classification (EXPLANATION_REQUEST, QUIZ_REQUEST, GREETING …)
- Compound question decomposition into sub_questions
- Clean target_topic extraction (no "what is / explain" prefix)
- Fallback behaviour on LLM failure
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
import json


# ── Helpers ────────────────────────────────────────────────────────────────

def _planner_json(**kwargs) -> str:
    """Build a minimal valid planner JSON response."""
    defaults = {
        "reasoning": "Test reasoning.",
        "intent": "EXPLANATION_REQUEST",
        "sub_questions": ["What is machine learning?"],
        "target_topic": "machine learning",
        "search_queries": ["machine learning definition"],
        "extracted_subject": None,
        "response_format": "conceptual",
        "requires_table_data": False,
        "requires_image_data": False,
        "confidence": 0.9,
        "needs_clarification": False,
        "recommended_action": "EXPLAIN",
    }
    defaults.update(kwargs)
    return json.dumps(defaults)


# ── Tests ──────────────────────────────────────────────────────────────────

class TestQueryAnalyzerHeuristics:
    """Tests that exercise deterministic heuristic paths (no LLM)."""

    @pytest.mark.asyncio
    async def test_greeting_fast_path(self):
        """Bare greetings must be classified without an LLM call."""
        from app.rag.query_analyzer import QueryAnalyzerAgent
        agent = QueryAnalyzerAgent()
        for greeting in ["hello", "hi", "hey", "Hello!", "hi."]:
            plan = await agent.analyze(greeting)
            assert plan["intent"] == "GREETING", f"Expected GREETING for '{greeting}', got {plan['intent']}"
            assert plan["recommended_action"] == "GREET"

    @pytest.mark.asyncio
    async def test_explanation_request_via_mock(self):
        """A factual question should be classified as EXPLANATION_REQUEST."""
        from app.rag.query_analyzer import QueryAnalyzerAgent

        mock_response = _planner_json(intent="EXPLANATION_REQUEST", target_topic="SVM hyperplane")

        with patch("app.rag.ollama_client.ollama.chat", new=AsyncMock(return_value=mock_response)):
            agent = QueryAnalyzerAgent()
            plan = await agent.analyze("What is the SVM hyperplane?")

        assert plan["intent"] == "EXPLANATION_REQUEST"
        assert plan["recommended_action"] == "EXPLAIN"

    @pytest.mark.asyncio
    async def test_quiz_request_classification(self):
        """'Quiz me on SVMs' must yield QUIZ_REQUEST."""
        from app.rag.query_analyzer import QueryAnalyzerAgent

        mock_response = _planner_json(
            intent="QUIZ_REQUEST",
            response_format="quiz",
            recommended_action="QUIZ_QUESTION",
        )

        with patch("app.rag.ollama_client.ollama.chat", new=AsyncMock(return_value=mock_response)):
            agent = QueryAnalyzerAgent()
            plan = await agent.analyze("Quiz me on SVMs")

        assert plan["intent"] == "QUIZ_REQUEST"
        assert plan["response_format"] == "quiz"

    @pytest.mark.asyncio
    async def test_study_notes_classification(self):
        """'Create a md file on neural networks' should yield STUDY_NOTES_REQUEST."""
        from app.rag.query_analyzer import QueryAnalyzerAgent

        mock_response = _planner_json(
            intent="STUDY_NOTES_REQUEST",
            response_format="study_notes",
            recommended_action="EXPLAIN",
        )

        with patch("app.rag.ollama_client.ollama.chat", new=AsyncMock(return_value=mock_response)):
            agent = QueryAnalyzerAgent()
            plan = await agent.analyze("Create a md file on neural networks")

        assert plan["intent"] == "STUDY_NOTES_REQUEST"
        assert plan["response_format"] == "study_notes"

    @pytest.mark.asyncio
    async def test_target_topic_is_clean(self):
        """target_topic must never be a full question sentence."""
        from app.rag.query_analyzer import QueryAnalyzerAgent

        # The mock returns a dirty topic; the parser should clean it
        mock_response = _planner_json(target_topic="what is gradient descent")

        with patch("app.rag.ollama_client.ollama.chat", new=AsyncMock(return_value=mock_response)):
            agent = QueryAnalyzerAgent()
            plan = await agent.analyze("Explain gradient descent")

        topic = plan.get("target_topic") or ""
        assert not topic.lower().startswith("what is"), \
            f"target_topic must be cleaned; got: '{topic}'"

    @pytest.mark.asyncio
    async def test_compound_question_decomposed(self):
        """A compound question must produce multiple sub_questions."""
        from app.rag.query_analyzer import QueryAnalyzerAgent

        mock_response = _planner_json(
            sub_questions=["What is SVM?", "How does it differ from logistic regression?"],
        )

        with patch("app.rag.ollama_client.ollama.chat", new=AsyncMock(return_value=mock_response)):
            agent = QueryAnalyzerAgent()
            plan = await agent.analyze("What is SVM and how does it differ from logistic regression?")

        assert len(plan["sub_questions"]) >= 2, "Compound question should produce ≥ 2 sub_questions"

    @pytest.mark.asyncio
    async def test_fallback_on_llm_failure(self):
        """When LLM fails entirely, heuristic fallback must be returned (no crash)."""
        from app.rag.query_analyzer import QueryAnalyzerAgent

        with patch("app.rag.ollama_client.ollama.chat", new=AsyncMock(side_effect=RuntimeError("LLM down"))):
            agent = QueryAnalyzerAgent(max_retries=0)
            plan = await agent.analyze("Explain backpropagation")

        # Must return a valid plan dict without raising
        assert "intent" in plan
        assert "recommended_action" in plan

    @pytest.mark.asyncio
    async def test_malformed_json_triggers_retry_and_fallback(self):
        """Malformed JSON from LLM must trigger retry then fallback."""
        from app.rag.query_analyzer import QueryAnalyzerAgent

        with patch("app.rag.ollama_client.ollama.chat", new=AsyncMock(return_value="not-valid-json!!!")):
            agent = QueryAnalyzerAgent(max_retries=1)
            plan = await agent.analyze("Explain k-means clustering")

        assert "intent" in plan  # should degrade gracefully

    @pytest.mark.asyncio
    async def test_topics_and_entities_extraction(self):
        """Advanced architecture: verify topics and technical entities extraction."""
        from app.rag.query_analyzer import QueryAnalyzerAgent

        mock_response = json.dumps({
            "reasoning": "Photosynthesis concept explanation with chlorophyll entity.",
            "intent": "EXPLANATION_REQUEST",
            "topics": ["Biology", "Photosynthesis"],
            "entities": ["chlorophyll", "ATP", "Calvin cycle"],
            "sub_questions": ["What is photosynthesis?", "What is the role of chlorophyll?"],
            "target_topic": "Photosynthesis",
            "search_queries": ["photosynthesis", "chlorophyll ATP"],
            "response_format": "conceptual",
            "requires_table_data": False,
            "requires_image_data": True,
            "retrieval_plan": {"sources": ["vector", "bm25", "images"], "tools": ["none"]},
            "status": "clear",
            "clarification_prompt": None,
            "confidence": 0.95,
            "recommended_action": "EXPLAIN",
        })

        with patch("app.rag.ollama_client.ollama.chat", new=AsyncMock(return_value=mock_response)):
            agent = QueryAnalyzerAgent()
            plan = await agent.analyze("Explain photosynthesis and the role of chlorophyll with diagram")

        assert "Biology" in plan["topics"] or "Photosynthesis" in plan["topics"]
        assert "chlorophyll" in plan["entities"]
        assert "images" in plan["retrieval_plan"]["sources"]
        assert plan["status"] == "clear"

    @pytest.mark.asyncio
    async def test_ambiguity_and_clarification_prompt(self):
        """Advanced architecture: verify ambiguity detection & clarification prompt generation."""
        from app.rag.query_analyzer import QueryAnalyzerAgent

        mock_response = json.dumps({
            "reasoning": "Query is a single vague term without context.",
            "intent": "EXPLANATION_REQUEST",
            "topics": ["Formula"],
            "entities": [],
            "sub_questions": ["formula"],
            "target_topic": "Formula",
            "search_queries": ["formula"],
            "response_format": "conceptual",
            "requires_table_data": False,
            "requires_image_data": False,
            "retrieval_plan": {"sources": ["vector", "bm25"], "tools": ["none"]},
            "status": "needs_clarification",
            "clarification_prompt": "Which formula from your textbook would you like to explore (e.g., quadratic formula, Newton's law)?",
            "confidence": 0.3,
            "needs_clarification": True,
            "recommended_action": "CLARIFY",
        })

        with patch("app.rag.ollama_client.ollama.chat", new=AsyncMock(return_value=mock_response)):
            agent = QueryAnalyzerAgent()
            plan = await agent.analyze("formula")

        assert plan["status"] == "needs_clarification"
        assert plan["needs_clarification"] is True
        assert "Which formula" in plan["clarification_prompt"]

    @pytest.mark.asyncio
    async def test_comparison_fast_path_retrieval_plan(self):
        """Verify comparison fast-path populates retrieval_plan with tables."""
        from app.rag.query_analyzer import QueryAnalyzerAgent

        agent = QueryAnalyzerAgent()
        plan = await agent.analyze("difference between CNN and RNN")

        assert plan["response_format"] == "comparison"
        assert plan["requires_table_data"] is True
        assert "tables" in plan["retrieval_plan"]["sources"]
        assert any(t.lower() == "cnn" for t in plan["topics"]) or any(e.lower() == "cnn" for e in plan["entities"])
        assert plan["status"] == "clear"

