"""
Planning Agent — Advanced Query Analysis & Retrieval-Strategy Router.

Architecture
------------
This module is the "planner" half of a two-agent pipeline (planner -> executor,
see decision_agent.py). Its only job is to *think about the question* before
anything is retrieved or answered:

    1. THINK       — classify true pedagogical intent, decompose multi-part
                     questions into sub-questions, decide what kind of source
                     material (text / table / image) is needed, and pick a
                     response format contract (comparison / list / conceptual /
                     diagram / quiz).
    2. GROUND      — check the extracted topic against the session's known
                     curriculum topics with a *scored, multi-signal* matcher
                     (not a single boolean), and check whether the relevant
                     material has actually finished indexing yet. This is
                     what stops the executor from saying "out of material
                     scope" for a topic that is sitting right there in the
                     sidebar, just not indexed yet.
    3. SELF-RATE   — the LLM reports its own confidence in the classification.
                     Low confidence flags `needs_clarification` instead of
                     silently guessing.
    4. VALIDATE    — every LLM output is parsed defensively, retried once with
                     a stricter prompt on failure, and finally backed by
                     deterministic heuristics so the app never crashes on a
                     malformed model response.

Keeping this as a separate, narrow-purpose LLM call (rather than folding
planning into the final-answer prompt) is what makes the pipeline "agentic":
the planner can be inspected, unit-tested, and iterated on independently of
answer generation.
"""
import json
import re
import asyncio
import difflib
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Union
from app.rag.llm_client import llm_client


PLANNER_SYSTEM_PROMPT = """You are the Planning Agent for DeepTutor, an advanced AI educational reasoning platform.
You do not answer the student. You THINK ABOUT the question and produce a structured retrieval + response plan that a downstream tutoring executor agent will execute.

Work through this 5-pillar reasoning chain internally before writing JSON:
1. INTENT CLASSIFICATION: What does the student actually want done?
   - "EXPLANATION_REQUEST": Conceptual learning / teaching / explaining / comparing concepts.
   - "PROBLEM_SOLVING_REQUEST": Step-by-step problem solving, math derivation, code, or analytical exercise.
   - "STUDY_NOTES_REQUEST": Structured study notes, cheat sheet, revision summary, Markdown/MD reference file.
   - "QUIZ_REQUEST": Be tested / quizzed ("quiz me", "test me", "ask 5 questions").
   - "QUIZ_ANSWER": Answering a previous quiz question.
   - "STUDY_PLAN_REQUEST": Timetable, study schedule, revision strategy, curriculum roadmap.
   - "MATERIAL_TOPICS_REQUEST": Curriculum inquiry asking what topics/chapters are in the uploaded material.
   - "NEW_SUBJECT_DECLARATION": Explicitly starting/switching a course/subject (not a question).
   - "GREETING": Simple pleasantries.
2. TOPIC & ENTITY EXTRACTION:
   - topics: Array of high-level subject, chapter, or concept topics (e.g. ["Biology", "Photosynthesis"]).
   - entities: Array of specific technical entities, formulas, laws, theorems, algorithms, or constants (e.g. ["chlorophyll", "Calvin cycle", "ATP"]).
3. QUERY DECOMPOSITION & IMPLICIT REQUIREMENTS:
   - Break compound queries into atomic sub-questions that can each be answered from focused retrieval. If a single atomic question, sub_questions = [the question itself].
   - Identify implicit visual needs: e.g. "create an image" / "draw" / "diagram" / "flowchart" / "architecture" / "visualize" -> response_format = "diagram", requires_image_data = true; "compare" / "trade-offs" / "numbers" -> requires_table_data = true.
4. RESOURCE & RETRIEVAL PLANNING:
   - sources: Subset of ["vector", "bm25", "tables", "images"].
     - Include "tables" if numeric, trade-off, or tabular data is needed.
     - Include "images" if diagrams, figures, or architecture visual workflows are needed.
   - tools: Tools required, e.g. ["none"], ["calculator"], ["code"].
5. QUERY QUALITY & AMBIGUITY CHECK:
   - status: "clear" if query is complete and answerable. "ambiguous" or "needs_clarification" if query is vague, missing key context, or under-specified.
   - clarification_prompt: If status is not "clear", formulate a friendly clarifying question or suggested prompt. Otherwise null.
   - confidence: Rate 0.0-1.0 confidence in this classification.

CRITICAL RULES:
- NEVER classify a question sentence (contains what/how/why/explain/compare/difference/? etc.) as "NEW_SUBJECT_DECLARATION". Questions are always "EXPLANATION_REQUEST", "PROBLEM_SOLVING_REQUEST", "STUDY_NOTES_REQUEST", "QUIZ_REQUEST", or "QUIZ_ANSWER".
- `target_topic` and `extracted_subject` must be clean concept/subject noun-phrases, never a full question sentence and never prefixed with "what is/explain/tell me about".
- Expand short acronyms, variable names, or abbreviations into full technical search queries in search_queries (e.g., "q k v" -> ["q k v", "Queries Keys Values", "Query Key Value attention", "Multi-Head Attention"]).
- If the student is answering a quiz (a short answer like "A", "Option B", a single term, or a short free-text response immediately following a quiz question in conversation context), intent is "QUIZ_ANSWER".

Respond with ONLY this JSON object, no preamble, no markdown fences:
{
  "reasoning": "1-3 sentence internal reasoning trace covering steps 1-5 above",
  "intent": "EXPLANATION_REQUEST" | "PROBLEM_SOLVING_REQUEST" | "STUDY_NOTES_REQUEST" | "QUIZ_REQUEST" | "QUIZ_ANSWER" | "STUDY_PLAN_REQUEST" | "MATERIAL_TOPICS_REQUEST" | "NEW_SUBJECT_DECLARATION" | "GREETING",
  "topics": ["topic 1", "topic 2"],
  "entities": ["entity 1", "entity 2"],
  "sub_questions": ["atomic sub-question 1", "atomic sub-question 2"],
  "target_topic": "Clean topic/entity name or null",
  "search_queries": ["query 1", "query 2"],
  "extracted_subject": "Clean broad subject name if declaring new subject, else null",
  "response_format": "comparison" | "list" | "diagram" | "quiz" | "study_plan" | "study_notes" | "conceptual",
  "requires_table_data": true | false,
  "requires_image_data": true | false,
  "retrieval_plan": {
    "sources": ["vector", "bm25"],
    "tools": ["none"]
  },
  "status": "clear" | "ambiguous" | "needs_clarification",
  "clarification_prompt": "Clarifying question if ambiguous or null",
  "confidence": 0.0,
  "needs_clarification": true | false,
  "recommended_action": "EXPLAIN" | "SOLVE" | "QUIZ_QUESTION" | "EVALUATE_ANSWER" | "GENERATE_PLAN" | "SET_SUBJECT" | "GREET" | "CLARIFY"
}
"""

