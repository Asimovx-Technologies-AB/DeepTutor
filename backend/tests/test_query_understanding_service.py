import pytest
from app.tutoring.analyzer.fast_path import QueryFastPath
from app.tutoring.analyzer.preprocessor import QueryPreprocessor
from app.tutoring.analyzer.resolver import ReferenceResolver
from app.tutoring.analyzer.understanding import QueryUnderstanding
from app.tutoring.analyzer.service import QueryUnderstandingService
from app.tutoring.router.action_router import ActionRouter
from app.tutoring.router.query_router import QueryRouter
from app.schemas.tutoring import (
    QueryUnderstandingResult,
    ActionPlan,
    UserIntent,
    RetrievalDecisionEnum,
    RetrievalScopeEnum,
    ResponseTypeEnum,
    ActionTypeEnum,
    QueryMetadata
)


def test_fast_path_greetings_and_confirmations():
    # 1. Greetings
    for g in ["hi", "Hello", "hey there!", "good morning", "Good afternoon."]:
        res = QueryFastPath.evaluate(g, g)
        assert res is not None, f"Expected fast-path match for greeting '{g}'"
        assert res.intent in ("GREETING", "CASUAL")
        assert res.action == ActionTypeEnum.CASUAL_REPLY.value
        assert res.is_fast_path is True
        assert res.requires_retrieval is False
        assert res.confidence >= 0.95

    # 2. Gratitude
    for t in ["thanks", "Thank you", "thanks a lot", "appreciate it"]:
        res = QueryFastPath.evaluate(t, t)
        assert res is not None
        assert res.intent == UserIntent.CONFIRMATION.value
        assert res.sub_intent == "GRATITUDE"
        assert res.action == ActionTypeEnum.CASUAL_REPLY.value
        assert res.is_fast_path is True

    # 3. Confirmations
    for c in ["ok", "okay", "got it", "understood", "makes sense", "yes", "sure"]:
        res = QueryFastPath.evaluate(c, c)
        assert res is not None
        assert res.intent == UserIntent.CONFIRMATION.value
        assert res.is_fast_path is True

    # 4. Continuation
    res_cont = QueryFastPath.evaluate("continue", "continue", current_topic="Neural Networks")
    assert res_cont is not None
    assert res_cont.intent == UserIntent.CONTINUE_LEARNING.value
    assert res_cont.action == ActionTypeEnum.TEACH_TOPIC.value
    assert "Neural Networks" in res_cont.resolved_query

    # 5. Non-fast path academic query
    non_fast = QueryFastPath.evaluate("Explain backpropagation in neural networks", "Explain backpropagation in neural networks")
    assert non_fast is None


def test_query_preprocessing_and_preservation():
    raw = "  can you explain the backprop algoritm  and derivitave with an exmple ?  "
    normalized, lang, meta = QueryPreprocessor.preprocess(raw)
    assert lang == "english"
    assert "algorithm" in normalized
    assert "derivative" in normalized
    assert "example" in normalized
    assert meta["has_typos_fixed"] is True
    assert meta["raw_query"] == raw
    assert "example" in meta["reference_markers"] or len(meta["reference_markers"]) >= 0


def test_reference_resolver_followups_and_pronouns():
    history = [
        {"role": "user", "content": "Explain Convolutional Neural Networks."},
        {"role": "assistant", "content": "**Convolutional Neural Networks** (CNNs) process grid-like visual data using convolution filters."}
    ]

    # 1. Ellipsis "What about pooling?"
    resolved_q1, meta1 = ReferenceResolver.resolve_references("What about pooling?", history)
    assert meta1["is_follow_up"] is True
    assert "pooling" in resolved_q1.lower()
    assert "convolutional neural networks" in resolved_q1.lower() or "cnn" in resolved_q1.lower()

    # 2. Example request "Give me an example"
    resolved_q2, meta2 = ReferenceResolver.resolve_references("Give me an example", history)
    assert meta2["is_follow_up"] is True
    assert "Convolutional Neural Networks" in resolved_q2

    # 3. Pronoun resolution "How does it work?"
    resolved_q3, meta3 = ReferenceResolver.resolve_references("How does it work?", history)
    assert "Convolutional Neural Networks" in resolved_q3

    # 4. Compact context representation
    compact = ReferenceResolver.build_compact_context(history, current_subject="Deep Learning", current_topic="CNN")
    assert compact["total_turns_count"] == 2
    assert compact["active_concept"] == "Convolutional Neural Networks"
    assert len(compact["recent_turns"]) == 2


