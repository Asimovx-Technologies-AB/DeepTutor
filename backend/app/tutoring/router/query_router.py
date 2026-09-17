from typing import Tuple, Literal
from app.schemas.tutoring import QueryMetadata
from app.tutoring.router.action_router import ActionRouter

RouteDestination = Literal[
    "RETRIEVAL_PIPELINE",
    "CASUAL_PIPELINE",
    "SUMMARY_PIPELINE",
    "ASSESSMENT_PIPELINE",
    "PROBLEM_SOLVING_PIPELINE",
    "STUDY_PLAN_PIPELINE",
    "DIRECT_LLM_PIPELINE",
    "DOCUMENT_TOPIC_ANALYSIS_PIPELINE",
    "CLARIFY_PIPELINE",
    "INSUFFICIENT_EVIDENCE_PIPELINE",
    "MATERIAL_NOT_SUPPORTED_PIPELINE",
    "ANSWER_CHALLENGE_PIPELINE",
    "TEACHER_MODE_PIPELINE"
]

RetrievalStrategy = Literal[
    "cross_lesson",
    "thematic",
    "multi_concept",
    "contextual"
]


class QueryRouter:
    """
    Router Decision Diamond:
    Routes analyzed query to specialized execution pipelines and selects retrieval strategy.
    """

    @classmethod
    def route_query(cls, meta: QueryMetadata, has_active_document: bool) -> Tuple[RouteDestination, RetrievalStrategy]:
        intent = meta.intent

        # 1. If understanding_result is present, leverage ActionRouter
        if meta.understanding_result:
            exec_route, ret_strat = ActionRouter.route_action(meta.understanding_result, has_active_document)
            strat_mapped: RetrievalStrategy = ret_strat if ret_strat in ("cross_lesson", "thematic", "multi_concept", "contextual") else "contextual"
            if exec_route == "TEACHER_MODE_PIPELINE":
                return "TEACHER_MODE_PIPELINE", "thematic"
            elif exec_route == "CASUAL_PIPELINE":
                return "CASUAL_PIPELINE", "contextual"
            elif exec_route == "SUMMARIZER_PIPELINE":
                return "SUMMARY_PIPELINE", "thematic"
            elif exec_route == "QUIZ_GENERATOR":
                return "ASSESSMENT_PIPELINE", "thematic"
            elif exec_route == "PROBLEM_SOLVER_PIPELINE":
                return "PROBLEM_SOLVING_PIPELINE", "contextual"
            elif exec_route == "STUDY_PLAN_SERVICE":
                return "STUDY_PLAN_PIPELINE", "contextual"
            elif exec_route == "DIRECT_LLM":
                return "DIRECT_LLM_PIPELINE", "contextual"
            elif exec_route == "DOCUMENT_TOPIC_ANALYSIS_PIPELINE":
                return "DOCUMENT_TOPIC_ANALYSIS_PIPELINE", "contextual"
            elif exec_route == "CLARIFICATION_REPLY":
                return "CLARIFY_PIPELINE", "none"
            elif exec_route == "INSUFFICIENT_EVIDENCE_REPLY":
                return "INSUFFICIENT_EVIDENCE_PIPELINE", "none"
            elif exec_route == "MATERIAL_NOT_SUPPORTED_REPLY":
                return "MATERIAL_NOT_SUPPORTED_PIPELINE", "none"
            elif exec_route == "ANSWER_CHALLENGE_PIPELINE":
                return "ANSWER_CHALLENGE_PIPELINE", "none"
            elif exec_route == "RAG_RETRIEVAL":
                return "RETRIEVAL_PIPELINE", strat_mapped

        # 2. Legacy / Fallback matching
        if intent == "TEACH_TOPIC":
            return "TEACHER_MODE_PIPELINE", "thematic"
        elif intent == "ANSWER_CHALLENGE":
            return "ANSWER_CHALLENGE_PIPELINE", "none"
        elif intent in ("CASUAL", "GREETING", "CONFIRMATION"):
            return "CASUAL_PIPELINE", "contextual"
        elif intent in ("SUMMARY", "STUDY_NOTES", "GENERATE_NOTES", "SUMMARIZE"):
            return "SUMMARY_PIPELINE", "thematic"
        elif intent in ("QUIZ", "GENERATE_QUIZ", "GENERATE_FLASHCARDS"):
            return "ASSESSMENT_PIPELINE", "thematic"
        elif intent in ("PROBLEM_SOLVING", "SOLVE_PROBLEM"):
            return "PROBLEM_SOLVING_PIPELINE", "contextual"
        elif intent in ("CREATE_STUDY_PLAN", "MODIFY_STUDY_PLAN"):
            return "STUDY_PLAN_PIPELINE", "contextual"
        elif intent == "DOCUMENT_TOPIC_ANALYSIS":
            return "DOCUMENT_TOPIC_ANALYSIS_PIPELINE", "contextual"

        # 3. Retrieval Pipeline Strategy Selection
        if meta.question_complexity == "comparative" or len(meta.extracted_entities) >= 2 or intent in ("COMPARISON", "COMPARE_CONCEPTS"):
            strategy = "multi_concept"
        elif meta.learning_objective in ["analyze", "evaluate"] or "chapter" in meta.resolved_query.lower():
            strategy = "cross_lesson"
        elif len(meta.extracted_entities) == 1:
            strategy = "thematic"
        else:
            strategy = "contextual"

        return "RETRIEVAL_PIPELINE", strategy