_MAX_RETRIES = 2
_LOW_CONFIDENCE_THRESHOLD = 0.5

# Topic-match confidence at/above which we treat the topic as *confirmed present*
# in the material — strong enough to override a downstream "out of scope" guess.
_TOPIC_MATCH_CONFIRM_THRESHOLD = 0.72
# Below this, treat the topic as genuinely unmatched rather than "maybe".
_TOPIC_MATCH_REJECT_THRESHOLD = 0.45

# Statuses that mean "don't trust a retrieval miss yet" — the document hasn't
# finished becoming searchable. Extend this set if the ingestion pipeline adds
# more granular states (e.g. "chunking", "embedding").
_INDEXING_IN_PROGRESS_STATUSES = {"indexing", "processing", "queued", "pending", "embedding", "chunking"}

# ─── Meta-referential detection ("what did you just say", "the previous module") ──
# Ported from study_agents.py's is_meta_referential_query so the planner can flag
# these *before* generation, rather than leaving the executor to infer from raw
# history and risk fabricating a recap of a turn that never happened.
_META_REFERENTIAL_PATTERNS = [
    r"\b(above|previous|last|prior|preceding)\s+(module|response|answer|explanation|topic|turn|content|lecture|lesson|section|material|chapter|discussion)\b",
    r"\b(what|that)\s+(you|we)\s+(gave|explained|discussed|covered|provided|wrote|taught|generated)\b",
    r"\b(module|content|topic|answer|response|concept|material)\s+(you|we)\s+(gave|gave me|explained|discussed|provided|wrote|taught)\b",
    r"\b(go back to|revisit|recap)\b.*\b(previous|last|prior|earlier)\b",
]
_META_REFERENTIAL_PHRASES = (
    "above module", "previous module", "module you gave", "module above", "module you gave me",
    "above response", "above answer", "above explanation", "above content", "above topic", "above text",
    "previous response", "previous answer", "previous explanation", "previous turn", "previous topic", "previous content",
    "last response", "last answer", "last explanation", "last topic", "last module", "last content",
    "what you gave", "what you gave me", "what you just gave", "what you just explained", "what you explained",
    "what we discussed", "what we just discussed", "what you wrote", "what you just taught", "what you taught",
    "earlier in this session", "earlier you said", "you said earlier",
)


def _is_meta_referential(lower_msg: str) -> bool:
    """True if the message asks about a PRIOR turn in this session, rather than a new
    topic — e.g. 'what did you just explain', 'go back to the previous module'."""
    if any(p in lower_msg for p in _META_REFERENTIAL_PHRASES):
        return True
    return any(re.search(pat, lower_msg) for pat in _META_REFERENTIAL_PATTERNS)


