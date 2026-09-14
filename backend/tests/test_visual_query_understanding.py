import pytest
from app.tutoring.analyzer.understanding import QueryUnderstanding
from app.schemas.tutoring import QueryMetadata, ContextBundle
from app.tutoring.teaching.agent import TeachingAgent


def test_visual_query_classification_mermaid():
    """Verify that hierarchical, process, or classification queries yield visual_modality='mermaid'."""
    queries = [
        "draw a flowchart of the water cycle",
        "show a flowchart of how government classifies forests in India",
        "give me a mindmap of machine learning algorithms",
        "classification of forest resources in India with a chart",
    ]
    for q in queries:
        meta = QueryUnderstanding.analyze_query(
            raw_query=q,
            resolved_query=q,
            conversation_history=[],
        )
        assert meta.visual_modality == "mermaid", f"Failed for query: {q}, got {meta.visual_modality}"
        assert meta.visual_prompt_focus is not None


def test_visual_query_classification_svg():
    """Verify that spatial, technical, geometric, or image queries yield visual_modality='svg'."""
    queries = [
        "draw an image of a plant cell with labels",
        "show me a diagram of a right-angled triangle showing Pythagoras theorem",
        "draw a vector diagram of forces acting on an inclined plane",
        "illustrate the structure of an atom with an image",
    ]
    for q in queries:
        meta = QueryUnderstanding.analyze_query(
            raw_query=q,
            resolved_query=q,
            conversation_history=[],
        )
        assert meta.visual_modality == "svg", f"Failed for query: {q}, got {meta.visual_modality}"
        assert meta.visual_prompt_focus is not None


def test_non_visual_query_classification():
    """Verify that standard conceptual or QA queries yield visual_modality='none'."""
    queries = [
        "what is an adverb?",
        "define momentum in one sentence",
        "solve 2x + 5 = 15",
    ]
    for q in queries:
        meta = QueryUnderstanding.analyze_query(
            raw_query=q,
            resolved_query=q,
            conversation_history=[],
        )
        assert meta.visual_modality == "none", f"Expected none for query: {q}, got {meta.visual_modality}"


def test_teaching_agent_prompt_injection_mermaid():
    """Verify that TeachingAgent injects Mermaid directives when visual_modality is mermaid."""
    meta = QueryMetadata(
        raw_query="flowchart of forest types",
        normalized_query="flowchart of forest types",
        resolved_query="flowchart of forest types",
        intent="EXPLANATION",
        visual_modality="mermaid",
        visual_prompt_focus="Classification of forest types in India",
    )
    bundle = ContextBundle(topic_title="Geography")
    sys_prompt, user_prompt = TeachingAgent._build_prompts(meta, bundle)

    assert "MERMAID.JS VISUALIZATIONS" in sys_prompt
    assert "```mermaid" in user_prompt or "Mermaid diagram" in user_prompt


def test_teaching_agent_prompt_injection_svg():
    """Verify that TeachingAgent injects SVG directives when visual_modality is svg."""
    meta = QueryMetadata(
        raw_query="draw a diagram of an atom",
        normalized_query="draw a diagram of an atom",
        resolved_query="draw a diagram of an atom",
        intent="EXPLANATION",
        visual_modality="svg",
        visual_prompt_focus="Diagram of an atom with protons, neutrons, electrons",
    )
    bundle = ContextBundle(topic_title="Physics")
    sys_prompt, user_prompt = TeachingAgent._build_prompts(meta, bundle)

    assert "INLINE SVG DIAGRAMS" in sys_prompt
    assert "Inline SVG vector diagram" in user_prompt
    assert "Visual Breakdown" in user_prompt


def test_teaching_agent_prompt_includes_visual_breakdown_contract():
    """Verify that TeachingAgent system prompt explicitly requires Visual Breakdown below diagrams."""
    meta = QueryMetadata(
        raw_query="draw SVM hyperplane",
        normalized_query="draw SVM hyperplane",
        resolved_query="draw SVM hyperplane",
        intent="EXPLANATION",
        visual_modality="svg",
        visual_prompt_focus="Support Vector Machine maximum margin hyperplane",
    )
    bundle = ContextBundle(topic_title="Machine Learning")
    sys_prompt, user_prompt = TeachingAgent._build_prompts(meta, bundle)

    assert "MANDATORY VISUAL BREAKDOWN" in sys_prompt
    assert "#### 🔍 Visual Breakdown (How to Read this Diagram)" in sys_prompt
    assert "Visual Breakdown" in user_prompt


def test_answer_validator_visual_breakdown_scoring():
    """Verify that AnswerValidator awards pedagogy score for visual breakdowns."""
    from app.tutoring.validation.validator import AnswerValidator

    response_with_breakdown = (
        "### Support Vector Machines\n\n"
        "In simple terms, an SVM finds the widest decision street between two classes.\n\n"
        "```svg\n"
        "<svg viewBox=\"0 0 600 350\" xmlns=\"http://www.w3.org/2000/svg\" class=\"w-full\">\n"
        "<line x1=\"50\" y1=\"300\" x2=\"550\" y2=\"50\" stroke=\"#EF4444\" stroke-width=\"3\" />\n"
        "</svg>\n"
        "```\n\n"
        "#### 🔍 Visual Breakdown (How to Read this Diagram)\n"
        "- 🔴 **Red Line (Hyperplane)**: The optimal decision boundary separating the two classes.\n"
        "- 🔵 **Blue Dots**: Class A data points.\n"
        "- 🟢 **Green Dots**: Class B data points.\n\n"
        "### 💡 Interactive Checkpoint\n"
        "What happens to the margin if we remove a non-support vector point?"
    )

    bundle = ContextBundle(topic_title="Machine Learning")
    result = AnswerValidator.validate_response(response_with_breakdown, bundle)

    assert result.is_valid is True
    assert result.validation_status == "PASS"
    assert result.pedagogy_score >= 0.8

