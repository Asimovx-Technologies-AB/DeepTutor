import re
import json
import logging
from typing import Dict, Any, Optional, List, Tuple
from app.schemas.tutoring import PreGenerationPlan
from app.services.llm_service import default_llm_service

logger = logging.getLogger(__name__)


_CLASSIFICATION_SYSTEM_PROMPT = """You are the Pre-Generation Response Classifier for DeepTutor, an AI teaching engine.
Your task is to classify the student's request into a strict execution plan BEFORE any response is generated.

Classify the input query into JSON matching this exact schema:
{
  "depth": "answer_only" | "short" | "detailed" | "default",
  "format": "bullets" | "table" | "stepwise" | "prose",
  "visual": "none" | "required" | "conditional",
  "skip_followup_question": boolean,
  "reasoning": "Short 1-sentence rationale for the decision."
}

RULES FOR CLASSIFICATION:
1. DEPTH:
   - "answer_only": Student wants ONLY the final result/answer with no explanation, steps, or follow-up.
   - "short": Student requests brevity ("briefly", "in short", "tl;dr", "quick answer", "summarize in 2 lines").
   - "detailed": Student requests depth ("in detail", "elaborate", "step by step", "with examples", "deep dive").
   - "default": No explicit length cue. Standard balanced response.

2. FORMAT:
   - "bullets": Requests bullet points or a list ("in bullet points", "as a list").
   - "table": Requests a table or compares items ("in a table", "compare X and Y", "X vs Y").
   - "stepwise": Requests procedural or step-by-step instructions ("step by step", "walk through the steps", "how to").
   - "prose": Standard paragraph output (default).

3. VISUAL:
   - "none": MUST be 'none' for:
     a) Plain practice questions or quiz requests ("create N questions", "quiz me", "practice problems") EXCEPT when asking for important questions, exam topics, or whole material curriculum overview (which require a concept relationship graph).
     b) Meta/progress queries ("show my weak topics", "how am I doing").
     c) Pure text definitions or simple arithmetic ("define X in one sentence", "time complexity of X", "list causes of X").
     d) Plain follow-up clarifications ("explain that again", "simplify that").
     e) Any query with depth="answer_only".
   - "required": Query explicitly asks for a diagram/image/flowchart/table/mindmap, OR the topic is inherently algorithmic (sorting, search, data structures, dijkstra, quicksort, trees, arrays), spatial, or anatomical.
   - "conditional": Default for technical concepts, comparisons, or detailed explanations where a diagram enhances understanding.

4. CONFLICT RESOLUTION:
   - If depth="answer_only", set visual="none" and skip_followup_question=true.
   - Format and depth cues combine independently (e.g. "briefly in bullet points" -> depth="short", format="bullets").
   - Low confidence / ambiguity MUST default to depth="default", format="prose", visual="conditional". NEVER over-generate.

Return ONLY the raw JSON object. Do not include markdown code fences."""


