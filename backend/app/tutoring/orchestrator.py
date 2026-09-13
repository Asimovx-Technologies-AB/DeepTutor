import time
import logging
from typing import List, Dict, Any, Optional, Generator
from sqlalchemy.orm import Session
from app.models.session import StudySession, ChatMessage, StudentMastery
from app.schemas.tutoring import (
    QueryMetadata, ContextBundle, TeachingResponse, AnswerValidationResult
)
from app.tutoring.analyzer.preprocessor import QueryPreprocessor
from app.tutoring.analyzer.context import ContextIntegrator
from app.tutoring.analyzer.resolver import ReferenceResolver
from app.tutoring.analyzer.understanding import QueryUnderstanding
from app.tutoring.router.query_router import QueryRouter
from app.tutoring.retrieval.orchestrator import MultiStrategyRetrievalOrchestrator
from app.tutoring.teaching.agent import TeachingAgent
from app.tutoring.validation.validator import AnswerValidator
from app.tutoring.pipelines.casual import CasualPipeline
from app.tutoring.pipelines.summary import SummaryPipeline
from app.tutoring.pipelines.assessment import AssessmentPipeline
from app.tutoring.pipelines.problem_solving import ProblemSolvingPipeline

logger = logging.getLogger(__name__)


class TutoringQueryOrchestrator:
    """
    Master Query Analyzer & Tutoring Orchestrator:
    Executes the complete pipeline:
    Query Preprocessing -> Context Integration -> Reference Resolution ->
    Query Understanding -> Router -> Specialized Retrieval -> Teaching Agent ->
    Answer Validation -> Database State Update.
    """

    @classmethod
    def process_query(
        cls,
        session: Session,
        raw_query: str,
        session_id: Optional[str] = None,
        user_id: str = "default_user",
        topic_id: Optional[str] = None,
        topic_title: Optional[str] = None,
        active_page: Optional[int] = None,
    ) -> Dict[str, Any]:
        start_time = time.time()

        # 1. Query Preprocessing
        normalized_query, language, val_meta = QueryPreprocessor.preprocess(raw_query)

        # 2. Context Integration
        context = ContextIntegrator.assemble_context(
            session=session,
            session_id=session_id,
            user_id=user_id,
            topic_id=topic_id
        )
        doc_id = context.get("document_id")

        # 3. Reference Resolution
        resolved_query, ref_meta = ReferenceResolver.resolve_references(
            query=normalized_query,
            conversation_history=context["history"]
        )

        # 4. Query Understanding
        query_meta = QueryUnderstanding.analyze_intent_and_metadata(
            raw_query=raw_query,
            normalized_query=normalized_query,
            resolved_query=resolved_query,
            language=language,
            is_follow_up=ref_meta["is_follow_up"]
        )

        # 5. Router Decision
        route_dest, retrieval_strategy = QueryRouter.route_query(
            meta=query_meta,
            has_active_document=bool(doc_id)
        )

        # 6. Execute Routed Pipeline
        context_bundle = ContextBundle(
            document_id=doc_id,
            topic_id=topic_id,
            topic_title=topic_title or context.get("document_title"),
            resolved_query=resolved_query,
            conversation_history=context["history"],
        )

        if route_dest == "CASUAL_PIPELINE":
            res_dict = CasualPipeline.generate_response(raw_query)
        elif route_dest == "SUMMARY_PIPELINE":
            # Retrieve broad context for summary
            context_bundle = MultiStrategyRetrievalOrchestrator.retrieve_context_bundle(
                session=session,
                query_meta=query_meta,
                strategy="thematic",
                document_id=doc_id,
                topic_title=topic_title,
                top_k=6
            )
            res_dict = SummaryPipeline.generate_summary(context_bundle)
        elif route_dest == "ASSESSMENT_PIPELINE":
            context_bundle = MultiStrategyRetrievalOrchestrator.retrieve_context_bundle(
                session=session,
                query_meta=query_meta,
                strategy="thematic",
                document_id=doc_id,
                topic_title=topic_title,
                top_k=4
            )
            res_dict = AssessmentPipeline.generate_quiz(context_bundle)
        elif route_dest == "PROBLEM_SOLVING_PIPELINE":
            context_bundle = MultiStrategyRetrievalOrchestrator.retrieve_context_bundle(
                session=session,
                query_meta=query_meta,
                strategy="contextual",
                document_id=doc_id,
                active_page=active_page,
                top_k=4
            )
            res_dict = ProblemSolvingPipeline.solve_problem(resolved_query, context_bundle)
        else:
            # RETRIEVAL_PIPELINE
            context_bundle = MultiStrategyRetrievalOrchestrator.retrieve_context_bundle(
                session=session,
                query_meta=query_meta,
                strategy=retrieval_strategy,
                document_id=doc_id,
                topic_title=topic_title,
                active_page=active_page,
                top_k=5
            )
            # Teaching Agent
            teaching_resp = TeachingAgent.generate_teaching_response(query_meta, context_bundle)
            res_dict = {
                "content": teaching_resp.content,
                "intent": teaching_resp.intent,
                "citations": [c.model_dump() for c in teaching_resp.citations],
                "grounding_score": teaching_resp.grounding_score,
                "socratic_follow_up": teaching_resp.socratic_follow_up,
                "suggested_questions": teaching_resp.suggested_questions,
            }

        # 7. Answer Validation Gate
        validation_result = AnswerValidator.validate_response(res_dict["content"], context_bundle)
        res_dict["validation"] = validation_result.model_dump()

        latency_ms = round((time.time() - start_time) * 1000, 2)
        res_dict["latency_ms"] = latency_ms

        # 8. Post-Processing & State Update (Database Persistence)
        if session_id:
            cls._update_session_state(
                session=session,
                session_id=session_id,
                topic_id=topic_id,
                user_query=raw_query,
                assistant_response=res_dict["content"],
                intent=query_meta.intent,
                citations=res_dict["citations"],
                grounding_score=validation_result.grounding_score,
                latency_ms=latency_ms,
                entities=query_meta.extracted_entities
            )

        return res_dict

    @classmethod
    def stream_query_response(
        cls,
        session: Session,
        raw_query: str,
        session_id: Optional[str] = None,
        user_id: str = "default_user",
        topic_id: Optional[str] = None,
        topic_title: Optional[str] = None,
        active_page: Optional[int] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Server-Sent Events (SSE) streaming generator.
        Emits phase events, tokens, citations, and completion.
        Uses true real-time token streaming from TeachingAgent to minimize TTFT.
        """
        start_time = time.time()
        yield {"type": "phase_start", "phase": "Analyzing Query & Context", "phase_key": "analysis"}

        # 1. Query Preprocessing
        normalized_query, language, val_meta = QueryPreprocessor.preprocess(raw_query)

        # 2. Context Integration
        context = ContextIntegrator.assemble_context(
            session=session,
            session_id=session_id,
            user_id=user_id,
            topic_id=topic_id
        )
        doc_id = context.get("document_id")

        # 3. Reference Resolution
        resolved_query, ref_meta = ReferenceResolver.resolve_references(
            query=normalized_query,
            conversation_history=context["history"]
        )

        # 4. Query Understanding
        query_meta = QueryUnderstanding.analyze_intent_and_metadata(
            raw_query=raw_query,
            normalized_query=normalized_query,
            resolved_query=resolved_query,
            language=language,
            is_follow_up=ref_meta["is_follow_up"]
        )

        # 5. Router Decision
        route_dest, retrieval_strategy = QueryRouter.route_query(
            meta=query_meta,
            has_active_document=bool(doc_id)
        )

        # 6. Retrieve Context
        context_bundle = MultiStrategyRetrievalOrchestrator.retrieve_context_bundle(
            session=session,
            query_meta=query_meta,
            strategy=retrieval_strategy if route_dest == "RETRIEVAL_PIPELINE" else "thematic",
            document_id=doc_id,
            topic_title=topic_title or context.get("document_title"),
            active_page=active_page,
            top_k=5
        )

        yield {"type": "phase_end", "phase": "Analysis Complete", "phase_key": "analysis"}
        yield {"type": "phase_start", "phase": "Synthesizing Socratic Explanation", "phase_key": "synthesis"}

        # Emit citations / sources early
        citations_data = [c.model_dump() for c in context_bundle.citations]
        yield {"type": "sources", "data": citations_data}

        # True live token streaming
        full_content_chunks = []
        for token in TeachingAgent.stream_teaching_tokens(query_meta, context_bundle):
            full_content_chunks.append(token)
            yield {"type": "token", "token": token, "data": token}

        full_content = "".join(full_content_chunks)
        validation_result = AnswerValidator.validate_response(full_content, context_bundle)
        yield {"type": "grounding", "data": validation_result.model_dump()}

        latency_ms = round((time.time() - start_time) * 1000, 2)
        yield {"type": "phase_end", "phase": "Synthesis Complete", "phase_key": "synthesis"}
        yield {"type": "done", "latency_ms": latency_ms}

        # 8. Post-Processing & State Update (Database Persistence)
        if session_id:
            cls._update_session_state(
                session=session,
                session_id=session_id,
                topic_id=topic_id,
                user_query=raw_query,
                assistant_response=full_content,
                intent=query_meta.intent,
                citations=citations_data,
                grounding_score=validation_result.faithfulness_score,
                latency_ms=latency_ms,
                entities=query_meta.extracted_entities
            )

    @classmethod
    def _update_session_state(
        cls,
        session: Session,
        session_id: str,
        topic_id: Optional[str],
        user_query: str,
        assistant_response: str,
        intent: str,
        citations: List[Dict[str, Any]],
        grounding_score: float,
        latency_ms: float,
        entities: List[str]
    ):
        try:
            # 1. Ensure Study Session exists
            sess = session.query(StudySession).filter(StudySession.id == session_id).first()
            if not sess:
                sess = StudySession(
                    id=session_id,
                    title="Study Session",
                    subject="General Study",
                    message_count=2,
                    status="active"
                )
                session.add(sess)
                session.flush()
            else:
                sess.message_count = (sess.message_count or 0) + 2

            # 2. Record User & Assistant Messages
            user_msg = ChatMessage(
                session_id=session_id,
                topic_id=topic_id,
                role="user",
                content=user_query,
                intent=intent
            )
            asst_msg = ChatMessage(
                session_id=session_id,
                topic_id=topic_id,
                role="assistant",
                content=assistant_response,
                intent=intent,
                citations=citations,
                grounding_score=grounding_score,
                latency_ms=latency_ms
            )
            session.add_all([user_msg, asst_msg])

            # 4. Update Student Mastery progression
            for ent in entities[:3]:
                mastery = session.query(StudentMastery).filter(
                    StudentMastery.user_id == sess.user_id if sess else "default_user",
                    StudentMastery.concept == ent
                ).first()
                if not mastery:
                    mastery = StudentMastery(
                        user_id=sess.user_id if sess else "default_user",
                        concept=ent,
                        mastery_score=0.6,
                        practice_attempts=1,
                        successful_attempts=1
                    )
                    session.add(mastery)
                else:
                    mastery.practice_attempts += 1
                    mastery.successful_attempts += 1
                    mastery.mastery_score = min(1.0, mastery.mastery_score + 0.05)

            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Error persisting conversation state: {e}")
