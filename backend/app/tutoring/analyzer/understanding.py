import re
import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from app.schemas.tutoring import QueryMetadata, PreGenerationPlan
from app.services.llm_service import default_llm_service
from app.tutoring.analyzer.pre_gen_classifier import PreGenerationClassifier

logger = logging.getLogger(__name__)

_UNDERSTANDING_SYSTEM_PROMPT = """You are the cognitive Query Understanding & Reasoning module for DeepTutor, an elite AI Professor.
Analyze the student's message in the context of the recent study dialogue and return ONLY a valid JSON object.

Intent Taxonomy:
- "PRACTICE_QUESTIONS": Student asks for questions, exercises, or exam preparation problems to study/practice (e.g. "give me 5 questions in svm", "i have exam tomorrow give me questions on chapter 2", "only need questions", "practice questions").
- "STUDY_NOTES": Student explicitly asks for study notes, revision notes, topic notes, cheat sheets, or a study guide (e.g. "give me notes", "make study notes", "prepare revision notes for chapter 2", "summary notes"). CRITICAL: NEVER classify requests for notes as "QUIZ" or flashcards! Flashcards ("QUIZ") are ONLY for explicit requests like "quiz me", "flashcard deck", "make an interactive test".
- "QUIZ": ONLY when the student explicitly wants an interactive multiple-choice quiz or flashcard cards widget (e.g. "quiz me", "generate flashcard deck", "make an interactive quiz", "give me an MCQ test").
- "EXPLANATION": Student asks to explain, define, or teach a concept (e.g. "what is SVM?", "how does backprop work?").
- "COMPARISON": Comparing two concepts (e.g. "SVM vs Random Forest", "difference between X and Y").
- "PROBLEM_SOLVING": Asking to solve a problem, compute, or derive a formula.
- "SUMMARY": Summary, roadmap, or syllabus overview.
- "CASUAL": Greetings or pleasantries.
- "FOLLOW_UP": Directly asking about, correcting, or following up on previous assistant responses.
- "DOCUMENT_QA": General question grounded in textbook facts.

Critical Reasoning Rules:
1. DIALOGUE CONTINUITY: If the query is short or implicit (e.g. "only need questions", "give me 3 more", "solve question 2"), identify the active concept from the recent conversation history (e.g. "Support Vector Machines (SVM)").
2. USER CONSTRAINTS & FORMAT:
   - If the student specifies "only need questions", "just questions", "no answers", or wants to test themselves, set "questions_only": true and "include_answers": false.
   - If the student requests explanations, walk-throughs, or solutions, set "questions_only": false and "include_answers": true.
3. COUNT: Extract question count if specified, or default to 5 for practice questions if not specified.
4. PAGE & TABLE REFERENCES:
   - If the query mentions a specific page (e.g. "page 22", "page number 22", "on page 5", "p. 10"), extract "referenced_page": <integer>.
   - If the query mentions a table (e.g. "table 1.2", "solve the table in page 22", "table 3"), extract "referenced_table": "<table name or 'table'>" and set "intent": "PROBLEM_SOLVING" with format_directives {"solve_table": true, "include_complete_table": true}.
5. VISUAL AID & DIAGRAM REASONING:
   Analyze whether the student asks for or strongly benefits from an image, diagram, chart, or visualization.
   PRIORITIZE RICH INLINE SVG DIAGRAMS FOR ALGORITHMS, DATA STRUCTURES & TECHNICAL ILLUSTRATIONS:
   - "svg" (visual_modality: "svg"): HIGHEST PRIORITY FOR ALGORITHMS & DATA STRUCTURES (e.g. "Binary search with low/mid/high pointers", "Quicksort partition step", "Merge sort recursion tree", "Dijkstra shortest path weights", "BFS/DFS exploration", "Gradient descent loss curve", "Neural network layers & weights", "Dynamic programming table", "Array, Stack, Queue, Linked List, Heap, Hashmap, Tree visualizations"). ALSO for spatial, physical, anatomical, geometric, optical, or mathematical coordinate systems (e.g. "Plant cell anatomy", "Forces on an inclined plane", "Right-angled triangle Pythagoras theorem", "Ray optics"). SVG gives rich colored boxes, pointers, and memory states that standard text boxes cannot match.
   - "flowchart_lr" (visual_modality: "mermaid"): For non-algorithmic chronological progressions, evolutions across historical eras or phases, pipelines, and life-cycles (e.g. "Evolution of the Internet (Phases 1-4)", "SDLC stages", "Photosynthesis stages"). NEVER use a mindmap for sequential phases.
   - "concept_graph" (visual_modality: "mermaid"): For IMPORTANT QUESTIONS, EXAM TOPICS, or TOPIC MASTERY queries. When student asks for important questions or key concepts, generate a conceptual relationship graph (flowchart TD/graph TD) mapping core topics and question themes.
   - "sequence" (visual_modality: "mermaid"): For multi-actor communication, network protocols, client-server exchanges (e.g. "TCP 3-way handshake", "OAuth2 authorization flow", "DNS resolution").
   - "state_diagram" (visual_modality: "mermaid"): For finite state machines, state lifecycles, and status transitions (e.g. "Process lifecycle states", "Thread states").
   - "mindmap" (visual_modality: "mermaid"): ONLY for broad, non-sequential syllabus pillars, chapter outlines, or unranked brainstorming where order does not matter.
   - "flowchart_td" (visual_modality: "mermaid"): For hierarchical classifications and organizational trees (e.g. "Classification of Forest Types in India").
   - "none" (visual_modality: "none"): For pure text definitions, simple arithmetic, or casual greetings.
    If not "none", provide "visual_prompt_focus" detailing what to visualize (e.g. "Step-by-step vector illustration of Binary Search with low, mid, high pointers", "Horizontal flowchart of Internet evolution across Phases 1 to 4").
6. PASTED MULTIPLE-CHOICE QUESTIONS (MCQS) & BATCH QUESTIONS (STRICT VISUAL SUPPRESSION):
   - If the student pastes an external multiple-choice question with options (e.g. A, B, C, D or Options: A. ... B. ...):
     Set "is_pasted_mcq": true, "intent": "PROBLEM_SOLVING", "visual_modality": "none", "visual_diagram_type": "none".
     MCQs require step-by-step reasoning, bold correct answer identification, and distractor breakdown — NEVER visual diagrams.
   - If the student pastes a batch of 2 or more questions to solve at once (e.g. 1. ... 2. ... or Q1 ... Q2 ...):
     Set "is_batch_questions": true, "batch_question_count": <count>, "intent": "PROBLEM_SOLVING", "visual_modality": "none", "visual_diagram_type": "none".
     Multi-question batches require full sequential answers for each question — NEVER visual diagrams.
7. QUERY SCOPE REASONING (WHOLE MATERIAL VS. CHAT TOPIC VS. AMBIGUITY):
   - "global_material": When the student asks for questions, summary, or topics from the ENTIRE document or across all topics (e.g. "from this material", "from the whole material", "cover all the topics", "from all chapters", "entire syllabus", "overall"):
     Set "query_scope": "global_material", "target_topic": null.
     CRITICAL: NEVER lock onto the previous discussion topic (e.g. Ensemble Learning) when the student asked to cover all topics or the whole material!
   - "current_topic": When the student explicitly continues the ongoing discussion topic (e.g. "tell me more about this", "step 2 of this algorithm", "give 3 more questions on bagging").
   - "specific_topic": When the student explicitly introduces or names a distinct topic (e.g. "what is SVM?", "questions on Random Forest").
   - "ambiguous_scope": When the student asks an open request (e.g. "give me 5 questions", "quiz me", "important questions") immediately after discussing a specific topic, and it is ambiguous whether they want questions on that specific topic or from the entire study material:
     Set "query_scope": "ambiguous_scope", and formulate "scope_clarification_prompt" asking whether they want questions on the previous topic or across all topics.
8. CONTEXT SOURCE REASONING (DIALOGUE HISTORY VS. STUDY MATERIAL):
   - "dialogue_history": Set "context_source": "dialogue_history" when the student asks about the chat conversation itself, previous tutor explanations, or past turns (e.g. "summarize our chat", "what did we discuss before?", "repeat your previous answer", "explain line 2 of what you said").
   - "study_material": Set "context_source": "study_material" for queries asking about document textbook concepts, formulas, algorithms, exam practice problems, or general course facts.

Output JSON format:
{
  "intent": "PRACTICE_QUESTIONS" | "QUIZ" | "STUDY_NOTES" | "EXPLANATION" | "COMPARISON" | "PROBLEM_SOLVING" | "SUMMARY" | "CASUAL" | "FOLLOW_UP" | "DOCUMENT_QA",
  "context_source": "dialogue_history" | "study_material",
  "target_topic": "The exact subject concept (e.g. 'Support Vector Machines (SVM)'). Ground in conversation history if query is an implicit follow-up, BUT set to null if query_scope is 'global_material'.",
  "query_scope": "global_material" | "current_topic" | "specific_topic" | "ambiguous_scope",
  "scope_clarification_prompt": null, // string clarification question if scope is ambiguous, or null
  "question_count": 5, // integer count if requested or applicable, or null
  "referenced_page": 22, // integer page number if user mentioned a page, or null
  "referenced_table": "Table 1.2", // string table name or "table" if user mentioned a table, or null
  "visual_modality": "none" | "mermaid" | "svg",
  "visual_diagram_type": "none" | "flowchart_lr" | "flowchart_td" | "concept_graph" | "sequence" | "state_diagram" | "mindmap" | "svg",
  "visual_prompt_focus": "Description of the visual to generate, or null",
  "is_pasted_mcq": true | false,
  "is_batch_questions": true | false,
  "batch_question_count": null, // integer count if batch of questions, or null
  "format_directives": {
    "questions_only": true | false,
    "include_answers": true | false,
    "solve_table": true | false,
    "include_complete_table": true | false,
    "special_instructions": "Clear instruction for the teaching agent"
  },
  "entities": ["SVM", "Support Vector Machines"],
  "needs_latex": false,
  "needs_table": false,
  "resolved_query": "Clean, focused academic query for textbook search"
}"""


