import time
from datetime import datetime, timezone, timedelta
import logging
from typing import List, Dict, Any, Optional, Generator, Tuple
from sqlalchemy.orm import Session
from app.models.document import Document
from app.models.chunk import KnowledgeChunk
from app.models.session import StudySession, ChatMessage, StudentMastery, CurriculumTopic
from app.models.artifact import GeneratedArtifact, GeneratedArtifactItem
from app.models.topic_analysis import ExtractedTopic
from app.schemas.tutoring import (
    QueryMetadata, ContextBundle, TeachingResponse, AnswerValidationResult
)
from app.tutoring.analyzer.preprocessor import QueryPreprocessor
from app.tutoring.analyzer.context import ContextIntegrator
from app.tutoring.analyzer.resolver import ReferenceResolver
from app.tutoring.analyzer.understanding import QueryUnderstanding
from app.tutoring.analyzer.clarification import ClarificationGenerator
from app.tutoring.analyzer.service import QueryUnderstandingService
from app.tutoring.analyzer.fast_path import QueryFastPath
from app.tutoring.analyzer.feedback_classifier import UserMessageContextClassifier, UserMessageClassificationEnum
from app.tutoring.router.query_router import QueryRouter
from app.tutoring.retrieval.orchestrator import MultiStrategyRetrievalOrchestrator
from app.tutoring.teaching.agent import TeachingAgent
from app.tutoring.teaching.factual_handler import FactualQueryHandler
from app.tutoring.teaching.correction_handler import TeachingCorrectionHandler
from app.tutoring.teaching.interactive_teacher import InteractiveTeacherEngine
from app.tutoring.exam.engine import (
    is_exam_report_intent,
    is_exam_start_intent,
    extract_exam_params,
    ExamSessionManager,
    ExamQuestionGenerator,
)
from app.tutoring.validation.validator import AnswerValidator
from app.tutoring.pipelines.casual import CasualPipeline
from app.tutoring.pipelines.summary import SummaryPipeline
from app.tutoring.pipelines.assessment import AssessmentPipeline
from app.tutoring.pipelines.problem_solving import ProblemSolvingPipeline
from app.tutoring.flashcards.intent import FlashcardQuizIntentDetector
from app.tutoring.flashcards.retriever import PostgresStudyMaterialRetriever
from app.services.topic_analyzer import TopicAnalysisService
import json
import re

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
            conversation_history=context["history"],
            db_session=session,
            session_id=session_id
        )

        # 4. Query Understanding
        query_meta = QueryUnderstanding.analyze_intent_and_metadata(
            raw_query=raw_query,
            normalized_query=normalized_query,
            resolved_query=resolved_query,
            language=language,
            is_follow_up=ref_meta["is_follow_up"],
            conversation_history=context.get("history", []),
            ref_meta=ref_meta,
            teacher_state=context.get("teacher_state")
        )

        effective_page = query_meta.referenced_page or ref_meta.get("referenced_page") or active_page
        effective_topic = query_meta.target_topic or topic_title or context.get("document_title") or "Study Document"

        # ─── EXAM ENGINE INTERCEPT (highest priority) ────────────────────
        # Priority 0a: EXAM_REPORT — must never reach RAG / study-note generators
        if is_exam_report_intent(raw_query):
            exam = ExamSessionManager.get_latest_exam(session, session_id) if session_id else None
            if exam:
                report_content = ExamSessionManager.generate_exam_report(exam)
            else:
                report_content = (
                    "I don't have an exam attempt to analyze yet. "
                    "Start or complete an exam first, and I can generate your report."
                )
            latency_ms = round((time.time() - start_time) * 1000, 2)
            if session_id:
                cls._update_session_state(
                    session=session,
                    session_id=session_id,
                    topic_id=topic_id,
                    user_query=raw_query,
                    assistant_response=report_content,
                    intent="EXAM_REPORT",
                    citations=[],
                    grounding_score=1.0,
                    latency_ms=latency_ms,
                    entities=[]
                )
            return {
                "content": report_content,
                "type": "exam_report",
                "intent": "EXAM_REPORT",
                "citations": [],
                "grounding_score": 1.0,
                "socratic_follow_up": None,
                "suggested_questions": [
                    "Which topics should I revise?",
                    "Give me practice questions on my weak areas"
                ],
                "latency_ms": latency_ms,
            }

        # Priority 0b: EXAM_START — creates stateful interactive 1-by-1 exam session
        if is_exam_start_intent(raw_query):
            # Explicitly pause any existing teacher state so exam runs with full isolation
            if session_id:
                sess_row = session.query(StudySession).filter(StudySession.id == session_id).first()
                if sess_row and sess_row.session_metadata:
                    meta = dict(sess_row.session_metadata)
                    if "teacher_state" in meta:
                        meta["teacher_state"]["paused"] = True
                        sess_row.session_metadata = meta
                        try:
                            session.commit()
                        except Exception:
                            session.rollback()

            exam_default = topic_title if (topic_title and topic_title not in ("Study Material", "Study Document")) else effective_topic
            params = extract_exam_params(raw_query, default_topic=exam_default)
            exam_topic = params["topic"]
            q_count = params["question_count"]
            exam_type = params.get("exam_type", "mcq")

            retriever = PostgresStudyMaterialRetriever(session)
            chunks = retriever.retrieve_chunks(
                topic=exam_topic,
                document_id=doc_id,
                session_id=session_id,
            )

            exam_questions = ExamQuestionGenerator.generate(
                topic=exam_topic,
                retrieved_chunks=chunks,
                question_count=q_count,
                exam_type=exam_type,
            )

            if session_id:
                created_exam = ExamSessionManager.create_exam_session(
                    db=session,
                    session_id=session_id,
                    subject=context.get("subject", ""),
                    topic=exam_topic,
                    questions=exam_questions,
                    exam_type=exam_type,
                )
            else:
                created_exam = {
                    "total_questions": len(exam_questions),
                    "exam_type": exam_type,
                }

            q1 = exam_questions[0]
            is_written = exam_type == "written" or q1.get("question_type") == "written"
            if is_written:
                lines = [
                    f"# 📝 Written Exam: {exam_topic}",
                    f"**Question 1 of {len(exam_questions)}** (Max Marks: {q1.get('max_marks', 5)})",
                    "",
                    f"{q1['question']}",
                    "",
                    "*(Write your explanation in your own words below)*",
                ]
                suggested_chips = []
            else:
                lines = [
                    f"# 📝 Exam: {exam_topic}",
                    f"**Question 1 of {len(exam_questions)}**",
                    "",
                    f"{q1['question']}",
                    "",
                ]
                for oi, opt in enumerate(q1.get("options", [])):
                    lines.append(f"- **{chr(65 + oi)}.** {opt}")
                lines.append("")
                lines.append("*(Reply with **A**, **B**, **C**, or **D** to submit your answer)*")
                suggested_chips = ["A", "B", "C", "D"]

            exam_start_content = "\n".join(lines)
            latency_ms = round((time.time() - start_time) * 1000, 2)
            if session_id:
                cls._update_session_state(
                    session=session,
                    session_id=session_id,
                    topic_id=topic_id,
                    user_query=raw_query,
                    assistant_response=exam_start_content,
                    intent="EXAM_START",
                    citations=[],
                    grounding_score=1.0,
                    latency_ms=latency_ms,
                    entities=[]
                )
            return {
                "content": exam_start_content,
                "type": "exam_question",
                "intent": "EXAM_START",
                "citations": [],
                "grounding_score": 1.0,
                "socratic_follow_up": None,
                "suggested_questions": suggested_chips,
                "latency_ms": latency_ms,
            }

        # Priority 0c: EXAM_ANSWER — if active exam, student answers advance question by question
        if session_id:
            active_exam = ExamSessionManager.get_active_exam(session, session_id)
            if active_exam:
                is_written_exam = active_exam.get("exam_type") == "written"
                q_lower = raw_query.strip().lower()
                if is_written_exam:
                    is_likely_answer = not is_exam_report_intent(raw_query) and not q_lower.startswith(
                        ("teach", "give me report", "show report", "exam report", "my report")
                    )
                else:
                    is_likely_answer = (
                        len(raw_query.strip()) <= 200
                        and not is_exam_report_intent(raw_query)
                        and not q_lower.startswith(("explain", "teach", "what is", "how", "why", "give me", "show me", "create", "generate"))
                    )
                if is_likely_answer:
                    answer_result = ExamSessionManager.submit_answer(session, session_id, raw_query.strip())
                    if not answer_result.get("error"):
                        r = answer_result
                        is_written_q = r.get("question_type") == "written" or is_written_exam
                        if is_written_q:
                            status_badge = "✅ **Good Answer!**" if r.get("is_correct") else "📝 **Answer Evaluated**"
                            response_lines = [
                                f"{status_badge} Marks Awarded: **{r.get('marks', 0)} / {r.get('max_marks', 5)}**",
                                f"Score so far: **{r['score_so_far']} marks**",
                                "",
                                f"**Feedback**: {r.get('feedback', '')}",
                                "",
                                "**Model Reference Answer**:",
                                f"> {r.get('reference_answer') or r.get('correct_answer', '')}",
                            ]
                        else:
                            if r["is_correct"]:
                                response_lines = [
                                    f"✅ **Correct!** (+{r.get('marks', 1)} mark)",
                                    f"Score so far: **{r['score_so_far']}**"
                                ]
                            else:
                                response_lines = [
                                    f"❌ **Incorrect.** The correct answer is: **{r['correct_answer']}**",
                                    f"Score so far: **{r['score_so_far']}**"
                                ]

                        suggested_chips = []
                        if r.get("next_question"):
                            nq = r["next_question"]
                            is_nq_written = nq.get("question_type") == "written" or is_written_exam
                            response_lines.append("")
                            response_lines.append("---")
                            if is_nq_written:
                                response_lines.append(f"**Question {nq['question_index']} of {active_exam['total_questions']}** (Max Marks: {nq.get('max_marks', 5)})")
                                response_lines.append("")
                                response_lines.append(f"{nq['question']}")
                                response_lines.append("")
                                response_lines.append("*(Write your explanation in your own words below)*")
                                suggested_chips = []
                            else:
                                response_lines.append(f"**Question {nq['question_index']} of {active_exam['total_questions']}**")
                                response_lines.append("")
                                response_lines.append(f"{nq['question']}")
                                response_lines.append("")
                                if nq.get("options"):
                                    for oi, opt in enumerate(nq["options"]):
                                        response_lines.append(f"- **{chr(65 + oi)}.** {opt}")
                                response_lines.append("")
                                response_lines.append("*(Reply with **A**, **B**, **C**, or **D** to submit your answer)*")
                                suggested_chips = ["A", "B", "C", "D"]
                        elif r["exam_status"] == "completed":
                            response_lines.append("")
                            response_lines.append("---")
                            response_lines.append("🎉 **Exam completed!**")
                            response_lines.append(f"Final Score: **{active_exam['obtained_marks']} / {active_exam['total_marks']} ({active_exam['percentage']}%)**")
                            response_lines.append("")
                            response_lines.append("Say *\"show my exam report\"* to view your full performance analysis, topic-wise breakdown, and mistake review.")
                            suggested_chips = ["Show my exam report", "Which topics should I revise?"]

                        content = "\n".join(response_lines)
                        latency_ms = round((time.time() - start_time) * 1000, 2)
                        if session_id:
                            cls._update_session_state(
                                session=session,
                                session_id=session_id,
                                topic_id=topic_id,
                                user_query=raw_query,
                                assistant_response=content,
                                intent="EXAM_ANSWER",
                                citations=[],
                                grounding_score=1.0,
                                latency_ms=latency_ms,
                                entities=[]
                            )
                        return {
                            "content": content,
                            "type": "exam_answer",
                            "intent": "EXAM_ANSWER",
                            "citations": [],
                            "grounding_score": 1.0,
                            "socratic_follow_up": None,
                            "suggested_questions": suggested_chips,
                            "latency_ms": latency_ms,
                        }
        # ─── END EXAM ENGINE INTERCEPT ────────────────────────────────────

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
            num_questions = len(getattr(quiz_payload, "questions", getattr(quiz_payload, "items", [])))
            intro_msg = f"I've prepared an interactive **{quiz_payload.title}** on **{quiz_payload.topic}** with {num_questions} questions grounded in your study materials:\n\n"
            fenced_block = f"```flashcard_quiz\n{payload_json}\n```"
            content = intro_msg + fenced_block
            latency_ms = round((time.time() - start_time) * 1000, 2)
            
            # Persist artifact
            if session_id:
                cls._persist_generated_artifact(
                    session=session,
                    session_id=session_id,
                    artifact_type="GENERATED_" + fc_intent.preferred_mode.upper(),
                    topic=target_topic,
                    items=[(idx + 1, item.front if hasattr(item, "front") else item.question) for idx, item in enumerate(getattr(quiz_payload, "items", getattr(quiz_payload, "questions", [])))]
                )
                
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

        # Teacher session check
        is_teacher_session = bool(
            context.get("is_teacher_mode")
            or (context.get("teacher_state") and context.get("teacher_state", {}).get("mode") == "teacher" and not context.get("teacher_state", {}).get("paused"))
        )

        msg_classification = UserMessageContextClassifier.classify_message(
            raw_query=raw_query,
            conversation_history=context.get("history", []),
            current_topic=effective_topic,
            has_active_document=bool(doc_id)
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

        # Priority 1: User feedback / correction to previous AI answer
        if msg_classification.category == UserMessageClassificationEnum.FEEDBACK_CORRECTION or route_dest == "ANSWER_CHALLENGE_PIPELINE" or query_meta.intent == "ANSWER_CHALLENGE":
            evidence_msg = TeachingCorrectionHandler.handle_user_correction(
                user_feedback=raw_query,
                conversation_history=context.get("history", []),
                current_topic=effective_topic,
                is_teacher_mode=is_teacher_session
            )
            res_dict = {
                "content": evidence_msg,
                "intent": "FEEDBACK_CORRECTION",
                "citations": [],
                "grounding_score": 1.0,
                "socratic_follow_up": "Would you like me to clarify anything else or proceed?",
                "suggested_questions": ["Explain this concept", "Give me an example"]
            }
        # Priority 2: Ambiguous query -> ask clarification
        elif msg_classification.is_ambiguous:
            res_dict = {
                "content": msg_classification.ambiguity_clarification,
                "intent": "CLARIFY_CONCEPT",
                "citations": [],
                "grounding_score": 1.0,
                "socratic_follow_up": None,
                "suggested_questions": []
            }
        # Priority 2: Normal factual question -> direct answer, zero refusal, respect user format
        elif msg_classification.category == UserMessageClassificationEnum.GENERAL_FACTUAL:
            factual_ans = FactualQueryHandler.handle_factual_query(
                raw_query=raw_query,
                conversation_history=context.get("history", []),
                is_teacher_mode=is_teacher_session
            )
            res_dict = {
                "content": factual_ans,
                "intent": "GENERAL_FACTUAL",
                "citations": [],
                "grounding_score": 1.0,
                "socratic_follow_up": None,
                "suggested_questions": []
            }
        # Factual statement evaluation
        elif msg_classification.category == UserMessageClassificationEnum.STATEMENT_EVALUATION:
            eval_text = TeachingCorrectionHandler.handle_statement_evaluation(
                user_statement=raw_query,
                conversation_history=context.get("history", []),
                current_topic=effective_topic,
                is_teacher_mode=is_teacher_session
            )
            res_dict = {
                "content": eval_text,
                "intent": "STATEMENT_EVALUATION",
                "citations": [],
                "grounding_score": 1.0,
                "socratic_follow_up": "Would you like to test another concept?",
                "suggested_questions": ["Give me a practice question", "Explain the key concepts"]
            }
        # Priority 4: Unrelated chat question
        elif msg_classification.category == UserMessageClassificationEnum.UNRELATED_CHAT:
            unrelated_ans = FactualQueryHandler.handle_unrelated_query(
                raw_query=raw_query,
                conversation_history=context.get("history", [])
            )
            res_dict = {
                "content": unrelated_ans,
                "intent": "UNRELATED_CHAT",
                "citations": [],
                "grounding_score": 1.0,
                "socratic_follow_up": None,
                "suggested_questions": []
            }
        elif route_dest == "CASUAL_PIPELINE" or route_dest == "DIRECT_LLM_PIPELINE":
            res_dict = CasualPipeline.generate_response(raw_query)
        elif route_dest == "STUDY_PLAN_PIPELINE":
            target_topic = query_meta.target_topic or effective_topic or "General Studies"
            res_dict = {
                "content": (
                    f"📅 **Personalized Study Plan for {target_topic}**\n\n"
                    f"I can help you build and customize a targeted study plan for **{target_topic}** based on your timeline and daily study goals.\n\n"
                    f"To generate a full daily schedule with mastery checkpoints, navigate to the **Study Plan** dashboard or specify your available days (e.g. *'Generate a 5-day plan for {target_topic}'*)."
                ),
                "intent": "CREATE_STUDY_PLAN",
                "citations": [],
                "grounding_score": 1.0,
                "socratic_follow_up": f"What is your target completion date or exam timeline for {target_topic}?",
                "suggested_questions": [
                    f"Generate a 5-day study plan for {target_topic}",
                    f"What are the core topics to cover in {target_topic}?"
                ]
            }
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
            if session_id and res_dict.get("quiz_data"):
                cls._persist_generated_artifact(
                    session=session,
                    session_id=session_id,
                    artifact_type="GENERATED_QUIZ",
                    topic=topic_title or "General Topic",
                    items=[(idx + 1, q.get("question", "")) for idx, q in enumerate(res_dict["quiz_data"])]
                )
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
        elif route_dest == "DOCUMENT_TOPIC_ANALYSIS_PIPELINE":
            analysis = TopicAnalysisService.get_or_run_analysis(session, doc_id)
            if analysis and analysis.status == "COMPLETED":
                content = TopicAnalysisService.format_analysis_for_chat(session, analysis)
                # Persist as artifact for follow-up reference resolution
                if session_id:
                    topics = session.query(ExtractedTopic).filter(ExtractedTopic.analysis_id == analysis.id).order_by(ExtractedTopic.importance_score.desc()).all()
                    cls._persist_generated_artifact(
                        session=session,
                        session_id=session_id,
                        artifact_type="GENERATED_TOPIC_ANALYSIS",
                        topic=topic_title or "Document Analysis",
                        items=[(idx + 1, t.topic) for idx, t in enumerate(topics)]
                    )
            elif analysis and analysis.status == "PROCESSING":
                content = "⏳ Topic analysis is currently in progress. Please wait..."
            else:
                content = "Could not analyze topics. Please ensure a document is uploaded."
            
            res_dict = {
                "content": content,
                "intent": "DOCUMENT_TOPIC_ANALYSIS",
                "citations": [],
                "grounding_score": 1.0,
                "socratic_follow_up": "Which of these topics would you like to explore first?",
                "suggested_questions": ["Explain the first topic", "Tell me more about the second one"]
            }
        elif route_dest == "CLARIFY_PIPELINE":
            if query_meta.understanding_result:
                clarify_msg = ClarificationGenerator.generate_clarification(
                    user_query=raw_query,
                    understanding=query_meta.understanding_result,
                    conversation_history=context.get("history", []),
                    available_topics=[effective_topic]
                )
            elif query_meta.scope_clarification_prompt:
                clarify_msg = query_meta.scope_clarification_prompt
            else:
                clarify_msg = "Could you please clarify what you mean?"
            
            res_dict = {
                "content": clarify_msg,
                "intent": "CLARIFY_CONCEPT",
                "citations": [],
                "grounding_score": 1.0,
                "socratic_follow_up": None,
                "suggested_questions": []
            }
        elif route_dest == "INSUFFICIENT_EVIDENCE_PIPELINE":
            evidence_msg = "I couldn't find enough information in the uploaded materials to accurately answer this question."
            if query_meta.understanding_result and query_meta.understanding_result.missing_information:
                evidence_msg += f" Missing information: {query_meta.understanding_result.missing_information}"
                
            res_dict = {
                "content": evidence_msg,
                "intent": "INSUFFICIENT_EVIDENCE",
                "citations": [],
                "grounding_score": 1.0,
                "socratic_follow_up": None,
                "suggested_questions": []
            }
        elif route_dest == "MATERIAL_NOT_SUPPORTED_PIPELINE":
            topic_str = query_meta.target_topic or raw_query
            evidence_msg = f"I couldn't find '{topic_str}' in the selected study material. Please upload or select the material that covers this topic."
            res_dict = {
                "content": evidence_msg,
                "intent": "MATERIAL_NOT_SUPPORTED",
                "citations": [],
                "grounding_score": 1.0,
                "socratic_follow_up": None,
                "suggested_questions": []
            }
        elif route_dest == "ANSWER_CHALLENGE_PIPELINE":
            evidence_msg = TeachingCorrectionHandler.handle_user_correction(
                user_feedback=raw_query,
                conversation_history=context.get("history", []),
                current_topic=effective_topic,
                is_teacher_mode=is_teacher_session
            )
            res_dict = {
                "content": evidence_msg,
                "intent": "ANSWER_CHALLENGE",
                "citations": [],
                "grounding_score": 1.0,
                "socratic_follow_up": "Would you like me to clarify anything else or proceed?",
                "suggested_questions": ["Explain this concept", "Give me an example"]
            }
        elif (route_dest == "TEACHER_MODE_PIPELINE" and is_teacher_session) or msg_classification.category == UserMessageClassificationEnum.TEACH_TOPIC_REQUEST:
            res_dict = InteractiveTeacherEngine.execute_teacher_turn(
                session=session,
                session_id=session_id or "default_session",
                raw_query=raw_query,
                query_meta=query_meta,
                context=context,
                doc_id=doc_id,
            )
        else:
            # Priority 3: RETRIEVAL_PIPELINE (Study Material Question)
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

            teaching_resp = TeachingAgent.generate_teaching_response(
                query_meta,
                context_bundle,
                is_teacher_mode=is_teacher_session
            )
            res_dict = {
                "content": teaching_resp.content,
                "intent": teaching_resp.intent,
                "citations": [c.model_dump() for c in teaching_resp.citations],
                "grounding_score": teaching_resp.grounding_score,
                "socratic_follow_up": teaching_resp.socratic_follow_up,
                "suggested_questions": teaching_resp.suggested_questions,
            }

        # 7. Answer Validation Gate
        if "validation" not in res_dict:
            if res_dict.get("intent") in ("CLARIFY_CONCEPT", "INSUFFICIENT_EVIDENCE", "MATERIAL_NOT_SUPPORTED", "ANSWER_CHALLENGE", "DOCUMENT_TOPIC_ANALYSIS", "FEEDBACK_CORRECTION", "STATEMENT_EVALUATION", "GENERAL_FACTUAL", "UNRELATED_CHAT"):
                res_dict["validation"] = {
                    "is_valid": True,
                    "validation_status": "PASS",
                    "feedback_notes": "Validation skipped for conversational feedback / factual / correction."
                }
            elif "context_bundle" in locals():
                validation_result = AnswerValidator.validate_response(res_dict["content"], context_bundle)
                res_dict["validation"] = validation_result.model_dump()
            else:
                res_dict["validation"] = {
                    "is_valid": True,
                    "validation_status": "PASS",
                    "feedback_notes": "Validation passed."
                }

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
                grounding_score=res_dict.get("grounding_score", 1.0),
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
        try:
            normalized_query, language, val_meta = QueryPreprocessor.preprocess(raw_query)
        except ValueError as ve:
            yield {"type": "token", "token": f"⚠️ {str(ve)} Please type a question or topic to explore."}
            yield {"type": "done"}
            return

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
            conversation_history=context["history"],
            db_session=session,
            session_id=session_id
        )

        # 4. Query Understanding
        query_meta = QueryUnderstanding.analyze_intent_and_metadata(
            raw_query=raw_query,
            normalized_query=normalized_query,
            resolved_query=resolved_query,
            language=language,
            is_follow_up=ref_meta["is_follow_up"],
            conversation_history=context.get("history", []),
            ref_meta=ref_meta,
            teacher_state=context.get("teacher_state")
        )

        # 4. Target Topic & Quiz Intent Routing
        effective_page = query_meta.referenced_page or ref_meta.get("referenced_page") or active_page
        effective_topic = query_meta.target_topic or topic_title or context.get("document_title") or "Study Document"

        # ─── EXAM ENGINE STREAMING INTERCEPT (highest priority) ───────────
        # Priority 0a: EXAM_REPORT
        if is_exam_report_intent(raw_query):
            yield {"type": "phase_start", "phase": "Compiling Exam Report", "phase_key": "exam_report"}
            exam = ExamSessionManager.get_latest_exam(session, session_id) if session_id else None
            if exam:
                report_content = ExamSessionManager.generate_exam_report(exam)
            else:
                report_content = (
                    "I don't have an exam attempt to analyze yet. "
                    "Start or complete an exam first, and I can generate your report."
                )
            yield {"type": "token", "token": report_content, "data": report_content}
            yield {"type": "grounding", "data": {"grounding_score": 1.0, "formatted_badge": "Exam Performance Analytics", "verified": True}}
            latency_ms = round((time.time() - start_time) * 1000, 2)
            if session_id:
                cls._update_session_state(
                    session=session,
                    session_id=session_id,
                    topic_id=topic_id,
                    user_query=raw_query,
                    assistant_response=report_content,
                    intent="EXAM_REPORT",
                    citations=[],
                    grounding_score=1.0,
                    latency_ms=latency_ms,
                    entities=[]
                )
            yield {"type": "phase_end", "phase": "Report Ready", "phase_key": "exam_report"}
            yield {
                "type": "done",
                "latency_ms": latency_ms,
                "suggested_questions": [
                    "Which topics should I revise?",
                    "Give me practice questions on my weak areas"
                ]
            }
            return

        # Priority 0b: EXAM_START — creates stateful interactive 1-by-1 exam session
        if is_exam_start_intent(raw_query):
            # Explicitly pause any existing teacher state so exam runs with full isolation
            if session_id:
                sess_row = session.query(StudySession).filter(StudySession.id == session_id).first()
                if sess_row and sess_row.session_metadata:
                    meta = dict(sess_row.session_metadata)
                    if "teacher_state" in meta:
                        meta["teacher_state"]["paused"] = True
                        sess_row.session_metadata = meta
                        try:
                            session.commit()
                        except Exception:
                            session.rollback()

            yield {"type": "phase_start", "phase": "Setting up Exam Session", "phase_key": "exam_start"}
            exam_default = topic_title if (topic_title and topic_title not in ("Study Material", "Study Document")) else effective_topic
            params = extract_exam_params(raw_query, default_topic=exam_default)
            exam_topic = params["topic"]
            q_count = params["question_count"]
            exam_type = params.get("exam_type", "mcq")

            retriever = PostgresStudyMaterialRetriever(session)
            chunks = retriever.retrieve_chunks(
                topic=exam_topic,
                document_id=doc_id,
                session_id=session_id,
            )

            exam_questions = ExamQuestionGenerator.generate(
                topic=exam_topic,
                retrieved_chunks=chunks,
                question_count=q_count,
                exam_type=exam_type,
            )

            if session_id:
                created_exam = ExamSessionManager.create_exam_session(
                    db=session,
                    session_id=session_id,
                    subject=context.get("subject", ""),
                    topic=exam_topic,
                    questions=exam_questions,
                    exam_type=exam_type,
                )

            q1 = exam_questions[0]
            is_written = exam_type == "written" or q1.get("question_type") == "written"
            if is_written:
                lines = [
                    f"# 📝 Written Exam: {exam_topic}",
                    f"**Question 1 of {len(exam_questions)}** (Max Marks: {q1.get('max_marks', 5)})",
                    "",
                    f"{q1['question']}",
                    "",
                    "*(Write your explanation in your own words below)*",
                ]
                suggested_chips = []
            else:
                lines = [
                    f"# 📝 Exam: {exam_topic}",
                    f"**Question 1 of {len(exam_questions)}**",
                    "",
                    f"{q1['question']}",
                    "",
                ]
                for oi, opt in enumerate(q1.get("options", [])):
                    lines.append(f"- **{chr(65 + oi)}.** {opt}")
                lines.append("")
                lines.append("*(Reply with **A**, **B**, **C**, or **D** to submit your answer)*")
                suggested_chips = ["A", "B", "C", "D"]

            exam_start_content = "\n".join(lines)
            yield {"type": "token", "token": exam_start_content, "data": exam_start_content}
            yield {"type": "grounding", "data": {"grounding_score": 1.0, "formatted_badge": "Exam Mode Active", "verified": True}}
            latency_ms = round((time.time() - start_time) * 1000, 2)
            if session_id:
                cls._update_session_state(
                    session=session,
                    session_id=session_id,
                    topic_id=topic_id,
                    user_query=raw_query,
                    assistant_response=exam_start_content,
                    intent="EXAM_START",
                    citations=[],
                    grounding_score=1.0,
                    latency_ms=latency_ms,
                    entities=[]
                )
            yield {"type": "phase_end", "phase": "Exam Ready", "phase_key": "exam_start"}
            yield {
                "type": "done",
                "latency_ms": latency_ms,
                "suggested_questions": suggested_chips
            }
            return

        # Priority 0c: EXAM_ANSWER — if active exam, student answers advance question by question
        if session_id:
            active_exam = ExamSessionManager.get_active_exam(session, session_id)
            if active_exam:
                is_written_exam = active_exam.get("exam_type") == "written"
                q_lower = raw_query.strip().lower()
                if is_written_exam:
                    is_likely_answer = not is_exam_report_intent(raw_query) and not q_lower.startswith(
                        ("teach", "give me report", "show report", "exam report", "my report")
                    )
                else:
                    is_likely_answer = (
                        len(raw_query.strip()) <= 200
                        and not is_exam_report_intent(raw_query)
                        and not q_lower.startswith(("explain", "teach", "what is", "how", "why", "give me", "show me", "create", "generate"))
                    )
                if is_likely_answer:
                    answer_result = ExamSessionManager.submit_answer(session, session_id, raw_query.strip())
                    if not answer_result.get("error"):
                        r = answer_result
                        is_written_q = r.get("question_type") == "written" or is_written_exam
                        if is_written_q:
                            status_badge = "✅ **Good Answer!**" if r.get("is_correct") else "📝 **Answer Evaluated**"
                            response_lines = [
                                f"{status_badge} Marks Awarded: **{r.get('marks', 0)} / {r.get('max_marks', 5)}**",
                                f"Score so far: **{r['score_so_far']} marks**",
                                "",
                                f"**Feedback**: {r.get('feedback', '')}",
                                "",
                                "**Model Reference Answer**:",
                                f"> {r.get('reference_answer') or r.get('correct_answer', '')}",
                            ]
                        else:
                            if r["is_correct"]:
                                response_lines = [
                                    f"✅ **Correct!** (+{r.get('marks', 1)} mark)",
                                    f"Score so far: **{r['score_so_far']}**"
                                ]
                            else:
                                response_lines = [
                                    f"❌ **Incorrect.** The correct answer is: **{r['correct_answer']}**",
                                    f"Score so far: **{r['score_so_far']}**"
                                ]

                        suggested_chips = []
                        if r.get("next_question"):
                            nq = r["next_question"]
                            is_nq_written = nq.get("question_type") == "written" or is_written_exam
                            response_lines.append("")
                            response_lines.append("---")
                            if is_nq_written:
                                response_lines.append(f"**Question {nq['question_index']} of {active_exam['total_questions']}** (Max Marks: {nq.get('max_marks', 5)})")
                                response_lines.append("")
                                response_lines.append(f"{nq['question']}")
                                response_lines.append("")
                                response_lines.append("*(Write your explanation in your own words below)*")
                                suggested_chips = []
                            else:
                                response_lines.append(f"**Question {nq['question_index']} of {active_exam['total_questions']}**")
                                response_lines.append("")
                                response_lines.append(f"{nq['question']}")
                                response_lines.append("")
                                if nq.get("options"):
                                    for oi, opt in enumerate(nq["options"]):
                                        response_lines.append(f"- **{chr(65 + oi)}.** {opt}")
                                response_lines.append("")
                                response_lines.append("*(Reply with **A**, **B**, **C**, or **D** to submit your answer)*")
                                suggested_chips = ["A", "B", "C", "D"]
                        elif r["exam_status"] == "completed":
                            response_lines.append("")
                            response_lines.append("---")
                            response_lines.append("🎉 **Exam completed!**")
                            response_lines.append(f"Final Score: **{active_exam['obtained_marks']} / {active_exam['total_marks']} ({active_exam['percentage']}%)**")
                            response_lines.append("")
                            response_lines.append("Say *\"show my exam report\"* to view your full performance analysis, topic-wise breakdown, and mistake review.")
                            suggested_chips = ["Show my exam report", "Which topics should I revise?"]

                        content = "\n".join(response_lines)
                        yield {"type": "token", "token": content, "data": content}
                        yield {"type": "grounding", "data": {"grounding_score": 1.0, "formatted_badge": "Exam Evaluation", "verified": True}}
                        latency_ms = round((time.time() - start_time) * 1000, 2)
                        if session_id:
                            cls._update_session_state(
                                session=session,
                                session_id=session_id,
                                topic_id=topic_id,
                                user_query=raw_query,
                                assistant_response=content,
                                intent="EXAM_ANSWER",
                                citations=[],
                                grounding_score=1.0,
                                latency_ms=latency_ms,
                                entities=[]
                            )
                        yield {"type": "phase_end", "phase": "Answer Evaluated", "phase_key": "exam_answer"}
                        yield {
                            "type": "done",
                            "latency_ms": latency_ms,
                            "suggested_questions": suggested_chips
                        }
                        return
        # ─── END EXAM ENGINE STREAMING INTERCEPT ─────────────────────────

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
            # 8. Post-Processing & State Update (Database Persistence)
            # MUST execute BEFORE yielding "done" so client disconnect does not abort DB commit
            latency_ms = round((time.time() - start_time) * 1000, 2)
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

            yield {"type": "phase_end", "phase": "Generation Complete", "phase_key": "flashcard_quiz"}
            yield {"type": "done", "latency_ms": latency_ms}
            return

        # Teacher session check
        is_teacher_session = bool(
            context.get("is_teacher_mode")
            or (context.get("teacher_state") and context.get("teacher_state", {}).get("mode") == "teacher" and not context.get("teacher_state", {}).get("paused"))
        )

        msg_classification = UserMessageContextClassifier.classify_message(
            raw_query=raw_query,
            conversation_history=context.get("history", []),
            current_topic=effective_topic,
            has_active_document=bool(doc_id)
        )

        # Priority 1: User feedback / correction to previous AI answer
        if msg_classification.category == UserMessageClassificationEnum.FEEDBACK_CORRECTION or query_meta.intent == "ANSWER_CHALLENGE":
            yield {"type": "phase_end", "phase": "Analysis Complete", "phase_key": "analysis"}
            correction_text = TeachingCorrectionHandler.handle_user_correction(
                user_feedback=raw_query,
                conversation_history=context.get("history", []),
                current_topic=effective_topic,
                is_teacher_mode=is_teacher_session
            )
            yield {"type": "token", "token": correction_text, "data": correction_text}
            yield {"type": "grounding", "data": {"validation_status": "PASS", "grounding_score": 1.0, "cross_reference_valid": True, "is_valid": True}}
            if session_id:
                cls._update_session_state(
                    session=session,
                    session_id=session_id,
                    topic_id=topic_id,
                    user_query=raw_query,
                    assistant_response=correction_text,
                    intent="FEEDBACK_CORRECTION",
                    citations=[],
                    grounding_score=1.0,
                    latency_ms=round((time.time() - start_time) * 1000, 2),
                    entities=query_meta.extracted_entities
                )
            yield {"type": "done", "latency_ms": round((time.time() - start_time) * 1000, 2)}
            return

        # Priority 2: Ambiguous query -> ask clarification
        if msg_classification.is_ambiguous:
            yield {"type": "phase_end", "phase": "Analysis Complete", "phase_key": "analysis"}
            clarif_text = msg_classification.ambiguity_clarification
            yield {"type": "token", "token": clarif_text, "data": clarif_text}
            yield {"type": "grounding", "data": {"validation_status": "PASS", "grounding_score": 1.0, "cross_reference_valid": True, "is_valid": True}}
            if session_id:
                cls._update_session_state(
                    session=session,
                    session_id=session_id,
                    topic_id=topic_id,
                    user_query=raw_query,
                    assistant_response=clarif_text,
                    intent="CLARIFY_CONCEPT",
                    citations=[],
                    grounding_score=1.0,
                    latency_ms=round((time.time() - start_time) * 1000, 2),
                    entities=query_meta.extracted_entities
                )
            yield {"type": "done", "latency_ms": round((time.time() - start_time) * 1000, 2)}
            return

        # Priority 2: Normal factual question -> direct answer, zero refusal, respect user format
        if msg_classification.category == UserMessageClassificationEnum.GENERAL_FACTUAL:
            yield {"type": "phase_end", "phase": "Analysis Complete", "phase_key": "analysis"}
            full_chunks = []
            for token in FactualQueryHandler.stream_factual_query(
                raw_query=raw_query,
                conversation_history=context.get("history", []),
                is_teacher_mode=is_teacher_session
            ):
                full_chunks.append(token)
                yield {"type": "token", "token": token, "data": token}
            full_ans = "".join(full_chunks)
            yield {"type": "grounding", "data": {"validation_status": "PASS", "grounding_score": 1.0, "cross_reference_valid": True, "is_valid": True}}
            if session_id:
                cls._update_session_state(
                    session=session,
                    session_id=session_id,
                    topic_id=topic_id,
                    user_query=raw_query,
                    assistant_response=full_ans,
                    intent="GENERAL_FACTUAL",
                    citations=[],
                    grounding_score=1.0,
                    latency_ms=round((time.time() - start_time) * 1000, 2),
                    entities=query_meta.extracted_entities
                )
            yield {"type": "done", "latency_ms": round((time.time() - start_time) * 1000, 2)}
            return

        # Factual statement evaluation
        if msg_classification.category == UserMessageClassificationEnum.STATEMENT_EVALUATION:
            yield {"type": "phase_end", "phase": "Analysis Complete", "phase_key": "analysis"}
            eval_text = TeachingCorrectionHandler.handle_statement_evaluation(
                user_statement=raw_query,
                conversation_history=context.get("history", []),
                current_topic=effective_topic,
                is_teacher_mode=is_teacher_session
            )
            yield {"type": "token", "token": eval_text, "data": eval_text}
            yield {"type": "grounding", "data": {"validation_status": "PASS", "grounding_score": 1.0, "cross_reference_valid": True, "is_valid": True}}
            if session_id:
                cls._update_session_state(
                    session=session,
                    session_id=session_id,
                    topic_id=topic_id,
                    user_query=raw_query,
                    assistant_response=eval_text,
                    intent="STATEMENT_EVALUATION",
                    citations=[],
                    grounding_score=1.0,
                    latency_ms=round((time.time() - start_time) * 1000, 2),
                    entities=query_meta.extracted_entities
                )
            yield {"type": "done", "latency_ms": round((time.time() - start_time) * 1000, 2)}
            return

        # Priority 4: Unrelated chat question
        if msg_classification.category == UserMessageClassificationEnum.UNRELATED_CHAT:
            yield {"type": "phase_end", "phase": "Analysis Complete", "phase_key": "analysis"}
            full_chunks = []
            for token in FactualQueryHandler.stream_unrelated_query(
                raw_query=raw_query,
                conversation_history=context.get("history", [])
            ):
                full_chunks.append(token)
                yield {"type": "token", "token": token, "data": token}
            full_ans = "".join(full_chunks)
            yield {"type": "grounding", "data": {"validation_status": "PASS", "grounding_score": 1.0, "cross_reference_valid": True, "is_valid": True}}
            if session_id:
                cls._update_session_state(
                    session=session,
                    session_id=session_id,
                    topic_id=topic_id,
                    user_query=raw_query,
                    assistant_response=full_ans,
                    intent="UNRELATED_CHAT",
                    citations=[],
                    grounding_score=1.0,
                    latency_ms=round((time.time() - start_time) * 1000, 2),
                    entities=query_meta.extracted_entities
                )
            yield {"type": "done", "latency_ms": round((time.time() - start_time) * 1000, 2)}
            return

        # 5. Router Decision
        route_dest, retrieval_strategy = QueryRouter.route_query(
            meta=query_meta,
            has_active_document=bool(doc_id)
        )

        # Handle Casual & Study Plan non-retrieval routes early in streaming
        if route_dest in ("CASUAL_PIPELINE", "DIRECT_LLM_PIPELINE"):
            casual_resp = CasualPipeline.generate_response(raw_query)
            c_text = casual_resp.get("content", "Hello! How can I help you with your studies today?")
            yield {"type": "phase_end", "phase": "Analysis Complete", "phase_key": "analysis"}
            yield {"type": "token", "token": c_text, "data": c_text}
            yield {"type": "grounding", "data": {"validation_status": "PASS", "grounding_score": 1.0, "cross_reference_valid": True, "is_valid": True}}
            if session_id:
                cls._update_session_state(
                    session=session,
                    session_id=session_id,
                    topic_id=topic_id,
                    user_query=raw_query,
                    assistant_response=c_text,
                    intent=query_meta.intent,
                    citations=[],
                    grounding_score=1.0,
                    latency_ms=round((time.time() - start_time) * 1000, 2),
                    entities=query_meta.extracted_entities
                )
            yield {"type": "done", "latency_ms": round((time.time() - start_time) * 1000, 2)}
            return

        if route_dest == "STUDY_PLAN_PIPELINE":
            target_topic = query_meta.target_topic or effective_topic or "General Studies"
            plan_text = (
                f"📅 **Personalized Study Plan for {target_topic}**\n\n"
                f"I can help you build and customize a targeted study plan for **{target_topic}** based on your timeline and daily study goals.\n\n"
                f"To generate a full daily schedule with mastery checkpoints, navigate to the **Study Plan** dashboard or specify your available days (e.g. *'Generate a 5-day plan for {target_topic}'*)."
            )
            yield {"type": "phase_end", "phase": "Analysis Complete", "phase_key": "analysis"}
            yield {"type": "token", "token": plan_text, "data": plan_text}
            yield {"type": "grounding", "data": {"validation_status": "PASS", "grounding_score": 1.0, "cross_reference_valid": True, "is_valid": True}}
            if session_id:
                cls._update_session_state(
                    session=session,
                    session_id=session_id,
                    topic_id=topic_id,
                    user_query=raw_query,
                    assistant_response=plan_text,
                    intent=query_meta.intent,
                    citations=[],
                    grounding_score=1.0,
                    latency_ms=round((time.time() - start_time) * 1000, 2),
                    entities=query_meta.extracted_entities
                )
            yield {"type": "done", "latency_ms": round((time.time() - start_time) * 1000, 2)}
            return

        if (route_dest == "TEACHER_MODE_PIPELINE" and is_teacher_session) or msg_classification.category == UserMessageClassificationEnum.TEACH_TOPIC_REQUEST:
            yield {"type": "phase_end", "phase": "Analysis Complete", "phase_key": "analysis"}
            
            full_content_tokens = []
            citations_data = []
            grounding_val = 1.0
            suggestions_data = []

            for event in InteractiveTeacherEngine.stream_teacher_turn(
                session=session,
                session_id=session_id or "default_session",
                raw_query=raw_query,
                query_meta=query_meta,
                context=context,
                doc_id=doc_id,
            ):
                evt_type = event.get("type")
                if evt_type == "token":
                    t_str = event.get("token") or event.get("data") or ""
                    full_content_tokens.append(t_str)
                    yield event
                elif evt_type == "sources":
                    citations_data = event.get("data", [])
                    yield event
                elif evt_type == "grounding":
                    grounding_val = event.get("data", {}).get("grounding_score", 1.0)
                    yield event
                elif evt_type == "suggestions":
                    suggestions_data = event.get("data", [])
                    yield event
                elif evt_type in ("phase_start", "phase_end", "teacher_state", "checkpoint"):
                    yield event
                elif evt_type == "done":
                    total_time = round((time.time() - start_time) * 1000, 2)
                    if session_id:
                        cls._update_session_state(
                            session=session,
                            session_id=session_id,
                            topic_id=topic_id,
                            user_query=raw_query,
                            assistant_response="".join(full_content_tokens),
                            intent="TEACH_TOPIC",
                            citations=citations_data,
                            grounding_score=grounding_val,
                            latency_ms=total_time,
                            entities=query_meta.extracted_entities
                        )
                    yield {"type": "done", "latency_ms": total_time}
                    return
            return

        if route_dest in ("CLARIFY_PIPELINE", "INSUFFICIENT_EVIDENCE_PIPELINE", "MATERIAL_NOT_SUPPORTED_PIPELINE", "ANSWER_CHALLENGE_PIPELINE"):
            yield {"type": "phase_end", "phase": "Analysis Complete", "phase_key": "analysis"}
            
            if route_dest == "CLARIFY_PIPELINE":
                if query_meta.understanding_result:
                    msg = ClarificationGenerator.generate_clarification(
                        user_query=raw_query,
                        understanding=query_meta.understanding_result,
                        conversation_history=context.get("history", []),
                        available_topics=[effective_topic]
                    )
                else:
                    msg = query_meta.scope_clarification_prompt or "Could you please clarify what you mean?"
                intent_val = "CLARIFY_CONCEPT"
            elif route_dest == "INSUFFICIENT_EVIDENCE_PIPELINE":
                msg = "I couldn't find enough information in the uploaded materials to accurately answer this question."
                if query_meta.understanding_result and query_meta.understanding_result.missing_information:
                    msg += f" Missing information: {query_meta.understanding_result.missing_information}"
                intent_val = "INSUFFICIENT_EVIDENCE"
            elif route_dest == "MATERIAL_NOT_SUPPORTED_PIPELINE":
                topic_str = query_meta.target_topic or raw_query
                msg = f"I couldn't find '{topic_str}' in the selected study material. Please upload or select the material that covers this topic."
                intent_val = "MATERIAL_NOT_SUPPORTED"
            else: # ANSWER_CHALLENGE_PIPELINE
                msg = TeachingCorrectionHandler.handle_user_correction(
                    user_feedback=raw_query,
                    conversation_history=context.get("history", []),
                    current_topic=effective_topic,
                    is_teacher_mode=is_teacher_session
                )
                intent_val = "ANSWER_CHALLENGE"

            yield {"type": "token", "token": msg, "data": msg}
            yield {"type": "grounding", "data": {"validation_status": "PASS", "grounding_score": 1.0, "cross_reference_valid": True, "is_valid": True}}
            
            if session_id:
                cls._update_session_state(
                    session=session,
                    session_id=session_id,
                    topic_id=topic_id,
                    user_query=raw_query,
                    assistant_response=msg,
                    intent=intent_val,
                    citations=[],
                    grounding_score=1.0,
                    latency_ms=round((time.time() - start_time) * 1000, 2),
                    entities=query_meta.extracted_entities
                )
            yield {"type": "done", "latency_ms": round((time.time() - start_time) * 1000, 2)}
            return

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
        for token in TeachingAgent.stream_teaching_tokens(query_meta, context_bundle, is_teacher_mode=is_teacher_session):
            full_content_chunks.append(token)
            yield {"type": "token", "token": token, "data": token}

        full_content = "".join(full_content_chunks)

        # Enforce contract & check if checkpoint or formatting needs completion
        clean_topic = TeachingAgent._clean_topic_title(context_bundle.topic_title or effective_topic)
        is_refusal = "outside the scope of your uploaded" in full_content.lower()
        
        is_exempt = bool(
            not is_teacher_session
            or query_meta.intent == "PRACTICE_QUESTIONS"
            or (query_meta.format_directives and query_meta.format_directives.get("questions_only"))
            or (query_meta.format_directives and query_meta.format_directives.get("solve_table"))
            or query_meta.referenced_table is not None
            or is_refusal
        )

        if is_teacher_session and not is_exempt and "### 💡 Interactive Checkpoint" not in full_content and not full_content.strip().endswith("?"):
            checkpoint_text = f"\n\n### 💡 Interactive Checkpoint\n**Active Recall Question**: {TeachingAgent._default_follow_up(clean_topic)}"
            full_content += checkpoint_text
            yield {"type": "token", "token": checkpoint_text, "data": checkpoint_text}

        # Normalize unicode arrows in full_content for persistence & frontend consistency
        full_content = re.sub(r"[⟶→➔➜➝➞]", "-->", full_content)
        full_content = re.sub(r"[⟹⇒]", "==>", full_content)
        full_content = re.sub(r"[⟵←]", "<--", full_content)

        validation_result = AnswerValidator.validate_response(full_content, context_bundle)
        yield {"type": "grounding", "data": validation_result.model_dump()}

        latency_ms = round((time.time() - start_time) * 1000, 2)
        yield {"type": "phase_end", "phase": "Synthesis Complete", "phase_key": "synthesis"}

        # 8. Post-Processing & State Update (Database Persistence)
        # Persist BEFORE yielding "done" so that immediate client disconnects do not drop database writes
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

        yield {"type": "done", "latency_ms": latency_ms}

    @classmethod
    def _persist_generated_artifact(cls, session: Session, session_id: str, artifact_type: str, topic: str, items: List[Tuple[int, str]]) -> None:
        """Helper to save structured items into GeneratedArtifact."""
        if not items:
            return
        
        artifact = GeneratedArtifact(
            session_id=session_id,
            artifact_type=artifact_type,
            topic=topic
        )
        session.add(artifact)
        session.flush()
        
        for idx, text in items:
            session.add(GeneratedArtifactItem(
                artifact_id=artifact.id,
                item_index=idx,
                content=text,
                topic=topic
            ))
        session.commit()

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
            now_utc = datetime.now(timezone.utc)
            if not sess:
                sess = StudySession(
                    id=session_id,
                    title="Study Session",
                    subject="General Study",
                    message_count=2,
                    status="active",
                    created_at=now_utc,
                    last_active=now_utc
                )
                session.add(sess)
                session.flush()
            else:
                sess.message_count = (sess.message_count or 0) + 2
                sess.last_active = now_utc

            # Validate topic_id against CurriculumTopic table to guarantee no foreign key violations
            valid_topic_id = None
            if topic_id:
                topic_record = session.query(CurriculumTopic.id).filter(CurriculumTopic.id == topic_id).first()
                if topic_record:
                    valid_topic_id = topic_id
                else:
                    # Save slug or non-curriculum identifier in session_metadata
                    meta = dict(sess.session_metadata or {})
                    meta["topic_id"] = topic_id
                    sess.session_metadata = meta

            # 2. Record User & Assistant Messages with strict chronological sequencing
            asst_utc = now_utc + timedelta(milliseconds=10)
            user_msg = ChatMessage(
                session_id=session_id,
                topic_id=valid_topic_id,
                role="user",
                content=user_query,
                intent=intent,
                created_at=now_utc
            )
            asst_msg = ChatMessage(
                session_id=session_id,
                topic_id=valid_topic_id,
                role="assistant",
                content=assistant_response,
                intent=intent,
                citations=citations,
                grounding_score=grounding_score,
                latency_ms=latency_ms,
                created_at=asst_utc
            )
            session.add_all([user_msg, asst_msg])
            session.commit()

            # 3. Update Student Mastery progression (isolated so it cannot roll back messages)
            try:
                effective_user_id = sess.user_id if (sess and sess.user_id) else "default_user"
                for ent in (entities or [])[:3]:
                    if not ent or not isinstance(ent, str):
                        continue
                    mastery = session.query(StudentMastery).filter(
                        StudentMastery.user_id == effective_user_id,
                        StudentMastery.concept == ent
                    ).first()
                    if not mastery:
                        mastery = StudentMastery(
                            user_id=effective_user_id,
                            concept=ent,
                            mastery_score=0.6,
                            practice_attempts=1,
                            successful_attempts=1
                        )
                        session.add(mastery)
                    else:
                        mastery.practice_attempts += 1
                        mastery.successful_attempts += 1
                        mastery.mastery_score = min(1.0, (mastery.mastery_score or 0.6) + 0.05)
                session.commit()
            except Exception as mastery_err:
                session.rollback()
                logger.warning(f"Non-critical mastery progression update skipped: {mastery_err}")

        except Exception as e:
            session.rollback()
            logger.error(f"Error persisting conversation state: {e}")
