import pytest
from app.models.document import Document
from app.models.chunk import KnowledgeChunk
from app.models.session import StudySession, ChatMessage, CurriculumTopic
from app.api.study import (
    create_study_session,
    get_study_session,
    delete_study_session,
    batch_delete_sessions,
    remove_document_from_session
)
from app.tutoring.orchestrator import TutoringQueryOrchestrator


def test_session_creation_and_retrieval(db_session):
    """Verifies that new study sessions can be created via payload and retrieved with topic count."""
    created = create_study_session(
        payload={"title": "Linear Algebra Study", "subject": "Mathematics"},
        db=db_session
    )
    assert created["id"] is not None
    assert created["title"] == "Linear Algebra Study"
    assert created["subject"] == "Mathematics"
    assert created["topic_count"] == 0
    assert created["status"] == "active"

    # Fetch through get_study_session
    fetched = get_study_session(session_id=created["id"], db=db_session)
    assert fetched["id"] == created["id"]
    assert fetched["title"] == "Linear Algebra Study"
    assert fetched["curriculum_topics"] == []


def test_session_data_isolation_and_independence(db_session):
    """
    Verifies that multiple sessions stored in the same database remain completely independent.
    Session A (with document chunks) must never bleed citations or chat history into Session B.
    """
    # 1. Setup Document and Chunks for Session A
    doc_a = Document(
        id="doc-session-a",
        filename="svm_algorithms.pdf",
        page_count=5,
        file_hash="hash_session_a",
        file_size_bytes=2048,
        file_path="local://svm_algorithms.pdf"
    )
    db_session.add(doc_a)

    chunk_a = KnowledgeChunk(
        id="chunk-svm-1",
        document_id=doc_a.id,
        page_number=1,
        chunk_index=0,
        content="Support Vector Machines find the optimal separating hyperplane with maximum geometric margin.",
        chunk_type="definition",
        topic="Hyperplane Optimization",
        chapter_section="Section 1",
        confidence=0.98,
        search_text="Support Vector Machines find the optimal separating hyperplane with maximum geometric margin."
    )
    db_session.add(chunk_a)

    # Session A: Has document
    sess_a = StudySession(
        id="sess-user-a",
        document_id=doc_a.id,
        document_name=doc_a.filename,
        title="SVM Workspace",
        subject="Machine Learning",
        status="active"
    )
    # Session B: Independent workspace without document
    sess_b = StudySession(
        id="sess-user-b",
        document_id=None,
        document_name=None,
        title="Calculus Workspace",
        subject="Mathematics",
        status="active"
    )
    db_session.add(sess_a)
    db_session.add(sess_b)

    topic_a = CurriculumTopic(
        id="topic-a-1",
        session_id=sess_a.id,
        title="Hyperplane Optimization",
        order_index=1,
        mastered=False
    )
    topic_b = CurriculumTopic(
        id="topic-b-1",
        session_id=sess_b.id,
        title="Derivatives and Limits",
        order_index=1,
        mastered=False
    )
    db_session.add(topic_a)
    db_session.add(topic_b)
    db_session.commit()

    # Query in Session A -> should retrieve citations from doc_a
    result_a = TutoringQueryOrchestrator.process_query(
        session=db_session,
        raw_query="What is the margin in SVM?",
        session_id=sess_a.id,
        topic_title="Hyperplane Optimization"
    )
    assert len(result_a["citations"]) > 0
    assert any("support vector" in c["snippet"].lower() or "hyperplane" in c["snippet"].lower() for c in result_a["citations"])

    # Query in Session B -> should NOT retrieve any chunks from doc_a!
    result_b = TutoringQueryOrchestrator.process_query(
        session=db_session,
        raw_query="What is the margin in SVM?",
        session_id=sess_b.id,
        topic_title="Derivatives and Limits"
    )
    assert len(result_b["citations"]) == 0

    # Verify Chat Messages isolation
    msgs_a = db_session.query(ChatMessage).filter(ChatMessage.session_id == sess_a.id).all()
    msgs_b = db_session.query(ChatMessage).filter(ChatMessage.session_id == sess_b.id).all()

    assert len(msgs_a) == 2  # 1 user, 1 assistant
    assert len(msgs_b) == 2  # 1 user, 1 assistant
    # Verify no overlap
    msg_ids_a = {m.id for m in msgs_a}
    msg_ids_b = {m.id for m in msgs_b}
    assert msg_ids_a.isdisjoint(msg_ids_b)


def test_session_deletion_and_cascading(db_session):
    """
    Verifies that deleting a session cascades to its messages and topics,
    leaving other user sessions completely unharmed.
    """
    sess_1 = StudySession(id="sess-del-1", title="To Delete", subject="Test", status="active")
    sess_2 = StudySession(id="sess-keep-2", title="To Keep", subject="Test", status="active")
    db_session.add(sess_1)
    db_session.add(sess_2)

    db_session.add(ChatMessage(id="msg-del-1", session_id=sess_1.id, role="user", content="hello in 1"))
    db_session.add(ChatMessage(id="msg-keep-2", session_id=sess_2.id, role="user", content="hello in 2"))
    db_session.add(CurriculumTopic(id="top-del-1", session_id=sess_1.id, title="Topic 1", order_index=1))
    db_session.add(CurriculumTopic(id="top-keep-2", session_id=sess_2.id, title="Topic 2", order_index=1))
    db_session.commit()

    # Delete session 1
    resp = delete_study_session(session_id="sess-del-1", db=db_session)
    assert resp["status"] == "success"
    assert resp["deleted_id"] == "sess-del-1"

    # Verify session 1 is gone
    assert db_session.query(StudySession).filter(StudySession.id == "sess-del-1").first() is None
    assert db_session.query(ChatMessage).filter(ChatMessage.session_id == "sess-del-1").first() is None
    assert db_session.query(CurriculumTopic).filter(CurriculumTopic.session_id == "sess-del-1").first() is None

    # Verify session 2 is completely intact
    assert db_session.query(StudySession).filter(StudySession.id == "sess-keep-2").first() is not None
    assert db_session.query(ChatMessage).filter(ChatMessage.session_id == "sess-keep-2").first() is not None
    assert db_session.query(CurriculumTopic).filter(CurriculumTopic.session_id == "sess-keep-2").first() is not None


def test_batch_delete_sessions(db_session):
    """Verifies batch deletion of multiple sessions."""
    s1 = StudySession(id="batch-1", title="Batch 1", subject="Subject", status="active")
    s2 = StudySession(id="batch-2", title="Batch 2", subject="Subject", status="active")
    s3 = StudySession(id="batch-3", title="Batch 3", subject="Subject", status="active")
    db_session.add_all([s1, s2, s3])
    db_session.commit()

    resp = batch_delete_sessions(payload={"session_ids": ["batch-1", "batch-2"]}, db=db_session)
    assert resp["deleted_count"] == 2
    assert db_session.query(StudySession).filter(StudySession.id == "batch-1").first() is None
    assert db_session.query(StudySession).filter(StudySession.id == "batch-2").first() is None
    assert db_session.query(StudySession).filter(StudySession.id == "batch-3").first() is not None