class QueryUnderstanding:
    """
    Stage 4: Query Understanding.
    - LLM-powered Intent Detection, Topic Extraction & Format Reasoning
    - Multi-turn conversation awareness for implicit follow-ups
    - Differentiates Practice Questions vs. Interactive Quizzes
    - Extracts student constraints (e.g. questions only vs. full solutions)
    - Fallback heuristic analysis for offline resilience
    """

    CASUAL_PATTERNS = [
        re.compile(r"^(?:hi|hello|hey|good\s+(?:morning|afternoon|evening)|greetings|who\s+are\s+you)\b", re.IGNORECASE),
        re.compile(
            r"^(?:thanks|thank\s+you|thankyou|awesome|cool|bye|goodbye|"
            r"ok\s+thanks|ok\s+thank\s+you|ok\s+thankyou|okay\s+thanks|okay\s+thank\s+you|okay\s+thankyou|"
            r"got\s+it|makes\s+sense|understood|all\s+good|sounds\s+good|perfect\s+thanks|perfect\s+thank\s+you)\b",
            re.IGNORECASE
        ),
    ]

    SUMMARY_PATTERNS = [
        re.compile(r"\b(?:summarize|summary|overview|key\s+takeaways|briefly\s+describe)\b", re.IGNORECASE)
    ]

    QUIZ_PATTERNS = [
        re.compile(r"\b(?:quiz\s+me|generate\s+a\s+quiz|create\s+a\s+quiz|mcq\s+quiz|flashcards?|flshcards?)\b", re.IGNORECASE)
    ]

    PRACTICE_QUESTIONS_PATTERNS = [
        re.compile(r"\b(?:give\s+me|show\s+me|prepare|create|make)?\s*(?:\d+\s+)?(?:questions?|practice\s+questions?|problems?)\b", re.IGNORECASE),
        re.compile(r"\b(?:only\s+(?:need\s+)?questions?|just\s+questions?)\b", re.IGNORECASE)
    ]

    COMPARISON_PATTERNS = [
        re.compile(r"\b(?:compare|difference\s+between|versus|vs\.?|contrast)\b", re.IGNORECASE)
    ]

    PROBLEM_SOLVING_PATTERNS = [
        re.compile(r"\b(?:solve|calculate|compute|evaluate\s+the\s+integral|find\s+the\s+value|derive)\b", re.IGNORECASE)
    ]

    PAGE_PATTERN = re.compile(r"\b(?:(?:page\s*(?:number|no\.?|#)?|p\.)\s*(\d+))\b", re.IGNORECASE)
    TABLE_PATTERN = re.compile(r"\b(table\s*(?:\d+(?:\.\d+)*|[A-Za-z]))\b|\b(the\s+table|a\s+table|this\s+table)\b", re.IGNORECASE)
    FIGURE_PATTERN = re.compile(
        r"\b(?:(?:figure|fig\.?)\s*(\d+(?:[.-]\d+)+|\d+))\b|"
        r"\b(?:(\d+(?:[.-]\d+)+)\s*(?:figure|fig\.?))\b|"
        r"\b(the\s+figure|a\s+figure|this\s+figure|the\s+diagram|a\s+diagram|this\s+diagram|the\s+image|the\s+illustration)\b|"
        r"\b(?:figure|diagram|illustration)\b",
        re.IGNORECASE
    )

    @classmethod
    def _detect_pasted_mcq(cls, text: str) -> bool:
        """
        Detects if the student pasted an external multiple-choice question with options.
        Examples:
        - Contains 'Options:' followed by A, B, C, D (e.g. from user's screenshot).
        - Contains 2 or more option markers like '(A)', '(B)', or 'A.', 'B.', 'C.', 'D.'
        """
        # Explicit Options: header
        if re.search(r"\boptions?\s*:\s*(?:[A-Da-d1-4\n]|\([A-Da-d]\))", text, re.IGNORECASE):
            return True

        # Multiple option markers like A. B. C. D. or (A) (B) (C) (D)
        option_markers = re.findall(
            r"(?:^|\n|\s)(?:\([A-Da-d]\)|[A-Da-d][\.\):-])\s+[^\n]+",
            text
        )
        if len(option_markers) >= 3:
            return True
        if len(option_markers) >= 2 and (
            re.search(r"\boptions?\b", text, re.IGNORECASE)
            or "?" in text
            or re.search(r"\b(?:select|which|choose|what|identify|following|correct)\b", text, re.IGNORECASE)
        ):
            return True
        return False

    @classmethod
    def _detect_batch_questions(cls, text: str) -> Tuple[bool, Optional[int]]:
        """
        Detects if the student pasted multiple questions (e.g. 2 to 10 questions) to solve at once.
        Returns (is_batch, count).
        """
        # If student is asking the tutor to generate questions (e.g. "give me 5 questions in svm"),
        # that is NOT a batch of pasted questions.
        if re.search(r"\b(?:give\s+me|show\s+me|generate|prepare|create|make|need)\s*(?:\d+\s+)?(?:practice\s+)?questions?\b", text, re.IGNORECASE) and not re.search(r"\b(?:solve|answer)\s+(?:these|the\s+following)\b", text, re.IGNORECASE):
            numbered = re.findall(r"(?:^|\n)\s*(?:\d+[\.\)]|Q\d+[:\.-])\s+[A-Za-z]", text)
            if len(numbered) < 2:
                return False, None

        # Pattern 1: Numbered lines e.g. "1. What is...", "2. How does...", "Q1: Explain..."
        numbered_items = re.findall(r"(?:^|\n)\s*(?:\d+[\.\)]|Q\d+[:\.-])\s+([A-Za-z0-9\$\"'].{5,})", text)
        if len(numbered_items) >= 2:
            return True, len(numbered_items)

        # Pattern 2: Multiple questions ending with '?' separated by newlines
        q_lines = [ln.strip() for ln in text.split("\n") if ln.strip().endswith("?") and len(ln.strip().split()) >= 3]
        if len(q_lines) >= 2:
            return True, len(q_lines)

        return False, None

    GLOBAL_SCOPE_PATTERN = re.compile(
        r"\b(?:(?:from\s+)?(?:this|the)\s+(?:material|meterial|document|textbook|pdf|book|syllabus|curriculum|course|subject)|"
        r"(?:whole|entire|complete)\s+(?:material|meterial|document|textbook|pdf|book|syllabus|curriculum)|"
        r"(?:all|cover\s+all)\s+(?:the\s+)?topics|all\s+chapters|across\s+(?:all\s+)?chapters|"
        r"entire\s+syllabus|complete\s+syllabus|overall\s+topics|whole\s+syllabus)\b",
        re.IGNORECASE
    )

    @classmethod
    def _detect_query_scope(
        cls,
        text: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[str, Optional[str]]:
        """
        Determines whether the query targets the whole material, the active chat topic, or is ambiguous.
        Returns: (query_scope, scope_clarification_prompt)
        """
        cleaned = text.strip().lower()

        # 1. Explicit Global Material Scope
        if cls.GLOBAL_SCOPE_PATTERN.search(cleaned):
            return "global_material", None

        # Extract previous topic if present in dialogue history
        recent_topic = None
        if conversation_history:
            for turn in reversed(conversation_history):
                content = (turn.get("content") or turn.get("text") or "").strip()
                bold_m = re.search(r"\*\*([^*]+)\*\*", content)
                if bold_m and len(bold_m.group(1).strip()) > 2 and bold_m.group(1).strip() not in ["Note", "Correct Answer"]:
                    recent_topic = bold_m.group(1).strip()
                    break
                hist_match = re.search(r"\b(?:svm|cnn|rnn|pca|bert|lstm|gpt|knn|neural\s+network|support\s+vector\s+machine|bagging|boosting|random\s+forest|decision\s+tree)\b", content, re.IGNORECASE)
                if hist_match:
                    recent_topic = hist_match.group(0).strip().title()
                    break

        # 2. Check for explicit follow-up phrases on the active topic
        if any(w in cleaned for w in ["this algorithm", "this topic", "this concept", "tell me more about this", "step 2", "more on this"]):
            return "current_topic", None

        # 3. Check for explicit topic mention in the current text (e.g. "in svm", "about regression")
        has_named_topic = bool(re.search(r"\b(?:in|on|about|for|regarding)\s+[a-zA-Z0-9_\s-]+", cleaned))

        # 4. If student asks for questions/quiz without naming a topic, but there is an active previous topic
        is_generic_question_request = bool(re.search(
            r"^(?:give\s+me\s+)?(?:\d+\s+)?(?:important\s+)?(?:practice\s+)?questions?\??$|"
            r"^(?:quiz\s+me|test\s+me|make\s+a\s+quiz|give\s+questions)\b",
            cleaned
        ))
        if is_generic_question_request and recent_topic and not has_named_topic:
            prompt = f"I noticed we were just discussing **{recent_topic}**. Would you like these questions to focus specifically on **{recent_topic}**, or would you like a comprehensive set covering **all topics in your study material**?"
            return "ambiguous_scope", prompt

        return "specific_topic", None

    @classmethod
    def analyze_query(
        cls,
        raw_query: str,
        resolved_query: Optional[str] = None,
        normalized_query: Optional[str] = None,
        language: str = "english",
        is_follow_up: bool = False,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> QueryMetadata:
        """Convenience method forwarding to analyze_intent_and_metadata."""
        rq = resolved_query or raw_query
        nq = normalized_query or raw_query.lower().strip()
        return cls.analyze_intent_and_metadata(
            raw_query=raw_query,
            normalized_query=nq,
            resolved_query=rq,
            language=language,
            is_follow_up=is_follow_up,
            conversation_history=conversation_history,
        )

    @classmethod
    def analyze_intent_and_metadata(
        cls,
        raw_query: str,
        normalized_query: str,
        resolved_query: str,
        language: str,
        is_follow_up: bool = False,
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> QueryMetadata:
        """
        Uses live LLM with conversation history for query understanding; falls back to heuristic patterns if LLM unavailable.
        """
        # 0. Deterministic Fast-Path for Casual Greetings & Acknowledgments
        raw_lower = raw_query.lower()
        is_casual_match = any(pat.search(normalized_query) for pat in cls.CASUAL_PATTERNS) or any(pat.search(raw_lower.strip()) for pat in cls.CASUAL_PATTERNS)
        has_academic_keywords = any(w in raw_lower for w in ["what", "how", "why", "explain", "solve", "give", "question", "quiz", "page", "table", "figure", "diagram", "compare"])
        if is_casual_match and len(raw_lower.strip().split()) <= 6 and not has_academic_keywords:
            pre_gen_plan = PreGenerationClassifier.classify(
                raw_query=raw_query,
                resolved_query=resolved_query,
                intent="CASUAL",
                conversation_history=conversation_history,
            )
            return QueryMetadata(
                raw_query=raw_query,
                language=language,
                normalized_query=normalized_query,
                resolved_query=resolved_query,
                intent="CASUAL",
                target_topic=None,
                question_count=None,
                referenced_page=None,
                referenced_table=None,
                referenced_figure=None,
                format_directives={},
                extracted_entities=[],
                learning_objective="understand",
                difficulty_level="Beginner",
                response_requirements={
                    "needs_latex": False,
                    "needs_table": False,
                    "needs_steps": False,
                    "needs_socratic": False,
                },
                visual_modality="none",
                visual_diagram_type="none",
                visual_prompt_focus=None,
                question_complexity="simple",
                is_pasted_mcq=False,
                is_batch_questions=False,
                batch_question_count=None,
                query_scope="specific_topic",
                scope_clarification_prompt=None,
                pre_gen_plan=pre_gen_plan,
            )

        # 1. Attempt LLM-Powered Query Understanding
        if default_llm_service.is_live_model_configured():
            try:
                # Build recent conversation history context for the LLM
                history_prompt = ""
                if conversation_history:
                    recent_turns = []
                    for turn in conversation_history[-6:]:
                        role = "Student" if turn.get("role") == "user" else "Tutor"
                        content = (turn.get("content") or turn.get("text") or "").strip()
                        if content:
                            snip = content if len(content) <= 300 else content[:300] + "..."
                            recent_turns.append(f"{role}: {snip}")
                    if recent_turns:
                        history_prompt = "Recent Dialogue Context:\n" + "\n".join(recent_turns) + "\n\n"

                prompt = (
                    f"{history_prompt}"
                    f"Current Student Message: \"{raw_query}\"\n"
                    f"Analyze this query in dialogue context and return the JSON object:"
                )

                llm_response = default_llm_service.generate(
                    prompt=prompt,
                    system_prompt=_UNDERSTANDING_SYSTEM_PROMPT
                )
                if llm_response:
                    cleaned_json = re.sub(r"```(?:json)?", "", llm_response).strip().strip("`").strip()
                    parsed = json.loads(cleaned_json)
                    if isinstance(parsed, dict) and "intent" in parsed:
                        intent = parsed.get("intent", "DOCUMENT_QA")
                        context_source = str(parsed.get("context_source", "study_material")).lower().strip()
                        if context_source not in ("dialogue_history", "study_material"):
                            context_source = "study_material"

                        target_topic = parsed.get("target_topic")
                        question_count = parsed.get("question_count")
                        referenced_page = parsed.get("referenced_page")
                        referenced_table = parsed.get("referenced_table")
                        format_directives = parsed.get("format_directives") or {}
                        entities = parsed.get("entities") or []
                        if intent == "STUDY_NOTES":
                            format_directives["generate_study_notes"] = True
                        if ": " in resolved_query and re.search(r"\b(?:question|q|problem|item)\s*(?:#|no\.?|num\.?)?\s*\d+\b", raw_query, re.IGNORECASE):
                            parts = resolved_query.split(": ", 1)
                            if len(parts) == 2 and len(parts[1].strip()) >= 5:
                                format_directives["referenced_question_text"] = parts[1].strip()
                        if target_topic and target_topic not in entities:
                            entities.insert(0, target_topic)

                        needs_latex = bool(parsed.get("needs_latex"))
                        needs_table = bool(parsed.get("needs_table"))
                        refined_query = parsed.get("resolved_query") or resolved_query

                        # Extract visual modality and cognitive diagram type
                        visual_modality = str(parsed.get("visual_modality", "none")).lower().strip()
                        if visual_modality not in ("mermaid", "svg"):
                            visual_modality = "none"

                        visual_diagram_type = str(parsed.get("visual_diagram_type", "none")).lower().strip()
                        valid_diagram_types = (
                            "none", "flowchart_lr", "flowchart_td", "concept_graph",
                            "sequence", "state_diagram", "mindmap", "svg"
                        )
                        if visual_diagram_type not in valid_diagram_types:
                            if visual_modality == "svg":
                                visual_diagram_type = "svg"
                            elif visual_modality == "mermaid":
                                visual_diagram_type = "flowchart_td"
                            else:
                                visual_diagram_type = "none"

                        visual_prompt_focus = parsed.get("visual_prompt_focus")

                        # Scope reasoning: whole material vs. chat topic vs. ambiguous
                        det_scope, det_clarification = cls._detect_query_scope(raw_query, conversation_history)
                        parsed_scope = parsed.get("query_scope")
                        query_scope = det_scope if det_scope in ("global_material", "ambiguous_scope") else (parsed_scope or det_scope or "specific_topic")
                        scope_clarification_prompt = det_clarification or parsed.get("scope_clarification_prompt")

                        if query_scope == "global_material":
                            target_topic = None
                            format_directives["cover_all_topics"] = True
                            format_directives["whole_material"] = True
                            if visual_diagram_type == "concept_graph":
                                visual_prompt_focus = "Conceptual relationship network mapping the core pillars across the entire study material curriculum"

                        is_pasted_mcq = bool(parsed.get("is_pasted_mcq"))
                        is_batch_questions = bool(parsed.get("is_batch_questions"))
                        batch_question_count = parsed.get("batch_question_count")

                        # Deterministic check for pasted MCQs or batch questions
                        if cls._detect_pasted_mcq(raw_query):
                            is_pasted_mcq = True
                            is_batch_questions = False
                        else:
                            is_batch, b_count = cls._detect_batch_questions(raw_query)
                            if is_batch:
                                is_batch_questions = True
                                is_pasted_mcq = False
                                batch_question_count = b_count or batch_question_count
                            else:
                                is_batch_questions = False
                                batch_question_count = None

                        # Strict visual suppression for pasted MCQs and multi-question batches
                        if is_pasted_mcq:
                            intent = "PROBLEM_SOLVING"
                            visual_modality = "none"
                            visual_diagram_type = "none"
                            visual_prompt_focus = None
                            format_directives["is_pasted_mcq"] = True
                            format_directives["include_answers"] = True
                        elif is_batch_questions:
                            intent = "PROBLEM_SOLVING"
                            visual_modality = "none"
                            visual_diagram_type = "none"
                            visual_prompt_focus = None
                            format_directives["is_batch_questions"] = True
                            format_directives["include_answers"] = True
                            format_directives["batch_question_count"] = batch_question_count
                        # Safety check: if query is a simple short definition or basic math without visual keywords, ensure none
                        elif re.match(r"^(?:what is an? \w+\??|define \w+(?:\s+in\s+one\s+sentence)?\??|solve\s+\d+.*)$", raw_lower.strip()):
                            visual_modality = "none"
                            visual_diagram_type = "none"
                            visual_prompt_focus = None
                        elif is_seq_query := any(k in raw_lower for k in [
                            "evolution", "evolve", "phase", "phases", "step", "steps",
                            "stage", "stages", "pipeline", "chronological", "history", "timeline", "journey"
                        ]):
                            visual_modality = "mermaid"
                            visual_diagram_type = "flowchart_lr"
                            visual_prompt_focus = f"Sequential horizontal flowchart (LR) of {target_topic or refined_query}"
                        elif visual_modality == "none" or visual_diagram_type in ("none", "mindmap"):
                            # Cognitive topology refinement:
                            # 1. Explicit Mindmap requests
                            if any(k in raw_lower for k in ["mindmap", "mind map", "concept map"]):
                                visual_modality = "mermaid"
                                visual_diagram_type = "mindmap"
                                visual_prompt_focus = f"Mindmap of core branches for {target_topic or refined_query}"
                            # 2. Explicit Flowchart requests
                            elif any(k in raw_lower for k in ["flowchart", "flow chart"]):
                                is_seq = any(k in raw_lower for k in ["evolution", "phase", "step", "stage", "timeline"])
                                visual_modality = "mermaid"
                                visual_diagram_type = "flowchart_lr" if is_seq else "flowchart_td"
                                visual_prompt_focus = f"Flowchart of {target_topic or refined_query}"
                            # 3. Algorithms & Data Structures -> HIGH PRIORITY FOR INLINE SVG
                            elif any(k in raw_lower for k in [
                                "algorithm", "algorithms", "sorting", "sort", "quicksort", "merge sort",
                                "bubble sort", "insertion sort", "binary search", "linear search",
                                "dijkstra", "bfs", "dfs", "shortest path", "dynamic programming",
                                "gradient descent", "backpropagation", "neural network", "perceptron",
                                "data structure", "data structures", "array", "stack", "queue",
                                "linked list", "hashmap", "binary tree", "bst", "avl tree", "heap"
                            ]):
                                visual_modality = "svg"
                                visual_diagram_type = "svg"
                                visual_prompt_focus = f"Step-by-step vector illustration of {target_topic or refined_query} algorithm with visual pointers and states"
                            # 5. Important questions / exam questions -> concept_graph
                            elif any(k in raw_lower for k in [
                                "important question", "important questions", "exam question", "exam questions",
                                "key questions", "practice questions"
                            ]):
                                visual_modality = "mermaid"
                                visual_diagram_type = "concept_graph"
                                visual_prompt_focus = f"Concept relationship graph connecting core exam topics and question themes for {target_topic or refined_query}"
                            # 6. Protocols / Multi-actor interactions -> sequence
                            elif any(k in raw_lower for k in ["handshake", "protocol", "client-server", "client server", "oauth", "api exchange", "message exchange"]):
                                visual_modality = "mermaid"
                                visual_diagram_type = "sequence"
                                visual_prompt_focus = f"Sequence diagram of {target_topic or refined_query}"
                            # 7. State transitions -> state_diagram
                            elif any(k in raw_lower for k in ["state machine", "fsm", "state diagram", "lifecycle states", "status transitions"]):
                                visual_modality = "mermaid"
                                visual_diagram_type = "state_diagram"
                                visual_prompt_focus = f"State diagram of {target_topic or refined_query}"
                            # 8. Scientific, spatial, anatomical, physical, geometric -> svg
                            elif any(k in raw_lower for k in ["image", "diagram", "draw", "picture", "figure", "visualize", "illustration", "svg", "anatomy", "triangle", "vector", "cell", "atom", "force", "optic", "hyperplane", "circuit"]):
                                visual_modality = "svg"
                                visual_diagram_type = "svg"
                                visual_prompt_focus = f"Technical vector illustration of {target_topic or refined_query}"
                            # 9. Unordered syllabus pillars -> mindmap
                            elif any(k in raw_lower for k in ["syllabus", "curriculum", "chapters", "table of content", "core pillars", "pillars"]):
                                visual_modality = "mermaid"
                                visual_diagram_type = "mindmap"
                                visual_prompt_focus = f"Mindmap of core syllabus pillars, topics, and relationships for {target_topic or refined_query}"
                            # 10. Decision trees, hierarchies, classifications -> flowchart_td
                            elif any(k in raw_lower for k in ["hierarchy", "classification", "tree"]):
                                visual_modality = "mermaid"
                                visual_diagram_type = "flowchart_td"
                                visual_prompt_focus = f"Hierarchical classification of {target_topic or refined_query}"

                        # Safety check for page/table patterns in raw_query if LLM missed it
                        if referenced_page is None:
                            page_m = cls.PAGE_PATTERN.search(raw_query)
                            if page_m:
                                referenced_page = int(page_m.group(1))
                        if referenced_table is None:
                            tbl_m = cls.TABLE_PATTERN.search(raw_query)
                            if tbl_m:
                                referenced_table = tbl_m.group(1).title() if tbl_m.group(1) else "table"

                        # Extract figure reference if present
                        fig_m = cls.FIGURE_PATTERN.search(raw_query) or cls.FIGURE_PATTERN.search(normalized_query)
                        referenced_figure = None
                        if fig_m:
                            if fig_m.group(1) or fig_m.group(2):
                                f_num = fig_m.group(1) or fig_m.group(2)
                                f_hyphen = f_num.replace(".", "-")
                                f_dot = f_num.replace("-", ".")
                                referenced_figure = f"Figure {f_hyphen}"
                                fig_variants = [f"Figure {f_hyphen}", f"Figure {f_dot}", f"Fig {f_hyphen}", f"Fig. {f_dot}"]
                                for v in fig_variants:
                                    if v not in entities:
                                        entities.append(v)
                                if f"Figure {f_hyphen}" not in refined_query:
                                    refined_query = f"{refined_query} Figure {f_hyphen} (Figure {f_dot})"
                            elif fig_m.group(3):
                                referenced_figure = fig_m.group(3).strip().lower()
                            else:
                                referenced_figure = "figure"

                        # Safety check: if user asked "only need questions" or "just questions", enforce questions_only
                        if re.search(r"\b(?:only\s+(?:need\s+)?questions?|just\s+questions?|no\s+answers?)\b", raw_query, re.IGNORECASE):
                            format_directives["questions_only"] = True
                            format_directives["include_answers"] = False

                        if "table" in raw_query.lower() and any(w in raw_query.lower() for w in ["solve", "fill", "calculate", "complete", "check"]):
                            format_directives["solve_table"] = True
                            format_directives["include_complete_table"] = True
                            needs_table = True

                        pre_gen_plan = PreGenerationClassifier.classify(
                            raw_query=raw_query,
                            resolved_query=refined_query,
                            intent=intent,
                            conversation_history=conversation_history,
                        )
                        if pre_gen_plan.visual == "none" and not any(k in raw_lower for k in [
                            "algorithm", "algorithms", "sorting", "sort", "quicksort", "merge sort",
                            "binary search", "dijkstra", "data structure", "data structures", "stack", "queue",
                            "linked list", "array", "tree", "flowchart", "mindmap", "diagram", "svg", "image",
                            "draw", "show", "gradient descent", "backpropagation", "perceptron"
                        ]):
                            visual_modality = "none"
                            visual_diagram_type = "none"
                            visual_prompt_focus = None

                        return QueryMetadata(
                            raw_query=raw_query,
                            language=language,
                            normalized_query=normalized_query,
                            resolved_query=refined_query,
                            intent=intent,
                            context_source=context_source,
                            target_topic=target_topic,
                            question_count=int(question_count) if question_count else None,
                            referenced_page=int(referenced_page) if referenced_page is not None else None,
                            referenced_table=referenced_table,
                            referenced_figure=referenced_figure,
                            format_directives=format_directives,
                            extracted_entities=entities[:10],
                            learning_objective="analyze" if intent == "COMPARISON" else ("apply" if intent in ["PRACTICE_QUESTIONS", "PROBLEM_SOLVING"] else "understand"),
                            difficulty_level="Intermediate",
                            response_requirements={
                                "needs_latex": needs_latex,
                                "needs_table": needs_table or bool(referenced_table),
                                "needs_steps": intent in ["PROBLEM_SOLVING", "EXPLANATION", "COMPARISON"],
                                "needs_socratic": True,
                            },
                            visual_modality=visual_modality,
                            visual_diagram_type=visual_diagram_type,
                            visual_prompt_focus=visual_prompt_focus,
                            question_complexity="comparative" if intent == "COMPARISON" else "simple",
                            is_pasted_mcq=is_pasted_mcq,
                            is_batch_questions=is_batch_questions,
                            batch_question_count=int(batch_question_count) if batch_question_count is not None else None,
                            query_scope=query_scope,
                            scope_clarification_prompt=scope_clarification_prompt,
                            pre_gen_plan=pre_gen_plan,
                        )
            except Exception as e:
                logger.warning(f"[QueryUnderstanding] LLM understanding pass failed, falling back to heuristics: {e}")

        # 2. Heuristic Fallback
        return cls._heuristic_analysis(
            raw_query=raw_query,
            normalized_query=normalized_query,
            resolved_query=resolved_query,
            language=language,
            is_follow_up=is_follow_up,
            conversation_history=conversation_history
        )

    @classmethod
    def _heuristic_analysis(
        cls,
        raw_query: str,
        normalized_query: str,
        resolved_query: str,
        language: str,
        is_follow_up: bool,
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> QueryMetadata:
        cleaned = resolved_query.strip().lower()

        # Scope reasoning: whole material vs. chat topic vs. ambiguous
        det_scope, det_clarification = cls._detect_query_scope(raw_query, conversation_history)
        query_scope = det_scope
        scope_clarification_prompt = det_clarification

        # Extract count if present
        count_match = re.search(r"\b(\d+)\s*(?:questions?|mcqs?|flashcards?|cards?|problems?)\b", cleaned)
        question_count = int(count_match.group(1)) if count_match else None

        # Extract topic from "in <topic>", "on <topic>", "for <topic>", "about <topic>"
        target_topic = None
        if query_scope != "global_material":
            topic_match = re.search(r"\b(?:in|on|about|for|regarding)\s+([a-zA-Z0-9_\s-]+)$", cleaned)
            if topic_match:
                candidate = topic_match.group(1).strip()
                candidate = re.sub(r"[?!.,;]+$", "", candidate).strip()
                if candidate and candidate not in ("this", "it", "here", "them", "tomorrow", "exam", "this material", "this meterial"):
                    target_topic = candidate.upper() if len(candidate) <= 4 else candidate.title()

            # If target_topic is missing and we have conversation_history, infer from recent messages
            if not target_topic and conversation_history:
                for turn in reversed(conversation_history):
                    content = (turn.get("content") or turn.get("text") or "").strip()
                    hist_match = re.search(r"\b(?:svm|cnn|rnn|pca|bert|lstm|gpt|knn|neural\s+network|support\s+vector\s+machine)\b", content, re.IGNORECASE)
                    if hist_match:
                        found = hist_match.group(0).strip()
                        target_topic = found.upper() if len(found) <= 4 else found.title()
                        break

        # Extract page number if present
        page_m = cls.PAGE_PATTERN.search(cleaned)
        referenced_page = int(page_m.group(1)) if page_m else None

        # Extract table reference if present
        tbl_m = cls.TABLE_PATTERN.search(cleaned)
        referenced_table = tbl_m.group(1).title() if (tbl_m and tbl_m.group(1)) else ("table" if tbl_m else None)

        # Extract figure reference if present
        fig_m = cls.FIGURE_PATTERN.search(raw_query) or cls.FIGURE_PATTERN.search(normalized_query) or cls.FIGURE_PATTERN.search(cleaned)
        referenced_figure = None
        if fig_m:
            if fig_m.group(1) or fig_m.group(2):
                f_num = fig_m.group(1) or fig_m.group(2)
                f_hyphen = f_num.replace(".", "-")
                f_dot = f_num.replace("-", ".")
                referenced_figure = f"Figure {f_hyphen}"
            elif fig_m.group(3):
                referenced_figure = fig_m.group(3).strip().lower()
            else:
                referenced_figure = "figure"

        # Format directives
        format_directives: Dict[str, Any] = {}
        if ": " in resolved_query and re.search(r"\b(?:question|q|problem|item)\s*(?:#|no\.?|num\.?)?\s*\d+\b", raw_query, re.IGNORECASE):
            parts = resolved_query.split(": ", 1)
            if len(parts) == 2 and len(parts[1].strip()) >= 5:
                format_directives["referenced_question_text"] = parts[1].strip()
        if re.search(r"\b(?:only\s+(?:need\s+)?questions?|just\s+questions?|no\s+answers?)\b", cleaned):
            format_directives["questions_only"] = True
            format_directives["include_answers"] = False

        if "table" in cleaned and any(w in cleaned for w in ["solve", "fill", "calculate", "complete", "check"]):
            format_directives["solve_table"] = True
            format_directives["include_complete_table"] = True

        # Check for pasted MCQs or multi-question batches
        is_pasted_mcq = cls._detect_pasted_mcq(raw_query)
        is_batch_questions = False
        batch_question_count = None
        if is_pasted_mcq:
            format_directives["is_pasted_mcq"] = True
            format_directives["include_answers"] = True
        else:
            is_batch, b_count = cls._detect_batch_questions(raw_query)
            if is_batch:
                is_batch_questions = True
                batch_question_count = b_count
                format_directives["is_batch_questions"] = True
                format_directives["batch_question_count"] = b_count
                format_directives["include_answers"] = True

        # Extract topic from questions e.g. "followed in a bagging algorithm"
        if not target_topic and query_scope != "global_material":
            m = re.search(r"\b(?:in|of|for|about)\s+(?:an?|the)?\s*([a-zA-Z0-9_\s-]+?)\s+(?:algorithm|method|model|process|framework|protocol)\b", cleaned)
            if m:
                target_topic = f"{m.group(1).strip()} {m.group(0).split()[-1]}".title()

        if query_scope == "global_material":
            target_topic = None
            format_directives["cover_all_topics"] = True
            format_directives["whole_material"] = True

        # Intent Detection
        if is_pasted_mcq or is_batch_questions:
            intent = "PROBLEM_SOLVING"
        elif any(pat.search(cleaned) for pat in cls.CASUAL_PATTERNS) and len(cleaned.split()) <= 4:
            intent = "CASUAL"
        elif any(pat.search(cleaned) for pat in cls.QUIZ_PATTERNS):
            intent = "QUIZ"
        elif "table" in cleaned and any(w in cleaned for w in ["solve", "fill", "calculate", "complete"]):
            intent = "PROBLEM_SOLVING"
        elif any(pat.search(cleaned) for pat in cls.PRACTICE_QUESTIONS_PATTERNS) and ("question" in cleaned or "problem" in cleaned):
            intent = "PRACTICE_QUESTIONS"
        elif any(pat.search(cleaned) for pat in cls.SUMMARY_PATTERNS):
            intent = "SUMMARY"
        elif any(pat.search(cleaned) for pat in cls.COMPARISON_PATTERNS):
            intent = "COMPARISON"
        elif any(pat.search(cleaned) for pat in cls.PROBLEM_SOLVING_PATTERNS):
            intent = "PROBLEM_SOLVING"
        elif is_follow_up:
            intent = "FOLLOW_UP"
        elif any(w in cleaned for w in ["explain", "teach", "how does", "why does", "deep dive"]):
            intent = "EXPLANATION"
        else:
            intent = "DOCUMENT_QA"

        # Entity Extraction including acronyms like svm, cnn, rnn, pca, etc.
        entities = []
        if target_topic:
            entities.append(target_topic)
        acronyms = re.findall(r"\b(?:svm|cnn|rnn|pca|bert|lstm|gpt|knn|ann|nlp|llm|rl|dqn)\b", cleaned)
        for a in acronyms:
            upper_a = a.upper()
            if upper_a not in entities:
                entities.append(upper_a)

        if referenced_figure:
            fig_num = re.sub(r"[^\d.-]", "", referenced_figure)
            f_hyphen = fig_num.replace(".", "-")
            f_dot = fig_num.replace("-", ".")
            for fv in [f"Figure {f_hyphen}", f"Figure {f_dot}", f"Fig {f_hyphen}", f"Fig. {f_dot}"]:
                if fv not in entities:
                    entities.append(fv)

        raw_entities = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", resolved_query)
        action_verbs = {"Compare", "Explain", "Analyze", "Describe", "Define", "Discuss", "Show", "What", "How", "Why", "Tell", "Give"}
        for ent in raw_entities:
            words = ent.split()
            if words and words[0] not in action_verbs:
                entities.append(ent)

        needs_latex = bool(re.search(r"[∑∫√∂≤≥±=+\-*/^]|\b(?:formulas?|equations?|math|calculate|integral)\b", resolved_query, re.IGNORECASE))
        needs_table = bool(referenced_table or re.search(r"\b(?:table|comparison|tabular|columns|matrix)\b", resolved_query, re.IGNORECASE))

        # Cognitive Visual Modality & Diagram Typology Detection
        visual_modality = "none"
        visual_diagram_type = "none"
        visual_prompt_focus = None

        flowchart_lr_triggers = [
            "evolution", "evolve", "evolutions", "phase", "phases", "step", "steps",
            "stage", "stages", "pipeline", "chronological", "history", "timeline", "journey"
        ]
        concept_graph_triggers = [
            "important question", "important questions", "importent question", "importent questions",
            "exam question", "exam questions", "key question", "key questions", "practice question", "practice questions"
        ]
        sequence_triggers = [
            "handshake", "protocol", "client-server", "client server", "oauth",
            "api exchange", "message exchange", "request response"
        ]
        state_triggers = [
            "state machine", "fsm", "state diagram", "lifecycle states", "status transitions"
        ]
        algorithm_svg_triggers = [
            "algorithm", "algorithms", "sorting", "sort", "quicksort", "merge sort",
            "bubble sort", "insertion sort", "heap sort", "binary search", "linear search",
            "dijkstra", "bfs", "dfs", "breadth first", "depth first", "graph traversal",
            "shortest path", "dynamic programming", "knapsack", "gradient descent",
            "backpropagation", "backprop", "neural network", "perceptron", "decision boundary",
            "support vector", "svm hyperplane", "k-means", "knn", "a* search", "a star",
            "data structure", "data structures", "array", "arrays", "stack", "stacks",
            "queue", "queues", "linked list", "hash table", "hashmap", "hash map",
            "binary tree", "bst", "avl tree", "red-black tree", "heap", "trie"
        ]
        svg_triggers = [
            "svg", "draw", "diagram", "image", "picture", "figure", "illustration",
            "visualize", "structure", "anatomy", "vector", "cross-section", "cross section",
            "geometry", "triangle", "cell", "atom", "hyperplane", "optic", "optics", "force",
            "coordinate", "plot", "graph plot", "circuit", "lens", "molecule", "dna", "neuron"
        ]
        mindmap_triggers = [
            "syllabus", "curriculum", "chapters", "table of content", "core pillars",
            "pillars", "mindmap", "mind map", "concept map"
        ]
        flowchart_td_triggers = [
            "flowchart", "flow chart", "workflow", "process", "hierarchy", "classification", "tree", "decision tree"
        ]

        # Strict visual suppression for pasted MCQs and multi-question batches
        if is_pasted_mcq or is_batch_questions:
            visual_modality = "none"
            visual_diagram_type = "none"
            visual_prompt_focus = None
        # Safety check: simple short definition or pure arithmetic calculation -> none
        elif re.match(r"^(?:what is an? \w+\??|define \w+(?:\s+in\s+one\s+sentence)?\??|solve\s+\d+.*)$", cleaned):
            visual_modality = "none"
            visual_diagram_type = "none"
            visual_prompt_focus = None
        # 1. Explicit Mindmap requests (e.g. "give me a mindmap of machine learning algorithms")
        elif any(w in cleaned for w in ["mindmap", "mind map", "concept map"]):
            visual_modality = "mermaid"
            visual_diagram_type = "mindmap"
            visual_prompt_focus = f"Mindmap of core branches and topics for {target_topic or resolved_query}"
        # 2. Explicit Flowchart requests (e.g. "draw a flowchart of...")
        elif any(w in cleaned for w in ["flowchart", "flow chart"]):
            visual_modality = "mermaid"
            visual_diagram_type = "flowchart_lr" if any(w in cleaned for w in flowchart_lr_triggers) else "flowchart_td"
            visual_prompt_focus = f"Flowchart of {target_topic or resolved_query}"
        # 3. Network protocols & interactions
        elif any(w in cleaned for w in sequence_triggers):
            visual_modality = "mermaid"
            visual_diagram_type = "sequence"
            visual_prompt_focus = f"Sequence diagram of {target_topic or resolved_query}"
        # 4. Algorithms & Data Structures -> HIGH PRIORITY FOR INLINE SVG
        elif any(w in cleaned for w in algorithm_svg_triggers):
            visual_modality = "svg"
            visual_diagram_type = "svg"
            visual_prompt_focus = f"Step-by-step vector illustration of {target_topic or resolved_query} algorithm with visual pointers and states"
        # 5. Chronological / Evolutionary / Sequential Progressions (NEVER A MINDMAP)
        elif any(w in cleaned for w in flowchart_lr_triggers):
            visual_modality = "mermaid"
            visual_diagram_type = "flowchart_lr"
            visual_prompt_focus = f"Sequential horizontal flowchart (LR) illustrating the phases/evolution of {target_topic or resolved_query}"
        # 6. Important Questions / Whole Material -> Concept relationship graph
        elif query_scope == "global_material" or any(w in cleaned for w in concept_graph_triggers):
            visual_modality = "mermaid"
            visual_diagram_type = "concept_graph"
            if query_scope == "global_material":
                visual_prompt_focus = "Conceptual relationship network mapping the core pillars across the entire study material curriculum"
            else:
                visual_prompt_focus = f"Concept relationship network mapping core exam topics and question themes for {target_topic or resolved_query}"
        # 7. State transitions
        elif any(w in cleaned for w in state_triggers):
            visual_modality = "mermaid"
            visual_diagram_type = "state_diagram"
            visual_prompt_focus = f"State diagram of {target_topic or resolved_query}"
        # 8. General flowcharts / hierarchies / classifications
        elif any(w in cleaned for w in flowchart_td_triggers):
            visual_modality = "mermaid"
            visual_diagram_type = "flowchart_td"
            visual_prompt_focus = f"Flowchart or classification hierarchy for {target_topic or resolved_query}"
        # 9. Unordered syllabus pillars (Radial mindmap)
        elif any(w in cleaned for w in mindmap_triggers):
            visual_modality = "mermaid"
            visual_diagram_type = "mindmap"
            visual_prompt_focus = f"Mindmap of core syllabus pillars, topics, and relationships for {target_topic or resolved_query}"
        # 10. Spatial / Anatomical / Geometric / Physical SVG
        elif any(w in cleaned for w in svg_triggers) or "show me an image" in cleaned or "draw an image" in cleaned:
            visual_modality = "svg"
            visual_diagram_type = "svg"
            visual_prompt_focus = f"Technical vector illustration of {target_topic or resolved_query}"

        # Context Source Detection (dialogue_history vs. study_material)
        if any(w in cleaned for w in ["our chat", "previous answer", "what did we discuss", "what did you say", "repeat that", "earlier message", "in this chat"]):
            context_source = "dialogue_history"
        else:
            context_source = "study_material"

        # Pre-Generation Classification Pass
        pre_gen_plan = PreGenerationClassifier.classify(
            raw_query=raw_query,
            resolved_query=resolved_query,
            intent=intent,
            conversation_history=conversation_history,
        )

        if pre_gen_plan.visual == "none":
            visual_modality = "none"
            visual_diagram_type = "none"
            visual_prompt_focus = None

        return QueryMetadata(
            raw_query=raw_query,
            language=language,
            normalized_query=normalized_query,
            resolved_query=resolved_query,
            intent=intent,
            context_source=context_source,
            target_topic=target_topic,
            question_count=question_count,
            referenced_page=referenced_page,
            referenced_table=referenced_table,
            referenced_figure=referenced_figure,
            format_directives=format_directives,
            extracted_entities=list(dict.fromkeys(entities))[:10],
            learning_objective="analyze" if intent == "COMPARISON" else ("apply" if intent in ["PRACTICE_QUESTIONS", "PROBLEM_SOLVING"] else "understand"),
            difficulty_level="Intermediate",
            response_requirements={
                "needs_latex": needs_latex,
                "needs_table": needs_table,
                "needs_steps": intent in ["PROBLEM_SOLVING", "EXPLANATION", "COMPARISON"],
                "needs_socratic": True,
            },
            visual_modality=visual_modality,
            visual_diagram_type=visual_diagram_type,
            visual_prompt_focus=visual_prompt_focus,
            question_complexity="comparative" if intent == "COMPARISON" else "simple",
            is_pasted_mcq=is_pasted_mcq,
            is_batch_questions=is_batch_questions,
            batch_question_count=batch_question_count,
            query_scope=query_scope,
            scope_clarification_prompt=scope_clarification_prompt,
            pre_gen_plan=pre_gen_plan,
        )

