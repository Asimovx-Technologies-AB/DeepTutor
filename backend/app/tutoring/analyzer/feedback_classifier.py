import re
import json
import logging
from typing import List, Dict, Any, Optional
from app.schemas.tutoring import (
    UserMessageClassificationEnum,
    UserMessageClassificationResult
)
from app.services.llm_service import default_llm_service
from app.tutoring.teaching.factual_handler import FactualQueryHandler

logger = logging.getLogger(__name__)

_CORRECTION_PATTERNS = [
    re.compile(r"^(?:wrong|wrong\s+answer|(?:that|this|it)(?:'?s|\s+is)\s+wrong)$", re.IGNORECASE),
    re.compile(r"^(?:incorrect|(?:that|this|it)(?:'?s|\s+is)\s+incorrect)$", re.IGNORECASE),
    re.compile(r"^(?:not\s+correct|(?:that|this|it)(?:'?s|\s+is)\s+not\s+correct)$", re.IGNORECASE),
    re.compile(r"^(?:not\s+right|(?:that|this|it)(?:'?s|\s+is)\s+not\s+right)$", re.IGNORECASE),
    re.compile(r"^(?:that'?s\s+not\s+what\s+i\s+meant|not\s+what\s+i\s+meant|not\s+what\s+i\s+asked)$", re.IGNORECASE),
    re.compile(r"^(?:no|nope|nah)[.!]*$", re.IGNORECASE),
    re.compile(r"\b(?:you\s+are\s+wrong|you'?re\s+wrong|your\s+answer\s+is\s+wrong|your\s+explanation\s+is\s+wrong)\b", re.IGNORECASE),
    re.compile(r"\b(?:you\s+made\s+a\s+mistake|there\s+is\s+a\s+mistake|error\s+in\s+(?:your\s+)?answer)\b", re.IGNORECASE),
    re.compile(r"\b(?:you\s+misunderstood|i\s+didn'?t\s+ask\s+that)\b", re.IGNORECASE),
    re.compile(r"\b(?:actually\s+(?:it'?s|that'?s|the\s+answer\s+is))\b", re.IGNORECASE),
]

_CONTINUATION_PATTERNS = [
    re.compile(r"^(?:yes|continue|next|proceed|go\s+ahead|sure|ok|okay|carry\s+on|ready)[.!]*$", re.IGNORECASE),
    re.compile(r"^(?:explain\s+the\s+next|next\s+subtopic|next\s+concept|next\s+one)[.!]*$", re.IGNORECASE),
    re.compile(r"^(?:more\s+details?|tell\s+me\s+more|elaborate|keep\s+going)[.!]*$", re.IGNORECASE),
]

_CLARIFICATION_PATTERNS = [
    re.compile(r"\b(?:(?:what\s+)?i\s+(?:really\s+)?mean(?:t)?\s*(?:is|was)?|i'm\s+saying|i\s+am\s+saying|what\s+i'm\s+saying\s+is)\b", re.IGNORECASE),
    re.compile(r"\b(?:by\s+[^,;]+?\s+i\s+mean(?:t)?)\b", re.IGNORECASE),
    re.compile(r"\b(?:everything|all)\s+means\b", re.IGNORECASE),
    re.compile(r"\b(?:means|meaning)\s+(?:all|everything|that|to\s+say|the\s+whole)\b", re.IGNORECASE),
    re.compile(r"^(?:i\s+mean|i\s+meant)\b", re.IGNORECASE),
    re.compile(r"\bmeans\s+all\s+(?:the\s+)?topics?\b", re.IGNORECASE),
]

_TEACH_PATTERNS = [
    re.compile(r"\b(?:teach\s+me|teach\s+us|act\s+as\s+a\s+teacher|start\s+teaching|start\s+teacher\s+mode|start\s+teaching\s+mode|teach\s+step\s+by\s+step|teach\s+topic|teach\s+lesson)\b", re.IGNORECASE),
]

_STUDY_MATERIAL_KEYWORDS = [
    "document", "material", "uploaded", "notes", "textbook", "pdf", "chapter", "slide",
    "table in page", "page ", "diagram in", "syllabus", "summary of document", "what does the author say"
]

_QUESTION_PATTERNS = [
    re.compile(r"^(?:what|how|why|when|where|which|who|can\s+you|could\s+you|explain|teach|tell\s+me|give\s+me|show\s+me|is\s+it|are\s+there|does\s+it|do\s+we)\b", re.IGNORECASE),
    re.compile(r"\?$", re.IGNORECASE),
]

