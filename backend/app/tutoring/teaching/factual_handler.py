import re
import logging
from typing import Dict, Any, List, Optional, Generator
from app.services.llm_service import default_llm_service

logger = logging.getLogger(__name__)

_AMBIGUOUS_PATTERNS = [
    # "what is eight one", "what is 8 1", "eight one"
    (
        re.compile(r"\b(?:eight\s+one|8\s+1)\b", re.IGNORECASE),
        "Do you mean 81 (eighty-one), or are you asking about the 81st element (Thallium)?"
    ),
    # "what is one zero", "one zero", "1 0"
    (
        re.compile(r"\b(?:one\s+zero|1\s+0)\b", re.IGNORECASE),
        "Do you mean 10 (ten), binary 10 (two), or the 10th element (Neon)?"
    ),
]

_FACTUAL_SYSTEM_PROMPT = """You are DeepTutor's general factual knowledge assistant.
Your goal is to provide direct, accurate, and natural answers to factual questions (science, math, general knowledge, history, definitions, etc.).

CRITICAL GUIDELINES:
1. DIRECT AND FACTUAL: Answer the user's factual question accurately and cleanly.
2. USER FORMAT RESPECT:
   - If the user specifies "answer only", "i need answer only", "just the answer", "one word", or similar:
     Output ONLY the exact answer string (e.g. "Helium (He)." or "81"). DO NOT add greetings, explanations, or extra commentary!
   - Otherwise, provide a clear, concise 1-3 sentence factual explanation.
3. NO ARTIFICIAL REJECTION: Do NOT refuse the question because it is not in an uploaded document.
4. NO TEACHING ARTIFACTS:
   - NEVER append "### 💡 Interactive Checkpoint"
   - NEVER append "Active Recall Question"
   - NEVER append "Would you like me to continue to the next subtopic?"
   - Keep the answer clean, elegant, and focused."""

_UNRELATED_SYSTEM_PROMPT = """You are DeepTutor, a helpful and polite academic assistant.
The student asked an everyday, casual, or off-topic conversational question.

CRITICAL GUIDELINES:
1. Respond briefly, naturally, and warmly in 1-2 sentences.
2. DO NOT output robotic boilerplate such as:
   "I am your dedicated tutor for this study material..."
   "Please ask questions related to the uploaded document..."
3. NEVER append an "### 💡 Interactive Checkpoint" or "Active Recall Question".
4. Answer politely and keep the door open for learning questions."""


class FactualQueryHandler:
    """
    Handles general factual questions and unrelated conversational queries
    without forcing RAG retrieval, document refusal boilerplate, or artificial checkpoints.
    """

    @classmethod
    def check_ambiguity(cls, raw_query: str) -> Optional[str]:
        """
        Detects if a simple or phonetic query is ambiguous and returns
        a natural clarification question if needed.
        """
        q_clean = raw_query.strip()
        for pat, clarif in _AMBIGUOUS_PATTERNS:
            if pat.search(q_clean):
                return clarif
        return None

    @classmethod
    def handle_factual_query(
        cls,
        raw_query: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        is_teacher_mode: bool = False
    ) -> str:
        """Generates a direct, clean factual response."""
        # 1. Ambiguity check
        ambig_q = cls.check_ambiguity(raw_query)
        if ambig_q:
            return ambig_q

        # 2. Strict format extraction
        format_instruction = ""
        q_lower = raw_query.lower()
        if any(w in q_lower for w in ["answer only", "i need answer only", "just the answer", "one word", "only the answer"]):
            format_instruction = "\nUSER FORMAT CONSTRAINT: Provide ONLY the direct factual answer. Do not include full sentences, intros, or punctuation fluff."

        prompt = f"User Question: {raw_query}{format_instruction}"
        
        try:
            resp = default_llm_service.generate(
                prompt=prompt,
                system_prompt=_FACTUAL_SYSTEM_PROMPT
            )
            if resp and resp.strip():
                clean = resp.strip()
                # Clean any stray checkpoints if LLM hallucinated one
                clean = re.sub(r"###\s*💡\s*Interactive Checkpoint.*", "", clean, flags=re.DOTALL).strip()
                return clean
        except Exception as e:
            logger.error(f"[FactualQueryHandler] LLM generation failed: {e}")

        return "I could not retrieve the factual answer for this query. Please try rephrasing."

    @classmethod
    def stream_factual_query(
        cls,
        raw_query: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        is_teacher_mode: bool = False
    ) -> Generator[str, None, None]:
        """Streams tokens for a factual query."""
        ambig_q = cls.check_ambiguity(raw_query)
        if ambig_q:
            yield ambig_q
            return

        format_instruction = ""
        q_lower = raw_query.lower()
        if any(w in q_lower for w in ["answer only", "i need answer only", "just the answer", "one word", "only the answer"]):
            format_instruction = "\nUSER FORMAT CONSTRAINT: Provide ONLY the direct factual answer. Do not include full sentences, intros, or punctuation fluff."

        prompt = f"User Question: {raw_query}{format_instruction}"
        
        tokens_accum = []
        try:
            for token in default_llm_service.stream_generate(
                prompt=prompt,
                system_prompt=_FACTUAL_SYSTEM_PROMPT
            ):
                tokens_accum.append(token)
                yield token
            if tokens_accum:
                return
        except Exception as e:
            logger.error(f"[FactualQueryHandler] Streaming failed: {e}")

        # Fallback to single shot
        full = cls.handle_factual_query(raw_query, conversation_history, is_teacher_mode)
        yield full

    @classmethod
    def handle_unrelated_query(
        cls,
        raw_query: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """Handles an unrelated conversational query naturally without robotic refusal."""
        prompt = f"User said: {raw_query}"
        try:
            resp = default_llm_service.generate(
                prompt=prompt,
                system_prompt=_UNRELATED_SYSTEM_PROMPT
            )
            if resp and resp.strip():
                clean = resp.strip()
                clean = re.sub(r"###\s*💡\s*Interactive Checkpoint.*", "", clean, flags=re.DOTALL).strip()
                return clean
        except Exception as e:
            logger.error(f"[FactualQueryHandler] Unrelated query handling failed: {e}")

        return "I'm here to help! Let me know if you have any questions or if you'd like to dive into your study material."

    @classmethod
    def stream_unrelated_query(
        cls,
        raw_query: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> Generator[str, None, None]:
        """Streams a natural response for an unrelated query."""
        prompt = f"User said: {raw_query}"
        try:
            for token in default_llm_service.stream_generate(
                prompt=prompt,
                system_prompt=_UNRELATED_SYSTEM_PROMPT
            ):
                yield token
            return
        except Exception as e:
            logger.error(f"[FactualQueryHandler] Stream unrelated query failed: {e}")

        yield cls.handle_unrelated_query(raw_query, conversation_history)
