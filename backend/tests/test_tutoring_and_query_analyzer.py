import pytest
from app.models.session import StudySession, CurriculumTopic, ChatMessage
from app.models.chunk import KnowledgeChunk
from app.models.document import Document
from app.tutoring.analyzer.preprocessor import QueryPreprocessor
from app.tutoring.analyzer.resolver import ReferenceResolver
from app.tutoring.analyzer.understanding import QueryUnderstanding
from app.tutoring.router.query_router import QueryRouter
from app.tutoring.teaching.agent import TeachingAgent
from app.tutoring.validation.validator import AnswerValidator
from app.tutoring.orchestrator import TutoringQueryOrchestrator
from app.schemas.tutoring import ContextBundle, CitationItem, QueryMetadata
from app.schemas.chunk import KnowledgeChunkRead


def test_query_preprocessor():
    raw = "  can you explain the backprop algoritm  and derivitave ?  "
    normalized, lang, meta = QueryPreprocessor.preprocess(raw)
    assert lang == "english"
    assert "algorithm" in normalized # Typo fixed
    assert "derivative" in normalized # Typo fixed
    assert meta["has_typos_fixed"] is True


def test_figure_query_normalization_and_understanding():
    """Verify that inputs like 'explain 2.8 figure' or 'figure 2.8' normalize and extract Figure 2-8."""
    raw = "explain 2.8 figure"
    normalized, _, _ = QueryPreprocessor.preprocess(raw)
    assert "Figure 2-8" in normalized
    assert "Figure 2.8" in normalized

    meta = QueryUnderstanding.analyze_query(raw_query=raw)
    assert meta.referenced_figure == "Figure 2-8"
    assert any("Figure 2-8" in e for e in meta.extracted_entities)
    assert any("Figure 2.8" in e for e in meta.extracted_entities)


def test_reference_resolver():
    history = [
        {"role": "user", "content": "Tell me about Support Vector Machines."},
        {"role": "assistant", "content": "Support Vector Machines find the optimal separating hyperplane."}
    ]

    # Follow-up detection
    follow_up_q = "Why is that?"
    resolved, meta = ReferenceResolver.resolve_references(follow_up_q, history)
    assert meta["is_follow_up"] is True
    assert "Support Vector Machines" in resolved

    # Pronoun resolution
    pronoun_q = "How does it scale to high dimensional datasets?"
    resolved_p, meta_p = ReferenceResolver.resolve_references(pronoun_q, history)
    assert "Support Vector Machines" in resolved_p


def test_query_understanding():
    query = "Compare Linear Regression and Logistic Regression and explain their formulas."
    meta = QueryUnderstanding.analyze_intent_and_metadata(
        raw_query=query,
        normalized_query=query,
        resolved_query=query,
        language="english"
    )
    assert meta.intent == "COMPARISON"
    assert meta.learning_objective == "analyze"
    assert meta.response_requirements["needs_latex"] is True
    assert any("linear" in e.lower() or "regression" in e.lower() for e in meta.extracted_entities)


def test_query_router():
    meta_casual = QueryMetadata(
        raw_query="hello",
        normalized_query="hello",
        resolved_query="hello",
        intent="CASUAL"
    )
    dest, strat = QueryRouter.route_query(meta_casual, has_active_document=True)
    assert dest == "CASUAL_PIPELINE"

    meta_qa = QueryMetadata(
        raw_query="What is Gradient Descent?",
        normalized_query="What is Gradient Descent?",
        resolved_query="What is Gradient Descent?",
        intent="DOCUMENT_QA",
        extracted_entities=["Gradient Descent"]
    )
    dest_qa, strat_qa = QueryRouter.route_query(meta_qa, has_active_document=True)
    assert dest_qa == "RETRIEVAL_PIPELINE"
    assert strat_qa == "thematic"


def test_teaching_agent_and_answer_validation():
    chunk = KnowledgeChunkRead(
        id="c-teach-1",
        document_id="doc-1",
        page_number=4,
        chunk_index=0,
        content="Convolutional neural networks use kernel filters to detect spatial patterns in visual matrices.",
        chunk_type="definition",
        topic="Computer Vision",
        chapter_section="Chapter 4 > CNNs",
        confidence=0.98,
        related_concepts=["CNN", "kernel", "convolution"],
        keywords_entities=["Convolutional Neural Network"],
        formulas=[r"S(i,j) = (I * K)(i,j)"],
        examples=["Image edge detection"],
        provenance={"parser": "PyMuPDF"},
        relationship_metadata={},
        search_text="CNN kernel convolution"
    )

    context = ContextBundle(
        document_id="doc-1",
        topic_title="Computer Vision",
        resolved_query="How do convolutional networks process images?",
        conversation_history=[],
        student_mastery_context={},
        retrieved_chunks=[chunk],
        related_formulas=[r"S(i,j) = (I * K)(i,j)"],
        related_tables=[],
        citations=[
            CitationItem(
                chunk_id=chunk.id,
                page_number=chunk.page_number,
                chapter_section=chunk.chapter_section,
                snippet=chunk.content[:100],
                confidence=0.98
            )
        ]
    )

    query_meta = QueryMetadata(
        raw_query="How do convolutional networks process images?",
        normalized_query="How do convolutional networks process images?",
        resolved_query="How do convolutional networks process images?",
        intent="EXPLANATION",
        extracted_entities=["convolutional", "neural network"],
        response_requirements={"needs_latex": True, "needs_socratic": True}
    )

    # 1. Generate Teaching Response
    response = TeachingAgent.generate_teaching_response(query_meta, context)
    assert response is not None
    assert "Convolutional" in response.content or "CNN" in response.content
    assert len(response.citations) >= 1
    assert query_meta.response_requirements["needs_latex"] is True

    # 2. Answer Validation Gate
    val = AnswerValidator.validate_response(response.content, context)
    assert val.is_valid is True
    assert val.validation_status == "PASS"
    assert val.grounding_score >= 0.45
    assert val.cross_reference_valid is True