@dataclass
class QueryPlan:
    """Structured output of the planning pass. Backward-compatible dict via as_dict()."""
    intent: str = "EXPLANATION_REQUEST"
    reasoning: str = ""
    sub_questions: List[str] = field(default_factory=list)
    target_topic: Optional[str] = None
    search_queries: List[str] = field(default_factory=list)
    extracted_subject: Optional[str] = None
    response_format: str = "conceptual"
    requires_table_data: bool = False
    requires_image_data: bool = False
    confidence: float = 0.7
    needs_clarification: bool = False
    recommended_action: str = "EXPLAIN"
    # Advanced Query Analyzer Architecture extensions
    topics: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    retrieval_plan: Dict[str, Any] = field(default_factory=lambda: {"sources": ["bm25", "vector"], "tools": ["none"]})
    status: str = "clear"
    clarification_prompt: Optional[str] = None
    # --- Deterministic follow-up + material-gate extensions ---
    # True/False once checked against a known topic index; None = not checked
    # (no index was supplied, so the retrieval/grounding step decides instead).
    topic_in_material: Optional[bool] = None
    # True when this plan was produced by resolving a boolean ("yes"/"no")
    # reply against an explicit `pending_followup` rather than by the LLM
    # guessing from raw history text.
    resolved_from_followup: bool = False
    # --- Advanced grounding extensions (multi-signal topic match + indexing state) ---
    # 0.0-1.0 confidence that target_topic refers to a topic already present in
    # known_topics, from the best of several matching signals (exact / substring /
    # token-overlap / fuzzy-ratio) rather than a single difflib cutoff.
    topic_match_confidence: float = 0.0
    # The canonical topic title (exact string as it appears in known_topics) that
    # target_topic was matched against, if any. Fed back into search_queries so
    # retrieval searches using the material's own wording, not just the student's.
    matched_topic_title: Optional[str] = None
    # True if the material relevant to this session/topic is still being ingested
    # (chunked/embedded) — a retrieval miss under this condition must NOT be
    # reported as "out of material scope"; it's "not ready yet".
    material_indexing_in_progress: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ─── Follow-up contract ───────────────────────────────────────────────
# After every turn, the executor (DecisionAgent) reports what kind of
# yes/no offer it just made, e.g.:
#   {"type": "quiz_offer", "target_topic": "SVM", "count": 1}
#   {"type": "example_or_deepdive", "target_topic": "SVM"}
#   {"type": "topic_selection", "topics": ["Topic 1", "Topic 2", ...]}
#   {"type": "next_question", "question_number": 2, "total_questions": 5}
# The caller (chat route / session store) persists this dict and passes it
# back in as `pending_followup` on the *next* call to `analyze()`. This is
# what lets a bare "yes"/"no" be resolved deterministically instead of
# asking the LLM to re-read the last few chat turns and guess.
_FOLLOWUP_ACTION_MAP = {
    "quiz_offer": "QUIZ_QUESTION",
    "next_question": "EVALUATE_AND_NEXT_QUESTION",
    "example_or_deepdive": "EXPLAIN",
    "topic_selection": "EXPLAIN",
    "material_topics_offer": "LIST_TOPICS",
}
_FOLLOWUP_INTENT_MAP = {
    "quiz_offer": "QUIZ_REQUEST",
    "next_question": "QUIZ_ANSWER",
    "example_or_deepdive": "EXPLANATION_REQUEST",
    "topic_selection": "EXPLANATION_REQUEST",
    "material_topics_offer": "MATERIAL_TOPICS_REQUEST",
}


def _strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    return cleaned.strip()


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    cleaned = _strip_code_fences(text)
    if "{" not in cleaned or "}" not in cleaned:
        return None
    start, end = cleaned.find("{"), cleaned.rfind("}")
    try:
        return json.loads(cleaned[start:end + 1], strict=False)
    except Exception:
        return None


def _clean_topic_string(value: Optional[str]) -> Optional[str]:
    if not value or not isinstance(value, str):
        return None
    value = re.sub(
        r"^(what is|what are|explain|describe|tell me about|compare)\s+",
        "", value.strip(), flags=re.IGNORECASE,
    ).strip()
    value = value.rstrip("?.,!").strip()
    return value or None


_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(s: str) -> set:
    return set(_WORD_RE.findall(s.lower()))


def _score_topic_match(query_topic: str, candidate_title: str) -> float:
    """Multi-signal similarity between an extracted topic and a known curriculum
    title, returned as a single 0.0-1.0 confidence.

    The original implementation used a single `difflib.get_close_matches(cutoff=0.6)`
    call, which is brittle for short titles: "Encoder Decoder Stacks" vs.
    "Encoder and Decoder Stacks" can fall either side of a hard cutoff depending on
    stopwords alone. Combining several cheap signals and taking the max is more
    robust without needing an embedding call:

      - exact match (case-insensitive)              -> 1.0
      - one string fully contains the other          -> 0.9
      - token Jaccard overlap (order/stopword-proof)  -> up to ~0.85
      - difflib character-level ratio (typo-tolerant) -> up to ~0.85
    """
    a, b = query_topic.strip().lower(), candidate_title.strip().lower()
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0

    score = 0.0
    if a in b or b in a:
        score = max(score, 0.9)

    ta, tb = _tokens(a), _tokens(b)
    if ta and tb:
        jaccard = len(ta & tb) / len(ta | tb)
        score = max(score, jaccard * 0.85)

    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    score = max(score, ratio * 0.85)

    return round(score, 4)


