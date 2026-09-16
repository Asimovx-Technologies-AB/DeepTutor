import logging
from typing import List, Dict, Any, Optional
from app.schemas.tutoring import QueryUnderstandingResult, QueryMetadata
from app.tutoring.analyzer.preprocessor import QueryPreprocessor
from app.tutoring.analyzer.fast_path import QueryFastPath
from app.tutoring.analyzer.resolver import ReferenceResolver
from app.tutoring.analyzer.understanding import QueryUnderstanding

logger = logging.getLogger(__name__)


class QueryUnderstandingService:
    """
    Dedicated Query Understanding Service:
    Coordinates the end-to-end cognitive analysis pipeline:
    Raw User Query -> Preprocessor -> Fast Path -> Reference Resolution ->
    Query Understanding (Intent, Topics, Entities, Retrieval Needs, Action Planning).
    """

    @classmethod
    def analyze_query(
        cls,
        raw_user_query: str,
        conversation_context: Optional[List[Dict[str, Any]]] = None,
        user_context: Optional[Dict[str, Any]] = None,
        current_subject: Optional[str] = None,
        current_topic: Optional[str] = None,
        available_materials: Optional[List[Dict[str, Any]]] = None,
        available_tools: Optional[List[str]] = None,
    ) -> QueryUnderstandingResult:
        """
        Receives raw user input and context, and produces a strongly-typed QueryUnderstandingResult.
        """
        conversation_context = conversation_context or []
        user_context = user_context or {}
        available_materials = available_materials or []
        available_tools = available_tools or ["teaching_agent", "retrieval_service", "quiz_generator", "study_plan_service"]

        # 1. Stage 1: Preprocessing
        normalized_query, language, val_meta = QueryPreprocessor.preprocess(raw_user_query)

        # 2. Stage 2: Fast Path Evaluation
        fast_result = QueryFastPath.evaluate(
            normalized_query=normalized_query,
            original_query=raw_user_query,
            language=language,
            current_subject=current_subject,
            current_topic=current_topic
        )
        if fast_result is not None:
            logger.debug(f"[QueryUnderstandingService] Fast path matched for query '{raw_user_query}': {fast_result.intent}")
            return fast_result

        # 3. Stage 3: Conversation Reference Resolution & Compact Context
        resolved_query, ref_meta = ReferenceResolver.resolve_references(
            query=normalized_query,
            conversation_history=conversation_context
        )

        # 4. Stage 4: Query Understanding, Intent Detection, Topic/Entity Extraction & Action Planning
        understanding_result = QueryUnderstanding.analyze_query_structured(
            raw_query=raw_user_query,
            normalized_query=normalized_query,
            resolved_query=resolved_query,
            language=language,
            conversation_history=conversation_context,
            current_subject=current_subject,
            current_topic=current_topic,
            available_materials=available_materials,
            available_tools=available_tools
        )

        return understanding_result