def test_tutoring_orchestrator_end_to_end(db_session):
    # Setup document and session
    doc = Document(
        id="doc-tutor-test",
        file_hash="dummy_hash_for_tutoring_test_1234567890abcdef1234567890abcdef",
        filename="ai_principles.pdf",
        file_path="storage://ai_principles.pdf",
        file_size_bytes=5000,
        page_count=5,
        title="Artificial Intelligence Principles",
        status="INDEXED"
    )
    db_session.add(doc)

    chunk = KnowledgeChunk(
        id="chunk-tutor-1",
        document_id=doc.id,
        page_number=2,
        chunk_index=0,
        content="Reinforcement learning agents learn policies by receiving rewards and penalties from the environment.",
        chunk_type="definition",
        topic="Reinforcement Learning",
        chapter_section="Chapter 5 > RL",
        confidence=0.99,
        search_text="Reinforcement learning agents learn policies by receiving rewards and penalties from the environment."
    )
    db_session.add(chunk)

    study_sess = StudySession(
        id="sess-tutor-1",
        document_id=doc.id,
        title="Reinforcement Learning Study",
        subject="Computer Science",
        status="active"
    )
    db_session.add(study_sess)
    db_session.commit()

    # Process user query
    result = TutoringQueryOrchestrator.process_query(
        session=db_session,
        raw_query="What is reinforcement learning and how do rewards work?",
        session_id="sess-tutor-1",
        topic_title="Reinforcement Learning"
    )

    assert result is not None
    assert result["intent"] in ["DOCUMENT_QA", "EXPLANATION"]
    assert "Reinforcement" in result["content"] or "learning" in result["content"]
    assert len(result["citations"]) > 0
    assert result["validation"]["validation_status"] == "PASS"

    # Verify conversation history was persisted
    messages = db_session.query(ChatMessage).filter(ChatMessage.session_id == "sess-tutor-1").all()
    assert len(messages) == 2 # 1 user, 1 assistant
    assert messages[0].role == "user"
    assert messages[1].role == "assistant"
    assert messages[1].grounding_score > 0.0


def test_tutoring_orchestrator_main_topics_overview(db_session):
    doc = Document(
        id="doc-topics-test",
        file_hash="dummy_hash_for_topics_test_1234567890abcdef1234567890abcdef",
        filename="course_curriculum.pdf",
        file_path="storage://course_curriculum.pdf",
        file_size_bytes=4000,
        page_count=3,
        title="Machine Learning Syllabus",
        status="INDEXED"
    )
    db_session.add(doc)

    study_sess = StudySession(
        id="sess-topics-1",
        document_id=doc.id,
        title="ML Study Session",
        subject="Computer Science",
        status="active"
    )
    db_session.add(study_sess)

    topic1 = CurriculumTopic(
        id="topic-1",
        session_id=study_sess.id,
        document_id=doc.id,
        title="Supervised Learning",
        order_index=0,
        page_start=1,
        page_end=1
    )
    topic2 = CurriculumTopic(
        id="topic-2",
        session_id=study_sess.id,
        document_id=doc.id,
        title="Deep Neural Networks",
        order_index=1,
        page_start=2,
        page_end=3
    )
    db_session.add_all([topic1, topic2])
    
    from app.models.topic_analysis import DocumentTopicAnalysis, ExtractedTopic
    analysis = DocumentTopicAnalysis(
        id="analysis-1",
        document_id=doc.id,
        status="COMPLETED"
    )
    db_session.add(analysis)
    db_session.commit()
    
    t1 = ExtractedTopic(analysis_id="analysis-1", topic="Supervised Learning", importance_score=0.9)
    t2 = ExtractedTopic(analysis_id="analysis-1", topic="Deep Neural Networks", importance_score=0.8)
    db_session.add_all([t1, t2])
    db_session.commit()

    result = TutoringQueryOrchestrator.process_query(
        session=db_session,
        raw_query="what are the main topics",
        session_id="sess-topics-1"
    )

    assert result is not None
    assert "outside the scope" not in result["content"].lower()
    assert result["validation"]["validation_status"] == "PASS"


def test_tutoring_orchestrator_processing_document_guard(db_session):
    # Setup document in PROCESSING status with 0 indexed chunks
    doc = Document(
        id="doc-processing-guard",
        file_hash="dummy_hash_for_processing_guard_1234567890abcdef1234567890abcdef",
        filename="physics_notes.pdf",
        file_path="storage://physics_notes.pdf",
        file_size_bytes=8000,
        page_count=10,
        title="Physics 101",
        status="PROCESSING"
    )
    db_session.add(doc)

    study_sess = StudySession(
        id="sess-processing-guard",
        document_id=doc.id,
        title="Physics 101 Study",
        subject="Physics",
        status="active"
    )
    db_session.add(study_sess)
    db_session.commit()

    # Query before indexing completes
    result = TutoringQueryOrchestrator.process_query(
        session=db_session,
        raw_query="what is newton's second law?",
        session_id="sess-processing-guard"
    )

    assert result is not None
    assert result["intent"] == "PROCESSING_STATUS"
    assert "currently being processed and indexed" in result["content"].lower()
    assert "outside the scope" not in result["content"].lower()


