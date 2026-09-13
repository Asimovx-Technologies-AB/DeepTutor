from typing import Tuple, Literal
from app.schemas.tutoring import QueryMetadata

RouteDestination = Literal[
    "RETRIEVAL_PIPELINE",
    "CASUAL_PIPELINE",
    "SUMMARY_PIPELINE",
    "ASSESSMENT_PIPELINE",
    "PROBLEM_SOLVING_PIPELINE"
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

        # 1. Non-Retrieval Pipelines
        if intent == "CASUAL":
            return "CASUAL_PIPELINE", "contextual"
        elif intent == "SUMMARY":
            return "SUMMARY_PIPELINE", "thematic"
        elif intent == "QUIZ":
            return "ASSESSMENT_PIPELINE", "thematic"
        elif intent == "PROBLEM_SOLVING":
            return "PROBLEM_SOLVING_PIPELINE", "contextual"

        # 2. Retrieval Pipeline Strategy Selection
        if meta.question_complexity == "comparative" or len(meta.extracted_entities) >= 2:
            strategy = "multi_concept"
        elif meta.learning_objective in ["analyze", "evaluate"] or "chapter" in meta.resolved_query.lower():
            strategy = "cross_lesson"
        elif len(meta.extracted_entities) == 1:
            strategy = "thematic"
        else:
            strategy = "contextual"

        return "RETRIEVAL_PIPELINE", strategy
