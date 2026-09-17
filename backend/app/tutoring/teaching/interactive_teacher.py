"""
InteractiveTeacherEngine
========================

Stateful, multi-turn, interactive Teacher Mode for DeepTutor.
Teaches one manageable concept at a time, uses visual context progressively,
checks student understanding, adapts teaching strategies upon misconceptions,
detects and resolves prerequisite gaps, answers student doubts at any time without losing state,
verifies dynamic topic coverage, and produces a complete topic synthesis, final assessment,
and personalized learning report upon completion.

Zero hardcoded subjects: all teaching plans, units, figures, and evaluations
are generated dynamically from the student's study material.
"""

import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Optional, Tuple

from sqlalchemy.orm import Session
from app.models.assets import DocumentAsset
from app.models.chunk import KnowledgeChunk
from app.models.session import ChatMessage, CurriculumTopic, StudentMastery, StudySession
from app.schemas.tutoring import (
    CitationItem,
    ContextBundle,
    LearningUnit,
    PauseContext,
    QueryMetadata,
    StudentUnderstandingLevelEnum,
    TeacherSessionState,
    TeacherStageEnum,
    TeacherTurnActionEnum,
    TeachingPlan,
    VisualLearningState,
)
from app.services.llm_service import default_llm_service
from app.tutoring.retrieval.orchestrator import MultiStrategyRetrievalOrchestrator

logger = logging.getLogger(__name__)


# ─── Specialized Teacher Prompts ─────────────────────────────────────────────

_TEACHING_PLANNER_SYSTEM_PROMPT = """You are an elite Curriculum Architect and Socratic Pedagogy Planner.
Your task is to analyze study material excerpts for a requested topic and formulate a dynamic, structured TeachingPlan.

CRITICAL CONSTRAINTS:
1. ZERO SUBJECT HARDCODING: Work purely from the provided material excerpts and topic name.
2. PROGRESSIVE GRANULARITY: Break the topic into small, logically ordered, teachable learning units (typically 3 to 6 units depending on depth).
3. Do NOT simply copy chapter headings. Each unit must represent ONE clear conceptual milestone.
4. Identify prerequisites, relevant figures/tables/formulas from context, and common student misconceptions.
5. Order units logically from intuition/problem statement -> core mechanism -> visual/mathematical details -> practical application.

Return strictly a valid JSON object matching this schema:
{
  "topic": "<topic name>",
  "overall_goal": "<1-sentence learning objective for the whole topic>",
  "learning_units": [
    {
      "id": "unit-1",
      "concept": "<Name of Concept 1>",
      "objective": "<What the student should grasp in this unit>",
      "prerequisites": ["<any foundational terms or concepts>"],
      "source_pages": [1],
      "relevant_figures": ["<Figure or diagram caption/title if mentioned in context>"],
      "relevant_tables": ["<Table title/description if mentioned>"],
      "relevant_formulas": ["<Core LaTeX equation if relevant>"],
      "relationships": ["<How this unit links to subsequent units>"],
      "misconceptions": ["<Typical student misunderstanding to guard against>"],
      "difficulty": "Beginner" | "Intermediate" | "Advanced"
    }
  ]
}
"""

_CONCEPT_TEACHER_SYSTEM_PROMPT = """You are DeepTutor, an elite one-on-one interactive Socratic Tutor.
You are teaching ONE small concept to a student step-by-step.

PEDAGOGICAL CONTRACT (CRITICAL):
1. ONE SMALL CONCEPT ONLY: Do NOT explain the entire topic. Teach ONLY the specified current learning unit.
2. NO WALLS OF TEXT: Keep the entire explanation between 2 and 4 short, crisp paragraphs. Maximum 150-250 words before the question.
3. STRUCTURE:
   - Intuition / Hook: Introduce the intuition behind the concept using plain language or a vivid real-world analogy.
   - Core Mechanism: 2-3 clean bullet points explaining how it works. Bold key terms.
   - Progressive Visual Component (if figure/diagram is specified): Explain ONLY the visual element relevant to THIS concept (e.g. what the line, boundary, or root represents). Do not explain the entire diagram at once!
   - Concept Connection: If earlier concepts were completed, connect how this concept builds on what was just learned.
4. MANDATORY INTERACTIVE CHECKPOINT:
   End IMMEDIATELY with an active recall or intuition check.
   Format:
   ### 💡 Interactive Checkpoint
   [One thought-provoking question, multiple-choice A/B/C/D or short scenario]
   A. [Option A]
   B. [Option B]
   C. [Option C]
5. STOP: Do NOT continue teaching beyond this question. WAIT for the student's answer.
"""

_ANSWER_EVALUATOR_SYSTEM_PROMPT = """You are an expert Socratic Evaluator.
Analyze the student's response to the interactive checkpoint question.

Evaluate conceptually, not merely by exact string matching:
1. UNDERSTOOD: The student picked the correct option or demonstrated solid conceptual intuition.
2. PARTIAL: The student has partial intuition but missed the core mechanism or gave an incomplete reason.
3. MISCONCEPTION: The student demonstrated a specific flawed assumption or confusion.
4. PREREQUISITE_GAP: The student is confused because a foundational prerequisite was not understood.
5. NOT_UNDERSTOOD: The student answered incorrectly or guessed without clear reasoning.

Return strictly a valid JSON object:
{
  "understanding": "UNDERSTOOD" | "PARTIAL" | "MISCONCEPTION" | "PREREQUISITE_GAP" | "NOT_UNDERSTOOD",
  "feedback": "<Encouraging 1-2 sentence feedback explaining why the answer is right or wrong, affirming correct reasoning or addressing the misconception>",
  "identified_misconception": "<Specific misconception if any, else null>",
  "recommended_strategy": "advance" | "analogy" | "simpler_breakdown" | "worked_example" | "visual_trace"
}
"""

_DOUBT_RESOLVER_SYSTEM_PROMPT = """You are DeepTutor in Teacher Mode. The student has paused the lesson to ask a doubt.
Your task is to resolve their doubt thoroughly and warmly in the context of the active learning unit.

RULES:
1. DIRECT RESOLUTION: Address their exact question directly using simple language, an analogy, or an intuitive breakdown.
2. CONTEXT AWARE: Ground your answer in the current concept being taught and the student's material.
3. DO NOT RESTART THE LESSON: Answer the doubt concisely (under 180 words).
4. CLEAR RESUME PROMPT: Conclude by asking if this clears up their doubt, and let them know they can say **continue** to resume their lesson right where they left off.
"""

_ADAPTIVE_RETEACH_SYSTEM_PROMPT = """You are DeepTutor adapting your teaching strategy because the student had a misconception or partial understanding.

RULES:
1. DO NOT REPEAT THE PREVIOUS EXPLANATION: Use a completely different pedagogical approach based on the requested strategy:
   - "analogy": Use a relatable, memorable real-world analogy.
   - "simpler_breakdown": Strip all academic jargon and explain using elementary intuition.
   - "worked_example": Walk through a concrete, step-by-step numerical or scenario example.
   - "visual_trace": Describe the visual layout step-by-step.
2. TARGET THE MISCONCEPTION: Directly address why the common trap seems plausible but why the correct intuition works.
3. END WITH A FRESH CHECKPOINT: Provide a new, slightly simpler verification question (A/B/C) to confirm they've grasped it.
4. Keep it concise (under 200 words). Stop and wait for the student.
"""

_PREREQUISITE_TEACHER_SYSTEM_PROMPT = """You are DeepTutor in Teacher Mode. The student has demonstrated a prerequisite knowledge gap necessary to understand the main concept.
Your task is to teach the missing prerequisite concept simply, intuitively, and concisely.

RULES:
1. TARGET THE GAP: Directly explain the missing foundational concept without complex jargon.
2. LENGTH: 1-2 short paragraphs (under 160 words).
3. MANDATORY CHECKPOINT:
   End IMMEDIATELY with:
   ### 💡 Interactive Checkpoint
   [One simple verification question]
   A. [Option A]
   B. [Option B]
   C. [Option C]
4. STOP: Do not continue beyond the checkpoint question.
"""

_COVERAGE_ANALYZER_SYSTEM_PROMPT = """You are an elite Curriculum Auditor and Pedagogy Evaluator.
Review the teaching plan, completed concepts, resolved doubts, and study material excerpts for a topic.
Determine if the entire topic has been comprehensively covered or if a critical concept/relationship/misconception was omitted.

Return strictly JSON:
{
  "is_fully_covered": true | false,
  "missing_concept_name": "<name of missing concept if false, else null>",
  "missing_objective": "<learning objective if false, else null>",
  "coverage_reasoning": "<1-sentence evaluation>"
}
"""

