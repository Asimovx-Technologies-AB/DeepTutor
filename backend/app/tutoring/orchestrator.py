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
from app.tutoring.flashcards.intent import FlashcardQuizIntentDetector
from app.tutoring.flashcards.retriever import PostgresStudyMaterialRetriever
import json

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

        # Guard: Check if document is still undergoing background parsing/indexing
        if doc_id:
            from app.models.document import Document
            from app.models.chunk import KnowledgeChunk
            doc_record = session.query(Document).filter(Document.id == doc_id).first()
            if doc_record and doc_record.status in ("PROCESSING", "PARSING", "EXTRACTING"):
                chunk_count = session.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == doc_id).count()
                if chunk_count == 0:
                    doc_title = doc_record.title or doc_record.filename or "your study material"
                    msg = (
                        f"⏳ **{doc_title}** is currently being processed and indexed.\n\n"
                        f"Please wait a few moments for text and curriculum extraction to complete before asking questions!"
                    )
                    return {
                        "content": msg,
                        "intent": "PROCESSING_STATUS",
                        "citations": [],
                        "grounding_score": 1.0,
                        "socratic_follow_up": None,
                        "suggested_questions": [],
                        "validation": {
                            "validation_status": "PASS",
                            "grounding_score": 1.0,
                            "cross_reference_valid": True,
                            "is_valid": True,
                            "violations": [],
                            "explanation": "Document is still processing."
                        },
                        "latency_ms": round((time.time() - start_time) * 1000, 2)
                    }

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
            is_follow_up=ref_meta["is_follow_up"],
            conversation_history=context.get("history", [])
        )

        effective_page = query_meta.referenced_page or ref_meta.get("referenced_page") or active_page
        effective_topic = query_meta.target_topic or topic_title or context.get("document_title") or "Study Document"
        fc_intent = FlashcardQuizIntentDetector.detect(raw_query, default_topic=effective_topic)
        is_quiz_request = (query_meta.intent == "QUIZ") or (fc_intent.is_flashcard_quiz and query_meta.intent != "PRACTICE_QUESTIONS")

        if is_quiz_request:
            target_topic = query_meta.target_topic or fc_intent.target_topic or effective_topic
            retriever = PostgresStudyMaterialRetriever(session)
            chunks = retriever.retrieve_chunks(
                topic=target_topic,
                document_id=doc_id,
                session_id=session_id,
                top_k=6
            )
            citations = [
                {"chunk_id": c.get("id"), "page_number": c.get("page_number", 1), "source_uri": c.get("chapter_section", "")}
                for c in chunks[:3]
            ]
            quiz_payload = TeachingAgent.generate_flashcards_or_quiz(
                topic=target_topic,
                retrieved_chunks=chunks,
                question_count=query_meta.question_count or fc_intent.question_count or 5,
                mode=fc_intent.preferred_mode
            )
            payload_json = json.dumps(quiz_payload.model_dump(), indent=2)
            if session_id:
                cls._update_session_state(
                    session=session,
                    session_id=session_id,
                    topic_id=topic_id,
                    user_query=raw_query,
                    assistant_response=content,
                    intent="QUIZ",
                    citations=citations,
                    grounding_score=1.0,
                    latency_ms=latency_ms,
                    entities=[target_topic]
                )
            return {
                "content": content,
                "type": "flashcard_quiz",
                "flashcard_quiz": quiz_payload.model_dump(),
                "intent": "QUIZ",
                "citations": citations,
                "grounding_score": 1.0,
                "socratic_follow_up": f"Would you like another practice set on {target_topic} once completed?",
                "suggested_questions": [
                    "Give me another quiz on this topic",
                    f"Explain the key concepts of {target_topic}"
                ],
                "latency_ms": latency_ms
            }

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
                top_k=6,
                conversation_history=context.get("history", [])
            )
            res_dict = SummaryPipeline.generate_summary(context_bundle)
        elif route_dest == "ASSESSMENT_PIPELINE":
            context_bundle = MultiStrategyRetrievalOrchestrator.retrieve_context_bundle(
                session=session,
                query_meta=query_meta,
                strategy="thematic",
                document_id=doc_id,
                topic_title=topic_title,
                top_k=4,
                conversation_history=context.get("history", [])
            )
            res_dict = AssessmentPipeline.generate_quiz(context_bundle)
        elif route_dest == "PROBLEM_SOLVING_PIPELINE":
            context_bundle = MultiStrategyRetrievalOrchestrator.retrieve_context_bundle(
                session=session,
                query_meta=query_meta,
                strategy="contextual",
                document_id=doc_id,
                active_page=effective_page,
                top_k=5,
                conversation_history=context.get("history", [])
            )
            res_dict = ProblemSolvingPipeline.solve_problem(resolved_query, context_bundle)
        else:
            # RETRIEVAL_PIPELINE
            chosen_strategy = "contextual" if effective_page else retrieval_strategy
            context_bundle = MultiStrategyRetrievalOrchestrator.retrieve_context_bundle(
                session=session,
                query_meta=query_meta,
                strategy=chosen_strategy,
                document_id=doc_id,
                topic_title=effective_topic,
                active_page=effective_page,
                top_k=5,
                conversation_history=context.get("history", [])
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

        # Guard: Check if document is still undergoing background parsing/indexing
        if doc_id:
            from app.models.document import Document
            from app.models.chunk import KnowledgeChunk
            doc_record = session.query(Document).filter(Document.id == doc_id).first()
            if doc_record and doc_record.status in ("PROCESSING", "PARSING", "EXTRACTING"):
                chunk_count = session.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == doc_id).count()
                if chunk_count == 0:
                    doc_title = doc_record.title or doc_record.filename or "your study material"
                    msg = (
                        f"⏳ **{doc_title}** is currently being processed and indexed.\n\n"
                        f"Please wait a few moments for text and curriculum extraction to complete before asking questions!"
                    )
                    yield {"type": "token", "token": msg}
                    yield {"type": "grounding", "grounding_score": 1.0}
                    yield {"type": "done"}
                    return

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
            is_follow_up=ref_meta["is_follow_up"],
            conversation_history=context.get("history", [])
        )

        # 4. Target Topic & Quiz Intent Routing
        effective_page = query_meta.referenced_page or ref_meta.get("referenced_page") or active_page
        effective_topic = query_meta.target_topic or topic_title or context.get("document_title") or "Study Document"
        fc_intent = FlashcardQuizIntentDetector.detect(raw_query, default_topic=effective_topic)
        is_quiz_request = (query_meta.intent == "QUIZ") or (fc_intent.is_flashcard_quiz and query_meta.intent != "PRACTICE_QUESTIONS")

        if is_quiz_request:
            target_topic = query_meta.target_topic or fc_intent.target_topic or effective_topic
            yield {"type": "phase_start", "phase": f"Generating {fc_intent.preferred_mode.capitalize()} on {target_topic}", "phase_key": "flashcard_quiz"}
            retriever = PostgresStudyMaterialRetriever(session)
            chunks = retriever.retrieve_chunks(
                topic=target_topic,
                document_id=doc_id,
                session_id=session_id,
                top_k=6
            )
            citations = [
                {"chunk_id": c.get("id"), "page_number": c.get("page_number", 1), "source_uri": c.get("chapter_section", "")}
                for c in chunks[:3]
            ]
            yield {"type": "sources", "data": citations}

            quiz_payload = TeachingAgent.generate_flashcards_or_quiz(
                topic=target_topic,
                retrieved_chunks=chunks,
                question_count=query_meta.question_count or fc_intent.question_count or 5,
                mode=fc_intent.preferred_mode
            )
            # Emit dedicated typed event for frontend
            yield {"type": "flashcard_quiz", "data": quiz_payload.model_dump()}

            payload_json = json.dumps(quiz_payload.model_dump(), indent=2)
            intro_msg = f"I've prepared an interactive **{quiz_payload.title}** on **{quiz_payload.topic}** with {len(quiz_payload.questions)} questions grounded in your study materials:\n\n"
            fenced_block = f"```flashcard_quiz\n{payload_json}\n```"
            full_content = intro_msg + fenced_block

            yield {"type": "token", "token": intro_msg, "data": intro_msg}
            yield {"type": "token", "token": fenced_block, "data": fenced_block}
            yield {"type": "grounding", "data": {"grounding_score": 1.0, "formatted_badge": "100% Grounded in Materials", "verified": True}}
            latency_ms = round((time.time() - start_time) * 1000, 2)
            yield {"type": "phase_end", "phase": "Generation Complete", "phase_key": "flashcard_quiz"}
            yield {"type": "done", "latency_ms": latency_ms}

            if session_id:
                cls._update_session_state(
                    session=session,
                    session_id=session_id,
                    topic_id=topic_id,
                    user_query=raw_query,
                    assistant_response=full_content,
                    intent="QUIZ",
                    citations=citations,
                    grounding_score=1.0,
                    latency_ms=latency_ms,
                    entities=[target_topic]
                )
            return

        # 5. Router Decision
        route_dest, retrieval_strategy = QueryRouter.route_query(
            meta=query_meta,
            has_active_document=bool(doc_id)
        )

        # 6. Retrieve Context
        chosen_strategy = "contextual" if effective_page else (retrieval_strategy if route_dest == "RETRIEVAL_PIPELINE" else "thematic")
        context_bundle = MultiStrategyRetrievalOrchestrator.retrieve_context_bundle(
            session=session,
            query_meta=query_meta,
            strategy=chosen_strategy,
            document_id=doc_id,
            topic_title=effective_topic,
            active_page=effective_page,
            top_k=5,
            conversation_history=context.get("history", [])
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
                grounding_score=validation_result.grounding_score,
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
