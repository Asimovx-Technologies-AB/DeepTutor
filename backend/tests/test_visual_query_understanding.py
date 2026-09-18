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
        visual_diagram_type="flowchart_td",
        visual_prompt_focus="Classification of forest types in India",
    )
    bundle = ContextBundle(topic_title="Geography")
    sys_prompt, user_prompt = TeachingAgent._build_prompts(meta, bundle)

    assert "COGNITIVE VISUAL & DIAGRAM GENERATION RULES" in sys_prompt or "MERMAID" in sys_prompt
    assert "```mermaid" in user_prompt or "Mermaid" in user_prompt


def test_teaching_agent_prompt_injection_svg():
    """Verify that TeachingAgent injects SVG directives when visual_modality is svg."""
    meta = QueryMetadata(
        raw_query="draw a diagram of an atom",
        normalized_query="draw a diagram of an atom",
        resolved_query="draw a diagram of an atom",
        intent="EXPLANATION",
        visual_modality="svg",
        visual_diagram_type="svg",
        visual_prompt_focus="Diagram of an atom with protons, neutrons, electrons",
    )
    bundle = ContextBundle(topic_title="Physics")
    sys_prompt, user_prompt = TeachingAgent._build_prompts(meta, bundle)

    assert "INLINE SVG DIAGRAM" in sys_prompt
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
        visual_diagram_type="svg",
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


def test_visual_query_with_figure_includes_single_paragraph_and_breakdown():
    """Verify that visual queries with figure request prompt for diagram, single explanation paragraph, and visual breakdown."""
    meta = QueryMetadata(
        raw_query="what is Circles and Angle with a figure",
        normalized_query="what is Circles and Angle with a figure",
        resolved_query="what is Circles and Angle with a figure",
        intent="EXPLANATION",
        visual_modality="svg",
        visual_diagram_type="svg",
        visual_prompt_focus="Circle with central angle and inscribed angle subtended by the same arc",
    )
    bundle = ContextBundle(topic_title="Circle Geometry")
    sys_prompt, user_prompt = TeachingAgent._build_prompts(meta, bundle)

    assert "Inline SVG vector diagram" in user_prompt
    assert "ONE simple, intuitive explanation in a single concise paragraph" in user_prompt
    assert "#### 🔍 Visual Breakdown (How to Read this Diagram)" in user_prompt
    assert "Interactive Checkpoint" in user_prompt

    from app.tutoring.validation.validator import AnswerValidator

    response_text = (
        "```svg\n"
        "<svg viewBox=\"0 0 650 350\" xmlns=\"http://www.w3.org/2000/svg\" class=\"w-full\">\n"
        "<circle cx=\"325\" cy=\"175\" r=\"120\" fill=\"none\" stroke=\"#64748B\" stroke-dasharray=\"4\" />\n"
        "</svg>\n"
        "```\n\n"
        "In circle geometry, the Inscribed Angle Theorem establishes that an angle subtended at the center of a circle "
        "is always twice the angle subtended by the same arc at any point on the circle's circumference.\n\n"
        "#### 🔍 Visual Breakdown (How to Read this Diagram)\n"
        "- 🔵 **Center Point ($O$) and Radii**: The red dot at the center connected by blue lines to points $A$ and $B$, forming the central angle ($2x^\\circ$).\n"
        "- 🟢 **The Arc ($AB$)**: The highlighted green arc along the edge of the circle subtending both angles.\n"
        "- 🟠 **Angle at Circumference ($P$)**: The angle on the circle ($x^\\circ$) which is exactly half the central angle.\n"
        "- 🎯 **Key Insight**: An arc subtends twice the angle at the center as it does at any point on the remaining circumference.\n\n"
        "### 💡 Interactive Checkpoint\n"
        "If the central angle measures 100 degrees, what is the measure of the angle subtended at the circumference by the same arc?"
    )

    validation = AnswerValidator.validate_response(response_text, bundle)
    assert validation.is_valid is True
    assert validation.pedagogy_score >= 0.85


def test_teaching_agent_missing_table_anti_hallucination():
    """Verify that TeachingAgent alerts for missing table and demands clarification rather than hallucination."""
    meta = QueryMetadata(
        raw_query="solve table 9.4 on page 200",
        normalized_query="solve table 9.4 on page 200",
        resolved_query="solve table 9.4 on page 200",
        intent="PROBLEM_SOLVING",
        referenced_page=200,
        referenced_table="Table 9.4",
    )
    bundle = ContextBundle(
        topic_title="Mathematics",
        missing_table_requested=True,
        requested_table_name="Table 9.4",
        retrieved_chunks=[],
        related_tables=[],
    )
    sys_prompt, user_prompt = TeachingAgent._build_prompts(meta, bundle)

    assert "STRICT ANTI-HALLUCINATION GUARDRAILS FOR TABLES & FIGURES" in sys_prompt
    assert "TABLE QUERY (TABLE NOT FOUND - STRICT ANTI-HALLUCINATION)" in user_prompt
    assert "DO NOT HALLUCINATE OR INVENT TABLE DATA" in user_prompt
    assert "exact page number" in user_prompt


