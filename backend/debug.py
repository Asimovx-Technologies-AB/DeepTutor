import asyncio
from app.models.artifact import GeneratedArtifact, GeneratedArtifactItem
from app.tutoring.analyzer.resolver import ReferenceResolver
from app.tutoring.analyzer.understanding import QueryUnderstanding
from tests.test_reference_resolution import MockDBSession

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

print(f"Action: {query_meta.understanding_result.action}")
print(f"Intent: {query_meta.understanding_result.intent}")
print(f"Original LLM intent?: {query_meta.intent}")
