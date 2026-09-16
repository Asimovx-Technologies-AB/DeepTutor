import pytest
from app.tutoring.analyzer.understanding import QueryUnderstanding
from app.tutoring.analyzer.pre_gen_classifier import PreGenerationClassifier
from app.tutoring.router.query_router import QueryRouter
from app.tutoring.pipelines.casual import CasualPipeline


def test_casual_acknowledgment_intent_classification():
    """Verify that casual pleasantries and acknowledgments yield intent='CASUAL'."""
    queries = [
        "ok thankyou",
        "ok thank you",
        "okay thanks",
        "got it",
        "makes sense",
        "understood",
        "thankyou",
        "thanks",
        "cool thanks",
        "perfect thank you",
    ]

    for q in queries:
        meta = QueryUnderstanding.analyze_query(
            raw_query=q,
            resolved_query=q,
            conversation_history=[],
        )
        assert meta.intent == "CASUAL", f"Expected CASUAL intent for '{q}', got {meta.intent}"
        assert meta.visual_modality == "none", f"Expected visual_modality='none' for '{q}', got {meta.visual_modality}"


def test_casual_pre_generation_classification_plan():
    """Verify that CASUAL intent yields depth='short', visual='none', skip_followup_question=True."""
    queries = [
        "ok thankyou",
        "ok thank you",
        "got it",
    ]

    for q in queries:
        plan = PreGenerationClassifier.classify(
            raw_query=q,
            resolved_query=q,
            intent="CASUAL",
        )
        assert plan.depth == "short", f"Expected depth='short' for '{q}', got {plan.depth}"
        assert plan.visual == "none", f"Expected visual='none' for '{q}', got {plan.visual}"
        assert plan.skip_followup_question is True, f"Expected skip_followup_question=True for '{q}', got {plan.skip_followup_question}"


def test_casual_query_routing():
    """Verify that QueryRouter routes CASUAL queries to CASUAL_PIPELINE."""
    meta = QueryUnderstanding.analyze_query("ok thankyou", "ok thankyou", conversation_history=[])
    dest, strategy = QueryRouter.route_query(meta, has_active_document=True)
    assert dest == "CASUAL_PIPELINE", f"Expected CASUAL_PIPELINE destination, got {dest}"


def test_casual_pipeline_response():
    """Verify CasualPipeline produces clean, polite pleasantries without persona/topic hallucinations."""
    res = CasualPipeline.generate_response("ok thankyou")
    assert res["intent"] == "CASUAL"
    assert "parent" not in res["content"].lower()
    assert "figure" not in res["content"].lower()
    assert len(res["content"]) > 10