def test_teaching_agent_topics_overview_mindmap():
    """Verify that TeachingAgent requires an interactive overview diagram for syllabus / main topics."""
    meta = QueryMetadata(
        raw_query="what are the important topics in this syllabus",
        normalized_query="what are the important topics in this syllabus",
        resolved_query="what are the important topics in this syllabus",
        intent="SUMMARY",
        visual_modality="mermaid",
        visual_diagram_type="mindmap",
        visual_prompt_focus="Mindmap of core syllabus pillars",
    )
    bundle = ContextBundle(
        topic_title="Contemporary India II",
        curriculum_topics=["Economy", "Resources", "Ecology", "Agriculture"],
    )
    sys_prompt, user_prompt = TeachingAgent._build_prompts(meta, bundle)

    assert "INTERACTIVE OVERVIEW DIAGRAM" in user_prompt
    assert "```mermaid" in user_prompt
    assert "mindmap" in user_prompt


def test_evolution_query_selects_flowchart_lr_not_mindmap():
    """Verify that sequential/chronological evolution queries yield flowchart_lr, NOT radial mindmap."""
    queries = [
        "explain the evolution of the internet across its 4 phases",
        "phases of the internet with a diagram",
        "timeline and evolution of mobile communication 1G to 5G",
        "steps in the SDLC pipeline",
    ]
    for q in queries:
        meta = QueryUnderstanding.analyze_query(
            raw_query=q,
            resolved_query=q,
            conversation_history=[],
        )
        assert meta.visual_modality == "mermaid"
        assert meta.visual_diagram_type == "flowchart_lr", f"Expected flowchart_lr for '{q}', got {meta.visual_diagram_type}"
        assert meta.visual_diagram_type != "mindmap", f"Sequential evolution must NOT be a mindmap: '{q}'"

    # Verify TeachingAgent enforces horizontal flowchart LR and forbids radial mindmap
    meta = QueryMetadata(
        raw_query="evolution of the internet across 4 phases",
        normalized_query="evolution of the internet across 4 phases",
        resolved_query="evolution of the internet across 4 phases",
        intent="SUMMARY",
        visual_modality="mermaid",
        visual_diagram_type="flowchart_lr",
        visual_prompt_focus="Evolution of the internet across 4 phases",
    )
    bundle = ContextBundle(topic_title="Computer Networks")
    sys_prompt, user_prompt = TeachingAgent._build_prompts(meta, bundle)

    assert "MANDATORY SEQUENTIAL FLOWCHART" in user_prompt
    assert "flowchart LR" in user_prompt
    assert "DO NOT use a radial mindmap" in user_prompt


def test_important_questions_query_selects_concept_graph():
    """Verify that 'important questions' queries trigger a concept relationship graph for student intuition."""
    queries = [
        "give me 5 important questions in machine learning",
        "exam questions for chapter 3",
        "key questions on thermodynamics",
    ]
    for q in queries:
        meta = QueryUnderstanding.analyze_query(
            raw_query=q,
            resolved_query=q,
            conversation_history=[],
        )
        assert meta.visual_modality == "mermaid"
        assert meta.visual_diagram_type == "concept_graph", f"Expected concept_graph for '{q}', got {meta.visual_diagram_type}"

    # Verify TeachingAgent instructs generation of concept relationship graph
    meta = QueryMetadata(
        raw_query="5 important questions on machine learning",
        normalized_query="5 important questions on machine learning",
        resolved_query="5 important questions on machine learning",
        intent="PRACTICE_QUESTIONS",
        question_count=5,
        visual_modality="mermaid",
        visual_diagram_type="concept_graph",
        visual_prompt_focus="Concept relationship network for Machine Learning",
    )
    bundle = ContextBundle(topic_title="Machine Learning")
    sys_prompt, user_prompt = TeachingAgent._build_prompts(meta, bundle)

    assert "CONCEPT RELATIONSHIP GRAPH" in user_prompt
    assert "flowchart TD" in user_prompt
    assert "conceptual network" in user_prompt


