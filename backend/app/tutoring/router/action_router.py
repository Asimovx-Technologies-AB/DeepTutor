import logging
from typing import Tuple, Optional, Literal, Dict, Any
from app.schemas.tutoring import (
    QueryUnderstandingResult,
    QueryMetadata,
    ActionTypeEnum,
    ResponseTypeEnum,
    RetrievalScopeEnum
)

logger = logging.getLogger(__name__)

ExecutionRoute = Literal[
    "DIRECT_LLM",
    "RAG_RETRIEVAL",
    "QUIZ_GENERATOR",
    "STUDY_PLAN_SERVICE",
    "SUMMARIZER_PIPELINE",
    "PROBLEM_SOLVER_PIPELINE",
    "CASUAL_PIPELINE",
    "CLARIFICATION_REPLY",
    "DOCUMENT_TOPIC_ANALYSIS_PIPELINE"
]

RetrievalStrategyType = Literal[
    "cross_lesson",
    "thematic",
    "multi_concept",
    "contextual",
    "none"
]


class ActionRouter:
    """
    Action Router:
    Takes structured QueryUnderstandingResult and maps to concrete execution route
    and retrieval strategy.
    """

    @classmethod
    def route_action(
        cls,
        understanding: QueryUnderstandingResult,
        has_active_document: bool = True
    ) -> Tuple[ExecutionRoute, RetrievalStrategyType]:
        action = understanding.action
        intent = understanding.intent

        if hasattr(understanding, "decision") and understanding.decision == "CLARIFY":
            return "CLARIFICATION_REPLY", "none"
        if hasattr(understanding, "decision") and understanding.decision == "INSUFFICIENT_EVIDENCE":
            return "INSUFFICIENT_EVIDENCE_REPLY", "none"

        # 1. Low Confidence / Scope Clarification
        if understanding.confidence < 0.5 and understanding.clarification_prompt:
            return "CLARIFICATION_REPLY", "none"

        # 2. Fast Path / Greetings / Pleasantries
        if action == ActionTypeEnum.CASUAL_REPLY.value or intent in ("CASUAL", "GREETING", "CONFIRMATION"):
            return "CASUAL_PIPELINE", "none"

        # 3. Study Plan Actions
        if action in (ActionTypeEnum.CREATE_STUDY_PLAN.value, ActionTypeEnum.MODIFY_STUDY_PLAN.value) or intent in ("CREATE_STUDY_PLAN", "MODIFY_STUDY_PLAN"):
            return "STUDY_PLAN_SERVICE", "none"

        # 4. Assessment / Quiz / Flashcards
        if action in (ActionTypeEnum.GENERATE_QUIZ.value, ActionTypeEnum.GENERATE_FLASHCARDS.value) or intent in ("QUIZ", "GENERATE_QUIZ", "GENERATE_FLASHCARDS"):
            return "QUIZ_GENERATOR", "thematic"

        # 5. Summary / Notes / Roadmap
        if action == ActionTypeEnum.GENERATE_SUMMARY.value or intent in ("SUMMARY", "STUDY_NOTES", "GENERATE_NOTES", "SUMMARIZE"):
            return "SUMMARIZER_PIPELINE", "thematic"

        # 6. Problem Solving / Math / Formula
        if action == ActionTypeEnum.SOLVE_PROBLEM.value or intent in ("PROBLEM_SOLVING", "SOLVE_PROBLEM"):
            return "PROBLEM_SOLVER_PIPELINE", "contextual"

        # 7. Retrieval / RAG vs. Direct LLM
        if action == ActionTypeEnum.EXPLAIN_GENERATED_QUESTION.value:
            return "RAG_RETRIEVAL", "contextual"

        if action == ActionTypeEnum.ANALYZE_IMPORTANT_TOPICS.value or intent == "DOCUMENT_TOPIC_ANALYSIS":
            return "DOCUMENT_TOPIC_ANALYSIS_PIPELINE", "none"

        if not understanding.requires_retrieval or not has_active_document:
            return "DIRECT_LLM", "none"

        # Determine retrieval strategy
        if len(understanding.topics) >= 2 or intent in ("COMPARISON", "COMPARE_CONCEPTS") or len(understanding.entities) >= 2:
            strategy = "multi_concept"
        elif "chapter" in understanding.resolved_query.lower() or "syllabus" in understanding.resolved_query.lower() or understanding.retrieval_scope == RetrievalScopeEnum.SPECIFIC_CHAPTER.value:
            strategy = "cross_lesson"
        elif len(understanding.entities) == 1 or understanding.retrieval_scope == RetrievalScopeEnum.CURRENT_TOPIC.value:
            strategy = "thematic"
        else:
            strategy = "contextual"

        return "RAG_RETRIEVAL", strategy