class PreGenerationClassifier:
    """
    Pre-Generation Classification Layer:
    Determines response depth, structural format, visual need, and follow-up behavior
    before generator execution.
    """

    # --- REGEX PATTERNS FOR FAST DETERMINISTIC MATCHING ---
    ANSWER_ONLY_PATTERNS = [
        re.compile(r"\b(?:just\s+(?:the\s+)?answer|answer\s+only|only\s+the\s+answer|no\s+explanation|just\s+result|result\s+only|without\s+explanation|no\s+reasoning|no\s+steps)\b", re.IGNORECASE),
        re.compile(r"^(?:solve|calculate)\s+[0-9xXyZ\$\+\-\*\/\^\(\)\=\s\.]+$", re.IGNORECASE),
        re.compile(r"^(?:what\s+is)\s+\d+[\d\s\+\-\*\/\^\(\)\.]+$", re.IGNORECASE),
    ]

    SHORT_DEPTH_PATTERNS = [
        re.compile(r"\b(?:briefly|in\s+short|quick\s+answer|tl;?dr|short\s+answer|in\s+one\s+sentence|in\s+1\s+sentence|in\s+a\s+few\s+sentences|keep\s+it\s+short|make\s+it\s+brief|brief\s+overview|summarize\s+in\s+\d+\s+lines)\b", re.IGNORECASE)
    ]

    DETAILED_DEPTH_PATTERNS = [
        re.compile(r"\b(?:explain\s+in\s+detail|in\s+detail|elaborate|deep\s+dive|comprehensive|thorough|with\s+examples|full\s+explanation|in\s+depth|exhaustive)\b", re.IGNORECASE)
    ]

    BULLETS_FORMAT_PATTERNS = [
        re.compile(r"\b(?:in\s+bullet\s+points?|as\s+a\s+list|in\s+a\s+list|bulleted\s+list|bullet\s+points?|bullet\s+list|list\s+of)\b", re.IGNORECASE)
    ]

    TABLE_FORMAT_PATTERNS = [
        re.compile(r"\b(?:in\s+a\s+table|as\s+a\s+table|tabular|table\s+format|comparison\s+table)\b", re.IGNORECASE),
        re.compile(r"\b(?:compare|difference\s+between|vs\.?|versus)\b", re.IGNORECASE)
    ]

    STEPWISE_FORMAT_PATTERNS = [
        re.compile(r"\b(?:step[- ]by[- ]step|walk\s+me\s+through|walk\s+through\s+the\s+steps|steps?\s+to|procedural\s+steps)\b", re.IGNORECASE)
    ]

    # VISUAL NONE PATTERNS
    VISUAL_NONE_GENERATIVE = re.compile(
        r"\b(?:create\s+\d+\s+questions?|give\s+(?:me\s+)?(?:\d+\s+)?questions?|quiz\s+me|make\s+a\s+quiz|test\s+me|practice\s+problems?|flashcards?|practice\s+questions?)\b",
        re.IGNORECASE
    )

    VISUAL_NONE_META = re.compile(
        r"\b(?:how\s+am\s+i\s+doing|show\s+my\s+weak\s+topics|what'?s\s+next|my\s+progress|learning\s+stats|my\s+mastery)\b",
        re.IGNORECASE
    )

    VISUAL_NONE_PURE_FACTUAL = re.compile(
        r"\b(?:what\s+is|what\s+are|define|time\s+complexity|space\s+complexity|who\s+discovered|syntax\s+of|formula\s+for|list\s+(?:the\s+)?causes|main\s+causes)\b",
        re.IGNORECASE
    )

    VISUAL_NONE_FOLLOWUP_CLARIFICATION = re.compile(
        r"^(?:explain\s+that\s+again|simplify\s+that|what\s+did\s+you\s+mean|i\s+don'?t\s+understand|can\s+you\s+rephrase)\??$",
        re.IGNORECASE
    )

    VISUAL_REQUIRED_PATTERNS = [
        re.compile(r"\b(?:draw|show|generate|create|render|make)\s+(?:a\s+|an\s+|the\s+)?(?:diagram|flowchart|mindmap|svg|image|figure|picture|chart|illustration|vector)\b", re.IGNORECASE),
        re.compile(r"\b(?:diagram\s+of|flowchart\s+of|mindmap\s+of|illustration\s+of|architecture\s+diagram|circuit\s+diagram|anatomical)\b", re.IGNORECASE)
    ]

    IS_VISUAL_CANDIDATE_PATTERN = re.compile(
        r"\b(?:algorithm|algorithms|sorting|sort|quicksort|merge\s+sort|bubble\s+sort|insertion\s+sort|"
        r"binary\s+search|linear\s+search|dijkstra|bfs|dfs|tree|array|stack|queue|linked\s+list|"
        r"graph|diagram|flowchart|mindmap|svg|image|figure|picture|chart|illustration|vector|"
        r"import[ae]nt\s+questions?|exam\s+questions?|key\s+questions?|practice\s+questions?|concept\s+graph|relationship\s+graph|"
        r"evolution|evolve|phases?|stages?|timeline|pipeline|sdlc|chronological|"
        r"handshake|protocol|client-server|oauth|sequence|"
        r"whole\s+(?:material|meterial|syllabus|curriculum)|cover\s+all\s+(?:the\s+)?topics|all\s+chapters|"
        r"architecture|circuit|anatomy)\b",
        re.IGNORECASE
    )

    @classmethod
    def classify(
        cls,
        raw_query: str,
        resolved_query: Optional[str] = None,
        intent: str = "DOCUMENT_QA",
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        skip_followup_default: bool = False
    ) -> PreGenerationPlan:
        """
        Executes pre-generation classification.
        Uses deterministic rule matching first; falls back to LLM pass if ambiguous.
        """
        raw_text = (raw_query or "").strip()
        resolved_text = (resolved_query or raw_text).strip()
        combined_text = raw_text if raw_text == resolved_text else f"{raw_text} {resolved_text}".strip()
        combined_text_lower = combined_text.lower()
        raw_lower = raw_text.lower()

        # 1. Deterministic Rule Pass (prefer raw_query for length/format cues, combined for visual candidates)
        depth, depth_confidence = cls._detect_depth(raw_lower)
        if depth_confidence < 1.0:
            d_res, d_conf = cls._detect_depth(combined_text_lower)
            if d_conf > depth_confidence:
                depth, depth_confidence = d_res, d_conf

        fmt, format_confidence = cls._detect_format(raw_lower, intent)
        if format_confidence < 1.0:
            f_res, f_conf = cls._detect_format(combined_text_lower, intent)
            if f_conf > format_confidence:
                fmt, format_confidence = f_res, f_conf

        vis, visual_confidence = cls._detect_visual(combined_text_lower, depth, intent, conversation_history)

        # 2. Conflict Resolution & Normalization
        # Rule: answer_only and CASUAL force visual = "none" and skip_followup_question = True
        skip_followup = skip_followup_default
        if intent == "STUDY_NOTES":
            depth = "detailed"
            vis = "conditional"
            skip_followup = False
        elif intent == "CASUAL":
            depth = "short"
            vis = "none"
            skip_followup = True
            fmt = "prose"
        elif depth == "answer_only":
            vis = "none"
            skip_followup = True
            # Format defaults to prose unless user explicitly asked for another format (e.g., "answer only in a table")
            if not any(pat.search(combined_text_lower) for pat in cls.TABLE_FORMAT_PATTERNS + cls.BULLETS_FORMAT_PATTERNS + cls.STEPWISE_FORMAT_PATTERNS):
                fmt = "prose"

        reasoning = f"Rule-based classification: depth={depth}, format={fmt}, visual={vis}."

        # High confidence rule match -> return directly
        if depth_confidence >= 0.8 and format_confidence >= 0.8 and visual_confidence >= 0.8:
            return PreGenerationPlan(
                depth=depth,
                format=fmt,
                visual=vis,
                skip_followup_question=skip_followup,
                reasoning=reasoning
            )

        # 3. LLM Fallback Pass for Low-Confidence / Ambiguous Cases
        if default_llm_service.is_live_model_configured():
            try:
                prompt = f"Student Message: \"{raw_text}\"\nClassify and return JSON:"
                response = default_llm_service.generate(
                    prompt=prompt,
                    system_prompt=_CLASSIFICATION_SYSTEM_PROMPT
                )
                if response:
                    cleaned_json = re.sub(r"```(?:json)?", "", response).strip().strip("`").strip()
                    parsed = json.loads(cleaned_json)
                    if isinstance(parsed, dict) and "depth" in parsed:
                        llm_depth = str(parsed.get("depth", "default")).lower()
                        llm_format = str(parsed.get("format", "prose")).lower()
                        llm_visual = str(parsed.get("visual", "conditional")).lower()
                        llm_skip = bool(parsed.get("skip_followup_question", False))
                        llm_reasoning = parsed.get("reasoning", "LLM pre-generation classification.")

                        # Validate field literals
                        if llm_depth not in ("answer_only", "short", "detailed", "default"):
                            llm_depth = "default"
                        if llm_format not in ("bullets", "table", "stepwise", "prose"):
                            llm_format = "prose"
                        if llm_visual not in ("none", "required", "conditional"):
                            llm_visual = "conditional"

                        # Protect visual candidates (algorithms, data structures, exam questions) from over-suppression in LLM pass
                        if bool(cls.IS_VISUAL_CANDIDATE_PATTERN.search(combined_text_lower)) and llm_depth != "answer_only" and llm_visual == "none":
                            llm_visual = "conditional"

                        # Apply hard conflict resolution on LLM output as well
                        if llm_depth == "answer_only":
                            llm_visual = "none"
                            llm_skip = True

                        return PreGenerationPlan(
                            depth=llm_depth,
                            format=llm_format,
                            visual=llm_visual,
                            skip_followup_question=llm_skip,
                            reasoning=llm_reasoning
                        )
            except Exception as e:
                logger.warning(f"[PreGenClassifier] LLM pass failed, falling back to rule defaults: {e}")

        # Default fallback for ambiguous cases: default to depth=default, format=prose, visual=conditional
        return PreGenerationPlan(
            depth=depth,
            format=fmt,
            visual=vis,
            skip_followup_question=skip_followup,
            reasoning=reasoning
        )

    @classmethod
    def _detect_depth(cls, text: str) -> Tuple[str, float]:
        # Answer Only
        for pat in cls.ANSWER_ONLY_PATTERNS:
            if pat.search(text):
                # Ensure no "explain", "why", or "how" is attached when matching solve
                if "solve" in text and any(w in text for w in ["explain", "why", "how", "step by step", "show work"]):
                    continue
                return "answer_only", 1.0

        # Short
        for pat in cls.SHORT_DEPTH_PATTERNS:
            if pat.search(text):
                return "short", 1.0

        # Detailed
        for pat in cls.DETAILED_DEPTH_PATTERNS:
            if pat.search(text):
                return "detailed", 1.0

        return "default", 0.9

    @classmethod
    def _detect_format(cls, text: str, intent: str) -> Tuple[str, float]:
        # Bullets
        for pat in cls.BULLETS_FORMAT_PATTERNS:
            if pat.search(text):
                return "bullets", 1.0

        # Table
        for pat in cls.TABLE_FORMAT_PATTERNS:
            if pat.search(text):
                return "table", 1.0
        if intent == "COMPARISON":
            return "table", 0.9

        # Stepwise
        for pat in cls.STEPWISE_FORMAT_PATTERNS:
            if pat.search(text):
                return "stepwise", 1.0

        return "prose", 0.9

    @classmethod
    def _detect_visual(
        cls,
        text: str,
        depth: str,
        intent: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[str, float]:
        # 1. answer_only forces visual="none"
        if depth == "answer_only":
            return "none", 1.0

        is_visual_candidate = bool(cls.IS_VISUAL_CANDIDATE_PATTERN.search(text))

        # 2. Generative / practice questions intent
        if (intent in ("PRACTICE_QUESTIONS", "QUIZ") or cls.VISUAL_NONE_GENERATIVE.search(text)) and not is_visual_candidate:
            return "none", 1.0

        # 3. Meta / progress queries
        if cls.VISUAL_NONE_META.search(text):
            return "none", 1.0

        # 4. Pure factual / definitional / complexity queries
        is_complexity_or_def = bool(re.search(r"\b(?:time\s+complexity|space\s+complexity|define\s+\w+|syntax\s+of|formula\s+for)\b", text, re.IGNORECASE))
        if (
            cls.VISUAL_NONE_PURE_FACTUAL.search(text)
            and (not is_visual_candidate or is_complexity_or_def)
            and not any(pat.search(text) for pat in cls.TABLE_FORMAT_PATTERNS)
            and not any(pat.search(text) for pat in cls.VISUAL_REQUIRED_PATTERNS)
        ):
            return "none", 1.0

        # 5. Follow-up clarification without visual reference
        if cls.VISUAL_NONE_FOLLOWUP_CLARIFICATION.search(text):
            # Check if previous turn had an image reference
            prior_had_image = False
            if conversation_history:
                for turn in reversed(conversation_history):
                    c = (turn.get("content") or turn.get("text") or "").strip().lower()
                    if "```mermaid" in c or "```svg" in c or "diagram" in c or "figure" in c:
                        prior_had_image = True
                        break
            if not prior_had_image:
                return "none", 1.0

        # 6. Explicit visual required
        for pat in cls.VISUAL_REQUIRED_PATTERNS:
            if pat.search(text):
                return "required", 1.0

        # 7. Fallback conditional
        return "conditional", 0.9