def test_sequence_protocol_query_classification():
    """Verify that network protocol and handshake queries yield sequence diagrams."""
    queries = [
        "explain the TCP 3-way handshake protocol",
        "OAuth2 client-server authentication flow",
    ]
    for q in queries:
        meta = QueryUnderstanding.analyze_query(
            raw_query=q,
            resolved_query=q,
            conversation_history=[],
        )
        assert meta.visual_modality == "mermaid"
        assert meta.visual_diagram_type == "sequence", f"Expected sequence for '{q}', got {meta.visual_diagram_type}"


def test_algorithm_queries_select_svg():
    """Verify that algorithm and data structure queries yield rich Inline SVG diagrams."""
    queries = [
        "how does binary search algorithm work",
        "quicksort partitioning algorithm with array states",
        "dijkstra shortest path algorithm",
        "explain gradient descent algorithm",
        "stack and queue data structures operations",
    ]
    for q in queries:
        meta = QueryUnderstanding.analyze_query(
            raw_query=q,
            resolved_query=q,
            conversation_history=[],
        )
        assert meta.visual_modality == "svg", f"Expected svg modality for '{q}', got {meta.visual_modality}"
        assert meta.visual_diagram_type == "svg", f"Expected svg diagram type for '{q}', got {meta.visual_diagram_type}"

    # Verify TeachingAgent generates tailored algorithm SVG directives
    meta = QueryMetadata(
        raw_query="how does binary search algorithm work",
        normalized_query="how does binary search algorithm work",
        resolved_query="how does binary search algorithm work",
        intent="EXPLANATION",
        visual_modality="svg",
        visual_diagram_type="svg",
        visual_prompt_focus="Binary search algorithm with low, mid, high pointers",
    )
    bundle = ContextBundle(topic_title="Computer Science")
    sys_prompt, user_prompt = TeachingAgent._build_prompts(meta, bundle)

    assert "INLINE SVG DIAGRAMS (HIGH PRIORITY FOR ALGORITHMS" in sys_prompt
    assert "ALGORITHM INLINE SVG" in user_prompt
    assert "Visual Breakdown" in user_prompt


def test_pasted_mcq_suppresses_diagrams():
    """Verify that a pasted MCQ with options (e.g. Bagging algorithm) suppresses diagrams and sets is_pasted_mcq=True."""
    mcq_query = (
        "Select the appropriate steps which are followed in a bagging algorithm:\n"
        "1. Bootstrap sample generation\n"
        "2. Weak learner generation\n"
        "3. Training\n"
        "4. Combining weak learners\n"
        "5. None of these\n"
        "Options:\n"
        "A. 1 -> 4\n"
        "B. 1 -> 5\n"
        "C. 2 -> 3 -> 4\n"
        "D. 2 -> 3 -> 5"
    )
    meta = QueryUnderstanding.analyze_query(
        raw_query=mcq_query,
        resolved_query=mcq_query,
        conversation_history=[],
    )

    assert meta.is_pasted_mcq is True, "Expected is_pasted_mcq to be True"
    assert meta.is_batch_questions is False, "MCQ with steps should not be treated as batch questions"
    assert meta.visual_modality == "none", f"Expected 'none' visual modality for pasted MCQ, got '{meta.visual_modality}'"
    assert meta.visual_diagram_type == "none", f"Expected 'none' diagram type for pasted MCQ, got '{meta.visual_diagram_type}'"
    assert meta.intent == "PROBLEM_SOLVING"

    # Verify TeachingAgent generates dedicated MCQ solving instructions with no visuals
    bundle = ContextBundle(topic_title="Machine Learning")
    sys_prompt, user_prompt = TeachingAgent._build_prompts(meta, bundle)

    assert "PASTED MULTIPLE-CHOICE QUESTION (MCQ) SOLVING" in user_prompt
    assert "Prominent Correct Answer" in user_prompt
    assert "Distractor Breakdown" in user_prompt
    assert "STRICT NO-IMAGE RULE" in user_prompt
    assert "Visual aid requested/warranted: no" in user_prompt
    assert "5. VISUAL GENERATION" not in user_prompt


