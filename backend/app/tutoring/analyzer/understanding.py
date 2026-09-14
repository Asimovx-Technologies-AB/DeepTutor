import re
import json
import logging
from typing import List, Dict, Any, Optional
from app.schemas.tutoring import QueryMetadata
from app.services.llm_service import default_llm_service

logger = logging.getLogger(__name__)

_UNDERSTANDING_SYSTEM_PROMPT = """You are the cognitive Query Understanding & Reasoning module for DeepTutor, an elite AI Professor.
Analyze the student's message in the context of the recent study dialogue and return ONLY a valid JSON object.

Intent Taxonomy:
- "PRACTICE_QUESTIONS": Student asks for questions, exercises, or exam preparation problems to study/practice (e.g. "give me 5 questions in svm", "i have exam tomorrow give me questions on chapter 2", "only need questions", "practice questions").
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

Output JSON format:
{
  "intent": "PRACTICE_QUESTIONS" | "QUIZ" | "EXPLANATION" | "COMPARISON" | "PROBLEM_SOLVING" | "SUMMARY" | "CASUAL" | "FOLLOW_UP" | "DOCUMENT_QA",
  "target_topic": "The exact subject concept (e.g. 'Support Vector Machines (SVM)'). Ground in conversation history if query is an implicit follow-up.",
  "question_count": 5, // integer count if requested or applicable, or null
  "referenced_page": 22, // integer page number if user mentioned a page, or null
  "referenced_table": "Table 1.2", // string table name or "table" if user mentioned a table, or null
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
        re.compile(r"^(?:thanks|thank\s+you|awesome|cool|bye|goodbye)\b", re.IGNORECASE),
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
                        target_topic = parsed.get("target_topic")
                        question_count = parsed.get("question_count")
                        referenced_page = parsed.get("referenced_page")
                        referenced_table = parsed.get("referenced_table")
                        format_directives = parsed.get("format_directives") or {}
                        entities = parsed.get("entities") or []
                        if target_topic and target_topic not in entities:
                            entities.insert(0, target_topic)

                        needs_latex = bool(parsed.get("needs_latex"))
                        needs_table = bool(parsed.get("needs_table"))
                        refined_query = parsed.get("resolved_query") or resolved_query

                        # Safety check for page/table patterns in raw_query if LLM missed it
                        if referenced_page is None:
                            page_m = cls.PAGE_PATTERN.search(raw_query)
                            if page_m:
                                referenced_page = int(page_m.group(1))
                        if referenced_table is None:
                            tbl_m = cls.TABLE_PATTERN.search(raw_query)
                            if tbl_m:
                                referenced_table = tbl_m.group(1).title() if tbl_m.group(1) else "table"

                        # Safety check: if user asked "only need questions" or "just questions", enforce questions_only
                        if re.search(r"\b(?:only\s+(?:need\s+)?questions?|just\s+questions?|no\s+answers?)\b", raw_query, re.IGNORECASE):
                            format_directives["questions_only"] = True
                            format_directives["include_answers"] = False

                        if "table" in raw_query.lower() and any(w in raw_query.lower() for w in ["solve", "fill", "calculate", "complete", "check"]):
                            format_directives["solve_table"] = True
                            format_directives["include_complete_table"] = True
                            needs_table = True

                        return QueryMetadata(
                            raw_query=raw_query,
                            language=language,
                            normalized_query=normalized_query,
                            resolved_query=refined_query,
                            intent=intent,
                            target_topic=target_topic,
                            question_count=int(question_count) if question_count else None,
                            referenced_page=int(referenced_page) if referenced_page is not None else None,
                            referenced_table=referenced_table,
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
                            question_complexity="comparative" if intent == "COMPARISON" else "simple",
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

        # Extract count if present
        count_match = re.search(r"\b(\d+)\s*(?:questions?|mcqs?|flashcards?|cards?|problems?)\b", cleaned)
        question_count = int(count_match.group(1)) if count_match else None

        # Extract topic from "in <topic>", "on <topic>", "for <topic>", "about <topic>"
        topic_match = re.search(r"\b(?:in|on|about|for|regarding)\s+([a-zA-Z0-9_\s-]+)$", cleaned)
        target_topic = None
        if topic_match:
            candidate = topic_match.group(1).strip()
            candidate = re.sub(r"[?!.,;]+$", "", candidate).strip()
            if candidate and candidate not in ("this", "it", "here", "them", "tomorrow", "exam"):
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

        # Format directives
        format_directives: Dict[str, Any] = {}
        if re.search(r"\b(?:only\s+(?:need\s+)?questions?|just\s+questions?|no\s+answers?)\b", cleaned):
            format_directives["questions_only"] = True
            format_directives["include_answers"] = False

        if "table" in cleaned and any(w in cleaned for w in ["solve", "fill", "calculate", "complete", "check"]):
            format_directives["solve_table"] = True
            format_directives["include_complete_table"] = True

        # Intent Detection
        if any(pat.search(cleaned) for pat in cls.CASUAL_PATTERNS) and len(cleaned.split()) <= 4:
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

        raw_entities = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", resolved_query)
        action_verbs = {"Compare", "Explain", "Analyze", "Describe", "Define", "Discuss", "Show", "What", "How", "Why", "Tell", "Give"}
        for ent in raw_entities:
            words = ent.split()
            if words and words[0] not in action_verbs:
                entities.append(ent)

        needs_latex = bool(re.search(r"[∑∫√∂≤≥±=+\-*/^]|\b(?:formulas?|equations?|math|calculate|integral)\b", resolved_query, re.IGNORECASE))
        needs_table = bool(referenced_table or re.search(r"\b(?:table|comparison|tabular|columns|matrix)\b", resolved_query, re.IGNORECASE))

        return QueryMetadata(
            raw_query=raw_query,
            language=language,
            normalized_query=normalized_query,
            resolved_query=resolved_query,
            intent=intent,
            target_topic=target_topic,
            question_count=question_count,
            referenced_page=referenced_page,
            referenced_table=referenced_table,
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
            question_complexity="comparative" if intent == "COMPARISON" else "simple",
        )

