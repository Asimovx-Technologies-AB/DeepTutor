import pytest
from app.tutoring.analyzer.understanding import QueryUnderstanding
from app.tutoring.analyzer.pre_gen_classifier import PreGenerationClassifier
from app.tutoring.router.query_router import QueryRouter
from app.tutoring.teaching.agent import TeachingAgent
from app.schemas.tutoring import QueryMetadata, ContextBundle


def test_study_notes_intent_classification():
    """Verify that requests for notes classify as intent='STUDY_NOTES' and NOT 'QUIZ'."""
    queries = [
        "give me notes",
        "make study notes for chapter 2",
        "prepare revision notes",
        "give me cheat sheet notes",
    ]

    for q in queries:
        meta = QueryUnderstanding.analyze_query(raw_query=q, resolved_query=q, conversation_history=[])
        assert meta.intent == "STUDY_NOTES", f"Expected intent='STUDY_NOTES' for '{q}', got {meta.intent}"
        assert meta.intent != "QUIZ", f"Query '{q}' should NOT be classified as QUIZ"


def test_context_source_dialogue_history_classification():
    """Verify that queries referencing past chat turns classify as context_source='dialogue_history'."""
    chat_queries = [
        "summarize our chat",
        "what did we discuss before?",
        "repeat your previous answer",
        "explain line 2 of what you said in this chat",
    ]

    for q in chat_queries:
        meta = QueryUnderstanding.analyze_query(raw_query=q, resolved_query=q, conversation_history=[])
        assert meta.context_source == "dialogue_history", f"Expected context_source='dialogue_history' for '{q}', got {meta.context_source}"


def test_query_router_study_notes_does_not_route_to_assessment():
    """Verify QueryRouter routes STUDY_NOTES away from ASSESSMENT_PIPELINE."""
    meta = QueryMetadata(
        raw_query="give me notes",
        normalized_query="give me notes",
        resolved_query="give me notes",
        intent="STUDY_NOTES",
    )
    dest, strategy = QueryRouter.route_query(meta, has_active_document=True)
    assert dest != "ASSESSMENT_PIPELINE", f"Expected non-ASSESSMENT destination for STUDY_NOTES, got {dest}"
    assert dest == "SUMMARY_PIPELINE", f"Expected SUMMARY_PIPELINE destination for STUDY_NOTES, got {dest}"


test_teaching_agent_prompt_includes_study_notes_contract_defined = False

def test_teaching_agent_prompt_includes_study_notes_and_context_source_contracts():
    """Verify TeachingAgent injects Study Notes and Dialogue Context contracts into prompt."""
    meta = QueryMetadata(
        raw_query="give me notes on our chat",
        normalized_query="give me notes on our chat",
        resolved_query="give me notes on our chat",
        intent="STUDY_NOTES",
        context_source="dialogue_history",
        format_directives={"generate_study_notes": True},
    )
    bundle = ContextBundle(
        resolved_query="give me notes on our chat",
        conversation_history=[
            {"role": "user", "content": "What is IoT?"},
            {"role": "assistant", "content": "IoT connects physical devices to the internet."},
        ]
    )

    sys_prompt, user_prompt = TeachingAgent._build_prompts(meta, bundle)
    assert "PUBLICATION-GRADE STUDY NOTES CONTRACT" in sys_prompt
    assert "DO NOT GENERATE AN INTERACTIVE FLASHCARD OR QUIZ DECK" in sys_prompt
    assert "DIALOGUE CONTEXT GROUNDING CONTRACT" in sys_prompt