def test_multi_question_batch_suppresses_diagrams():
    """Verify that 2 to 10 pasted questions suppress diagrams and set is_batch_questions=True."""
    batch_query = (
        "1. What is the difference between Bagging and Boosting?\n"
        "2. Why is Random Forest an ensemble method?\n"
        "3. How does out-of-bag error estimation work?\n"
        "4. What is the role of bootstrap sampling in variance reduction?\n"
        "5. When would Boosting overfit compared to Bagging?"
    )
    meta = QueryUnderstanding.analyze_query(
        raw_query=batch_query,
        resolved_query=batch_query,
        conversation_history=[],
    )

    assert meta.is_pasted_mcq is False
    assert meta.is_batch_questions is True, "Expected is_batch_questions to be True"
    assert meta.batch_question_count == 5, f"Expected 5 questions, got {meta.batch_question_count}"
    assert meta.visual_modality == "none", f"Expected 'none' visual modality for batch questions, got '{meta.visual_modality}'"
    assert meta.visual_diagram_type == "none", f"Expected 'none' diagram type for batch questions, got '{meta.visual_diagram_type}'"

    # Verify TeachingAgent generates sequential multi-question prompt without diagrams
    bundle = ContextBundle(topic_title="Machine Learning")
    sys_prompt, user_prompt = TeachingAgent._build_prompts(meta, bundle)

    assert "BATCH MULTI-QUESTION SOLVING" in user_prompt
    assert "### Question 1:" in user_prompt
    assert "STRICT NO-IMAGE RULE" in user_prompt
    assert "Visual aid requested/warranted: no" in user_prompt
    assert "5. VISUAL GENERATION" not in user_prompt


def test_mcq_options_and_batch_checkpoint_preservation():
    """Verify that _enforce_response_contract preserves MCQ options and does not add artificial checkpoints."""
    mcq_meta = QueryMetadata(
        raw_query="Select steps in bagging algorithm... Options: A. 1->4 B. 1->5",
        normalized_query="select steps in bagging algorithm... options: a. 1->4 b. 1->5",
        resolved_query="Select steps in bagging algorithm... Options: A. 1->4 B. 1->5",
        intent="PROBLEM_SOLVING",
        is_pasted_mcq=True,
    )

    mcq_response = (
        "### Bagging Algorithm Analysis\n\n"
        "In a Bagging algorithm, bootstrap samples are drawn with replacement and base models are trained.\n\n"
        "**Correct Answer: Option A (1 -> 4)**\n\n"
        "Options:\n"
        "1. Option A: Correct, covers the complete pipeline.\n"
        "2. Option B: Incorrect, Step 5 is None of these."
    )

    cleaned = TeachingAgent._enforce_response_contract(mcq_response, "Machine Learning", mcq_meta)
    assert "Options:" in cleaned, "MCQ Options should NOT be stripped by menu cleaner"
    assert "Option A" in cleaned
    assert "### 💡 Interactive Checkpoint" not in cleaned, "Exempt queries should not have artificial checkpoints appended"


def test_whole_material_query_scope_and_anti_narrowing():
    """Verify that whole material questions cover all topics and do not collapse onto the previous turn's topic."""
    from app.tutoring.analyzer.resolver import CoreferencePronounResolver

    conv_history = [
        {"role": "user", "content": "Explain bagging in machine learning"},
        {"role": "assistant", "content": "### **Ensemble Learning (Bagging)**\n\nBagging trains multiple models in parallel."},
    ]
    raw_query = "give 10 importent questions from this meterial and its answer also, cover all the topics"

    # Step 1: Pronoun Resolver should not corrupt "this meterial" with "Ensemble Learning (Bagging)"
    resolved = CoreferencePronounResolver.resolve(raw_query, conv_history)
    assert "Ensemble Learning (Bagging) meterial" not in resolved["resolved_query"]
    assert resolved["meta"].get("scope") == "global"

    # Step 2: QueryUnderstanding should detect global_material scope and not leak target_topic
    meta = QueryUnderstanding.analyze_query(
        raw_query=raw_query,
        resolved_query=resolved["resolved_query"],
        conversation_history=conv_history,
    )
    assert meta.query_scope == "global_material", f"Expected global_material, got {meta.query_scope}"
    assert meta.target_topic is None, f"Expected target_topic=None for whole material, got {meta.target_topic}"
    assert meta.format_directives.get("cover_all_topics") is True
    assert meta.visual_diagram_type == "concept_graph"
    assert "entire study material curriculum" in (meta.visual_prompt_focus or "").lower()

    # Step 3: TeachingAgent prompt should instruct the LLM to cover all topics across curriculum
    bundle = ContextBundle(
        topic_title="Ensemble Learning",
        curriculum_topics=["Supervised Learning", "Linear Regression", "Decision Trees", "Ensemble Methods", "Neural Networks"],
    )
    sys_prompt, user_prompt = TeachingAgent._build_prompts(meta, bundle)

    assert "COMPREHENSIVE PRACTICE QUESTIONS (WHOLE MATERIAL - ALL TOPICS)" in user_prompt
    assert "CRITICAL ANTI-NARROWING RULE" in user_prompt
    assert "CONCEPT RELATIONSHIP GRAPH" in user_prompt
    assert "Entire Study Material" in user_prompt