_CLASSIFIER_PROMPT = """You are DeepTutor's Dialogue Intent & Context Classifier.
Analyze the user's latest message together with the preceding conversation context.

Determine which category best describes the user's message:
1. "FEEDBACK_CORRECTION": The user is disputing, correcting, or providing negative feedback about the AI's previous answer or explanation (e.g., "wrong", "that's wrong", "incorrect", "no", "not correct", "you are wrong", "that's not what I meant", "actually it is 4 not 5").
2. "NEW_QUESTION_REQUEST": A new student question or request to explain, define, or understand a topic, concept, formula, or algorithm (e.g., "What is gradient descent?", "Can you explain backpropagation?", "what is svm , explain with a figure", "explain decision trees").
3. "GENERAL_FACTUAL": A simple, standalone factual, mathematical, or scientific question that can be answered from general world knowledge without needing a specific uploaded PDF (e.g., "what is 81?", "what is eight one?", "what is the second element in periodic table?", "what is the speed of light?", "who invented the telephone?").
4. "STUDY_MATERIAL_QUESTION": A question specifically about or referencing the uploaded study document, course notes, specific chapter, page text, or document content (e.g. "what does page 4 say?", "according to chapter 2", "in the uploaded slides").
5. "UNRELATED_CHAT": Casual conversation, everyday greetings, or off-topic chit-chat unrelated to academic learning.
6. "STATEMENT_EVALUATION": The student is asserting a factual claim, sharing an attempted answer, or answering an earlier question.
7. "CLARIFICATION_CONTINUATION": Confirming, continuing, asking for simpler explanation, or asking a direct follow-up on the current topic.
8. "TEACH_TOPIC_REQUEST": An explicit request to enter interactive teaching/lecture mode (e.g., "teach me SVM", "act as a teacher and teach me Decision Trees", "start teacher mode", "start teaching").

CRITICAL RULES:
- Short feedback messages like "wrong", "wrong answer", "that's wrong", "incorrect", "no", "not correct", "this is wrong", "that's not what I meant" must ALWAYS be classified as FEEDBACK_CORRECTION, NEVER as a new question!
- If the user asks a simple general factual question (like "what is 81", "what is eight one", "what is the second element"), classify as GENERAL_FACTUAL.
- Never classify a general factual question as UNRELATED_CHAT.
- CRITICAL: "TEACH_TOPIC_REQUEST" requires the user to EXPLICITLY use words like "teach me", "act as a teacher", "start teacher mode", "start teaching", "teach step by step". Standard questions and requests to explain (such as "what is X", "explain X", "explain with a figure", "how does X work", "why...") must NEVER be classified as TEACH_TOPIC_REQUEST! Classify them as NEW_QUESTION_REQUEST or GENERAL_FACTUAL.

Respond ONLY with a JSON object:
{
  "category": "FEEDBACK_CORRECTION" | "NEW_QUESTION_REQUEST" | "GENERAL_FACTUAL" | "STUDY_MATERIAL_QUESTION" | "UNRELATED_CHAT" | "STATEMENT_EVALUATION" | "CLARIFICATION_CONTINUATION" | "TEACH_TOPIC_REQUEST",
  "confidence": 0.0 to 1.0,
  "reasoning": "Brief rationale"
}"""


