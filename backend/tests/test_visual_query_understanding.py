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
