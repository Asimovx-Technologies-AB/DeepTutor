import pytest
from app.schemas.tutoring import QueryMetadata, UserMessageClassificationEnum
from app.tutoring.analyzer.feedback_classifier import UserMessageContextClassifier
from app.tutoring.analyzer.understanding import QueryUnderstanding
from app.tutoring.analyzer.pre_gen_classifier import PreGenerationClassifier
from app.tutoring.router.query_router import QueryRouter
from app.tutoring.teaching.interactive_teacher import InteractiveTeacherEngine


def test_normal_queries_never_trigger_teach_mode():
    """Verify standard questions and explanation requests do not trigger TEACH_TOPIC or TEACH_TOPIC_REQUEST."""
    standard_queries = [
        "what is svm , explain with a figure",
        "what is svm",
        "explain svm",
        "explain svm with a figure",
        "explain svm with a diagram",
        "how does backpropagation work",
        "why does gradient descent oscillate",
        "can you explain decision trees",
        "tell me about logistic regression",
    ]

    for q in standard_queries:
        # 1. Topic extractor must not treat normal Q&A as teaching topic
        extracted = QueryUnderstanding.extract_teach_topic(q)
        assert extracted is None, f"Query '{q}' should NOT extract a teaching topic, got '{extracted}'"

        # 2. Context classifier must never return TEACH_TOPIC_REQUEST for normal inquiries
        classified = UserMessageContextClassifier.classify_message(q)
        assert classified.category != UserMessageClassificationEnum.TEACH_TOPIC_REQUEST, (
            f"Query '{q}' should NOT be classified as TEACH_TOPIC_REQUEST, got '{classified.category}'"
        )


def test_explicit_teach_queries_trigger_teach_mode():
    """Verify explicit teach requests successfully trigger TEACH_TOPIC and TEACH_TOPIC_REQUEST."""
    teach_queries = [
        ("Teach me SVM", "SVM"),
        ("Act as a teacher and teach me Decision Trees", "Decision Tree"),
        ("teach me about Photosynthesis step by step", "Photosynthesis"),
        ("Start teaching", "this topic"),
        ("Teach me this chapter", "this chapter"),
    ]

    for q, expected_sub in teach_queries:
        extracted = QueryUnderstanding.extract_teach_topic(q)
        assert extracted is not None, f"Query '{q}' should have extracted a topic"
        assert expected_sub.lower() in extracted.lower(), f"Expected '{expected_sub}' in '{extracted}'"

        classified = UserMessageContextClassifier.classify_message(q)
        assert classified.category == UserMessageClassificationEnum.TEACH_TOPIC_REQUEST, (
            f"Query '{q}' should be classified as TEACH_TOPIC_REQUEST, got '{classified.category}'"
        )


def test_visual_request_sets_visual_required():
    """Verify visual requests like 'explain with a figure' trigger visual='required'."""
    plan1 = PreGenerationClassifier.classify("what is svm , explain with a figure")
    assert plan1.visual == "required", f"Expected visual='required', got '{plan1.visual}'"

    plan2 = PreGenerationClassifier.classify("explain gradient descent with a diagram")
    assert plan2.visual == "required", f"Expected visual='required', got '{plan2.visual}'"


def test_active_teacher_session_does_not_hijack_substantive_questions():
    """Verify that asking a normal question inside an active teacher session routes to RETRIEVAL_PIPELINE, not TEACHER_MODE_PIPELINE."""
    teacher_state = {
        "mode": "teacher",
        "topic": "Machine Learning",
        "current_subtopic": "Foundations",
        "paused": False,
    }

    # Turn A: Student asks an ad-hoc question
    meta_question = QueryUnderstanding.analyze_intent_and_metadata(
        raw_query="what is svm , explain with a figure",
        normalized_query="what is svm , explain with a figure",
        resolved_query="what is svm , explain with a figure",
        language="en",
        teacher_state=teacher_state,
    )

    dest_q, _ = QueryRouter.route_query(meta_question, has_active_document=True)
    assert dest_q == "RETRIEVAL_PIPELINE", f"Ad-hoc question should route to RETRIEVAL_PIPELINE, got '{dest_q}'"
    assert meta_question.intent != "TEACH_TOPIC", f"Intent should not be overridden to TEACH_TOPIC for ad-hoc question"

    # Turn B: Student says 'continue' -> should route to TEACHER_MODE_PIPELINE
    meta_continue = QueryUnderstanding.analyze_intent_and_metadata(
        raw_query="continue",
        normalized_query="continue",
        resolved_query="continue",
        language="en",
        teacher_state=teacher_state,
    )

    dest_c, _ = QueryRouter.route_query(meta_continue, has_active_document=True)
    assert dest_c == "TEACHER_MODE_PIPELINE", f"Continue command should route to TEACHER_MODE_PIPELINE, got '{dest_c}'"
