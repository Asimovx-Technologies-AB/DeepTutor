import pytest
from app.tutoring.analyzer.pre_gen_classifier import PreGenerationClassifier
from app.tutoring.analyzer.understanding import QueryUnderstanding
from app.schemas.tutoring import QueryMetadata, ContextBundle, PreGenerationPlan
from app.tutoring.teaching.agent import TeachingAgent


def test_pre_gen_classification_matrix_20_queries():
    """
    Validates pre-generation classification across 20 sample queries
    spanning depth, format, visual, and conflict resolution combinations.
    """
    test_cases = [
        # (query, expected_depth, expected_format, expected_visual, expected_skip_followup)
        ("just the answer", "answer_only", "prose", "none", True),
        ("just the answer, in a table", "answer_only", "table", "none", True),
        ("solve 2x + 5 = 15", "answer_only", "prose", "none", True),
        ("only the answer for 15 * 8", "answer_only", "prose", "none", True),
        
        ("briefly explain photosynthesis in bullet points", "short", "bullets", "conditional", False),
        ("create 5 questions on photosynthesis, briefly", "short", "prose", "none", False),
        ("in short, what is RAM?", "short", "prose", "none", False),
        ("give me a list of key concepts in Machine Learning in short", "short", "bullets", "conditional", False),
        ("tl;dr summary of chapter 1", "short", "prose", "conditional", False),
        
        ("explain SVM in detail step by step", "detailed", "stepwise", "conditional", False),
        ("elaborate in detail on backpropagation in bullet points", "detailed", "bullets", "conditional", False),
        ("deep dive into gradient descent", "detailed", "prose", "conditional", False),
        
        ("draw a flowchart of the water cycle", "default", "prose", "required", False),
        ("explain the architecture diagram of transformers", "default", "prose", "required", False),
        ("compare bagging and boosting", "default", "table", "conditional", False),
        ("what is the difference between SVM and Random Forest in a table", "default", "table", "conditional", False),
        
        ("what is the time complexity of quicksort", "default", "prose", "none", False),
        ("define momentum", "default", "prose", "none", False),
        ("quiz me on chapter 3", "default", "prose", "none", False),
        ("how am I doing", "default", "prose", "none", False),
        ("show my weak topics", "default", "prose", "none", False),
        ("explain that again", "default", "prose", "none", False),
    ]

    for q, exp_depth, exp_fmt, exp_vis, exp_skip in test_cases:
        plan = PreGenerationClassifier.classify(
            raw_query=q,
            resolved_query=q,
            intent="DOCUMENT_QA"
        )
        assert plan.depth == exp_depth, f"[{q}] Expected depth={exp_depth}, got {plan.depth}"
        assert plan.format == exp_fmt, f"[{q}] Expected format={exp_fmt}, got {plan.format}"
        assert plan.visual == exp_vis, f"[{q}] Expected visual={exp_vis}, got {plan.visual}"
        assert plan.skip_followup_question == exp_skip, f"[{q}] Expected skip_followup={exp_skip}, got {plan.skip_followup_question}"


def test_query_understanding_attaches_pre_gen_plan():
    """Verify QueryUnderstanding integrates PreGenerationClassifier and sets pre_gen_plan."""
    raw = "briefly list the main causes of inflation in bullet points"
    meta = QueryUnderstanding.analyze_query(
        raw_query=raw,
        resolved_query=raw,
        conversation_history=[],
    )

    assert meta.pre_gen_plan is not None
    assert meta.pre_gen_plan.depth == "short"
    assert meta.pre_gen_plan.format == "bullets"
    assert meta.pre_gen_plan.visual == "none"
    assert meta.visual_modality == "none"


def test_generator_hard_constraints_injection_in_prompts():
    """Verify TeachingAgent injects PRE-GENERATION HARD CONSTRAINTS into prompt block."""
    meta = QueryMetadata(
        raw_query="just the answer, in a table",
        normalized_query="just the answer, in a table",
        resolved_query="just the answer, in a table",
        intent="PROBLEM_SOLVING",
        pre_gen_plan=PreGenerationPlan(
            depth="answer_only",
            format="table",
            visual="none",
            skip_followup_question=True,
            reasoning="Rule-based: answer_only forces visual=none and skip_followup=true."
        )
    )
    bundle = ContextBundle(topic_title="Mathematics")
    sys_prompt, user_prompt = TeachingAgent._build_prompts(meta, bundle)

    assert "=== PRE-GENERATION HARD CONSTRAINTS (MANDATORY TO OBEY) ===" in sys_prompt
    assert "DEPTH CONSTRAINT [answer_only]" in sys_prompt
    assert "FORMAT CONSTRAINT [table]" in sys_prompt
    assert "VISUAL CONSTRAINT [none]" in sys_prompt
    assert "INTERACTIVE CHECKPOINT CONSTRAINT" in sys_prompt


def test_contract_enforcement_skips_checkpoint_for_answer_only():
    """Verify _enforce_response_contract skips adding checkpoint when pre_gen_plan depth is answer_only."""
    meta = QueryMetadata(
        raw_query="solve 2x + 5 = 15",
        normalized_query="solve 2x + 5 = 15",
        resolved_query="solve 2x + 5 = 15",
        intent="PROBLEM_SOLVING",
        pre_gen_plan=PreGenerationPlan(
            depth="answer_only",
            format="prose",
            visual="none",
            skip_followup_question=True
        )
    )

    response_text = "x = 5"
    cleaned = TeachingAgent._enforce_response_contract(response_text, "Algebra", meta)

    assert cleaned == "x = 5"
    assert "### 💡 Interactive Checkpoint" not in cleaned