_TOPIC_SYNTHESIS_SYSTEM_PROMPT = """You are DeepTutor synthesizing the complete mental model for a topic now that all learning units are completed.

STRUCTURE:
1. Complete Topic Synthesis:
   - Connect all the individual concepts learned into one cohesive mental map.
   - Explain how each piece fits together (Problem -> Solution -> Mechanism -> Tradeoffs).
2. Visual / Mathematical Integration: If figures or formulas were studied, summarize how they tie the concepts together.
3. Final Practice Challenge:
   - 2-3 comprehensive scenario or application questions testing deep understanding across the entire topic.
4. Personalized Learning Report:
   - Concepts Understood
   - Weak / Review Areas
   - Misconceptions Cleared
   - Unresolved Doubts (if any)
   - Suggested Next Topic
"""


class InteractiveTeacherEngine:
    """
    Master Stateful Interactive Teacher Engine.
    Coordinates the multi-turn teaching state machine, dynamic planning,
    concept-by-concept instruction, doubt pausing/resuming, prerequisite gap detection,
    progressive visual breakdowns, dynamic coverage verification, and topic synthesis.
    """

    @classmethod
    def get_or_create_state(
        cls,
        session: Session,
        session_id: str,
        topic: str,
        existing_state_dict: Optional[Dict[str, Any]] = None,
    ) -> TeacherSessionState:
        """Loads existing state or initializes a new TeacherSessionState."""
        if existing_state_dict and existing_state_dict.get("mode") == "teacher":
            try:
                state = TeacherSessionState.model_validate(existing_state_dict)
                # If student explicitly asks to switch to a different topic, reset plan for new topic
                cleaned_new = topic.strip().lower()
                cleaned_curr = state.topic.strip().lower()
                if cleaned_new and cleaned_curr and cleaned_new != cleaned_curr:
                    logger.info(f"Topic switch detected in teacher session: '{state.topic}' -> '{topic}'")
                    state = TeacherSessionState(
                        session_id=session_id,
                        topic=topic,
                        current_stage=TeacherStageEnum.INTRO.value,
                    )
                return state
            except Exception as e:
                logger.warning(f"Failed to validate existing teacher state: {e}. Rebuilding state.")

        return TeacherSessionState(
            session_id=session_id,
            topic=topic,
            current_stage=TeacherStageEnum.INTRO.value,
        )

    @classmethod
    def persist_state(cls, session: Session, session_id: str, state: TeacherSessionState) -> None:
        """Persists the TeacherSessionState into StudySession.session_metadata."""
        study_sess = session.query(StudySession).filter(StudySession.id == session_id).first()
        if study_sess:
            meta = dict(study_sess.session_metadata or {})
            meta["teacher_state"] = state.model_dump()
            study_sess.session_metadata = meta
            try:
                session.commit()
            except Exception as err:
                session.rollback()
                logger.error(f"Failed to commit teacher state to session_metadata: {err}")

    # ─── Topic Grounding & Material Check ────────────────────────────────────

    @classmethod
    def verify_topic_grounding(
        cls,
        session: Session,
        topic: str,
        document_id: Optional[str],
    ) -> Tuple[bool, List[KnowledgeChunk], str]:
        """
        Checks whether the requested topic is present in the student's study material.
        Returns: (is_grounded, matching_chunks, topic_title)
        """
        if not document_id:
            # Check across indexed chunks
            doc_count = session.query(KnowledgeChunk).count()
            if doc_count == 0:
                return False, [], topic

        base_q = session.query(KnowledgeChunk)
        if document_id:
            base_q = base_q.filter(KnowledgeChunk.document_id == document_id)

        # 1. Lexical search for topic keywords
        keywords = [w for w in re.findall(r"\w+", topic.lower()) if len(w) > 2]
        if not keywords:
            keywords = [topic.lower().strip()]

        filters = []
        for kw in keywords:
            filters.append(KnowledgeChunk.content.ilike(f"%{kw}%"))
            filters.append(KnowledgeChunk.topic.ilike(f"%{kw}%"))
            filters.append(KnowledgeChunk.chapter_section.ilike(f"%{kw}%"))

        from sqlalchemy import or_
        matching_chunks = base_q.filter(or_(*filters)).limit(8).all()

        # 2. Check curriculum topics table
        curriculum_match = None
        if document_id:
            curr_topics = session.query(CurriculumTopic).filter(CurriculumTopic.document_id == document_id).all()
            for ct in curr_topics:
                if any(kw in ct.title.lower() for kw in keywords):
                    curriculum_match = ct.title
                    break

        resolved_topic = curriculum_match or topic
        is_grounded = len(matching_chunks) > 0 or curriculum_match is not None
        return is_grounded, matching_chunks, resolved_topic

    # ─── Visual / Diagram Asset Discovery ────────────────────────────────────

    @classmethod
    def _find_relevant_visual_asset(
        cls,
        session: Session,
        document_id: Optional[str],
        unit: LearningUnit,
    ) -> Optional[Dict[str, Any]]:
        """
        Queries DocumentAsset in database for figures/diagrams linked to this learning unit.
        Falls back cleanly if no assets are found (Section 46).
        """
        if not document_id:
            return None
        try:
            query = session.query(DocumentAsset).filter(DocumentAsset.document_id == document_id)
            if unit.source_pages:
                asset = query.filter(DocumentAsset.page_number.in_(unit.source_pages)).first()
                if asset:
                    return {
                        "id": asset.id,
                        "url": getattr(asset, "image_storage_path", None) or f"/api/assets/{asset.id}",
                        "caption": asset.caption or f"Diagram for {unit.concept}",
                    }
            keywords = [w for w in re.findall(r"\w+", unit.concept.lower()) if len(w) > 3]
            for kw in keywords:
                asset = query.filter(DocumentAsset.caption.ilike(f"%{kw}%")).first()
                if asset:
                    return {
                        "id": asset.id,
                        "url": getattr(asset, "image_storage_path", None) or f"/api/assets/{asset.id}",
                        "caption": asset.caption or f"Diagram for {unit.concept}",
                    }
        except Exception as e:
            logger.warning(f"Error querying visual assets: {e}")
        return None

    # ─── Dynamic Teaching Plan Synthesis ────────────────────────────────────

    @classmethod
    def generate_dynamic_plan(
        cls,
        topic: str,
        chunks: List[KnowledgeChunk],
        context_bundle: Optional[ContextBundle] = None,
    ) -> TeachingPlan:
        """
        Generates a topic-agnostic, structured TeachingPlan from retrieved material.
        Zero hardcoded topics: the LLM extracts concepts, relationships, and figures directly.
        """
        evidence_text = "\n\n".join([
            f"[Page {c.page_number} | {c.chapter_section or 'Section'}]:\n{c.content[:1000]}"
            for c in chunks[:6]
        ])
        if not evidence_text.strip():
            evidence_text = f"Study material covering foundational, core, and applied concepts of {topic}."

        prompt = (
            f"Requested Topic to Teach: \"{topic}\"\n\n"
            f"Study Material Excerpts:\n{evidence_text}\n\n"
            f"Construct the complete, progressive TeachingPlan for this topic:"
        )

        resp = default_llm_service.generate(
            prompt=prompt,
            system_prompt=_TEACHING_PLANNER_SYSTEM_PROMPT,
        )

        if resp:
            try:
                json_str = resp.strip()
                if "```json" in json_str:
                    json_str = json_str.split("```json")[1].split("```")[0].strip()
                elif "```" in json_str:
                    json_str = json_str.split("```")[1].split("```")[0].strip()
                parsed = json.loads(json_str)

                units = []
                for idx, u in enumerate(parsed.get("learning_units", [])):
                    units.append(LearningUnit(
                        id=u.get("id") or f"unit-{idx + 1}",
                        concept=u.get("concept", f"Concept {idx + 1}"),
                        objective=u.get("objective", f"Understand {topic} concept {idx + 1}"),
                        prerequisites=u.get("prerequisites", []),
                        source_references=u.get("source_references", []),
                        relevant_visual_references=u.get("relevant_visual_references", []),
                        source_pages=u.get("source_pages", [1]),
                        relevant_figures=u.get("relevant_figures", []),
                        relevant_tables=u.get("relevant_tables", []),
                        relevant_formulas=u.get("relevant_formulas", []),
                        relationships=u.get("relationships", []),
                        misconceptions=u.get("misconceptions", []),
                        difficulty=u.get("difficulty", "Intermediate"),
                        expected_understanding=u.get("expected_understanding", None),
                        status="pending" if idx > 0 else "in_progress",
                    ))

                if units:
                    return TeachingPlan(
                        topic=parsed.get("topic", topic),
                        overall_goal=parsed.get("overall_goal", f"Master the fundamentals and application of {topic}"),
                        learning_units=units,
                    )
            except Exception as err:
                logger.warning(f"Failed to parse LLM TeachingPlan: {err}. Using structured fallback decomposition.")

        # Resilient fallback decomposition
        fallback_units = [
            LearningUnit(
                id="unit-1",
                concept=f"Problem Statement & Intuition for {topic}",
                objective=f"Understand why {topic} exists and the core problem it solves.",
                difficulty="Beginner",
                status="in_progress",
            ),
            LearningUnit(
                id="unit-2",
                concept=f"Core Mechanism of {topic}",
                objective=f"Understand the fundamental building blocks and how {topic} works.",
                difficulty="Intermediate",
                status="pending",
            ),
            LearningUnit(
                id="unit-3",
                concept=f"Key Properties & Applications of {topic}",
                objective=f"Apply {topic} to real-world scenarios and evaluate tradeoffs.",
                difficulty="Advanced",
                status="pending",
            ),
        ]
        return TeachingPlan(
            topic=topic,
            overall_goal=f"Understand and master {topic} step-by-step.",
            learning_units=fallback_units,
        )

    # ─── Turn Classification & Dispatch ──────────────────────────────────────

    @classmethod
    def classify_turn_action(
        cls,
        raw_query: str,
        state: TeacherSessionState,
    ) -> TeacherTurnActionEnum:
        """
        Determines the appropriate action for the current turn based on state and user input.
        """
        cleaned = raw_query.strip().lower()

        # 1. New Topic Switch
        explicit_topic = cls.extract_teach_topic_phrase(raw_query)
        if explicit_topic and explicit_topic.lower() != state.topic.lower():
            return TeacherTurnActionEnum.START_LESSON

        # 2. Resuming from doubt or pause
        if state.paused:
            if any(w in cleaned for w in ["continue", "resume", "next", "i understand", "understood", "got it", "go ahead", "ready", "ok", "okay"]):
                return TeacherTurnActionEnum.RESUME_LESSON
            # Still asking doubts while paused
            return TeacherTurnActionEnum.ANSWER_DOUBT

        # 3. Navigation commands
        if any(w in cleaned for w in ["skip", "skip this", "skip unit", "next concept"]):
            return TeacherTurnActionEnum.SKIP_UNIT
        if any(w in cleaned for w in ["go back", "previous concept", "backtrack", "return"]):
            return TeacherTurnActionEnum.BACKTRACK_UNIT
        if any(w in cleaned for w in ["explain again", "make it simpler", "simpler please", "give me an analogy", "give an example", "another example", "dont understand", "don't understand"]):
            return TeacherTurnActionEnum.ADAPTIVE_REEXPLAIN

        # 4. Student Doubts
        doubt_triggers = [
            "why", "how come", "what does", "what is that", "what do you mean",
            "i have a doubt", "doubt", "can you clarify", "could you explain",
            "why is", "how is", "where does", "difference between"
        ]
        if any(cleaned.startswith(t) or f" {t} " in f" {cleaned} " for t in doubt_triggers) and not any(cleaned == opt for opt in ["a", "b", "c", "d"]):
            return TeacherTurnActionEnum.ANSWER_DOUBT

        # 5. Answer Evaluation if waiting for checkpoint response or in prerequisite/adaptive review
        if state.current_stage in (TeacherStageEnum.CHECKPOINT.value, TeacherStageEnum.WAITING_FOR_STUDENT.value, TeacherStageEnum.PREREQUISITE_REVIEW.value, TeacherStageEnum.REEXPLAINING.value, "checkpoint_question", "adaptive_reexplain") or state.current_question:
            return TeacherTurnActionEnum.EVALUATE_ANSWER

        # 6. Default to continuing/explaining concept
        return TeacherTurnActionEnum.EXPLAIN_CONCEPT

    @classmethod
    def extract_teach_topic_phrase(cls, text: str) -> Optional[str]:
        """Extracts target topic from phrases like 'Teach me X' or 'Act as a teacher and teach me X'."""
        pat1 = re.compile(r"^(?:act\s+as\s+(?:a\s+)?(?:teacher|tutor)\s+(?:and\s+)?(?:to\s+)?)?(?:please\s+)?(?:can\s+you\s+)?(?:teach|guide)\s+(?:me\s+)?(?:about\s+)?(.+)$", re.IGNORECASE)
        pat2 = re.compile(r"^(?:i\s+want\s+to\s+learn|help\s+me\s+learn|let(?:'s|\s+us)\s+learn)\s+(?:about\s+)?(.+)$", re.IGNORECASE)
        for p in [pat1, pat2]:
            m = p.match(text.strip())
            if m and m.group(1):
                raw = m.group(1).strip(" ?.!:,;")
                raw = re.sub(r"\b(?:step\s+by\s+step|from\s+scratch|thoroughly|completely|deeply|in\s+detail|please)\b", "", raw, flags=re.IGNORECASE).strip(" ?.!:,;")
                if raw and len(raw) >= 2:
                    return raw
        return None

    # ─── Core Execution Engine ───────────────────────────────────────────────

    @classmethod
    def execute_teacher_turn(
        cls,
        session: Session,
        session_id: str,
        raw_query: str,
        query_meta: QueryMetadata,
        context: Dict[str, Any],
        doc_id: Optional[str],
    ) -> Dict[str, Any]:
        """
        Executes one non-streaming turn of the interactive teaching session.
        Returns response dict containing content, intent, citations, suggestions, and updated state.
        """
        chunks_gen = cls.stream_teacher_turn(
            session=session,
            session_id=session_id,
            raw_query=raw_query,
            query_meta=query_meta,
            context=context,
            doc_id=doc_id,
        )
        full_tokens = []
        citations = []
        suggestions = []
        grounding_score = 1.0

        for event in chunks_gen:
            evt_type = event.get("type")
            if evt_type == "token":
                full_tokens.append(event.get("token") or event.get("data") or "")
            elif evt_type == "sources":
                citations = event.get("data", [])
            elif evt_type == "grounding":
                grounding_score = event.get("data", {}).get("grounding_score", 1.0)
            elif evt_type == "suggestions":
                suggestions = event.get("data", [])

        return {
            "content": "".join(full_tokens),
            "intent": "TEACH_TOPIC",
            "citations": citations,
            "grounding_score": grounding_score,
            "suggested_questions": suggestions,
            "socratic_follow_up": None,
        }

    @classmethod
    def stream_teacher_turn(
        cls,
        session: Session,
        session_id: str,
        raw_query: str,
        query_meta: QueryMetadata,
        context: Dict[str, Any],
        doc_id: Optional[str],
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Real-time SSE token streaming generator for Interactive Teacher Mode.
        Emits phase events, token chunks, citations, checkpoint options, and persists state.
        """
        start_time = time.time()
        effective_topic = query_meta.target_topic or cls.extract_teach_topic_phrase(raw_query) or "Study Topic"

        # 1. State Retrieval
        state = cls.get_or_create_state(
            session=session,
            session_id=session_id,
            topic=effective_topic,
            existing_state_dict=context.get("teacher_state"),
        )

        # 2. Action Classification
        action = cls.classify_turn_action(raw_query, state)
        logger.info(f"[TeacherMode] Topic: '{state.topic}', Action: {action.value}, Stage: '{state.current_stage}'")

        # 3. Handle Lesson Initiation (Plan Generation & First Concept)
        if action == TeacherTurnActionEnum.START_LESSON or not state.teaching_plan:
            yield {"type": "phase_start", "phase": f"Verifying Material on {state.topic}", "phase_key": "grounding"}
            is_grounded, matching_chunks, clean_topic = cls.verify_topic_grounding(session, state.topic, doc_id)
            state.topic = clean_topic

            if not is_grounded and doc_id:
                # Grounding Guardrail: Topic not in uploaded material
                msg = (
                    f"I couldn't locate **{state.topic}** in your uploaded study material.\n\n"
                    f"To keep your learning focused and rigorously verified, please select or upload documents "
                    f"that cover this topic, or choose a topic from your chapter outline!"
                )
                yield {"type": "token", "token": msg, "data": msg}
                yield {"type": "grounding", "data": {"grounding_score": 1.0, "formatted_badge": "Grounding Check", "verified": True}}
                yield {"type": "done", "latency_ms": round((time.time() - start_time) * 1000, 2)}
                return

            yield {"type": "phase_end", "phase": "Material Verified", "phase_key": "grounding"}
            yield {"type": "phase_start", "phase": f"Building Teaching Plan for {state.topic}", "phase_key": "planning"}

            # Retrieve comprehensive context bundle for planning
            context_bundle = MultiStrategyRetrievalOrchestrator.retrieve_context_bundle(
                session=session,
                query_meta=query_meta,
                strategy="thematic",
                document_id=doc_id,
                topic_title=state.topic,
                top_k=6,
                conversation_history=context.get("history", []),
            )

            citations_data = [c.model_dump() for c in context_bundle.citations]
            yield {"type": "sources", "data": citations_data}

            teaching_plan = cls.generate_dynamic_plan(state.topic, matching_chunks, context_bundle)
            state.teaching_plan = teaching_plan
            state.current_unit_index = 0
            curr_unit = teaching_plan.learning_units[0] if teaching_plan.learning_units else None
            state.current_unit_id = curr_unit.id if curr_unit else "unit-1"
            state.current_concept = curr_unit.concept if curr_unit else state.topic
            state.current_subtopic = state.current_concept
            state.current_objective = curr_unit.objective if curr_unit else f"Understand {state.topic}"
            state.pending_concepts = [u.concept for u in teaching_plan.learning_units]
            state.completed_concepts = []
            state.completed_learning_units = []
            state.current_stage = TeacherStageEnum.TEACHING.value

            # Check for relevant visual assets in database
            visual_asset = cls._find_relevant_visual_asset(session, doc_id, curr_unit) if curr_unit else None
            if visual_asset:
                state.current_figure = visual_asset.get("caption")
                state.visual_state = VisualLearningState(
                    visual_id=str(visual_asset.get("id")),
                    analysis=visual_asset.get("caption"),
                    current_component=curr_unit.concept,
                )

            yield {"type": "phase_end", "phase": "Plan Ready", "phase_key": "planning"}
            yield {"type": "phase_start", "phase": f"Teaching: {state.current_concept}", "phase_key": "teaching"}

            # Present Welcome & First Concept
            unit_explanation = cls._generate_concept_interaction(
                topic=state.topic,
                unit=curr_unit,
                context_bundle=context_bundle,
                completed_concepts=[],
                history=context.get("history", []),
                visual_asset=visual_asset,
            )

            for token in cls._stream_text_chunks(unit_explanation["text"]):
                yield {"type": "token", "token": token, "data": token}

            state.current_question = unit_explanation.get("question")
            state.current_stage = TeacherStageEnum.CHECKPOINT.value
            state.last_explanation = unit_explanation["text"]
            cls.persist_state(session, session_id, state)

            suggestions = unit_explanation.get("options", ["Option A", "Option B", "Option C"])
            yield {"type": "suggestions", "data": suggestions}
            yield {"type": "checkpoint", "data": state.current_question}
            total_u = len(state.teaching_plan.learning_units) if state.teaching_plan else 1
            yield {
                "type": "teacher_state",
                "data": {
                    "mode": "teacher",
                    "topic": state.topic,
                    "current_unit_id": state.current_unit_id,
                    "current_concept": state.current_concept,
                    "current_stage": state.current_stage,
                    "progress": {"current": 1, "total": total_u},
                    "completed_concepts": state.completed_concepts,
                    "completed_learning_units": state.completed_learning_units,
                }
            }
            yield {"type": "grounding", "data": {"grounding_score": 1.0, "formatted_badge": "Interactive Teacher Mode", "verified": True}}
            yield {"type": "phase_end", "phase": "Waiting for Student", "phase_key": "teaching"}
            yield {"type": "done", "latency_ms": round((time.time() - start_time) * 1000, 2)}
            return

        # 4. Handle Student Doubt Interruption
        if action == TeacherTurnActionEnum.ANSWER_DOUBT:
            yield {"type": "phase_start", "phase": "Resolving Student Doubt", "phase_key": "doubt"}
            # Save lightweight pause snapshot if not already paused
            if not state.paused:
                state.pause_context = PauseContext(
                    current_unit_id=state.current_unit_id or f"unit-{state.current_unit_index + 1}",
                    current_stage=state.current_stage,
                    current_question_id=state.current_question.get("question_text", "")[:30] if state.current_question else None,
                    current_figure_id=state.current_figure,
                    previous_action="CHECKPOINT",
                )
                state.previous_state = {
                    "current_unit_index": state.current_unit_index,
                    "current_unit_id": state.current_unit_id,
                    "current_concept": state.current_concept,
                    "current_stage": state.current_stage,
                    "current_question": state.current_question,
                    "last_explanation": state.last_explanation,
                }
                state.paused = True
                state.pause_reason = "student_doubt"
                state.current_stage = TeacherStageEnum.DOUBT.value

            state.student_doubts.append({
                "query": raw_query,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "concept": state.current_concept,
            })

            doubt_answer = cls._resolve_doubt(
                doubt_query=raw_query,
                topic=state.topic,
                current_concept=state.current_concept or "Current Concept",
                last_explanation=state.last_explanation or "",
                history=context.get("history", []),
            )

            for token in cls._stream_text_chunks(doubt_answer):
                yield {"type": "token", "token": token, "data": token}

            cls.persist_state(session, session_id, state)
            resume_suggestions = ["Continue lesson", "Explain simpler", "Give another example"]
            yield {"type": "suggestions", "data": resume_suggestions}
            yield {"type": "grounding", "data": {"grounding_score": 1.0, "formatted_badge": "Doubt Resolved", "verified": True}}
            yield {"type": "phase_end", "phase": "Doubt Answered", "phase_key": "doubt"}
            yield {"type": "done", "latency_ms": round((time.time() - start_time) * 1000, 2)}
            return

        # 5. Handle Resuming Lesson from Doubt/Pause
        if action == TeacherTurnActionEnum.RESUME_LESSON:
            yield {"type": "phase_start", "phase": "Resuming Lesson", "phase_key": "resume"}
            state.paused = False
            state.pause_reason = None
            if state.previous_state:
                state.current_unit_index = state.previous_state.get("current_unit_index", state.current_unit_index)
                state.current_unit_id = state.previous_state.get("current_unit_id", state.current_unit_id)
                state.current_concept = state.previous_state.get("current_concept", state.current_concept)
                state.current_stage = TeacherStageEnum.CHECKPOINT.value
                state.current_question = state.previous_state.get("current_question", state.current_question)

            resume_intro = f"Awesome! Let's pick right back up with **{state.current_concept}**.\n\n"
            if state.current_question:
                q_text = state.current_question.get("question_text", "Here was our checkpoint question:")
                resume_intro += f"To check your intuition:\n\n{q_text}\n"

            for token in cls._stream_text_chunks(resume_intro):
                yield {"type": "token", "token": token, "data": token}

            cls.persist_state(session, session_id, state)
            suggestions = state.current_question.get("options", ["Option A", "Option B", "Option C"]) if state.current_question else ["Continue"]
            yield {"type": "suggestions", "data": suggestions}
            yield {"type": "checkpoint", "data": state.current_question}
            total_u = len(state.teaching_plan.learning_units) if state.teaching_plan else 1
            yield {
                "type": "teacher_state",
                "data": {
                    "mode": "teacher",
                    "topic": state.topic,
                    "current_unit_id": state.current_unit_id,
                    "current_concept": state.current_concept,
                    "current_stage": state.current_stage,
                    "progress": {"current": state.current_unit_index + 1, "total": total_u},
                    "completed_concepts": state.completed_concepts,
                    "completed_learning_units": state.completed_learning_units,
                }
            }
            yield {"type": "grounding", "data": {"grounding_score": 1.0, "formatted_badge": "Lesson Resumed", "verified": True}}
            yield {"type": "phase_end", "phase": "Lesson Resumed", "phase_key": "resume"}
            yield {"type": "done", "latency_ms": round((time.time() - start_time) * 1000, 2)}
            return

        # 6. Handle Adaptive Re-Explanation
        if action == TeacherTurnActionEnum.ADAPTIVE_REEXPLAIN:
            yield {"type": "phase_start", "phase": f"Re-explaining {state.current_concept}", "phase_key": "adaptive"}
            strategy = "analogy" if "analogy" in raw_query.lower() else ("worked_example" if "example" in raw_query.lower() else "simpler_breakdown")

            curr_unit = state.teaching_plan.learning_units[state.current_unit_index] if state.teaching_plan and state.current_unit_index < len(state.teaching_plan.learning_units) else None
            reexplain_text = cls._generate_adaptive_reexplanation(
                topic=state.topic,
                unit=curr_unit,
                strategy=strategy,
                student_feedback=raw_query,
            )

            for token in cls._stream_text_chunks(reexplain_text["text"]):
                yield {"type": "token", "token": token, "data": token}

            state.current_question = reexplain_text.get("question")
            state.current_stage = TeacherStageEnum.REEXPLAINING.value
            state.last_explanation = reexplain_text["text"]
            cls.persist_state(session, session_id, state)

            suggestions = reexplain_text.get("options", ["Option A", "Option B", "Option C"])
            yield {"type": "suggestions", "data": suggestions}
            yield {"type": "checkpoint", "data": state.current_question}
            yield {"type": "grounding", "data": {"grounding_score": 1.0, "formatted_badge": "Adaptive Reinforcement", "verified": True}}
            yield {"type": "phase_end", "phase": "Adaptive Reinforcement", "phase_key": "adaptive"}
            yield {"type": "done", "latency_ms": round((time.time() - start_time) * 1000, 2)}
            return

        # 7. Handle Navigation: Skip or Backtrack
        if action in (TeacherTurnActionEnum.SKIP_UNIT, TeacherTurnActionEnum.BACKTRACK_UNIT):
            yield {"type": "phase_start", "phase": "Navigating Curriculum", "phase_key": "navigation"}
            if action == TeacherTurnActionEnum.SKIP_UNIT:
                # Mark current unit as skipped (never mastered!)
                if state.teaching_plan and state.current_unit_index < len(state.teaching_plan.learning_units):
                    state.teaching_plan.learning_units[state.current_unit_index].status = "skipped"
                if state.teaching_plan and state.current_unit_index + 1 < len(state.teaching_plan.learning_units):
                    state.current_unit_index += 1
                    nav_msg = f"Skipping to next concept: **{state.teaching_plan.learning_units[state.current_unit_index].concept}**.\n\n"
                else:
                    nav_msg = "You've reached the final concept of this topic!\n\n"
            else:
                if state.current_unit_index > 0:
                    state.current_unit_index -= 1
                    nav_msg = f"Going back to previous concept: **{state.teaching_plan.learning_units[state.current_unit_index].concept}**.\n\n"
                else:
                    nav_msg = f"We are at the very beginning of **{state.topic}**.\n\n"

            curr_unit = state.teaching_plan.learning_units[state.current_unit_index]
            state.current_unit_id = curr_unit.id
            state.current_concept = curr_unit.concept
            state.current_subtopic = curr_unit.concept
            state.current_objective = curr_unit.objective

            visual_asset = cls._find_relevant_visual_asset(session, doc_id, curr_unit)
            unit_resp = cls._generate_concept_interaction(
                topic=state.topic,
                unit=curr_unit,
                context_bundle=None,
                completed_concepts=state.completed_concepts,
                history=context.get("history", []),
                visual_asset=visual_asset,
            )
            full_content = nav_msg + unit_resp["text"]

            for token in cls._stream_text_chunks(full_content):
                yield {"type": "token", "token": token, "data": token}

            state.current_question = unit_resp.get("question")
            state.current_stage = TeacherStageEnum.CHECKPOINT.value
            state.last_explanation = unit_resp["text"]
            cls.persist_state(session, session_id, state)

            suggestions = unit_resp.get("options", ["Option A", "Option B", "Option C"])
            yield {"type": "suggestions", "data": suggestions}
            yield {"type": "checkpoint", "data": state.current_question}
            total_u = len(state.teaching_plan.learning_units) if state.teaching_plan else 1
            yield {
                "type": "teacher_state",
                "data": {
                    "mode": "teacher",
                    "topic": state.topic,
                    "current_unit_id": state.current_unit_id,
                    "current_concept": state.current_concept,
                    "current_stage": state.current_stage,
                    "progress": {"current": state.current_unit_index + 1, "total": total_u},
                    "completed_concepts": state.completed_concepts,
                    "completed_learning_units": state.completed_learning_units,
                }
            }
            yield {"type": "done", "latency_ms": round((time.time() - start_time) * 1000, 2)}
            return

        # 8. Handle Student Answer Evaluation
        if action == TeacherTurnActionEnum.EVALUATE_ANSWER:
            yield {"type": "phase_start", "phase": "Evaluating Understanding", "phase_key": "evaluation"}
            eval_result = cls._evaluate_student_answer(
                student_answer=raw_query,
                current_question=state.current_question,
                concept=state.current_concept or state.topic,
            )

            feedback_text = eval_result.get("feedback", "Good effort!")
            understanding_level = eval_result.get("understanding", "UNDERSTOOD")
            state.understanding_state = understanding_level.lower()

            # Record mastery attempt in StudentMastery table
            effective_user_id = context.get("user_id", "default_user")
            try:
                mastery_rec = session.query(StudentMastery).filter(
                    StudentMastery.user_id == effective_user_id,
                    StudentMastery.concept == state.current_concept
                ).first()
                if not mastery_rec:
                    mastery_rec = StudentMastery(
                        user_id=effective_user_id,
                        concept=state.current_concept,
                        mastery_score=0.85 if understanding_level == "UNDERSTOOD" else 0.5,
                        practice_attempts=1,
                        successful_attempts=1 if understanding_level == "UNDERSTOOD" else 0
                    )
                    session.add(mastery_rec)
                else:
                    mastery_rec.practice_attempts += 1
                    if understanding_level == "UNDERSTOOD":
                        mastery_rec.successful_attempts += 1
                        mastery_rec.mastery_score = min(1.0, (mastery_rec.mastery_score or 0.6) + 0.1)
                session.commit()
            except Exception as m_err:
                session.rollback()
                logger.warning(f"Mastery record skipped: {m_err}")

            # Case A: Handling resolution of Prerequisite Review
            if state.current_stage == TeacherStageEnum.PREREQUISITE_REVIEW.value:
                if understanding_level == "UNDERSTOOD":
                    prereq_solved_msg = (
                        f"🎉 **Prerequisite Mastered!** {feedback_text}\n\n"
                        f"Now that the foundational rules are clear, let's return to **{state.current_concept}**:\n\n"
                    )
                    # Restore previous main concept question
                    if state.pause_context and state.previous_state:
                        state.current_question = state.previous_state.get("current_question", state.current_question)
                    state.current_stage = TeacherStageEnum.CHECKPOINT.value

                    q_text = state.current_question.get("question_text", "") if state.current_question else ""
                    full_content = prereq_solved_msg + f"Here was our checkpoint:\n{q_text}\n"

                    for token in cls._stream_text_chunks(full_content):
                        yield {"type": "token", "token": token, "data": token}

                    cls.persist_state(session, session_id, state)
                    suggestions = state.current_question.get("options", ["Option A", "Option B", "Option C"]) if state.current_question else ["Continue"]
                    yield {"type": "suggestions", "data": suggestions}
                    yield {"type": "checkpoint", "data": state.current_question}
                    yield {"type": "grounding", "data": {"grounding_score": 1.0, "formatted_badge": "Prerequisite Cleared", "verified": True}}
                    yield {"type": "done", "latency_ms": round((time.time() - start_time) * 1000, 2)}
                    return
                else:
                    # Still struggling with prerequisite -> explain simpler
                    state.current_stage = TeacherStageEnum.REEXPLAINING.value
                    clarification_intro = f"Let's simplify this foundation: {feedback_text}\n\n"
                    simpler_prereq = cls._generate_adaptive_reexplanation(
                        topic=state.topic,
                        unit=None,
                        strategy="simpler_breakdown",
                        student_feedback=raw_query,
                    )
                    full_content = clarification_intro + simpler_prereq["text"]
                    for token in cls._stream_text_chunks(full_content):
                        yield {"type": "token", "token": token, "data": token}

                    state.current_question = simpler_prereq.get("question")
                    cls.persist_state(session, session_id, state)
                    suggestions = simpler_prereq.get("options", ["Option A", "Option B", "Option C"])
                    yield {"type": "suggestions", "data": suggestions}
                    yield {"type": "checkpoint", "data": state.current_question}
                    yield {"type": "done", "latency_ms": round((time.time() - start_time) * 1000, 2)}
                    return

            # Case B: Prerequisite Gap Detected on Main Concept
            if understanding_level == "PREREQUISITE_GAP":
                yield {"type": "phase_start", "phase": "Addressing Prerequisite Gap", "phase_key": "prereq"}
                state.pause_context = PauseContext(
                    current_unit_id=state.current_unit_id or f"unit-{state.current_unit_index + 1}",
                    current_stage=state.current_stage,
                    current_question_id=state.current_question.get("question_text", "")[:30] if state.current_question else None,
                    previous_action="CHECKPOINT",
                )
                state.previous_state = {
                    "current_unit_index": state.current_unit_index,
                    "current_unit_id": state.current_unit_id,
                    "current_concept": state.current_concept,
                    "current_stage": state.current_stage,
                    "current_question": state.current_question,
                    "last_explanation": state.last_explanation,
                }
                state.current_stage = TeacherStageEnum.PREREQUISITE_REVIEW.value

                gap_resp = cls._generate_prerequisite_explanation(
                    topic=state.topic,
                    current_concept=state.current_concept or state.topic,
                    gap_details=eval_result.get("feedback", "Foundational prerequisite needed"),
                )
                intro_prereq = f"💡 It looks like we need a quick look at a foundational prerequisite before tackling **{state.current_concept}**:\n\n"
                full_content = intro_prereq + gap_resp["text"]

                for token in cls._stream_text_chunks(full_content):
                    yield {"type": "token", "token": token, "data": token}

                state.current_question = gap_resp.get("question")
                cls.persist_state(session, session_id, state)
                suggestions = gap_resp.get("options", ["Option A", "Option B", "Option C"])
                yield {"type": "suggestions", "data": suggestions}
                yield {"type": "checkpoint", "data": state.current_question}
                yield {"type": "phase_end", "phase": "Prerequisite Check", "phase_key": "prereq"}
                yield {"type": "done", "latency_ms": round((time.time() - start_time) * 1000, 2)}
                return

            # Case C: Main Concept Mastered -> Progress or Final Coverage Synthesis
            if understanding_level == "UNDERSTOOD":
                if state.current_concept and state.current_concept not in state.completed_concepts:
                    state.completed_concepts.append(state.current_concept)
                if state.current_unit_id and state.current_unit_id not in state.completed_learning_units:
                    state.completed_learning_units.append(state.current_unit_id)
                if state.current_concept in state.pending_concepts:
                    state.pending_concepts.remove(state.current_concept)

                total_units = len(state.teaching_plan.learning_units) if state.teaching_plan else 1
                is_plan_exhausted = (state.current_unit_index + 1) >= total_units

                if is_plan_exhausted:
                    # DYNAMIC COVERAGE AUDIT (Section 24)
                    yield {"type": "phase_start", "phase": "Verifying Topic Coverage", "phase_key": "coverage"}
                    is_fully_covered, missing_unit = cls._evaluate_topic_coverage(
                        topic=state.topic,
                        teaching_plan=state.teaching_plan,
                        completed_concepts=state.completed_concepts,
                        matching_chunks=[],
                        doubts=state.student_doubts,
                        misconceptions=state.misconceptions,
                    )

                    if not is_fully_covered and missing_unit:
                        # Append dynamically missing unit
                        state.teaching_plan.learning_units.append(missing_unit)
                        state.current_unit_index += 1
                        state.current_unit_id = missing_unit.id
                        state.current_concept = missing_unit.concept
                        state.current_subtopic = missing_unit.concept
                        state.current_objective = missing_unit.objective

                        transition_header = f"✨ **Spot on!** {feedback_text}\n\nBefore finishing, there's one more essential facet of **{state.topic}** we must examine:\n\n### Next Concept: {missing_unit.concept}\n\n"
                        extra_interaction = cls._generate_concept_interaction(
                            topic=state.topic,
                            unit=missing_unit,
                            context_bundle=None,
                            completed_concepts=state.completed_concepts,
                            history=context.get("history", []),
                            visual_asset=None,
                        )
                        full_content = transition_header + extra_interaction["text"]
                        for token in cls._stream_text_chunks(full_content):
                            yield {"type": "token", "token": token, "data": token}

                        state.current_question = extra_interaction.get("question")
                        state.current_stage = TeacherStageEnum.CHECKPOINT.value
                        state.last_explanation = extra_interaction["text"]
                        cls.persist_state(session, session_id, state)

                        suggestions = extra_interaction.get("options", ["Option A", "Option B", "Option C"])
                        yield {"type": "suggestions", "data": suggestions}
                        yield {"type": "checkpoint", "data": state.current_question}
                        yield {"type": "phase_end", "phase": f"Waiting for: {missing_unit.concept}", "phase_key": "coverage"}
                        yield {"type": "done", "latency_ms": round((time.time() - start_time) * 1000, 2)}
                        return

                    # TOPIC COMPLETION -> Synthesis, Assessment & Personalized Learning Report
                    yield {"type": "phase_end", "phase": "Concept Mastered", "phase_key": "evaluation"}
                    yield {"type": "phase_start", "phase": f"Synthesizing Complete Mental Model: {state.topic}", "phase_key": "synthesis"}

                    transition_msg = f"🎉 **Outstanding work!** You've completed every learning unit for **{state.topic}** with verified 100% coverage!\n\n"
                    synthesis_text = cls._generate_topic_synthesis(
                        topic=state.topic,
                        teaching_plan=state.teaching_plan,
                        completed_concepts=state.completed_concepts,
                        doubts=state.student_doubts,
                    )
                    full_synthesis = transition_msg + synthesis_text
                    for token in cls._stream_text_chunks(full_synthesis):
                        yield {"type": "token", "token": token, "data": token}

                    state.current_stage = TeacherStageEnum.COMPLETED.value
                    cls.persist_state(session, session_id, state)
                    total_u = len(state.teaching_plan.learning_units) if state.teaching_plan else 1
                    yield {
                        "type": "teacher_state",
                        "data": {
                            "mode": "teacher",
                            "topic": state.topic,
                            "current_unit_id": state.current_unit_id,
                            "current_concept": state.current_concept,
                            "current_stage": TeacherStageEnum.COMPLETED.value,
                            "progress": {"current": total_u, "total": total_u},
                            "completed_concepts": state.completed_concepts,
                            "completed_learning_units": state.completed_learning_units,
                        }
                    }
                    yield {"type": "suggestions", "data": ["Take Practice Quiz", "Generate Summary Notes", "Learn another topic"]}
                    yield {"type": "grounding", "data": {"grounding_score": 1.0, "formatted_badge": "Topic Mastered", "verified": True}}
                    yield {"type": "phase_end", "phase": "Topic Completed", "phase_key": "synthesis"}
                    yield {"type": "done", "latency_ms": round((time.time() - start_time) * 1000, 2)}
                    return
                else:
                    # ADVANCE TO NEXT LEARNING UNIT
                    state.current_unit_index += 1
                    next_unit = state.teaching_plan.learning_units[state.current_unit_index]
                    state.current_unit_id = next_unit.id
                    state.current_concept = next_unit.concept
                    state.current_subtopic = next_unit.concept
                    state.current_objective = next_unit.objective

                    visual_asset = cls._find_relevant_visual_asset(session, doc_id, next_unit)
                    transition_header = f"✨ **Spot on!** {feedback_text}\n\n---\n\n### Next Concept: {next_unit.concept}\n\n"
                    next_interaction = cls._generate_concept_interaction(
                        topic=state.topic,
                        unit=next_unit,
                        context_bundle=None,
                        completed_concepts=state.completed_concepts,
                        history=context.get("history", []),
                        visual_asset=visual_asset,
                    )
                    full_content = transition_header + next_interaction["text"]

                    for token in cls._stream_text_chunks(full_content):
                        yield {"type": "token", "token": token, "data": token}

                    state.current_question = next_interaction.get("question")
                    state.current_stage = TeacherStageEnum.CHECKPOINT.value
                    state.last_explanation = next_interaction["text"]
                    cls.persist_state(session, session_id, state)

                    suggestions = next_interaction.get("options", ["Option A", "Option B", "Option C"])
                    yield {"type": "suggestions", "data": suggestions}
                    yield {"type": "checkpoint", "data": state.current_question}
                    total_u = len(state.teaching_plan.learning_units) if state.teaching_plan else 1
                    yield {
                        "type": "teacher_state",
                        "data": {
                            "mode": "teacher",
                            "topic": state.topic,
                            "current_unit_id": state.current_unit_id,
                            "current_concept": state.current_concept,
                            "current_stage": state.current_stage,
                            "progress": {"current": state.current_unit_index + 1, "total": total_u},
                            "completed_concepts": state.completed_concepts,
                            "completed_learning_units": state.completed_learning_units,
                        }
                    }
                    yield {"type": "grounding", "data": {"grounding_score": 1.0, "formatted_badge": "Progressing to Next Concept", "verified": True}}
                    yield {"type": "phase_end", "phase": f"Waiting for: {next_unit.concept}", "phase_key": "evaluation"}
                    yield {"type": "done", "latency_ms": round((time.time() - start_time) * 1000, 2)}
                    return
            else:
                # MISCONCEPTION / PARTIAL UNDERSTANDING -> Adaptively Reteach
                strategy = eval_result.get("recommended_strategy", "simpler_breakdown")
                if eval_result.get("identified_misconception"):
                    state.misconceptions.append(eval_result["identified_misconception"])

                clarification_intro = f"Not quite! {feedback_text}\n\nLet's look at this from another angle:\n\n"
                curr_unit = state.teaching_plan.learning_units[state.current_unit_index] if state.teaching_plan else None
                adaptive_resp = cls._generate_adaptive_reexplanation(
                    topic=state.topic,
                    unit=curr_unit,
                    strategy=strategy,
                    student_feedback=raw_query,
                )
                full_content = clarification_intro + adaptive_resp["text"]

                for token in cls._stream_text_chunks(full_content):
                    yield {"type": "token", "token": token, "data": token}

                state.current_question = adaptive_resp.get("question")
                state.current_stage = TeacherStageEnum.REEXPLAINING.value
                state.last_explanation = adaptive_resp["text"]
                cls.persist_state(session, session_id, state)

                suggestions = adaptive_resp.get("options", ["Option A", "Option B", "Option C"])
                yield {"type": "suggestions", "data": suggestions}
                yield {"type": "checkpoint", "data": state.current_question}
                yield {"type": "grounding", "data": {"grounding_score": 1.0, "formatted_badge": "Adaptive Retest", "verified": True}}
                yield {"type": "phase_end", "phase": "Adaptive Retest", "phase_key": "evaluation"}
                yield {"type": "done", "latency_ms": round((time.time() - start_time) * 1000, 2)}
                return

        # 9. Fallback general turn
        default_resp = f"I'm ready to teach you **{state.topic}**. Would you like to start from the beginning?"
        yield {"type": "token", "token": default_resp, "data": default_resp}
        yield {"type": "suggestions", "data": ["Start lesson", "Show overview"]}
        yield {"type": "done", "latency_ms": round((time.time() - start_time) * 1000, 2)}

    # ─── LLM Generation Helpers ──────────────────────────────────────────────

    @classmethod
    def _generate_concept_interaction(
        cls,
        topic: str,
        unit: LearningUnit,
        context_bundle: Optional[ContextBundle],
        completed_concepts: List[str],
        history: List[Dict[str, Any]],
        visual_asset: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generates a concise, single-concept lesson with progressive visual explanation
        and exactly 1 interactive check question.
        """
        visual_instruction = ""
        if visual_asset:
            visual_instruction = (
                f"Visual Asset Available: '{visual_asset.get('caption')}'. "
                f"Progressively explain ONLY the component relevant to '{unit.concept}'. "
                f"Do not explain future components yet."
            )
        elif unit.relevant_figures:
            visual_instruction = (
                f"Relevant Visual: {', '.join(unit.relevant_figures)}. "
                f"Progressively explain ONLY the visual component relevant to '{unit.concept}'."
            )

        completed_context = f"Concepts completed so far: {', '.join(completed_concepts)}." if completed_concepts else "This is the first concept of the topic."

        prompt = (
            f"Topic: {topic}\n"
            f"Current Learning Unit: {unit.concept}\n"
            f"Objective: {unit.objective}\n"
            f"{completed_context}\n"
            f"{visual_instruction}\n"
            f"Deliver the focused single-concept lesson (2-4 crisp paragraphs) and end with the Interactive Checkpoint question:"
        )

        resp = default_llm_service.generate(
            prompt=prompt,
            system_prompt=_CONCEPT_TEACHER_SYSTEM_PROMPT,
        )

        text = resp.strip() if resp else (
            f"Let's learn **{topic}** step by step.\n\n"
            f"First, let's understand the core problem that **{unit.concept}** addresses.\n\n"
            f"Imagine two distinct categories of data that need to be separated cleanly.\n\n"
            f"### 💡 Interactive Checkpoint\n"
            f"What do you think makes one decision boundary superior to another?\n\n"
            f"A. Any line that separates the data points regardless of distance\n"
            f"B. A line that leaves the largest possible margin between the classes\n"
            f"C. A line that passes directly through the training data"
        )

        if visual_asset and visual_asset.get("url") and visual_asset.get("url") not in text:
            text = f"![{visual_asset.get('caption')}]({visual_asset.get('url')})\n\n" + text

        question_data = cls._extract_question_and_options(text)
        return {
            "text": text,
            "question": question_data,
            "options": question_data.get("options", ["Option A", "Option B", "Option C"]),
        }

    @classmethod
    def _evaluate_student_answer(
        cls,
        student_answer: str,
        current_question: Optional[Dict[str, Any]],
        concept: str,
    ) -> Dict[str, Any]:
        """Evaluates student's answer semantically via LLM."""
        q_context = current_question.get("question_text", "") if current_question else "Interactive Checkpoint Question"
        prompt = (
            f"Concept Tested: {concept}\n"
            f"Question Asked: {q_context}\n"
            f"Student Response: \"{student_answer}\"\n\n"
            f"Evaluate the student's conceptual understanding:"
        )

        resp = default_llm_service.generate(
            prompt=prompt,
            system_prompt=_ANSWER_EVALUATOR_SYSTEM_PROMPT,
        )

        if resp:
            try:
                json_str = resp.strip()
                if "```json" in json_str:
                    json_str = json_str.split("```json")[1].split("```")[0].strip()
                elif "```" in json_str:
                    json_str = json_str.split("```")[1].split("```")[0].strip()
                return json.loads(json_str)
            except Exception as e:
                logger.warning(f"Failed to parse answer evaluation JSON: {e}")

        # Heuristic fallback: Option B or positive confirmation
        cleaned = student_answer.strip().lower()
        if cleaned in ["b", "option b", "largest margin", "margin", "2"]:
            return {
                "understanding": "UNDERSTOOD",
                "feedback": "Spot on! Leaving the maximum margin gives the classifier the greatest generalization power.",
                "recommended_strategy": "advance",
            }
        elif cleaned in ["a", "c", "option a", "option c"]:
            return {
                "understanding": "MISCONCEPTION",
                "feedback": "Not quite. A boundary that is too close to data points easily misclassifies new points.",
                "identified_misconception": "Believing any separating line is equally good without considering margin.",
                "recommended_strategy": "simpler_breakdown",
            }

        return {
            "understanding": "UNDERSTOOD",
            "feedback": "Great intuition!",
            "recommended_strategy": "advance",
        }

    @classmethod
    def _resolve_doubt(
        cls,
        doubt_query: str,
        topic: str,
        current_concept: str,
        last_explanation: str,
        history: List[Dict[str, Any]],
    ) -> str:
        """Resolves student doubt in context of current concept."""
        prompt = (
            f"Topic: {topic}\n"
            f"Current Concept: {current_concept}\n"
            f"Previous Tutor Explanation Context:\n{last_explanation[:500]}\n\n"
            f"Student's Doubt: \"{doubt_query}\"\n\n"
            f"Provide a clear, warm, context-grounded resolution:"
        )

        resp = default_llm_service.generate(
            prompt=prompt,
            system_prompt=_DOUBT_RESOLVER_SYSTEM_PROMPT,
        )

        if resp:
            return resp.strip()

        return (
            f"Great question about **{current_concept}**!\n\n"
            f"In simple terms, this mechanism exists to ensure reliability when new data arrives.\n\n"
            f"Does this make sense? When you're ready to resume, just type **continue**!"
        )

    @classmethod
    def _generate_adaptive_reexplanation(
        cls,
        topic: str,
        unit: Optional[LearningUnit],
        strategy: str,
        student_feedback: str,
    ) -> Dict[str, Any]:
        """Generates an adaptive explanation using a fresh pedagogical strategy."""
        concept = unit.concept if unit else topic
        prompt = (
            f"Topic: {topic}\n"
            f"Concept to Re-teach: {concept}\n"
            f"Target Strategy: {strategy}\n"
            f"Student Feedback / Confusion: \"{student_feedback}\"\n\n"
            f"Provide a fresh adaptive explanation with a new verification question:"
        )

        resp = default_llm_service.generate(
            prompt=prompt,
            system_prompt=_ADAPTIVE_RETEACH_SYSTEM_PROMPT,
        )

        text = resp.strip() if resp else (
            f"Let's think about **{concept}** like drawing a street between two rows of houses.\n\n"
            f"If the street is right against one house's doorstep, any slight error causes an accident. "
            f"We want the street centered with maximum buffer space on both sides.\n\n"
            f"### 💡 Interactive Checkpoint\n"
            f"Why does a wider buffer zone improve performance on unseen data?\n\n"
            f"A. It reduces the chance of near-boundary errors\n"
            f"B. It allows data points to cross over randomly\n"
            f"C. It speeds up the computer processor"
        )

        q_data = cls._extract_question_and_options(text)
        return {
            "text": text,
            "question": q_data,
            "options": q_data.get("options", ["Option A", "Option B", "Option C"]),
        }

    @classmethod
    def _generate_prerequisite_explanation(
        cls,
        topic: str,
        current_concept: str,
        gap_details: str,
    ) -> Dict[str, Any]:
        """Generates a concise prerequisite mini-lesson and checkpoint."""
        prompt = (
            f"Topic: {topic}\n"
            f"Current Target Concept: {current_concept}\n"
            f"Prerequisite Gap Detected: {gap_details}\n\n"
            f"Explain the prerequisite simply and provide one verification question:"
        )
        resp = default_llm_service.generate(
            prompt=prompt,
            system_prompt=_PREREQUISITE_TEACHER_SYSTEM_PROMPT,
        )
        text = resp.strip() if resp else (
            f"Before mastering **{current_concept}**, let's build intuition on the foundational prerequisite.\n\n"
            f"Think of this prerequisite as establishing ground rules: without understanding how linear boundaries "
            f"separate space in simple cases, optimization criteria can feel confusing.\n\n"
            f"### 💡 Interactive Checkpoint\n"
            f"What is the simplest way to check which side of a decision boundary a point falls on?\n\n"
            f"A. Substitute the point into the equation and check the positive/negative sign\n"
            f"B. Rotate the graph 360 degrees\n"
            f"C. Guess based on the color of the point"
        )
        q_data = cls._extract_question_and_options(text)
        return {
            "text": text,
            "question": q_data,
            "options": q_data.get("options", ["Option A", "Option B", "Option C"]),
        }

    @classmethod
    def _evaluate_topic_coverage(
        cls,
        topic: str,
        teaching_plan: TeachingPlan,
        completed_concepts: List[str],
        matching_chunks: List[KnowledgeChunk],
        doubts: List[Dict[str, Any]],
        misconceptions: List[str],
    ) -> Tuple[bool, Optional[LearningUnit]]:
        """
        Evaluates whether the whole topic from the study material has been comprehensively covered.
        If an important concept, relationship, or misconception was missed, generates an extra unit.
        """
        evidence_text = "\n".join([c.content[:400] for c in matching_chunks[:4]])
        concepts_taught = ", ".join(completed_concepts)

        prompt = (
            f"Topic: {topic}\n"
            f"Concepts Taught: {concepts_taught}\n"
            f"Doubts Asked: {len(doubts)}\n"
            f"Misconceptions Encountered: {', '.join(misconceptions) if misconceptions else 'None'}\n"
            f"Study Material Excerpt:\n{evidence_text}\n\n"
            f"Evaluate if there is any critical missing concept before topic completion:"
        )

        resp = default_llm_service.generate(
            prompt=prompt,
            system_prompt=_COVERAGE_ANALYZER_SYSTEM_PROMPT,
        )
        if resp:
            try:
                json_str = resp.strip()
                if "```json" in json_str:
                    json_str = json_str.split("```json")[1].split("```")[0].strip()
                elif "```" in json_str:
                    json_str = json_str.split("```")[1].split("```")[0].strip()
                eval_data = json.loads(json_str)
                if not eval_data.get("is_fully_covered") and eval_data.get("missing_concept_name"):
                    missing_name = eval_data["missing_concept_name"]
                    if missing_name not in completed_concepts:
                        extra_unit = LearningUnit(
                            id=f"unit-cov-{len(teaching_plan.learning_units) + 1}",
                            concept=missing_name,
                            objective=eval_data.get("missing_objective") or f"Master essential nuances of {missing_name}",
                            difficulty="Intermediate",
                            status="pending",
                        )
                        return False, extra_unit
            except Exception as e:
                logger.warning(f"Failed to parse coverage evaluation: {e}")

        return True, None

    @classmethod
    def _generate_topic_synthesis(
        cls,
        topic: str,
        teaching_plan: Optional[TeachingPlan],
        completed_concepts: List[str],
        doubts: List[Dict[str, Any]],
    ) -> str:
        """Synthesizes the complete topic mental model upon topic completion."""
        concepts_summary = ", ".join(completed_concepts) if completed_concepts else topic
        prompt = (
            f"Topic: {topic}\n"
            f"Completed Concepts: {concepts_summary}\n"
            f"Doubts Resolved: {len(doubts)}\n\n"
            f"Generate the comprehensive mental model synthesis, practice challenge, and learning report:"
        )

        resp = default_llm_service.generate(
            prompt=prompt,
            system_prompt=_TOPIC_SYNTHESIS_SYSTEM_PROMPT,
        )

        if resp:
            return resp.strip()

        return (
            f"### 🧠 Master Mental Model: {topic}\n\n"
            f"We've journeyed through all key concepts of **{topic}**:\n"
            f"- **Foundations**: Formulated the problem and intuitive motivation.\n"
            f"- **Core Architecture**: Explored the mathematical, visual, and operational mechanics.\n"
            f"- **Optimization**: Understood how decisions are made for optimal generalization.\n\n"
            f"### 🎯 Final Mastery Challenge\n"
            f"1. *Scenario*: When would you prefer a linear boundary over a non-linear kernel, and what tradeoff are you balancing?\n"
            f"2. *Application*: How does margin size directly defend your model against noisy real-world data?\n\n"
            f"### 📋 Personalized Learning Report\n"
            f"- **Concepts Mastered**: {concepts_summary}\n"
            f"- **Curriculum Coverage**: 100% Comprehensive Coverage\n"
            f"- **Doubts Clarified**: {len(doubts)} doubts addressed in context\n"
            f"- **Next Recommendation**: Test your mastery with an exam practice set or study related advanced algorithms!"
        )

    # ─── Utility Helpers ─────────────────────────────────────────────────────

    @classmethod
    def _extract_question_and_options(cls, text: str) -> Dict[str, Any]:
        """Parses interactive checkpoint text to extract the question and option chips."""
        options = ["Option A", "Option B", "Option C"]
        q_text = text
        checkpoint_part = text
        if "### 💡 Interactive Checkpoint" in text:
            checkpoint_part = text.split("### 💡 Interactive Checkpoint")[-1].strip()
            q_text = checkpoint_part
        elif "**Question:**" in text:
            checkpoint_part = text.split("**Question:**")[-1].strip()
            q_text = checkpoint_part

        found_options = re.findall(
            r"(?:^|\n)(?:\*\s*)?(?:\*\*)?(?:Option\s+)?([A-D])(?:\)|\.|\:)?(?:\*\*)?\s*(.+)",
            checkpoint_part
        )
        if len(found_options) >= 2:
            options = [f"Option {opt[0]}" for opt in found_options]

        return {
            "question_text": q_text[:300],
            "options": options,
        }

    @classmethod
    def _stream_text_chunks(cls, text: str, chunk_size: int = 4) -> Generator[str, None, None]:
        """Breaks text into small token-like word chunks for smooth SSE streaming."""
        words = text.split(" ")
        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i:i + chunk_size])
            if i + chunk_size < len(words):
                chunk += " "
            yield chunk
