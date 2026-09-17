import pytest
from datetime import datetime, timezone
from app.models.artifact import GeneratedArtifact, GeneratedArtifactItem
from app.schemas.tutoring import QueryUnderstandingResult
from app.tutoring.analyzer.resolver import ReferenceResolver
from app.tutoring.analyzer.understanding import QueryUnderstanding

class MockQuery:
    def __init__(self, item):
        self.item = item
        
    def order_by(self, *args):
        return self
        
    def filter(self, *args):
        return self

    def limit(self, *args):
        return self
        
    def first(self):
        return self.item

    def all(self):
        return [self.item] if self.item is not None else []

class MockDBSession:
    def __init__(self, artifact=None, item=None):
        self.artifact = artifact
        self.item = item

    def query(self, model):
        if model == GeneratedArtifact:
            return MockQuery(self.artifact)
        elif model == GeneratedArtifactItem:
            return MockQuery(self.item)
        return MockQuery(None)

def test_resolve_artifact_reference():
    art = GeneratedArtifact(id="art_1", session_id="ses_1", artifact_type="PRACTICE_QUESTION_SET", topic="IoT")
    item = GeneratedArtifactItem(id="item_1", artifact_id="art_1", item_index=3, content="The World Economic Forum identifies the impact of IoT as the driving force behind the fourth Industrial Revolution.", topic="Fourth Industrial Revolution")
    
    mock_db = MockDBSession(artifact=art, item=item)
    
    resolved_query, meta = ReferenceResolver.resolve_references("explain question 3", [], db_session=mock_db, session_id="ses_1")
    
    assert meta["reference_type"] == "GENERATED_QUESTION"
    assert meta["reference_index"] == 3
    assert meta["artifact_id"] == "art_1"
    assert meta["resolved_topic"] == "Fourth Industrial Revolution"
    assert "The World Economic Forum" in resolved_query

def test_query_understanding_hijack_prevention():
    art = GeneratedArtifact(id="art_1", session_id="ses_1", artifact_type="PRACTICE_QUESTION_SET", topic="IoT")
    item = GeneratedArtifactItem(id="item_1", artifact_id="art_1", item_index=3, content="Explain Smart Creatures", topic="Smart Creatures")
    
    mock_db = MockDBSession(artifact=art, item=item)
    
    _, ref_meta = ReferenceResolver.resolve_references("explain question 3", [], db_session=mock_db, session_id="ses_1")
    
    query_meta = QueryUnderstanding.analyze_intent_and_metadata(
        raw_query="explain question 3",
        normalized_query="explain question 3",
        resolved_query="explain question 3",
        language="en",
        is_follow_up=False,
        conversation_history=[],
        ref_meta=ref_meta
    )

    print("REF_META:", ref_meta)
    print("ACTION:", query_meta.understanding_result.action)

    # Assert the RAG Hijack Prevention properties
    assert query_meta.understanding_result.action == "EXPLAIN_GENERATED_QUESTION"
    assert query_meta.understanding_result.reference_type == "GENERATED_QUESTION"
    assert query_meta.understanding_result.topic == "Smart Creatures" # Topic should be strictly derived from the artifact item

def test_ambiguity_fallback():
    # No artifact exists in DB
    mock_db = MockDBSession(artifact=None, item=None)
    
    resolved_query, meta = ReferenceResolver.resolve_references("explain question 3", [], db_session=mock_db, session_id="ses_1")
    
    # Should fallback to history extraction
    assert meta.get("reference_type") is None