class UserMessageContextClassifier:
    """
    Analyzes user messages with conversation context to discern whether the student
    is providing feedback/correction, asking a general factual question, asking about
    study material, engaging in unrelated chat, or making a factual statement.
    """

    @classmethod
    def classify_message(
        cls,
        raw_query: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        current_topic: Optional[str] = None,
        has_active_document: bool = True,
    ) -> UserMessageClassificationResult:
        query_clean = raw_query.strip()
        query_lower = query_clean.lower()
        history = conversation_history or []

        query_clean_nopunct = query_clean.rstrip(".?! \t")

        # 0. HIGHEST PRIORITY: Exam report requests must never be misclassified
        from app.tutoring.exam.engine import is_exam_report_intent
        if is_exam_report_intent(query_clean):
            return UserMessageClassificationResult(
                category=UserMessageClassificationEnum.GENERAL_FACTUAL,
                confidence=0.99,
                reasoning=f"Exam report request detected: '{query_clean}'. Routing to EXAM_REPORT pipeline.",
                is_exam_report=True,
            )

        # 1. PRIORITY 1: Fast deterministic regex matching for corrections/challenges
        for pat in _CORRECTION_PATTERNS:
            if pat.search(query_clean) or pat.search(query_clean_nopunct):
                # Edge case: if previous message explicitly asked a yes/no question like "Is X true?",
                # "no" might be an answer to that question rather than disputing the tutor.
                if query_clean_nopunct.lower() in ["no", "nope", "nah"] and history:
                    last_bot = history[-1].get("content", "") if history[-1].get("role") == "assistant" else ""
                    if "is this true or false" in last_bot.lower() or "answer yes or no" in last_bot.lower():
                        return UserMessageClassificationResult(
                            category=UserMessageClassificationEnum.STATEMENT_EVALUATION,
                            confidence=0.95,
                            reasoning="User answered 'no' to a true/false or yes/no question from the tutor.",
                            target_statement=query_clean,
                        )

                return UserMessageClassificationResult(
                    category=UserMessageClassificationEnum.FEEDBACK_CORRECTION,
                    confidence=0.99,
                    reasoning=f"Matched explicit correction pattern: '{query_clean}'",
                    target_statement=query_clean,
                )

        # 2. Fast deterministic matching for continuation
        for pat in _CONTINUATION_PATTERNS:
            if pat.search(query_clean) or pat.search(query_clean_nopunct):
                return UserMessageClassificationResult(
                    category=UserMessageClassificationEnum.CLARIFICATION_CONTINUATION,
                    confidence=0.98,
                    reasoning=f"Matched continuation pattern: '{query_clean}'",
                )

        # 2b. Fast deterministic matching for user clarifications / meta-dialogue ("X means Y", "i mean X")
        for pat in _CLARIFICATION_PATTERNS:
            if pat.search(query_clean) or pat.search(query_clean_nopunct):
                return UserMessageClassificationResult(
                    category=UserMessageClassificationEnum.CLARIFICATION_CONTINUATION,
                    confidence=0.98,
                    reasoning=f"Matched user clarification/meta-dialogue pattern: '{query_clean}'",
                )

        # 3. Fast deterministic matching for explicit teaching mode requests
        for pat in _TEACH_PATTERNS:
            if pat.search(query_clean):
                return UserMessageClassificationResult(
                    category=UserMessageClassificationEnum.TEACH_TOPIC_REQUEST,
                    confidence=0.95,
                    reasoning="User explicitly requested interactive teaching mode.",
                )

        # 4. Check for known ambiguous queries (e.g. "what is eight one?")
        ambig_q = FactualQueryHandler.check_ambiguity(query_clean)
        if ambig_q:
            return UserMessageClassificationResult(
                category=UserMessageClassificationEnum.GENERAL_FACTUAL,
                confidence=0.95,
                reasoning="Query has phonetic or entity ambiguity requiring clarification.",
                is_ambiguous=True,
                ambiguity_clarification=ambig_q,
            )

        # 5. Check if query is explicitly asking about the active topic or uploaded study material
        is_material_explicit = any(k in query_lower for k in _STUDY_MATERIAL_KEYWORDS)
        is_topic_match = bool(current_topic and len(current_topic.strip()) >= 3 and current_topic.lower() in query_lower)
        if (is_material_explicit or is_topic_match) and has_active_document:
            return UserMessageClassificationResult(
                category=UserMessageClassificationEnum.STUDY_MATERIAL_QUESTION,
                confidence=0.92,
                reasoning="Query explicitly references active topic or study material/notes/document.",
            )

        # 6. Check for simple general factual question patterns
        # e.g., "what is 81", "what is the second element", "what is 2 + 2", "who discovered X"
        has_question_pattern = any(pat.search(query_clean) for pat in _QUESTION_PATTERNS)
        simple_factual_triggers = [
            "element in periodic table", "second element", "first element", "third element",
            "speed of light", "capital of", "who invented", "who discovered",
            "atomic number", "boiling point", "square root of", "what is the formula of",
            "answer only", "i need answer only", "just the answer", "only the answer"
        ]
        is_number_factual = bool(re.search(r"^(?:what\s+is|what's|calculate)\s+(?:the\s+)?(?:\d+|[0-9+\-*/^().\s]+)\??$", query_clean, re.IGNORECASE))
        is_element_factual = bool(re.search(r"\b(?:first|second|third|fourth|fifth|\d+(?:st|nd|rd|th)?)\s+element\b", query_lower))

        if any(trig in query_lower for trig in simple_factual_triggers) or is_number_factual or is_element_factual:
            return UserMessageClassificationResult(
                category=UserMessageClassificationEnum.GENERAL_FACTUAL,
                confidence=0.95,
                reasoning="Matched simple factual knowledge trigger.",
            )

        # 7. Declarative statement check: if not a question and contains factual claim words
        words = query_clean.split()
        if not has_question_pattern and len(words) >= 2:
            # Exclude personal/conversational directives from academic statement evaluation
            first_w = words[0].lower()
            is_conversational = first_w in ["i", "we", "you", "let", "can", "please"] or any(
                query_lower.startswith(prefix) for prefix in [
                    "i mean", "i meant", "what i mean", "everything means", "all means",
                    "teach me", "tell me", "show me", "give me", "i want", "help me"
                ]
            )
            if not is_conversational:
                statement_indicators = [
                    " is ", " are ", " was ", " were ", " has ", " have ", " does ", " means ",
                    " equals ", " causes ", " results in ", " consists of ", " used for ", " because ",
                    " produces ", " creates ", " generates ", " forms ", " releases ", " contains ", " represents "
                ]
                if any(ind in f" {query_lower} " for ind in statement_indicators):
                    return UserMessageClassificationResult(
                        category=UserMessageClassificationEnum.STATEMENT_EVALUATION,
                        confidence=0.85,
                        reasoning="Contains declarative copula/relation indicating a factual statement.",
                        target_statement=query_clean,
                    )

        # 8. Fallback to lightweight LLM classification for nuanced inputs
        recent_history_str = "\n".join([
            f"{m.get('role', 'user')}: {m.get('content', '')[:200]}"
            for m in history[-3:]
        ]) if history else "None (Start of conversation)"

        prompt = (
            f"Topic: {current_topic or 'General Academic Study'}\n"
            f"Recent Dialogue Context:\n{recent_history_str}\n\n"
            f"Latest Student Message: \"{query_clean}\"\n\n"
            f"Classify the latest student message into JSON:"
        )

        try:
            resp = default_llm_service.generate(
                prompt=prompt,
                system_prompt=_CLASSIFIER_PROMPT,
            )
            if resp:
                clean_json = resp.strip()
                if "```json" in clean_json:
                    clean_json = clean_json.split("```json")[1].split("```")[0].strip()
                elif "```" in clean_json:
                    clean_json = clean_json.split("```")[1].split("```")[0].strip()
                parsed = json.loads(clean_json)
                cat_str = parsed.get("category", "NEW_QUESTION_REQUEST")
                try:
                    cat_enum = UserMessageClassificationEnum(cat_str)
                except ValueError:
                    cat_enum = UserMessageClassificationEnum.NEW_QUESTION_REQUEST

                # Programmatic guardrail: TEACH_TOPIC_REQUEST requires explicit teaching phrasing
                if cat_enum == UserMessageClassificationEnum.TEACH_TOPIC_REQUEST:
                    has_explicit_teach = any(pat.search(query_clean) for pat in _TEACH_PATTERNS)
                    if not has_explicit_teach:
                        cat_enum = UserMessageClassificationEnum.NEW_QUESTION_REQUEST
                        logger.info(f"[UserMessageContextClassifier] Guardrail: demoted TEACH_TOPIC_REQUEST without explicit teaching phrasing to NEW_QUESTION_REQUEST for query: {query_clean!r}")

                return UserMessageClassificationResult(
                    category=cat_enum,
                    confidence=float(parsed.get("confidence", 0.8)),
                    reasoning=parsed.get("reasoning", "LLM context classification"),
                    target_statement=query_clean if cat_enum == UserMessageClassificationEnum.STATEMENT_EVALUATION else None
                )
        except Exception as e:
            logger.warning(f"[UserMessageContextClassifier] LLM classification fallback failed: {e}")

        # Default safe fallback: if question pattern, treat as GENERAL_FACTUAL / NEW_QUESTION_REQUEST
        if has_question_pattern:
            return UserMessageClassificationResult(
                category=UserMessageClassificationEnum.NEW_QUESTION_REQUEST,
                confidence=0.7,
                reasoning="Interrogative query fallback",
            )

        return UserMessageClassificationResult(
            category=UserMessageClassificationEnum.NEW_QUESTION_REQUEST,
            confidence=0.7,
            reasoning="Default classification fallback",
        )
