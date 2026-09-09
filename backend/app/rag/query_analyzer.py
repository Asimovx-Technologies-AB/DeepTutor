"""
Planning Agent — Advanced Query Analysis & Retrieval-Strategy Router.

Architecture
------------
This module is the "planner" half of a two-agent pipeline (planner -> executor,
see decision_agent.py). Its only job is to *think about the question* before
anything is retrieved or answered:

    1. THINK     — classify true pedagogical intent, decompose multi-part
                   questions into sub-questions, decide what kind of source
                   material (text / table / image) is needed, and pick a
                   response format contract (comparison / list / conceptual /
                   diagram / quiz).
    2. SELF-RATE — the LLM reports its own confidence in the classification.
                   Low confidence flags `needs_clarification` instead of
                   silently guessing.
    3. VALIDATE  — every LLM output is parsed defensively, retried once with
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
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional
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
   - Identify implicit needs: e.g. "with diagram" / "visualize" -> requires_image_data = true; "compare" / "trade-offs" / "numbers" -> requires_table_data = true.
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

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


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


class QueryAnalyzerAgent:
    """Agentic planner: thinks about a student query before any retrieval or generation happens."""

    def __init__(self, max_retries: int = _MAX_RETRIES):
        self.max_retries = max_retries

    async def analyze(
        self,
        message: str,
        current_subject: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Runs the planning pass and returns a plan dict (superset of the legacy schema)."""
        raw_msg = message.strip()
        lower = raw_msg.lower()

        # ─── Fast-path Heuristics (<0.2ms, zero LLM cost) ───────────
        # 1. Bare greeting
        if re.fullmatch(r"(hi|hello|hey|good morning|good evening|hey there|greetings)[.!]?", lower):
            return QueryPlan(
                intent="GREETING",
                reasoning="Message is a bare greeting with no topical content.",
                confidence=0.98,
                recommended_action="GREET",
                status="clear",
                retrieval_plan={"sources": [], "tools": ["none"]},
            ).as_dict()

        # 2. Direct Confirmation / Denial
        if re.fullmatch(r"(yes|yeah|yep|sure|ok|okay|please do|no|nope|not now)[.!]?", lower):
            is_yes = lower in ("yes", "yeah", "yep", "sure", "ok", "okay", "please do")
            return QueryPlan(
                intent="CONFIRMATION" if is_yes else "NEGATION",
                reasoning=f"Message is a conversational {'affirmation' if is_yes else 'negation'}.",
                confidence=0.95,
                recommended_action="PROCEED" if is_yes else "ACKNOWLEDGE",
                status="clear",
                retrieval_plan={"sources": [], "tools": ["none"]},
            ).as_dict()

        # 3. Direct Comparison
        comp_match = re.search(r"\b(?:diff(?:erence)?\s+between|vs\.?|versus|compare)\s+([a-zA-Z0-9\s]+?)(?:\s+and\s+|\s+vs\.?\s+)([a-zA-Z0-9\s]+)", lower)
        if comp_match:
            item_a, item_b = comp_match.group(1).strip(), comp_match.group(2).strip()
            return QueryPlan(
                intent="EXPLANATION_REQUEST",
                reasoning=f"Direct comparison query between {item_a} and {item_b}.",
                target_topic=f"{item_a} vs {item_b}",
                topics=[item_a, item_b],
                entities=[item_a, item_b],
                search_queries=[f"{item_a} {item_b}", item_a, item_b],
                response_format="comparison",
                requires_table_data=True,
                retrieval_plan={"sources": ["bm25", "vector", "tables"], "tools": ["none"]},
                confidence=0.95,
                status="clear",
                recommended_action="EXPLAIN",
            ).as_dict()

        # 4. Study Notes Request
        if re.search(r"\b(?:notes?|study\s*notes?|summary|cheat\s*sheet)\s*(?:on|for|about)?\s*([a-zA-Z0-9\s]+)", lower):
            topic_str = _clean_topic_string(raw_msg)
            target = topic_str or current_subject
            return QueryPlan(
                intent="STUDY_NOTES_REQUEST",
                reasoning="Student explicitly requested reference study notes.",
                target_topic=target,
                topics=[target] if target else [],
                entities=[],
                search_queries=[topic_str or raw_msg],
                response_format="study_notes",
                retrieval_plan={"sources": ["bm25", "vector", "tables", "images"], "tools": ["none"]},
                confidence=0.92,
                status="clear",
                recommended_action="EXPLAIN",
            ).as_dict()

        # 5. Quiz / Test Request
        if re.search(r"\b(?:quiz\s*me|test\s*me|ask\s*me\s*\d*\s*questions?)\b", lower):
            return QueryPlan(
                intent="QUIZ_REQUEST",
                reasoning="Student requested an active recall quiz.",
                target_topic=current_subject,
                topics=[current_subject] if current_subject else [],
                entities=[],
                response_format="quiz",
                retrieval_plan={"sources": ["bm25", "vector"], "tools": ["none"]},
                confidence=0.95,
                status="clear",
                recommended_action="QUIZ",
            ).as_dict()

        # 6. Material Topics / Curriculum Inquiry
        if re.search(
            r"\b(?:what (?:is|are) (?:the )?topics?|topics? (?:for|of|in|from)|list (?:all )?(?:the )?topics?|show (?:all )?(?:the )?topics?|syllabus|curriculum|what does (?:this|the) (?:mat[ea]r[ia]l|pdf|document) cover|what is (?:in|inside) (?:this|the) (?:mat[ea]r[ia]l|pdf|document))\b",
            lower
        ):
            return QueryPlan(
                intent="MATERIAL_TOPICS_REQUEST",
                reasoning="Student requested the curriculum topics covered in the uploaded course material.",
                target_topic=current_subject,
                topics=[current_subject] if current_subject else [],
                entities=[],
                response_format="material_topics",
                retrieval_plan={"sources": ["bm25", "vector"], "tools": ["none"]},
                confidence=0.98,
                status="clear",
                recommended_action="LIST_TOPICS",
            ).as_dict()

        plan = await self._plan_with_retries(raw_msg, current_subject, history)
        return plan.as_dict()

    analyze_query = analyze

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
            return QueryPlan(
                intent="EXPLANATION_REQUEST",
                reasoning="Heuristic fallback: message matched question patterns.",
                sub_questions=[raw_msg],
                target_topic=topic,
                topics=[topic] if topic else [],
                entities=[],
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
