import pytest
from app.tutoring.analyzer.resolver import ReferenceResolver, CoreferencePronounResolver
from app.tutoring.analyzer.understanding import QueryUnderstanding
from app.tutoring.teaching.agent import TeachingAgent
from app.schemas.tutoring import ContextBundle, QueryMetadata


def test_question_index_resolution_from_history():
    """Verify that 'explain question 2' extracts the exact Question 2 statement from dialogue history."""
    conv_history = [
        {"role": "user", "content": "give me 5 questions from this material"},
        {
            "role": "assistant",
            "content": (
                "Here are 5 questions from your PDF:\n\n"
                "1. What is the difference between Supervised and Unsupervised Learning?\n"
                "2. Explain how Backpropagation computes gradients using the chain rule.\n"
                "3. Describe the hyperplane in Support Vector Machines.\n"
                "4. How does Bagging reduce variance in decision trees?\n"
                "5. What is the role of dropout in deep neural networks?"
            ),
        },
    ]

    raw_query = "explain question 2"
    res = CoreferencePronounResolver.resolve(raw_query, conv_history)

    assert "Explain how Backpropagation computes gradients using the chain rule" in res["resolved_query"]
    assert res["meta"].get("referenced_question_index") == 2
    assert "Explain how Backpropagation computes gradients using the chain rule" in res["meta"].get("referenced_question_text")


def test_question_index_resolution_word_number():
    """Verify that 'explain second question' or 'answer Q3' extracts the exact question statement."""
    conv_history = [
        {"role": "user", "content": "give me important questions"},
        {
            "role": "assistant",
            "content": (
                "### 5 Important Questions\n\n"
                "1. Define overfitting.\n"
                "2. Compare L1 and L2 regularization techniques.\n"
                "3. What is the cost function of Logistic Regression?"
            ),
        },
    ]

    raw_query = "explain second question"
    res = CoreferencePronounResolver.resolve(raw_query, conv_history)

    assert "Compare L1 and L2 regularization techniques" in res["resolved_query"]
    assert res["meta"].get("referenced_question_index") == 2


def test_teaching_agent_prompt_injection_for_referenced_question():
    """Verify that TeachingAgent injects dedicated instructions for explaining the referenced question."""
    meta = QueryMetadata(
        raw_query="explain question 2",
        normalized_query="explain question 2",
        resolved_query="explain question 2: Explain how Backpropagation computes gradients using the chain rule.",
        intent="EXPLANATION",
        format_directives={
            "referenced_question_index": 2,
            "referenced_question_text": "Explain how Backpropagation computes gradients using the chain rule.",
        },
    )
    bundle = ContextBundle(
        topic_title="Backpropagation",
        conversation_history=[
            {"role": "user", "content": "give me 5 questions"},
            {"role": "assistant", "content": "1. What is AI?\n2. Explain how Backpropagation computes gradients using the chain rule."},
        ],
    )

    sys_prompt, user_prompt = TeachingAgent._build_prompts(meta, bundle)

    assert "EXPLAINING SPECIFIC PREVIOUS QUESTION #2" in user_prompt
    assert "Explain how Backpropagation computes gradients using the chain rule" in user_prompt
    assert "Question Statement" in user_prompt
