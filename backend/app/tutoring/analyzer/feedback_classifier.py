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

_TEACH_PATTERNS = [
    re.compile(r"\b(?:teach\s+me|act\s+as\s+a\s+teacher|start\s+teacher\s+mode|teach\s+step\s+by\s+step)\b", re.IGNORECASE),
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
2. "GENERAL_FACTUAL": A simple, standalone factual, mathematical, or scientific question that can be answered from general world knowledge without needing a specific uploaded PDF (e.g., "what is 81?", "what is eight one?", "what is the second element in periodic table?", "what is the speed of light?", "who invented the telephone?").
3. "STUDY_MATERIAL_QUESTION": A question specifically about or referencing the uploaded study document, course notes, specific chapter, or page text.
4. "UNRELATED_CHAT": Casual conversation, everyday greetings, or off-topic chit-chat unrelated to academic learning.
5. "STATEMENT_EVALUATION": The student is asserting a factual claim, sharing an attempted answer, or answering an earlier question.
6. "CLARIFICATION_CONTINUATION": Confirming, continuing, asking for simpler explanation, or asking a direct follow-up on the current topic.
7. "TEACH_TOPIC_REQUEST": An explicit request to teach a topic interactively step-by-step.

CRITICAL RULES:
- Short feedback messages like "wrong", "wrong answer", "that's wrong", "incorrect", "no", "not correct", "this is wrong", "that's not what I meant" must ALWAYS be classified as FEEDBACK_CORRECTION, NEVER as a new question!
- If the user asks a simple general factual question (like "what is 81", "what is eight one", "what is the second element"), classify as GENERAL_FACTUAL.
- Never classify a general factual question as UNRELATED_CHAT.

Respond ONLY with a JSON object:
{
  "category": "FEEDBACK_CORRECTION" | "GENERAL_FACTUAL" | "STUDY_MATERIAL_QUESTION" | "UNRELATED_CHAT" | "STATEMENT_EVALUATION" | "CLARIFICATION_CONTINUATION" | "TEACH_TOPIC_REQUEST",
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

        # 1. PRIORITY 1: Fast deterministic regex matching for corrections/challenges
        for pat in _CORRECTION_PATTERNS:
            if pat.search(query_clean):
                # Edge case: if previous message explicitly asked a yes/no question like "Is X true?",
                # "no" might be an answer to that question rather than disputing the tutor.
                if query_lower in ["no", "nope", "nah"] and history:
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
            if pat.search(query_clean):
                return UserMessageClassificationResult(
                    category=UserMessageClassificationEnum.CLARIFICATION_CONTINUATION,
                    confidence=0.98,
                    reasoning=f"Matched continuation pattern: '{query_clean}'",
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

        # 5. Check if query is explicitly asking about the uploaded study material
        is_material_explicit = any(k in query_lower for k in _STUDY_MATERIAL_KEYWORDS)
        if is_material_explicit and has_active_document:
            return UserMessageClassificationResult(
                category=UserMessageClassificationEnum.STUDY_MATERIAL_QUESTION,
                confidence=0.92,
                reasoning="Query explicitly references uploaded study material/notes/document.",
            )

        # 6. Check for simple general factual question patterns
        # e.g., "what is 81", "what is the second element", "what is 2 + 2", "who discovered X"
        has_question_pattern = any(pat.search(query_clean) for pat in _QUESTION_PATTERNS)
        simple_factual_triggers = [
            "element in periodic table", "second element", "first element", "third element",
            "what is 81", "what is 8", "speed of light", "capital of", "who invented",
            "atomic number", "boiling point", "square root of", "what is the formula of",
            "answer only", "i need answer only"
        ]
        if any(trig in query_lower for trig in simple_factual_triggers):
            return UserMessageClassificationResult(
                category=UserMessageClassificationEnum.GENERAL_FACTUAL,
                confidence=0.95,
                reasoning="Matched simple factual knowledge trigger.",
            )

        # 7. Declarative statement check: if not a question and contains factual claim words
        words = query_clean.split()
        if not has_question_pattern and len(words) >= 2:
            statement_indicators = [
                " is ", " are ", " was ", " were ", " has ", " have ", " does ", " means ",
                " equals ", " causes ", " results in ", " consists of ", " used for ", " because "
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
