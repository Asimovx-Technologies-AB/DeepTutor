import re
import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from app.schemas.tutoring import (
    QueryMetadata,
    PreGenerationPlan,
    QueryUnderstandingResult,
    ActionPlan,
    UserIntent,
    RetrievalDecisionEnum,
    RetrievalScopeEnum,
    ResponseTypeEnum,
    ActionTypeEnum,
    DecisionStateEnum,
    OutputRequirements
)
from app.services.llm_service import default_llm_service
from app.tutoring.analyzer.pre_gen_classifier import PreGenerationClassifier

logger = logging.getLogger(__name__)

_UNDERSTANDING_SYSTEM_PROMPT = """You are DeepTutor's Query Understanding and Decision Engine.

Your task is NOT to answer the user's question.

Your task is to understand what the user wants, resolve references using
conversation context, determine the correct material scope, evaluate
whether enough evidence exists, and decide what DeepTutor should do next.

Analyze:
1. User intent
2. Requested action
3. Topics/entities
4. References to previous conversation
5. Document scope
6. Whether retrieval is needed
7. Whether complete-document analysis is needed
8. Whether the query is ambiguous
9. Whether sufficient evidence exists
10. Whether clarification is required
11. What action should be executed

IMPORTANT:
- Never guess when multiple interpretations are plausible.
- If the meaning is clear from context, resolve it automatically.
- If the meaning cannot be reliably determined, choose CLARIFY.
- Do not invent missing context or material content.
- Do not use retrieval results to redefine the user's intent. Retrieval is evidence, not intent.
- For document-level requests (identifying important topics, generating questions from the material, summarizing), do not treat Top-K retrieval as sufficient evidence. Use DOCUMENT_ANALYSIS.
- If the user asks for questions and answers, explicitly determine whether answers are requested and extract the requested number.
- If ambiguity exists, generate a concise, specific clarification question using the available context. Do not be vague.
- If the user asks to be taught a topic or learn interactively step-by-step (e.g. "Teach me SVM", "Act as a teacher and teach me Decision Trees", "I want to learn Newton's Laws"), you MUST choose intent="TEACH_TOPIC", action="TEACH_TOPIC", decision="ANSWER", and extract the clean target topic (e.g. "SVM", "Decision Tree").
- If the user explicitly confirms or continues an ongoing lesson (e.g. "continue", "next", "proceed", "yes", "explain again", "ready"), set intent="TEACH_TOPIC", action="TEACH_TOPIC", decision="ANSWER".
- CRITICAL: Standard concept questions and explanation requests (e.g. "what is SVM", "explain SVM with a figure", "how does backpropagation work", "explain decision trees") must NEVER be classified as TEACH_TOPIC! Always classify them as EXPLAIN_TOPIC or ANSWER_QUESTION.

Decision States:
- ANSWER: Clear query, normal RAG or fact answering.
- CLARIFY: Ambiguous query, needs clarification, or user is challenging/disputing a previous answer.
- RETRIEVE: Direct search query.
- DOCUMENT_ANALYSIS: Analyze whole document (topics, summarize).
- GENERATE: Generate questions, quizzes, flashcards.
- FOLLOW_UP: Contextual follow-up to previous turn.
- INSUFFICIENT_CONTEXT: Pronouns/references cannot be resolved.
- MATERIAL_NOT_SUPPORTED: Topic is clear but material does not contain it.
- INSUFFICIENT_EVIDENCE: Material mentions topic but lacks details.
- OUT_OF_SCOPE: Irrelevant.

Answerability States:
- ANSWERABLE: Ready to answer.
- AMBIGUOUS: Could mean multiple things.
- INSUFFICIENT_EVIDENCE: Needs more context.

Intent Taxonomy:
- ANSWER_QUESTION, EXPLAIN_TOPIC, TEACH_TOPIC, SUMMARIZE, SIMPLIFY, GENERATE_EXAMPLES, GENERATE_QUESTIONS, GENERATE_QUIZ, GENERATE_FLASHCARDS, CREATE_STUDY_PLAN, MODIFY_STUDY_PLAN, SEARCH_MATERIAL, ASK_FROM_MATERIAL, COMPARE_CONCEPTS, SOLVE_PROBLEM, CHECK_ANSWER, GENERATE_NOTES, DOCUMENT_TOPIC_ANALYSIS, CONTINUE_LEARNING, CLARIFY_CONCEPT, FOLLOW_UP, GREETING, CONFIRMATION, OUT_OF_SCOPE, ANSWER_CHALLENGE, EXAM_START, EXAM_ANSWER, EXAM_NEXT, EXAM_COMPLETE, EXAM_REPORT

Output JSON Schema:
{
  "original_query": "<exact raw query>",
  "resolved_query": "<resolved standalone academic search query>",
  "intent": "EXPLAIN_TOPIC",
  "sub_intent": "CONCEPTUAL_OVERVIEW",
  "subject": "Machine Learning",
  "topic": "Backpropagation",
  "subtopic": null,
  "topics": ["Backpropagation"],
  "entities": ["neural networks", "gradient descent"],
  "language": "en",
  "difficulty": "beginner" | "intermediate" | "advanced",
  "requires_context": true | false,
  "requires_retrieval": true | false,
  "retrieval_scope": "USER_MATERIAL" | "CURRENT_TOPIC" | "GLOBAL_KNOWLEDGE" | "NONE",
  "retrieval_query": "backpropagation algorithm neural networks",
  "requires_document_analysis": true | false,
  "analysis_scope": "COMPLETE_DOCUMENT" | null,
  "action": "EXPLAIN_TOPIC",
  "decision": "ANSWER" | "CLARIFY" | "DOCUMENT_ANALYSIS" | "GENERATE" | "INSUFFICIENT_CONTEXT" | "MATERIAL_NOT_SUPPORTED" | "INSUFFICIENT_EVIDENCE" | "OUT_OF_SCOPE",
  "answerability": {
    "status": "ANSWERABLE" | "AMBIGUOUS" | "INSUFFICIENT_EVIDENCE",
    "confidence": 0.95,
    "evidence_available": true
  },
  "intent_confidence": 0.95,
  "topic_confidence": 0.90,
  "reference_confidence": 0.99,
  "ambiguity_type": "INTENT" | "REFERENCE" | "ENTITY" | "TOPIC" | "DOCUMENT" | "SCOPE" | "OUTPUT" | "NONE",
  "clarification_needed": false,
  "clarification_question": null,
  "missing_information": [],
  "requested_count": null,
  "include_answers": false,
  "source_scope": null,
  "conversation_reference": null,
  "context_source": "dialogue_history" | "study_material",
  "response_type": "DETAILED_EXPLANATION" | "STEP_BY_STEP" | "COMPARISON" | "QUIZ" | "SIMPLE_EXPLANATION" | "TABLE",
  "requires_tool": false,
  "tool_name": null,
  "requires_example": true | false,
  "confidence": 0.95,
  "clarification_prompt": null,
  "question_count": null,
  "referenced_page": null,
  "referenced_table": null,
  "referenced_figure": null,
  "visual_modality": "none" | "svg",
  "visual_diagram_type": "none" | "flowchart_lr" | "flowchart_td" | "concept_graph" | "sequence" | "state_diagram" | "mindmap" | "svg",
  "visual_prompt_focus": null,
  "is_pasted_mcq": false,
  "is_batch_questions": false,
  "batch_question_count": null,
  "format_directives": {},
  "needs_latex": false,
  "needs_table": false,
  "output_requirements": {
    "format": "DEFAULT",
    "length": "DEFAULT",
    "include_explanation": true,
    "include_examples": false,
    "include_steps": false,
    "include_sources": false,
    "include_question": false
  }
}

Return ONLY valid JSON. No conversational text."""


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

    ANSWER_CHALLENGE_PATTERNS = [
        re.compile(r"\b(?:wrong|incorrect|false|mistake|error|bad\s+answer|not\s+right|inaccurate|disagree)\b", re.IGNORECASE),
        re.compile(r"i\s+think\s+you\s+are\s+giving\s+(?:the\s+)?wrong", re.IGNORECASE)
    ]

    DOCUMENT_TOPIC_ANALYSIS_PATTERN = re.compile(
        r"^(?:what are|show me|list|identify|give me)(?:\s+the)?\s+(?:important|key|major|main|critical|core)\s+(?:topics?|concepts?|chapters?|subjects?)\b|"
        r"^(?:important|key|major|main|critical)\s+(?:topics?|concepts?)\b|"
        r"\b(?:what|which)\s+(?:topics?\s+|concepts?\s+)?(?:should\s+I|do\s+I\s+need\s+to|to)\s+"
        r"(?:study|focus|learn|prepare|review|cover)\b|"
        r"\bidentify\s+(?:the\s+)?(?:important|key|major)\b|"
        r"^(?:topic|concept)\s+(?:map|analysis|overview)\b",
        re.IGNORECASE
    )

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

    TEACH_TOPIC_PATTERNS = [
        re.compile(
            r"^(?:act\s+as\s+(?:a\s+)?(?:teacher|tutor)\s+(?:and\s+)?(?:to\s+)?)?"
            r"(?:please\s+)?(?:can\s+you\s+)?(?:teach\s+(?:me|us)?|guide\s+(?:me|us)?)\s*(?:about\s+)?(.+)$",
            re.IGNORECASE
        ),
        re.compile(
            r"^(?:i\s+want\s+to\s+learn|help\s+me\s+learn|let(?:'s|\s+us)\s+learn)\s+(?:about\s+)?(.+)$",
            re.IGNORECASE
        ),
        re.compile(
            r"\b(?:teach\s+(?:me\s+|us\s+)?about|teach\s+me|teach\s+us|start\s+(?:teaching|teacher\s+mode)|teach\s+topic|teach\s+lesson)\s*(.*)$",
            re.IGNORECASE
        ),
        re.compile(
            r"^(?:please\s+)?(?:can\s+you\s+)?explain\s+(?:this|the)\s+topic\b",
            re.IGNORECASE
        ),
        re.compile(
            r"^(?:please\s+)?(?:can\s+you\s+)?teach\s+(?:me\s+)?(?:this\s+)?chapter\b",
            re.IGNORECASE
        ),
        re.compile(
            r"^(?:please\s+)?(?:can\s+you\s+)?start\s+(?:teaching|teacher\s+mode)\b",
            re.IGNORECASE
        ),
    ]

    @classmethod
    def extract_teach_topic(cls, text: str) -> Optional[str]:
        try:
            from app.tutoring.teaching.interactive_teacher import InteractiveTeacherEngine
            return InteractiveTeacherEngine.extract_teach_topic_phrase(text)
        except Exception:
            cleaned = text.strip()
            if re.search(r"^(?:please\s+)?(?:can\s+you\s+)?explain\s+(?:this|the)\s+topic\b", cleaned, re.IGNORECASE):
                return "this topic"
            if re.search(r"^(?:please\s+)?(?:can\s+you\s+)?teach\s+(?:me\s+)?(?:this\s+)?chapter\b", cleaned, re.IGNORECASE):
                return "this chapter"
            if re.search(r"^(?:start\s+teaching)\s*$", cleaned, re.IGNORECASE):
                return "this topic"
            for pat in cls.TEACH_TOPIC_PATTERNS:
                m = pat.search(cleaned)
                if m and m.lastindex and m.group(m.lastindex):
                    raw_t = m.group(m.lastindex).strip(" ?.!:,;")
                    raw_t = re.sub(
                        r"\b(?:step\s+by\s+step|from\s+scratch|thoroughly|completely|deeply|in\s+detail|please)\b",
                        "",
                        raw_t,
                        flags=re.IGNORECASE
                    ).strip(" ?.!:,;")
                    if raw_t and len(raw_t) >= 2 and raw_t.lower() not in ("everything", "all", "all topics"):
                        return raw_t
            return None

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
    def analyze_query_structured(
        cls,
        raw_query: str,
        normalized_query: Optional[str] = None,
        resolved_query: Optional[str] = None,
        language: str = "en",
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        current_subject: Optional[str] = None,
        current_topic: Optional[str] = None,
        available_materials: Optional[List[Dict[str, Any]]] = None,
        available_tools: Optional[List[str]] = None,
    ) -> QueryUnderstandingResult:
        """
        Unified entry point producing a strongly-typed QueryUnderstandingResult.
        Executes Fast-Path -> LLM Analyzer -> Heuristic Fallback.
        """
        norm_q = normalized_query or raw_query.strip()
        res_q = resolved_query or norm_q

        # 1. Fast Path
        from app.tutoring.analyzer.fast_path import QueryFastPath
        fast_res = QueryFastPath.evaluate(
            normalized_query=norm_q,
            original_query=raw_query,
            language=language,
            current_subject=current_subject,
            current_topic=current_topic
        )
        if fast_res:
            return fast_res

        # 2. Query Understanding (LLM or Heuristic)
        meta = cls.analyze_intent_and_metadata(
            raw_query=raw_query,
            normalized_query=norm_q,
            resolved_query=res_q,
            language=language,
            conversation_history=conversation_history
        )
        if meta.understanding_result:
            return meta.understanding_result

        # Fallback structured construction
        return cls._build_structured_result_from_meta(meta, raw_query, norm_q, res_q, language, current_subject, current_topic)

    @classmethod
    def _build_structured_result_from_meta(
        cls,
        meta: QueryMetadata,
        raw_query: str,
        normalized_query: str,
        resolved_query: str,
        language: str,
        current_subject: Optional[str] = None,
        current_topic: Optional[str] = None,
        ref_meta: Optional[Dict[str, Any]] = None
    ) -> QueryUnderstandingResult:
        print("DEBUG inside _map_to_understanding_result, ref_meta=", ref_meta)
        intent = meta.intent
        # Action planning
        requires_tool = False
        tool_name = None
        action = ActionTypeEnum.ANSWER_QUESTION.value
        decision = DecisionStateEnum.ANSWER

        if intent in ("CREATE_STUDY_PLAN", "MODIFY_STUDY_PLAN"):
            action = intent
            requires_tool = True
            tool_name = "study_plan_service"
            response_type = ResponseTypeEnum.STUDY_PLAN.value
            decision = DecisionStateEnum.GENERATE
        elif intent in ("QUIZ", "GENERATE_QUIZ", "GENERATE_FLASHCARDS", "GENERATE_QUESTIONS"):
            action = ActionTypeEnum.GENERATE_QUIZ.value
            requires_tool = True
            tool_name = "quiz_generator"
            response_type = ResponseTypeEnum.QUIZ.value
            decision = DecisionStateEnum.GENERATE
        elif intent in ("SUMMARY", "STUDY_NOTES", "GENERATE_NOTES"):
            action = ActionTypeEnum.GENERATE_SUMMARY.value
            response_type = ResponseTypeEnum.NOTES.value if "notes" in raw_query.lower() else ResponseTypeEnum.SUMMARY.value
            decision = DecisionStateEnum.DOCUMENT_ANALYSIS
        elif intent in ("PROBLEM_SOLVING", "SOLVE_PROBLEM"):
            action = ActionTypeEnum.SOLVE_PROBLEM.value
            response_type = ResponseTypeEnum.STEP_BY_STEP.value
        elif intent in ("COMPARISON", "COMPARE_CONCEPTS"):
            action = ActionTypeEnum.EXPLAIN_TOPIC.value
            response_type = ResponseTypeEnum.COMPARISON.value
        elif intent in ("CASUAL", "GREETING", "CONFIRMATION", "OUT_OF_SCOPE"):
            action = ActionTypeEnum.CASUAL_REPLY.value
            response_type = ResponseTypeEnum.DIRECT_ANSWER.value
            decision = DecisionStateEnum.OUT_OF_SCOPE if intent == "OUT_OF_SCOPE" else DecisionStateEnum.ANSWER
        elif intent == "DOCUMENT_TOPIC_ANALYSIS":
            action = ActionTypeEnum.ANALYZE_IMPORTANT_TOPICS.value
            requires_tool = False
            response_type = ResponseTypeEnum.DETAILED_EXPLANATION.value
            decision = DecisionStateEnum.DOCUMENT_ANALYSIS
        elif intent == "CLARIFY_CONCEPT":
            action = ActionTypeEnum.CLARIFY_QUERY.value
            response_type = ResponseTypeEnum.DIRECT_ANSWER.value
            decision = DecisionStateEnum.CLARIFY
        else:
            action = ActionTypeEnum.EXPLAIN_TOPIC.value if intent == "EXPLANATION" else ActionTypeEnum.ANSWER_QUESTION.value
            response_type = ResponseTypeEnum.DETAILED_EXPLANATION.value

        if ref_meta and ref_meta.get("reference_type") in ("GENERATED_QUESTION", "GENERATED_QUIZ", "GENERATED_FLASHCARD"):
            action = ActionTypeEnum.EXPLAIN_GENERATED_QUESTION.value
            intent = UserIntent.EXPLAIN_TOPIC.value
            response_type = ResponseTypeEnum.DETAILED_EXPLANATION.value
            requires_tool = False
            decision = DecisionStateEnum.ANSWER

        if "simple" in raw_query.lower() or "beginner" in raw_query.lower() or "easy" in raw_query.lower():
            difficulty = "beginner"
            if response_type == ResponseTypeEnum.DETAILED_EXPLANATION.value:
                response_type = ResponseTypeEnum.SIMPLE_EXPLANATION.value
        else:
            difficulty = meta.difficulty_level.lower() if meta.difficulty_level else "intermediate"

        requires_retrieval = intent not in ("CASUAL", "GREETING", "CONFIRMATION", "DOCUMENT_TOPIC_ANALYSIS")
        retrieval_scope = (
            RetrievalScopeEnum.NONE.value if not requires_retrieval
            else (RetrievalScopeEnum.USER_MATERIAL.value if meta.query_scope == "global_material" or "chapter" in raw_query.lower() or "material" in raw_query.lower()
                  else (RetrievalScopeEnum.CURRENT_TOPIC.value if meta.target_topic else RetrievalScopeEnum.USER_MATERIAL.value))
        )

        requires_example = bool(re.search(r"\b(?:example|examples|instance|sample)\b", raw_query, re.IGNORECASE))

        # Extract topics for comparison
        topics = []
        if meta.target_topic:
            topics.append(meta.target_topic)
        if intent in ("COMPARISON", "COMPARE_CONCEPTS"):
            comp_m = re.search(r"\b(?:between|compare)\s+([a-zA-Z0-9_\s-]+?)\s+(?:and|vs\.?|versus)\s+([a-zA-Z0-9_\s-]+)", raw_query, re.IGNORECASE)
            if comp_m:
                t1 = comp_m.group(1).strip().title()
                t2 = comp_m.group(2).strip().title()
                topics = [t1, t2]

        action_plan = ActionPlan(
            action=action,
            decision=decision,
            topic=meta.target_topic or (topics[0] if topics else current_topic),
            subtopic=None,
            topics=topics,
            retrieval_required=requires_retrieval,
            retrieval_scope=retrieval_scope,
            retrieval_query=meta.resolved_query,
            response_type=response_type,
            requires_tool=requires_tool,
            tool_name=tool_name,
            confidence=0.92,
            clarification_prompt=meta.scope_clarification_prompt
        )

        return QueryUnderstandingResult(
            original_query=raw_query,
            normalized_query=normalized_query,
            resolved_query=resolved_query,
            language=language,
            intent=intent,
            sub_intent=None,
            subject=current_subject,
            topic=meta.target_topic or (topics[0] if topics else current_topic),
            subtopic=None,
            topics=topics,
            entities=meta.extracted_entities,
            difficulty=difficulty,
            response_type=response_type,
            requires_context=bool(meta.context_source == "dialogue_history" or meta.target_topic is not None),
            requires_retrieval=requires_retrieval,
            retrieval_scope=retrieval_scope,
            retrieval_query=meta.resolved_query,
            action=action,
            decision=decision,
            action_plan=action_plan,
            requires_tool=requires_tool,
            tool_name=tool_name,
            confidence=0.92,
            requires_example=requires_example,
            clarification_prompt=meta.scope_clarification_prompt,
            is_fast_path=False,
            requires_document_analysis=(intent == "DOCUMENT_TOPIC_ANALYSIS"),
            analysis_scope="COMPLETE_DOCUMENT" if intent == "DOCUMENT_TOPIC_ANALYSIS" else None,
            reference_type=ref_meta.get("reference_type", "NONE") if ref_meta else "NONE",
            reference_target=ref_meta.get("reference_target") if ref_meta else None,
            reference_index=ref_meta.get("reference_index") if ref_meta else None,
            artifact_item_id=ref_meta.get("artifact_item_id") if ref_meta else None,
            ambiguity_status=ref_meta.get("ambiguity_status", "CLEAR") if ref_meta else "CLEAR",
            ambiguity_type=getattr(meta, "ambiguity_type", "NONE"),
            intent_confidence=getattr(meta, "intent_confidence", 1.0),
            topic_confidence=getattr(meta, "topic_confidence", 1.0),
            reference_confidence=getattr(meta, "reference_confidence", 1.0),
            output_requirements=getattr(meta, "output_requirements", None) or OutputRequirements()
        )

    @classmethod
    def analyze_intent_and_metadata(
        cls,
        raw_query: str,
        normalized_query: str,
        resolved_query: str,
        language: str,
        is_follow_up: bool = False,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        ref_meta: Optional[Dict[str, Any]] = None,
        teacher_state: Optional[Dict[str, Any]] = None
    ) -> QueryMetadata:
        """
        Uses live LLM with conversation history for query understanding; falls back to heuristic patterns if LLM unavailable.
        """
        # Explicit topic check for teacher mode initiation
        explicit_teach_topic = cls.extract_teach_topic(raw_query)
        has_active_teacher = bool(teacher_state and teacher_state.get("mode") == "teacher")

        # 0. Deterministic Fast-Path for Casual Greetings & Acknowledgments
        # Bypassed if in an active teacher mode session or asking to be taught
        raw_lower = raw_query.lower()
        is_casual_match = any(pat.search(normalized_query) for pat in cls.CASUAL_PATTERNS) or any(pat.search(raw_lower.strip()) for pat in cls.CASUAL_PATTERNS)
        has_academic_keywords = any(w in raw_lower for w in ["what", "how", "why", "explain", "solve", "give", "question", "quiz", "page", "table", "figure", "diagram", "compare", "teach", "learn"])
        if not has_active_teacher and not explicit_teach_topic and is_casual_match and len(raw_lower.strip().split()) <= 6 and not has_academic_keywords:
            from app.tutoring.analyzer.fast_path import QueryFastPath
            fast_res = QueryFastPath.evaluate(normalized_query, raw_query, language)
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
                understanding_result=fast_res
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

                resp = default_llm_service.generate(
                    prompt=prompt,
                    system_prompt=_UNDERSTANDING_SYSTEM_PROMPT
                )
                if resp:
                    json_str = resp.strip()
                    if "```json" in json_str:
                        json_str = json_str.split("```json")[1].split("```")[0].strip()
                    elif "```" in json_str:
                        json_str = json_str.split("```")[1].split("```")[0].strip()

                    parsed = json.loads(json_str)
                    if isinstance(parsed, dict) and "intent" in parsed:
                        raw_intent = str(parsed.get("intent", "DOCUMENT_QA")).upper()
                        # Map extended intent to canonical pipeline intent if needed
                        # Check if user is confirming or continuing an ongoing teacher session
                        is_continuation_turn = bool(
                            has_active_teacher and (
                                raw_intent in ("CONFIRMATION", "CONTINUE_LEARNING")
                                or any(raw_query.lower().strip().startswith(w) for w in ["yes", "continue", "next", "proceed", "sure", "ok", "okay", "go ahead", "explain again", "make it simpler", "ready"])
                                or raw_query.lower().strip() in ["yep", "yeah", "carry on", "next please", "next subtopic", "next concept"]
                            )
                        )

                        if raw_intent == "TEACH_TOPIC" or explicit_teach_topic:
                            legacy_intent = "TEACH_TOPIC"
                        elif is_continuation_turn:
                            legacy_intent = "TEACH_TOPIC"
                        elif raw_intent in ("EXPLAIN_TOPIC", "SIMPLIFY", "CLARIFY_CONCEPT"):
                            legacy_intent = "EXPLANATION"
                        elif raw_intent in ("COMPARE_CONCEPTS",):
                            legacy_intent = "COMPARISON"
                        elif raw_intent in ("GENERATE_QUIZ", "GENERATE_FLASHCARDS"):
                            legacy_intent = "QUIZ"
                        elif raw_intent in ("GENERATE_QUESTIONS", "GENERATE_EXAMPLES"):
                            legacy_intent = "PRACTICE_QUESTIONS"
                        elif raw_intent in ("SUMMARIZE", "GENERATE_NOTES"):
                            legacy_intent = "SUMMARY" if "SUMMARIZE" in raw_intent else "STUDY_NOTES"
                        elif raw_intent in ("SOLVE_PROBLEM", "CHECK_ANSWER"):
                            legacy_intent = "PROBLEM_SOLVING"
                        elif raw_intent in ("GREETING", "CONFIRMATION"):
                            legacy_intent = "CASUAL"
                        elif raw_intent in ("ANSWER_QUESTION", "SEARCH_MATERIAL", "ASK_FROM_MATERIAL"):
                            legacy_intent = "DOCUMENT_QA"

                        intent = legacy_intent
                        raw_cs = str(parsed.get("context_source", "")).lower().strip()
                        cleaned_lower = raw_query.lower()
                        if raw_cs in ("dialogue_history", "study_material"):
                            context_source = raw_cs
                        elif any(w in cleaned_lower for w in ["our chat", "previous answer", "what did we discuss", "what did you say", "repeat that", "earlier message", "in this chat", "what we discussed", "what you said"]):
                            context_source = "dialogue_history"
                        else:
                            context_source = "study_material"

                        target_topic = explicit_teach_topic or parsed.get("target_topic") or parsed.get("topic")
                        if has_active_teacher and not target_topic:
                            target_topic = teacher_state.get("topic")
                        question_count = parsed.get("question_count")
                        referenced_page = parsed.get("referenced_page")
                        referenced_table = parsed.get("referenced_table")
                        format_directives = parsed.get("format_directives") or {}
                        entities = parsed.get("entities") or []
                        
                        raw_out_reqs = parsed.get("output_requirements") or {}
                        from app.schemas.tutoring import OutputRequirements
                        out_reqs = OutputRequirements(
                            format=raw_out_reqs.get("format", "DEFAULT"),
                            length=raw_out_reqs.get("length", "DEFAULT"),
                            include_explanation=raw_out_reqs.get("include_explanation", True),
                            include_examples=raw_out_reqs.get("include_examples", False),
                            include_steps=raw_out_reqs.get("include_steps", False),
                            include_sources=raw_out_reqs.get("include_sources", False),
                            include_question=raw_out_reqs.get("include_question", False)
                        )
                        
                        if intent == "STUDY_NOTES":
                            format_directives["generate_study_notes"] = True
                        if ": " in resolved_query and re.search(r"\b(?:question|q|problem|item)\s*(?:#|no\.?|num\.?)?\s*\d+\b", raw_query, re.IGNORECASE):
                            parts = resolved_query.split(": ", 1)
                            if len(parts) == 2 and len(parts[1].strip()) >= 5:
                                format_directives["referenced_question_text"] = parts[1].strip()
                        if target_topic and target_topic not in entities:
                            entities.insert(0, target_topic)

                        needs_latex = bool(parsed.get("needs_latex", False)) or any(w in raw_query.lower() for w in ["formula", "equation", "math", "derive"])
                        needs_table = bool(parsed.get("needs_table", False))
                        refined_query = parsed.get("resolved_query") or resolved_query

                        # Extract visual modality and cognitive diagram type
                        visual_modality = str(parsed.get("visual_modality", "none")).lower().strip()
                        # All diagrams now rendered as SVG (mermaid removed)
                        if visual_modality in ("mermaid", "svg"):
                            visual_modality = "svg"
                        else:
                            visual_modality = "none"

                        visual_diagram_type = str(parsed.get("visual_diagram_type", "none")).lower().strip()
                        valid_diagram_types = (
                            "none", "flowchart_lr", "flowchart_td", "concept_graph",
                            "sequence", "state_diagram", "mindmap", "svg"
                        )
                        if visual_diagram_type not in valid_diagram_types:
                            if visual_modality == "svg":
                                visual_diagram_type = "svg"
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
                            visual_modality = "svg"
                            visual_diagram_type = "flowchart_lr"
                            visual_prompt_focus = f"Sequential horizontal flowchart (LR) of {target_topic or refined_query}"
                        elif visual_modality == "none" or visual_diagram_type in ("none", "mindmap"):
                            # Cognitive topology refinement:
                            # 1. Explicit Mindmap requests
                            if any(k in raw_lower for k in ["mindmap", "mind map", "concept map"]):
                                visual_modality = "svg"
                                visual_diagram_type = "mindmap"
                                visual_prompt_focus = f"Mindmap of core branches for {target_topic or refined_query}"
                            # 2. Explicit Flowchart requests
                            elif any(k in raw_lower for k in ["flowchart", "flow chart"]):
                                is_seq = any(k in raw_lower for k in ["evolution", "phase", "step", "stage", "timeline"])
                                visual_modality = "svg"
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
                                visual_modality = "svg"
                                visual_diagram_type = "concept_graph"
                                visual_prompt_focus = f"Concept relationship graph connecting core exam topics and question themes for {target_topic or refined_query}"
                            # 6. Protocols / Multi-actor interactions -> sequence
                            elif any(k in raw_lower for k in ["handshake", "protocol", "client-server", "client server", "oauth", "api exchange", "message exchange"]):
                                visual_modality = "svg"
                                visual_diagram_type = "sequence"
                                visual_prompt_focus = f"Sequence diagram of {target_topic or refined_query}"
                            # 7. State transitions -> state_diagram
                            elif any(k in raw_lower for k in ["state machine", "fsm", "state diagram", "lifecycle states", "status transitions"]):
                                visual_modality = "svg"
                                visual_diagram_type = "state_diagram"
                                visual_prompt_focus = f"State diagram of {target_topic or refined_query}"
                            # 8. Scientific, spatial, anatomical, physical, geometric -> svg
                            elif any(k in raw_lower for k in ["image", "diagram", "draw", "picture", "figure", "visualize", "illustration", "svg", "anatomy", "triangle", "vector", "cell", "atom", "force", "optic", "hyperplane", "circuit"]):
                                visual_modality = "svg"
                                visual_diagram_type = "svg"
                                visual_prompt_focus = f"Technical vector illustration of {target_topic or refined_query}"
                            # 9. Unordered syllabus pillars -> mindmap
                            elif any(k in raw_lower for k in ["syllabus", "curriculum", "chapters", "table of content", "core pillars", "pillars"]):
                                visual_modality = "svg"
                                visual_diagram_type = "mindmap"
                                visual_prompt_focus = f"Mindmap of core syllabus pillars, topics, and relationships for {target_topic or refined_query}"
                            # 10. Decision trees, hierarchies, classifications -> flowchart_td
                            elif any(k in raw_lower for k in ["hierarchy", "classification", "tree"]):
                                visual_modality = "svg"
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

                        meta_res = QueryMetadata(
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
                            difficulty_level=parsed.get("difficulty", "Intermediate").capitalize(),
                            response_requirements={
                                "needs_latex": needs_latex,
                                "needs_table": needs_table,
                                "needs_steps": False,
                                "needs_socratic": True
                            },
                            visual_modality=visual_modality,
                            visual_diagram_type=visual_diagram_type,
                            visual_prompt_focus=visual_prompt_focus,
                            question_complexity="comparative" if intent == "COMPARISON" else ("multi_hop" if len(entities) > 2 else "simple"),
                            is_pasted_mcq=is_pasted_mcq,
                            is_batch_questions=is_batch_questions,
                            batch_question_count=batch_question_count,
                            query_scope=query_scope,
                            scope_clarification_prompt=scope_clarification_prompt,
                            output_requirements=out_reqs,
                            pre_gen_plan=pre_gen_plan
                        )
                        
                        setattr(meta_res, "intent_confidence", parsed.get("intent_confidence", 1.0))
                        setattr(meta_res, "topic_confidence", parsed.get("topic_confidence", 1.0))
                        setattr(meta_res, "reference_confidence", parsed.get("reference_confidence", 1.0))
                        setattr(meta_res, "ambiguity_type", parsed.get("ambiguity_type", "NONE"))

                        meta_res.understanding_result = cls._build_structured_result_from_meta(
                            meta_res, raw_query, normalized_query, refined_query, language, None, target_topic, ref_meta
                        )
                        # Override with explicitly generated fields if provided
                        if "decision" in parsed:
                            meta_res.understanding_result.decision = parsed["decision"]
                            meta_res.understanding_result.action_plan.decision = parsed["decision"]
                        if "answerability" in parsed:
                            from app.schemas.tutoring import AnswerabilityCheck
                            meta_res.understanding_result.answerability = AnswerabilityCheck(**parsed["answerability"])
                        if "clarification_needed" in parsed:
                            meta_res.understanding_result.clarification_needed = parsed["clarification_needed"]
                        if "clarification_question" in parsed:
                            meta_res.understanding_result.clarification_question = parsed["clarification_question"]
                        if "missing_information" in parsed:
                            meta_res.understanding_result.missing_information = parsed["missing_information"]
                        if ref_meta and ref_meta.get("reference_type") in ("GENERATED_QUESTION", "GENERATED_QUIZ", "GENERATED_FLASHCARD"):
                            meta_res.understanding_result.action = "EXPLAIN_GENERATED_QUESTION"
                            meta_res.understanding_result.intent = "EXPLAIN_TOPIC"
                            meta_res.understanding_result.requires_tool = False
                            meta_res.understanding_result.reference_type = ref_meta["reference_type"]
                            meta_res.understanding_result.reference_index = ref_meta.get("reference_index")
                            meta_res.understanding_result.artifact_id = ref_meta.get("artifact_id")
                            meta_res.understanding_result.artifact_item_id = ref_meta.get("artifact_item_id")
                            meta_res.understanding_result.topic = ref_meta.get("resolved_topic") or meta_res.understanding_result.topic
                        return meta_res
            except Exception as e:
                logger.warning(f"[QueryUnderstanding] LLM understanding pass failed, falling back to heuristics: {e}")

        # 2. Heuristic Fallback
        meta_fallback = cls._heuristic_analysis(
            raw_query=raw_query,
            normalized_query=normalized_query,
            resolved_query=resolved_query,
            language=language,
            is_follow_up=is_follow_up,
            conversation_history=conversation_history,
            teacher_state=teacher_state
        )
        meta_fallback.understanding_result = cls._build_structured_result_from_meta(
            meta_fallback, raw_query, normalized_query, resolved_query, language
        )
        if ref_meta and ref_meta.get("reference_type") in ("GENERATED_QUESTION", "GENERATED_QUIZ", "GENERATED_FLASHCARD"):
            meta_fallback.understanding_result.action = "EXPLAIN_GENERATED_QUESTION"
            meta_fallback.understanding_result.intent = "EXPLAIN_TOPIC"
            meta_fallback.understanding_result.requires_tool = False
            meta_fallback.understanding_result.reference_type = ref_meta["reference_type"]
            meta_fallback.understanding_result.reference_index = ref_meta.get("reference_index")
            meta_fallback.understanding_result.artifact_id = ref_meta.get("artifact_id")
            meta_fallback.understanding_result.artifact_item_id = ref_meta.get("artifact_item_id")
            meta_fallback.understanding_result.topic = ref_meta.get("resolved_topic") or meta_fallback.understanding_result.topic
        return meta_fallback

    @classmethod
    def _heuristic_analysis(
        cls,
        raw_query: str,
        normalized_query: str,
        resolved_query: str,
        language: str,
        is_follow_up: bool,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        teacher_state: Optional[Dict[str, Any]] = None
    ) -> QueryMetadata:
        cleaned = resolved_query.strip().lower()
        explicit_teach_topic = cls.extract_teach_topic(raw_query) or cls.extract_teach_topic(resolved_query)
        has_active_teacher = bool(teacher_state and teacher_state.get("mode") == "teacher")

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
        if cls.DOCUMENT_TOPIC_ANALYSIS_PATTERN.search(cleaned):
            intent = "DOCUMENT_TOPIC_ANALYSIS"
        elif is_pasted_mcq or is_batch_questions:
            intent = "PROBLEM_SOLVING"
        elif any(w in cleaned for w in ["study plan", "study-plan", "study schedule", "learning schedule", "create plan", "make a plan"]):
            intent = "CREATE_STUDY_PLAN"
        elif any(w in cleaned for w in ["study notes", "revision notes", "make notes", "give me notes", "cheat sheet"]):
            intent = "STUDY_NOTES"
        elif any(pat.search(cleaned) for pat in cls.CASUAL_PATTERNS) and len(cleaned.split()) <= 4:
            intent = "CASUAL"
        elif any(pat.search(cleaned) for pat in cls.QUIZ_PATTERNS):
            intent = "QUIZ"
        elif "table" in cleaned and any(w in cleaned for w in ["solve", "fill", "calculate", "complete"]):
            intent = "PROBLEM_SOLVING"
        elif any(pat.search(cleaned) for pat in cls.PRACTICE_QUESTIONS_PATTERNS) and ("question" in cleaned or "problem" in cleaned):
            intent = "PRACTICE_QUESTIONS"
        elif any(pat.search(cleaned) for pat in cls.COMPARISON_PATTERNS):
            intent = "COMPARISON"
        elif any(pat.search(cleaned) for pat in cls.SUMMARY_PATTERNS):
            intent = "SUMMARY"
        elif any(pat.search(cleaned) for pat in cls.PROBLEM_SOLVING_PATTERNS):
            intent = "PROBLEM_SOLVING"
        elif any(pat.search(cleaned) for pat in cls.ANSWER_CHALLENGE_PATTERNS):
            intent = "ANSWER_CHALLENGE"
        elif explicit_teach_topic or any(pat.search(cleaned) for pat in cls.TEACH_TOPIC_PATTERNS):
            intent = "TEACH_TOPIC"
            target_topic = explicit_teach_topic or cls.extract_teach_topic(raw_query)
        elif has_active_teacher and (
            any(cleaned.startswith(w) for w in ["yes", "continue", "next", "proceed", "sure", "ok", "okay", "go ahead", "explain again", "make it simpler", "ready"])
            or cleaned in ["yep", "yeah", "carry on", "next please", "next subtopic", "next concept"]
        ):
            intent = "TEACH_TOPIC"
            target_topic = teacher_state.get("topic") if teacher_state else None
        elif is_follow_up:
            intent = "FOLLOW_UP"
        elif any(w in cleaned for w in ["explain", "how does", "why does", "deep dive"]):
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
            visual_modality = "svg"
            visual_diagram_type = "mindmap"
            visual_prompt_focus = f"Mindmap of core branches and topics for {target_topic or resolved_query}"
        # 2. Explicit Flowchart requests (e.g. "draw a flowchart of...")
        elif any(w in cleaned for w in ["flowchart", "flow chart"]):
            visual_modality = "svg"
            visual_diagram_type = "flowchart_lr" if any(w in cleaned for w in flowchart_lr_triggers) else "flowchart_td"
            visual_prompt_focus = f"Flowchart of {target_topic or resolved_query}"
        # 3. Network protocols & interactions
        elif any(w in cleaned for w in sequence_triggers):
            visual_modality = "svg"
            visual_diagram_type = "sequence"
            visual_prompt_focus = f"Sequence diagram of {target_topic or resolved_query}"
        # 4. Algorithms & Data Structures -> HIGH PRIORITY FOR INLINE SVG
        elif any(w in cleaned for w in algorithm_svg_triggers):
            visual_modality = "svg"
            visual_diagram_type = "svg"
            visual_prompt_focus = f"Step-by-step vector illustration of {target_topic or resolved_query} algorithm with visual pointers and states"
        # 5. Chronological / Evolutionary / Sequential Progressions (NEVER A MINDMAP)
        elif any(w in cleaned for w in flowchart_lr_triggers):
            visual_modality = "svg"
            visual_diagram_type = "flowchart_lr"
            visual_prompt_focus = f"Sequential horizontal flowchart (LR) illustrating the phases/evolution of {target_topic or resolved_query}"
        # 6. Important Questions / Whole Material -> Concept relationship graph
        elif query_scope == "global_material" or any(w in cleaned for w in concept_graph_triggers):
            visual_modality = "svg"
            visual_diagram_type = "concept_graph"
            if query_scope == "global_material":
                visual_prompt_focus = "Conceptual relationship network mapping the core pillars across the entire study material curriculum"
            else:
                visual_prompt_focus = f"Concept relationship network mapping core exam topics and question themes for {target_topic or resolved_query}"
        # 7. State transitions
        elif any(w in cleaned for w in state_triggers):
            visual_modality = "svg"
            visual_diagram_type = "state_diagram"
            visual_prompt_focus = f"State diagram of {target_topic or resolved_query}"
        # 8. General flowcharts / hierarchies / classifications
        elif any(w in cleaned for w in flowchart_td_triggers):
            visual_modality = "svg"
            visual_diagram_type = "flowchart_td"
            visual_prompt_focus = f"Flowchart or classification hierarchy for {target_topic or resolved_query}"
        # 9. Unordered syllabus pillars (Radial mindmap)
        elif any(w in cleaned for w in mindmap_triggers):
            visual_modality = "svg"
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
            understanding_result=cls._build_structured_result_from_meta(
                meta=QueryMetadata(
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
                ),
                raw_query=raw_query,
                normalized_query=normalized_query,
                resolved_query=resolved_query,
                language=language
            )
        )