class QueryAnalyzerAgent:
    """Agentic planner: thinks about a student query before any retrieval or generation happens."""

    def __init__(self, max_retries: int = _MAX_RETRIES):
        self.max_retries = max_retries

    async def analyze(
        self,
        message: str,
        current_subject: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        pending_followup: Optional[Dict[str, Any]] = None,
        known_topics: Optional[List[Union[str, Dict[str, Any]]]] = None,
        materials_status: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Runs the planning pass and returns a plan dict (superset of the legacy schema).

        pending_followup: what the previous turn's yes/no offer was about (see the
            contract above `_FOLLOWUP_ACTION_MAP`). When present and the message is a
            bare boolean, the plan is resolved deterministically — no LLM call.
        known_topics: the session's already-extracted curriculum topic list. Accepts
            either plain strings (`"Encoder And Decoder Stacks"`) or dicts
            (`{"title": "...", "status": "ready"}`) if a topic-level ingestion status
            is available. When supplied, the target topic is matched against it with
            a *scored* matcher (see `_score_topic_match`) rather than a single
            true/false check, and a confident match's canonical title is folded back
            into `search_queries` so retrieval actually finds it.
        materials_status: document-level ingestion status, e.g.
            `[{"filename": "Attention all u need.pdf", "status": "indexing"}]`. When
            any relevant material is still indexing, the plan is annotated with
            `material_indexing_in_progress=True` so the executor reports "still being
            processed" instead of a false "not in your material" — this is the gap
            that produced the false-negative "Out of Material Scope" result: the
            topic (Topic 4) was genuinely in the list, but the document badge shows
            "Indexing", so a retrieval-only check comes back empty.
        """
        raw_msg = message.strip()
        lower = raw_msg.lower()

        # ─── Fast-path 0: Deterministic boolean resolution against a known offer ───
        # This replaces guesswork: instead of classifying "yes"/"no" in a vacuum and
        # hoping the executor LLM infers the right thing from raw chat history, we
        # resolve it directly against the specific offer the previous turn made.

        _BOOL_PREFIX_RE = re.compile(
            r"^(yes|yeah|yep|yup|sure|ok|okay|please do|correct|affirmative|"
            r"no|nope|nah|not now|negative)[.!]?$"
        )
        _COMPOUND_BOOL_RE = re.compile(
            r"^(yes|yeah|yep|yup|sure|ok|okay|please do|correct|affirmative|"
            r"no|nope|nah|not now|negative)[.!,]?\s*"
            r"(?:and\s+(?:also\s+)?|also\s+|but\s+(?:also\s+)?|,\s*)"
            r"(.+)$",
            re.IGNORECASE | re.DOTALL,
        )

        if pending_followup:
            # Case A: Bare boolean — resolve entirely against the offer
            if _BOOL_PREFIX_RE.match(lower):
                plan = self._resolve_pending_followup(lower, pending_followup, current_subject)
                if plan is not None:
                    return self._apply_material_gate(plan, known_topics, materials_status).as_dict()

            # Case B: Boolean prefix + additional question
            #  e.g. "yes, and also explain the architecture of transformer"
            #  → resolve the "yes" against the offer, then LLM-analyze the rest,
            #    and merge both sub_questions + search_queries into one plan.
            compound_m = _COMPOUND_BOOL_RE.match(lower)
            if compound_m:
                bool_word = compound_m.group(1).lower()
                extra_question = compound_m.group(2).strip()

                followup_plan = self._resolve_pending_followup(
                    bool_word, pending_followup, current_subject
                )
                extra_plan_dict = await self._analyze_core(
                    extra_question, extra_question.lower(), current_subject, history
                )

                if followup_plan is not None:
                    extra_plan = QueryPlan(**extra_plan_dict)
                    # Merge: combine sub_questions and search_queries from both plans
                    merged_subs = list(followup_plan.sub_questions or [])
                    merged_searches = list(followup_plan.search_queries or [])
                    for sq in (extra_plan.sub_questions or []):
                        if sq not in merged_subs:
                            merged_subs.append(sq)
                    for sq in (extra_plan.search_queries or []):
                        if sq not in merged_searches:
                            merged_searches.append(sq)

                    merged = QueryPlan(
                        intent=extra_plan.intent if extra_plan.intent != "GREETING" else followup_plan.intent,
                        reasoning=(
                            f"Compound message: student accepted previous offer "
                            f"({pending_followup.get('type', 'unknown')}) AND asked: {extra_question}"
                        ),
                        confidence=min(followup_plan.confidence, extra_plan.confidence),
                        sub_questions=merged_subs,
                        search_queries=merged_searches,
                        response_format=extra_plan.response_format or followup_plan.response_format,
                        retrieval_plan=extra_plan.retrieval_plan or followup_plan.retrieval_plan,
                        recommended_action="ANSWER",
                        status="clear",
                    )
                    return self._apply_material_gate(merged, known_topics, materials_status).as_dict()

        plan_dict = await self._analyze_core(raw_msg, lower, current_subject, history)
        # Re-inflate to a QueryPlan so the gate can be applied uniformly, whether the
        # plan came back from a fast-path heuristic, the LLM, or the offline fallback.
        gated = self._apply_material_gate(QueryPlan(**plan_dict), known_topics, materials_status)
        return gated.as_dict()

    async def _analyze_core(
        self,
        raw_msg: str,
        lower: str,
        current_subject: Optional[str],
        history: Optional[List[Dict[str, str]]],
    ) -> Dict[str, Any]:
        """Original classification pipeline (fast-path regex heuristics, then the LLM
        planner, then the offline heuristic fallback). Kept separate from `analyze()`
        so the boolean short-circuit and the material gate wrap every exit path exactly
        once instead of being duplicated at every `return` below."""
        # ─── Fast-path Heuristic (<0.2ms, zero LLM cost) ────────────
        # Fast-path heuristic: no need to spend an LLM call on a bare greeting.
        if re.fullmatch(r"(hi|hello|hey|good morning|good evening|hey there|greetings)[.!]?", lower):
            return QueryPlan(
                intent="GREETING",
                reasoning="Message is a bare greeting with no topical content.",
                confidence=0.98,
                recommended_action="GREET",
                status="clear",
                retrieval_plan={"sources": [], "tools": ["none"]},
            ).as_dict()

        # All other queries are sent to the LLM planner to think, reason, and decompose
        plan = await self._plan_with_retries(raw_msg, current_subject, history)
        return plan.as_dict()

    analyze_query = analyze

    # ------------------------------------------------------------------
    # Deterministic boolean-follow-up resolution
    # ------------------------------------------------------------------

    def _resolve_pending_followup(
        self,
        lower_msg: str,
        pending_followup: Dict[str, Any],
        current_subject: Optional[str],
    ) -> Optional[QueryPlan]:
        """Turns a bare 'yes'/'no' into a concrete, unambiguous plan by looking at
        exactly what the previous turn offered — instead of intent classification
        in a vacuum. Returns None if the offer type isn't one we recognize, so the
        caller falls through to the generic LLM/heuristic path."""
        is_yes = lower_msg in ("yes", "yeah", "yep", "yup", "sure", "ok", "okay", "please do", "correct", "affirmative")
        followup_type = pending_followup.get("type")
        target_topic = pending_followup.get("target_topic") or current_subject

        if not is_yes:
            # A "no" always just acknowledges and waits — never guess a new action.
            return QueryPlan(
                intent="NEGATION",
                reasoning=f"Student declined the previous offer ({followup_type}).",
                target_topic=target_topic,
                confidence=0.97,
                recommended_action="ACKNOWLEDGE",
                status="clear",
                resolved_from_followup=True,
                retrieval_plan={"sources": [], "tools": ["none"]},
            )

        action = _FOLLOWUP_ACTION_MAP.get(followup_type)
        intent = _FOLLOWUP_INTENT_MAP.get(followup_type)
        if not action:
            return None

        if followup_type == "quiz_offer":
            count = pending_followup.get("count", 1)
            return QueryPlan(
                intent=intent,
                reasoning="Student confirmed the quiz offer from the previous turn.",
                target_topic=target_topic,
                topics=[target_topic] if target_topic else [],
                sub_questions=[f"Quiz me on {target_topic}" if target_topic else "Quiz me"],
                response_format="quiz",
                retrieval_plan={"sources": ["bm25", "vector"], "tools": ["none"]},
                confidence=0.97,
                status="clear",
                resolved_from_followup=True,
                recommended_action=action,
            )
        if followup_type == "next_question":
            return QueryPlan(
                intent=intent,
                reasoning="Student is answering an in-progress quiz question ('yes' as a literal answer, not a new request).",
                target_topic=target_topic,
                response_format="quiz",
                retrieval_plan={"sources": [], "tools": ["none"]},
                confidence=0.9,
                status="clear",
                resolved_from_followup=True,
                recommended_action=action,
            )
        if followup_type == "material_topics_offer":
            return QueryPlan(
                intent=intent,
                reasoning="Student confirmed they want the curriculum topic list.",
                target_topic=target_topic,
                response_format="material_topics",
                retrieval_plan={"sources": ["bm25", "vector"], "tools": ["none"]},
                confidence=0.97,
                status="clear",
                resolved_from_followup=True,
                recommended_action=action,
            )
        # "example_or_deepdive" / "topic_selection" and any other recognized offer:
        # re-run as a normal explanation request targeted at whatever was offered.
        return QueryPlan(
            intent=intent,
            reasoning=f"Student confirmed the follow-up offer ({followup_type}).",
            target_topic=target_topic,
            topics=[target_topic] if target_topic else [],
            sub_questions=[pending_followup.get("prompt") or f"Go deeper on {target_topic}"],
            response_format=pending_followup.get("response_format") or "conceptual",
            retrieval_plan={"sources": ["bm25", "vector"], "tools": ["none"]},
            confidence=0.93,
            status="clear",
            resolved_from_followup=True,
            recommended_action=action,
        )

    # ------------------------------------------------------------------
    # Advanced "is this topic actually in the material" gate
    # ------------------------------------------------------------------

    def _normalize_known_topics(
        self, known_topics: Optional[List[Union[str, Dict[str, Any]]]]
    ) -> List[Dict[str, Any]]:
        """Accepts either `["Title", ...]` or `[{"title": "...", "status": "ready"}, ...]`
        and normalizes to the dict form so the rest of the gate has one code path."""
        normalized = []
        for t in known_topics or []:
            if isinstance(t, dict):
                title = t.get("title") or t.get("name")
                if title:
                    normalized.append({"title": str(title), "status": t.get("status")})
            elif t:
                normalized.append({"title": str(t), "status": None})
        return normalized

    def _any_material_indexing(self, materials_status: Optional[List[Dict[str, Any]]]) -> bool:
        for m in materials_status or []:
            status = str(m.get("status") or "").strip().lower()
            if status in _INDEXING_IN_PROGRESS_STATUSES:
                return True
        return False

    def _apply_material_gate(
        self,
        plan: QueryPlan,
        known_topics: Optional[List[Union[str, Dict[str, Any]]]],
        materials_status: Optional[List[Dict[str, Any]]] = None,
    ) -> QueryPlan:
        """Grounds the plan against the session's known curriculum topics and the
        ingestion state of the underlying material.

        This is the fix for the "Out of Material Scope" false negative: previously,
        a topic that was clearly present (e.g. "Topic 4: Encoder And Decoder Stacks")
        could still be reported as out-of-scope if retrieval came back empty — which
        happens for certain while the source document is still indexing. Now:

          1. Topic matching is scored (0.0-1.0), not boolean, via `_score_topic_match`,
             so near-identical titles ("Encoder and Decoder Stacks" vs. "Encoder And
             Decoder Stacks") match confidently instead of depending on a single
             difflib cutoff.
          2. A confident match's canonical title is folded into `search_queries`,
             so retrieval searches using the material's own wording in addition to
             the student's phrasing.
          3. If the relevant material is still indexing, `material_indexing_in_progress`
             is set and `recommended_action` is steered to wait-and-retry rather than
             declaring the topic missing — a retrieval miss during indexing is not
             evidence of absence.
        """
        needs_material = plan.intent in (
            "EXPLANATION_REQUEST", "PROBLEM_SOLVING_REQUEST", "STUDY_NOTES_REQUEST", "QUIZ_REQUEST",
        )

        normalized_topics = self._normalize_known_topics(known_topics)
        indexing_in_progress = self._any_material_indexing(materials_status)
        plan.material_indexing_in_progress = indexing_in_progress

        if not needs_material or not plan.target_topic:
            return plan

        if normalized_topics:
            best_score, best_title, best_status = 0.0, None, None
            for entry in normalized_topics:
                s = _score_topic_match(plan.target_topic, entry["title"])
                if s > best_score:
                    best_score, best_title, best_status = s, entry["title"], entry.get("status")

            plan.topic_match_confidence = best_score

            if best_score >= _TOPIC_MATCH_CONFIRM_THRESHOLD:
                plan.topic_in_material = True
                plan.matched_topic_title = best_title
                # Feed the material's own canonical wording into retrieval — this is
                # what actually fixes retrieval misses caused by phrasing drift
                # ("encoder decoder stacks" vs "Encoder And Decoder Stacks").
                if best_title and best_title not in plan.search_queries:
                    plan.search_queries.insert(0, best_title)
                # Even a confirmed topic can be unsearchable if its own material is
                # still indexing — surface that distinctly from "not found".
                if best_status and str(best_status).strip().lower() in _INDEXING_IN_PROGRESS_STATUSES:
                    plan.material_indexing_in_progress = True
            elif best_score <= _TOPIC_MATCH_REJECT_THRESHOLD:
                plan.topic_in_material = False
            else:
                # Ambiguous middle ground: don't assert either way, let retrieval
                # (the true source of truth per the executor) decide.
                plan.topic_in_material = None
        else:
            # No topic index supplied at all — nothing to ground against.
            plan.topic_in_material = None

        # If we can't confirm the topic is present AND the material is still
        # indexing, this is "not ready" rather than "not covered" — steer the
        # executor there explicitly instead of letting a retrieval-empty result
        # get reported as out-of-scope.
        if indexing_in_progress and plan.topic_in_material is not True:
            plan.status = "needs_clarification"
            plan.needs_clarification = True
            plan.recommended_action = "WAIT_FOR_INDEXING"
            plan.clarification_prompt = (
                "Your document is still being indexed — this can take a few seconds "
                "for a large file. Please try again shortly."
            )

        return plan

    async def _plan_with_retries(
        self,
        raw_msg: str,
        current_subject: Optional[str],
        history: Optional[List[Dict[str, str]]],
    ) -> QueryPlan:
        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                data = await self._call_planner_llm(raw_msg, current_subject, history, strict=attempt > 0)
                if data:
                    return self._parse_plan(data, raw_msg)
            except Exception as e:  # noqa: BLE001 - we deliberately degrade, never crash
                last_error = e
                print(f"[QueryAnalyzerAgent] planning attempt {attempt} failed: {e}")
            if attempt < self.max_retries:
                await asyncio.sleep(0.4 * (attempt + 1))

        if last_error:
            print(f"[QueryAnalyzerAgent] all planning attempts exhausted, using heuristic fallback: {last_error}")
        return self._heuristic_plan(raw_msg, current_subject)

    async def _call_planner_llm(
        self,
        raw_msg: str,
        current_subject: Optional[str],
        history: Optional[List[Dict[str, str]]],
        strict: bool,
    ) -> Optional[Dict[str, Any]]:
        messages = [{"role": "system", "content": PLANNER_SYSTEM_PROMPT}]

        if strict:
            messages.append({
                "role": "system",
                "content": "Your previous response was not valid JSON or was incomplete. "
                            "Respond with ONLY the raw JSON object described above — no prose, no fences.",
            })

        if current_subject:
            messages.append({"role": "system", "content": f"Current Active Subject: {current_subject}"})

        if history:
            messages.append({
                "role": "system",
                "content": f"Recent Conversation Context: {json.dumps(history[-4:])}",
            })

        messages.append({"role": "user", "content": f'Analyze this student query: "{raw_msg}"'})

        temperature = 0.1 if not strict else 0.0
        raw_response = await llm_client.chat(messages, temperature=temperature)
        return _extract_json(raw_response)

    def _parse_plan(self, data: Dict[str, Any], raw_msg: str) -> QueryPlan:
        intent = data.get("intent") or "EXPLANATION_REQUEST"

        # Guardrail: a question sentence is never a subject declaration, regardless of what the LLM said.
        is_question = bool(re.search(
            r"\b(what|how|why|when|where|which|explain|describe|difference|types|"
            r"summarize|important|concepts|compare)\b|\?",
            raw_msg.lower(),
        ))
        if is_question and intent == "NEW_SUBJECT_DECLARATION":
            intent = "EXPLANATION_REQUEST"

        target_topic = _clean_topic_string(data.get("target_topic"))
        extracted_subject = (
            _clean_topic_string(data.get("extracted_subject"))
            if intent == "NEW_SUBJECT_DECLARATION" and not is_question else None
        )

        # Extract topics array
        raw_topics = data.get("topics") or []
        if isinstance(raw_topics, str):
            raw_topics = [raw_topics]
        topics = [_clean_topic_string(t) for t in raw_topics if _clean_topic_string(t)]
        if not topics and target_topic:
            topics = [target_topic]

        # Extract technical entities
        raw_entities = data.get("entities") or []
        if isinstance(raw_entities, str):
            raw_entities = [raw_entities]
        entities = [str(e).strip() for e in raw_entities if str(e).strip()]

        sub_questions = data.get("sub_questions") or []
        if not isinstance(sub_questions, list) or not sub_questions:
            sub_questions = [raw_msg]

        search_queries = data.get("search_queries") or []
        if not isinstance(search_queries, list):
            search_queries = []
        if target_topic and target_topic not in search_queries:
            search_queries.insert(0, target_topic)
        for t in topics:
            if t and t not in search_queries:
                search_queries.append(t)
        for sq in sub_questions:
            if sq not in search_queries:
                search_queries.append(sq)
        if raw_msg not in search_queries:
            search_queries.append(raw_msg)

        requires_table_data = bool(data.get("requires_table_data", False))
        requires_image_data = bool(data.get("requires_image_data", False))

        # Build retrieval plan
        raw_plan = data.get("retrieval_plan")
        if isinstance(raw_plan, dict):
            sources = list(raw_plan.get("sources") or ["bm25", "vector"])
            tools = list(raw_plan.get("tools") or ["none"])
        else:
            sources = ["bm25", "vector"]
            tools = ["none"]

        if requires_table_data and "tables" not in sources:
            sources.append("tables")
        if requires_image_data and "images" not in sources:
            sources.append("images")

        retrieval_plan = {"sources": sources, "tools": tools}

        try:
            confidence = float(data.get("confidence", 0.7))
        except (TypeError, ValueError):
            confidence = 0.7
        confidence = max(0.0, min(1.0, confidence))

        needs_clarification = bool(data.get("needs_clarification", False)) or confidence < _LOW_CONFIDENCE_THRESHOLD
        status = str(data.get("status") or ("needs_clarification" if needs_clarification else "clear")).lower()
        if status not in ("clear", "ambiguous", "needs_clarification"):
            status = "needs_clarification" if needs_clarification else "clear"

        clarification_prompt = data.get("clarification_prompt")
        if status in ("ambiguous", "needs_clarification") and not clarification_prompt:
            clarification_prompt = f"Could you specify what aspect of {target_topic or 'this concept'} you would like to focus on?"

        return QueryPlan(
            intent=intent,
            reasoning=str(data.get("reasoning", "")).strip(),
            sub_questions=sub_questions,
            target_topic=target_topic if not is_question or intent != "NEW_SUBJECT_DECLARATION" else target_topic,
            search_queries=search_queries,
            extracted_subject=extracted_subject,
            response_format=data.get("response_format") or "conceptual",
            requires_table_data=requires_table_data,
            requires_image_data=requires_image_data,
            confidence=confidence,
            needs_clarification=needs_clarification,
            recommended_action=data.get("recommended_action") or "EXPLAIN",
            topics=topics,
            entities=entities,
            retrieval_plan=retrieval_plan,
            status=status,
            clarification_prompt=clarification_prompt,
        )

    def _heuristic_plan(self, raw_msg: str, current_subject: Optional[str]) -> QueryPlan:
        """Deterministic fallback used only if the LLM is unreachable after all retries."""
        lower = raw_msg.lower()
        is_study_notes = bool(re.search(
            r"\b(study notes?|cheat sheet|revision notes?|study map|summari[sz]e.*as notes|create.*(?:md|\.md|markdown)\s*(?:file|doc)?|make.*(?:md|\.md|markdown)\s*(?:file|doc)?|generate.*(?:md|\.md|markdown)\s*(?:file|doc)?|(?:md|\.md|markdown)\s*(?:file|doc)?\s*(?:on|for|about))\b", lower
        ))
        is_question = bool(re.search(
            r"\b(what|how|why|when|where|which|explain|describe|difference|types|"
            r"summarize|important|concepts|compare)\b|\?",
            lower,
        ))
        is_quiz = bool(re.search(r"\b(quiz|test me|ask me|practice questions)\b", lower))
        is_comparison = bool(re.search(r"\b(vs|versus|compare|difference|trade-?offs?)\b", lower))
        is_diagram = bool(re.search(r"\b(diagram|architecture|figure|visual|image)\b", lower))

        if is_study_notes:
            clean_topic = _clean_topic_string(
                re.sub(
                    r"\b(give me|make|create|prepare|generate|summarize|as|write)?\s*(a\s*)?(study notes?|cheat sheet|revision notes?|study map|notes?|(?:md|\.md|markdown)\s*(?:file|doc)?)\s*(on|for|about|of)?\s*",
                    "", lower, flags=re.IGNORECASE
                )
            )
            topic = (clean_topic.title() if clean_topic and len(clean_topic) > 2 else current_subject)
            return QueryPlan(
                intent="STUDY_NOTES_REQUEST",
                reasoning="Heuristic fallback: matched explicit study-notes / MD file keywords.",
                sub_questions=[raw_msg],
                target_topic=topic,
                topics=[topic] if topic else [],
                entities=[],
                search_queries=[q for q in [topic, raw_msg] if q],
                response_format="study_notes",
                requires_table_data=True,
                retrieval_plan={"sources": ["bm25", "vector", "tables", "images"], "tools": ["none"]},
                confidence=0.5,
                status="clear",
                needs_clarification=False,
                recommended_action="EXPLAIN",
            )

        if is_quiz:
            return QueryPlan(
                intent="QUIZ_REQUEST",
                reasoning="Heuristic fallback: matched quiz-request keywords.",
                sub_questions=[raw_msg],
                target_topic=current_subject,
                topics=[current_subject] if current_subject else [],
                entities=[],
                search_queries=[current_subject or "important concepts", raw_msg],
                response_format="quiz",
                retrieval_plan={"sources": ["bm25", "vector"], "tools": ["none"]},
                confidence=0.4,
                status="clear",
                needs_clarification=False,
                recommended_action="QUIZ_QUESTION",
            )
        if is_question:
            clean_topic = _clean_topic_string(
                re.sub(r"^(what are the most important concepts in)\s+", "", lower, flags=re.IGNORECASE)
            )
            fmt = "comparison" if is_comparison else ("diagram" if is_diagram else "conceptual")
            topic = (clean_topic.title() if clean_topic and len(clean_topic) > 2 else current_subject)
            sources = ["bm25", "vector"]
            if is_comparison:
                sources.append("tables")
            if is_diagram:
                sources.append("images")

            # Extract comparison topics/entities if this is a comparison
            comp_topics = []
            if is_comparison:
                comp_match = re.search(r"\b(?:diff(?:erence)?\s+between|vs\.?|versus|compare)\s+([a-zA-Z0-9\s]+?)(?:\s+and\s+|\s+vs\.?\s+)([a-zA-Z0-9\s]+)", lower)
                if comp_match:
                    comp_topics = [comp_match.group(1).strip().title(), comp_match.group(2).strip().title()]
            topics_list = comp_topics if comp_topics else ([topic] if topic else [])

            return QueryPlan(
                intent="EXPLANATION_REQUEST",
                reasoning="Heuristic fallback: message matched question patterns.",
                sub_questions=[raw_msg],
                target_topic=topic,
                topics=topics_list,
                entities=comp_topics,
                search_queries=[q for q in [topic, raw_msg] if q],
                response_format=fmt,
                requires_table_data=is_comparison,
                requires_image_data=is_diagram,
                retrieval_plan={"sources": sources, "tools": ["none"]},
                confidence=0.4,
                status="clear",
                needs_clarification=False,
                recommended_action="EXPLAIN",
            )

        subj_title = raw_msg.title()
        return QueryPlan(
            intent="NEW_SUBJECT_DECLARATION",
            reasoning="Heuristic fallback: no question markers found, treating as a subject name.",
            sub_questions=[raw_msg],
            target_topic=subj_title,
            topics=[subj_title],
            entities=[],
            search_queries=[subj_title],
            extracted_subject=subj_title,
            response_format="conceptual",
            retrieval_plan={"sources": ["bm25", "vector"], "tools": ["none"]},
            confidence=0.35,
            status="needs_clarification",
            needs_clarification=True,
            clarification_prompt=f"Would you like to study {subj_title}? You can ask a question or attach your textbook to begin.",
            recommended_action="SET_SUBJECT",
        )


# Singleton instance (kept for drop-in compatibility with existing imports)
query_analyzer = QueryAnalyzerAgent()