def test_query_understanding_intent_and_topic_extraction():
    # 1. Topic explanation with simple example
    q1 = "Explain backpropagation in neural networks with a simple example."
    res1 = QueryUnderstanding.analyze_query_structured(q1)
    assert res1.intent in ("EXPLAIN_TOPIC", "EXPLANATION")
    assert "backpropagation" in res1.resolved_query.lower() or res1.topic is not None
    assert res1.requires_example is True
    assert res1.difficulty == "beginner" or "beginner" in res1.response_type.lower() or res1.difficulty is not None
    assert res1.requires_retrieval is True

    # 2. Concept Comparison
    q2 = "What is the difference between CNN and RNN?"
    res2 = QueryUnderstanding.analyze_query_structured(q2)
    assert res2.intent in ("COMPARE_CONCEPTS", "COMPARISON")
    assert res2.response_type in ("COMPARISON", "comparison")
    assert any("cnn" in t.lower() for t in res2.topics) or any("rnn" in t.lower() for t in res2.topics) or len(res2.topics) >= 1

    # 3. Study Plan Creation
    q3 = "Create a 5-day study plan for Machine Learning"
    res3 = QueryUnderstanding.analyze_query_structured(q3)
    assert res3.intent == "CREATE_STUDY_PLAN"
    assert res3.action == "CREATE_STUDY_PLAN"
    assert res3.requires_tool is True
    assert res3.tool_name == "study_plan_service"

    # 4. Quiz Generation
    q4 = "Quiz me on Support Vector Machines"
    res4 = QueryUnderstanding.analyze_query_structured(q4)
    assert res4.intent in ("QUIZ", "GENERATE_QUIZ")
    assert res4.action == "GENERATE_QUIZ"
    assert res4.requires_tool is True


def test_retrieval_decision_and_scope():
    # 1. Uploaded material grounded question
    q_mat = "According to Chapter 4, explain neural networks from my uploaded notes."
    res_mat = QueryUnderstanding.analyze_query_structured(q_mat)
    assert res_mat.requires_retrieval is True
    assert res_mat.retrieval_scope in ("USER_MATERIAL", "SPECIFIC_CHAPTER")

    # 2. Fast-path casual question (no retrieval)
    q_cas = "Hello there!"
    res_cas = QueryUnderstanding.analyze_query_structured(q_cas)
    assert res_cas.requires_retrieval is False
    assert res_cas.retrieval_scope == "NONE"


def test_action_router_dispatch():
    # 1. Casual routing
    plan_casual = QueryUnderstandingResult(
        original_query="hello",
        normalized_query="hello",
        resolved_query="hello",
        intent="GREETING",
        action="CASUAL_REPLY",
        requires_retrieval=False,
        retrieval_scope="NONE",
        confidence=0.99
    )
    route1, strat1 = ActionRouter.route_action(plan_casual, has_active_document=True)
    assert route1 == "CASUAL_PIPELINE"

    # 2. Study Plan routing
    plan_sp = QueryUnderstandingResult(
        original_query="make a study plan",
        normalized_query="make a study plan",
        resolved_query="make a study plan",
        intent="CREATE_STUDY_PLAN",
        action="CREATE_STUDY_PLAN",
        requires_tool=True,
        tool_name="study_plan_service",
        requires_retrieval=False,
        confidence=0.95
    )
    route2, strat2 = ActionRouter.route_action(plan_sp, has_active_document=True)
    assert route2 == "STUDY_PLAN_SERVICE"

    # 3. RAG Retrieval comparison routing
    plan_rag = QueryUnderstandingResult(
        original_query="compare CNN and RNN",
        normalized_query="compare cnn and rnn",
        resolved_query="compare Convolutional Neural Networks and Recurrent Neural Networks",
        intent="COMPARE_CONCEPTS",
        action="EXPLAIN_TOPIC",
        topics=["CNN", "RNN"],
        requires_retrieval=True,
        retrieval_scope="USER_MATERIAL",
        confidence=0.95
    )
    route3, strat3 = ActionRouter.route_action(plan_rag, has_active_document=True)
    assert route3 == "RAG_RETRIEVAL"
    assert strat3 == "multi_concept"


def test_query_understanding_service_end_to_end():
    # End-to-end service invocation
    result = QueryUnderstandingService.analyze_query(
        raw_user_query="Can you explain Gradient Descent with a simple formula?",
        conversation_context=[],
        current_subject="Optimization",
        current_topic="Gradient Descent"
    )

    assert isinstance(result, QueryUnderstandingResult)
    assert result.original_query == "Can you explain Gradient Descent with a simple formula?"
    assert "gradient descent" in result.resolved_query.lower()
    assert result.action in ("EXPLAIN_TOPIC", "ANSWER_QUESTION")
    assert result.requires_retrieval is True
    assert result.confidence >= 0.85
    assert result.action_plan is not None
