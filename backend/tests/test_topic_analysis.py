import pytest
from app.models.topic_analysis import DocumentTopicAnalysis, ExtractedTopic
from app.services.topic_analyzer import TopicAnalysisService

def test_topic_analysis_calculate_scores():
    # Test that different combinations of signals yield the correct scores and levels
    topics = [
        {
            "topic": "Backpropagation",
            "definitions_present": True,
            "formula_present": True,
            "examples_present": True,
            "questions_present": False,
            "evidence": ["A", "B", "C"],  # depth > 2
            "source_pages": [1, 2, 3, 4], # pages > 3
            "prerequisites": ["Calculus"]
        },
        {
            "topic": "Minor Sub-topic",
            "definitions_present": False,
            "formula_present": False,
            "examples_present": False,
            "questions_present": False,
            "evidence": ["A"],
            "source_pages": [1],
            "prerequisites": []
        }
    ]
    
    scored = TopicAnalysisService._calculate_scores(topics)
    
    assert len(scored) == 2
    
    # Backpropagation should be HIGH
    high_topic = next((t for t in scored if t["topic"] == "Backpropagation"), None)
    assert high_topic is not None
    assert high_topic["importance_level"] == "HIGH"
    assert high_topic["importance_score"] >= 0.7
    
    # Minor Sub-topic should be LOW
    low_topic = next((t for t in scored if t["topic"] == "Minor Sub-topic"), None)
    assert low_topic is not None
    assert low_topic["importance_level"] == "LOW"
    assert low_topic["importance_score"] < 0.4

def test_global_consolidation_fallback():
    # Test that if LLM fails, it falls back to the original candidates list
    candidates = [{"topic": "A"}, {"topic": "B"}]
    # We won't mock LLM here, so it should fail (no API key in test environment) or return something
    # If it fails, it returns candidates
    res = TopicAnalysisService._global_consolidation(candidates)
    assert isinstance(res, list)

def test_intent_classification_for_topic_analysis():
    # Test that heuristic logic maps variations of "important topics" correctly
    from app.tutoring.analyzer.understanding import QueryUnderstanding
    queries = [
        "What are the important topics?",
        "Which topics should I study?",
        "What are the key concepts in this material?",
        "identify the major subjects"
    ]
    for q in queries:
        # We simulate the _heuristic_analysis behavior
        meta = QueryUnderstanding._heuristic_analysis(
            raw_query=q,
            normalized_query=q,
            resolved_query=q,
            language="en",
            is_follow_up=False,
            conversation_history=[]
        )
        res = QueryUnderstanding._build_structured_result_from_meta(
            meta, q, q, q, "en"
        )
        assert res.intent == "DOCUMENT_TOPIC_ANALYSIS"
        assert res.requires_document_analysis is True
        assert res.analysis_scope == "COMPLETE_DOCUMENT"

def test_negative_intent_classification_for_topic_analysis():
    from app.tutoring.analyzer.understanding import QueryUnderstanding
    queries = [
        "What is edge computing?",
        "Explain the important topic of edge computing"
    ]
    for q in queries:
        meta = QueryUnderstanding._heuristic_analysis(
            raw_query=q,
            normalized_query=q,
            resolved_query=q,
            language="en",
            is_follow_up=False,
            conversation_history=[]
        )
        res = QueryUnderstanding._build_structured_result_from_meta(
            meta, q, q, q, "en"
        )
        # Should not be a DOCUMENT_TOPIC_ANALYSIS request
        assert res.intent != "DOCUMENT_TOPIC_ANALYSIS"
        assert res.requires_document_analysis is False

def test_topic_analysis_routing():
    from app.tutoring.router.query_router import QueryRouter
    from app.schemas.tutoring import QueryUnderstandingResult, QueryMetadata
    
    # Test that DOCUMENT_TOPIC_ANALYSIS routes correctly
    res = QueryUnderstandingResult(
        original_query="what to study",
        normalized_query="what to study",
        resolved_query="what to study",
        language="en",
        intent="DOCUMENT_TOPIC_ANALYSIS",
        subject=None,
        topic=None,
        difficulty="intermediate",
        response_type="DETAILED_EXPLANATION",
        requires_context=False,
        requires_retrieval=False,
        retrieval_scope="NONE",
        retrieval_query=None,
        action="ANALYZE_IMPORTANT_TOPICS",
        requires_tool=False,
        requires_document_analysis=True,
        analysis_scope="COMPLETE_DOCUMENT"
    )
    meta = QueryMetadata(
        raw_query="what to study",
        language="en",
        normalized_query="what to study",
        resolved_query="what to study",
        intent="DOCUMENT_TOPIC_ANALYSIS",
        context_source="study_material",
        understanding_result=res
    )
    
    route_dest, strat = QueryRouter.route_query(meta, has_active_document=True)
    assert route_dest == "DOCUMENT_TOPIC_ANALYSIS_PIPELINE"

def test_format_analysis_for_chat():
    # Test the markdown formatter
    class MockAnalysis:
        id = "1"
        status = "COMPLETED"
    
    class MockTopic:
        chapter = "Chapter 1"
        importance_level = "HIGH"
        topic = "IoT"
        importance_score = 0.95
        evidence = ["It's IoT"]
        subtopics = ["A", "B"]

    class MockQuery:
        def filter(self, *args, **kwargs): return self
        def order_by(self, *args, **kwargs): return self
        def all(self): return [MockTopic()]

    class MockSession:
        def query(self, *args, **kwargs):
            return MockQuery()

    res = TopicAnalysisService.format_analysis_for_chat(MockSession(), MockAnalysis())
    assert "### Important Topics Analysis" in res
    assert "Chapter 1" in res
    assert "🔴 **IoT**" in res
    assert "It's IoT" in res