def test_pronoun_resolver_does_not_hijack_container_specifiers():
    """Verify that phrases like 'this material', 'this document', 'this textbook' are never replaced with prior topics."""
    from app.tutoring.analyzer.resolver import CoreferencePronounResolver

    conv_history = [
        {"role": "user", "content": "Tell me about Support Vector Machines"},
        {"role": "assistant", "content": "### **Support Vector Machines (SVM)**\n\nSVM finds the optimal hyperplane."},
    ]

    queries = [
        "give 5 questions from this material",
        "what are the main topics in this document?",
        "summarize this textbook",
        "how many chapters in this syllabus?",
    ]

    for q in queries:
        res = CoreferencePronounResolver.resolve(q, conv_history)
        assert "Support Vector Machines (SVM) material" not in res["resolved_query"]
        assert "Support Vector Machines (SVM) document" not in res["resolved_query"]
        assert "Support Vector Machines (SVM) textbook" not in res["resolved_query"]
        assert "Support Vector Machines (SVM) syllabus" not in res["resolved_query"]


def test_ambiguous_question_request_triggers_clarification():
    """Verify that a generic question request with an active chat topic prompts the user for clarification."""
    conv_history = [
        {"role": "user", "content": "What is Backpropagation?"},
        {"role": "assistant", "content": "### **Convolutional Neural Networks**\n\nCNNs use convolutions for feature maps."},
    ]
    ambiguous_query = "give me 5 questions"

    meta = QueryUnderstanding.analyze_query(
        raw_query=ambiguous_query,
        resolved_query=ambiguous_query,
        conversation_history=conv_history,
    )

    assert meta.query_scope == "ambiguous_scope", f"Expected ambiguous_scope, got {meta.query_scope}"
    assert meta.scope_clarification_prompt is not None
    assert "Convolutional Neural Networks" in meta.scope_clarification_prompt
    assert "all topics" in meta.scope_clarification_prompt.lower()

    # Verify TeachingAgent generates a clarification prompt and suppresses visual generation
    bundle = ContextBundle(topic_title="Convolutional Neural Networks")
    sys_prompt, user_prompt = TeachingAgent._build_prompts(meta, bundle)

    assert "CLARIFICATION ON SCOPE NEEDED" in user_prompt
    assert "Visual aid requested/warranted: no" in user_prompt
    assert "5. VISUAL GENERATION" not in user_prompt


def test_explicit_single_topic_query_preserves_specific_scope():
    """Verify that an explicit single-topic question request stays specific and targets that topic."""
    conv_history = [
        {"role": "user", "content": "Explain Bagging"},
        {"role": "assistant", "content": "### **Ensemble Learning**\n\nBagging is an ensemble technique."},
    ]
    topic_query = "give me 5 questions on Decision Trees"

    meta = QueryUnderstanding.analyze_query(
        raw_query=topic_query,
        resolved_query=topic_query,
        conversation_history=conv_history,
    )

    assert meta.query_scope == "specific_topic"
    assert meta.target_topic == "Decision Trees"


def test_topic_explanation_and_query_specificity_contract():
    """Verify that TeachingAgent and InteractiveTeacher prompts enforce simple explanation, bulleted subtopics, and query-specific constraints."""
    from app.tutoring.teaching.agent import _RESPONSE_CONTRACT
    from app.tutoring.teaching.interactive_teacher import _SUBTOPIC_TEACHER_SYSTEM_PROMPT, _QUESTION_ANSWERER_SYSTEM_PROMPT

    # 1. Check _RESPONSE_CONTRACT in agent.py
    assert "DEFINITION & TOPIC EXPLANATION" in _RESPONSE_CONTRACT
    assert "ONE Short Paragraph" in _RESPONSE_CONTRACT
    assert "Key Points (bullet list)" in _RESPONSE_CONTRACT
    assert "NO UNREQUESTED FLUFF" in _RESPONSE_CONTRACT
    assert "BREVITY IS KEY" in _RESPONSE_CONTRACT
    assert "STRICT QUERY-SPECIFIC FOCUS" in _RESPONSE_CONTRACT

    # 2. Check interactive teacher prompts
    assert "Explain the subtopic simply and clearly" in _SUBTOPIC_TEACHER_SYSTEM_PROMPT
    assert "concise bullet points" in _SUBTOPIC_TEACHER_SYSTEM_PROMPT
    assert "ANSWER DIRECTLY & SPECIFICALLY" in _QUESTION_ANSWERER_SYSTEM_PROMPT





