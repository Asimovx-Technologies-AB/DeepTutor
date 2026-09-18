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


def test_question_index_resolution_across_multiple_intervening_turns():
    """Verify that question index resolution finds questions even after multiple intervening turns."""
    conv_history = [
        {"role": "user", "content": "give me 3 questions on thermodynamics"},
        {
            "role": "assistant",
            "content": (
                "### 📝 Practice Questions: Thermodynamics\n\n"
                "1. **Zeroth Law**: State the zeroth law of thermodynamics.\n"
                "2. **Carnot Engine**: Calculate the theoretical efficiency of a Carnot cycle operating between 500K and 300K.\n"
                "3. **Entropy**: Explain why the entropy of an isolated system never decreases."
            ),
        },
        {"role": "user", "content": "can you tell me a fun fact about physics?"},
        {"role": "assistant", "content": "Did you know that hot water can freeze faster than cold water under certain conditions? This is called the Mpemba effect."},
        {"role": "user", "content": "that is so cool!"},
        {"role": "assistant", "content": "It really is! Physics is full of surprising phenomena."},
    ]

    raw_query = "explain question 2"
    res = CoreferencePronounResolver.resolve(raw_query, conv_history)

    assert "Carnot Engine" in res["resolved_query"] or "Carnot cycle" in res["resolved_query"]
    assert res["meta"].get("referenced_question_index") == 2
    assert "Carnot cycle" in res["meta"].get("referenced_question_text")
    assert "Thermodynamics" in res["meta"].get("referenced_question_text")


def test_question_index_resolution_with_heading_filter():
    """Verify that when the user specifies a topic, question resolution targets that specific question set."""
    conv_history = [
        {"role": "user", "content": "questions on isomerism"},
        {
            "role": "assistant",
            "content": (
                "### 📝 Practice Questions: Isomerism\n\n"
                "1. **Structural Isomers**: Differentiate chain and position isomerism.\n"
                "2. **Stereoisomerism**: Explain optical activity in lactic acid."
            ),
        },
        {"role": "user", "content": "questions on alkanes"},
        {
            "role": "assistant",
            "content": (
                "### 📝 Practice Questions: Alkanes\n\n"
                "1. **Combustion**: Write the balanced combustion reaction for propane.\n"
                "2. **Halogenation**: Describe free-radical chlorination of methane."
            ),
        },
    ]

    raw_query = "what is the answer to question 2 from isomerism?"
    res = CoreferencePronounResolver.resolve(raw_query, conv_history)

    assert "Stereoisomerism" in res["resolved_query"] or "lactic acid" in res["resolved_query"]
    assert res["meta"].get("referenced_question_index") == 2
    assert "lactic acid" in res["meta"].get("referenced_question_text")


def test_practice_questions_heading_enforcement():
    """Verify that _enforce_response_contract ensures the practice questions heading is present."""
    meta = QueryMetadata(
        raw_query="give me questions on optics",
        normalized_query="give me questions on optics",
        resolved_query="give me questions on optics",
        intent="PRACTICE_QUESTIONS",
    )
    raw_content = "1. **Snell's Law**: State Snell's law of refraction.\n2. **Total Internal Reflection**: Define critical angle."
    formatted = TeachingAgent._enforce_response_contract(raw_content, "Optics", meta)

    assert "### 📝 Practice Questions: Optics" in formatted
    assert "1. **Snell's Law**" in formatted

