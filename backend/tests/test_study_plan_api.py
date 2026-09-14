import pytest
from datetime import datetime, timezone, timedelta
from app.models.study_plan import StudyPlan
from app.models.session import StudySession, CurriculumTopic
from app.api.study_plan import (
    generate_study_plan,
    get_my_plans,
    get_study_plan,
    toggle_day_completion,
    verify_day_quiz,
    generate_day_notes,
    delete_study_plan,
    GeneratePlanRequest,
    ToggleDayRequest,
    VerifyQuizRequest,
    DayNotesRequest,
)


def test_study_plan_crud_and_persistence(db_session):
    """
    Verifies that a StudyPlan record can be created, fetched, updated,
    and deleted with proper persistence in the database.
    """
    target = (datetime.now(timezone.utc).date() + timedelta(days=14)).strftime("%Y-%m-%d")
    
    # 1. Generate plan
    req = GeneratePlanRequest(
        target_date=target,
        hours_per_day=2.5,
        language="en"
    )
    created = generate_study_plan(req=req, user_id="test_student", db=db_session)
    assert created["id"] is not None
    assert created["total_days"] == 14
    assert created["hours_per_day"] == 2.5
    assert len(created["schedule"]) == 14
    assert created["completed_days"] == []

    plan_id = created["id"]

    # 2. Retrieve via my-plans
    my_plans = get_my_plans(user_id="test_student", db=db_session)
    assert len(my_plans) >= 1
    assert any(p["id"] == plan_id for p in my_plans)

    # 3. Retrieve single plan
    fetched = get_study_plan(plan_id=plan_id, db=db_session)
    assert fetched["id"] == plan_id
    assert fetched["title"] == created["title"]

    # 4. Toggle day completion
    toggle_res = toggle_day_completion(
        plan_id=plan_id,
        req=ToggleDayRequest(day_number=1),
        db=db_session
    )
    assert 1 in toggle_res["completed_days"]

    # Toggle day off
    toggle_res2 = toggle_day_completion(
        plan_id=plan_id,
        req=ToggleDayRequest(day_number=1),
        db=db_session
    )
    assert 1 not in toggle_res2["completed_days"]

    # 5. Quiz verification
    # Failed quiz (< 70%)
    fail_quiz = verify_day_quiz(
        plan_id=plan_id,
        req=VerifyQuizRequest(day_number=2, score_percentage=60.0),
        db=db_session
    )
    assert fail_quiz["passed"] is False
    assert 2 not in fail_quiz["completed_days"]

    # Passed quiz (>= 70%)
    pass_quiz = verify_day_quiz(
        plan_id=plan_id,
        req=VerifyQuizRequest(day_number=2, score_percentage=85.0),
        db=db_session
    )
    assert pass_quiz["passed"] is True
    assert 2 in pass_quiz["completed_days"]

    # 6. Generate and cache day notes
    notes_res = generate_day_notes(
        req=DayNotesRequest(
            plan_id=plan_id,
            day_number=2,
            day_topic="Foundations of Machine Learning",
            key_concepts=["Supervised Learning", "Cost Function"],
            force_regenerate=False
        ),
        db=db_session
    )
    assert "Foundations of Machine Learning" in notes_res["notes"]

    # Second fetch should hit cached notes
    cached_notes = generate_day_notes(
        req=DayNotesRequest(
            plan_id=plan_id,
            day_number=2,
            day_topic="Foundations of Machine Learning",
            force_regenerate=False
        ),
        db=db_session
    )
    assert cached_notes["cached"] is True
    assert cached_notes["notes"] == notes_res["notes"]

    # 7. Delete plan
    del_res = delete_study_plan(plan_id=plan_id, db=db_session)
    assert del_res["status"] == "deleted"

    # Confirm not found
    with pytest.raises(Exception):
        get_study_plan(plan_id=plan_id, db=db_session)


def test_study_plan_generation_with_curriculum_topics(db_session):
    """
    Verifies that when a session_id with existing CurriculumTopics is provided,
    the generated schedule intelligently binds real topics and concepts into the milestones.
    """
    # Create study session
    sess = StudySession(
        id="session-plan-test",
        title="Cell Biology & Genetics",
        subject="Biology"
    )
    db_session.add(sess)

    # Add curriculum topics
    t1 = CurriculumTopic(
        session_id=sess.id,
        title="Mitosis and Cell Cycle",
        summary="Phases of eukaryotic cell division.",
        key_concepts=["Prophase", "Metaphase", "Anaphase", "Telophase"],
        order_index=0
    )
    t2 = CurriculumTopic(
        session_id=sess.id,
        title="DNA Replication & Repair",
        summary="Mechanisms of double helix replication.",
        key_concepts=["Helicase", "Polymerase", "Okazaki Fragments"],
        order_index=1
    )
    db_session.add_all([t1, t2])
    db_session.commit()

    target = (datetime.now(timezone.utc).date() + timedelta(days=6)).strftime("%Y-%m-%d")
    req = GeneratePlanRequest(
        session_id=sess.id,
        target_date=target,
        hours_per_day=1.5
    )
    plan = generate_study_plan(req=req, user_id="bio_student", db=db_session)
    assert "Cell Biology" in plan["title"]
    assert plan["total_days"] == 6

    # Verify discovered topics mapped into the schedule
    schedule_topics = [d["topic"] for d in plan["schedule"]]
    assert "Mitosis and Cell Cycle" in schedule_topics
    assert "DNA Replication & Repair" in schedule_topics


def test_study_plan_grounded_in_document_chunks(db_session):
    """
    Verifies that when a document with KnowledgeChunks exists in the database,
    study plan generation directly extracts the chapters, sections, and concepts
    from the chunks, producing a 100% document-grounded roadmap.
    """
    from app.models.document import Document
    from app.models.chunk import KnowledgeChunk

    # Create Document
    doc = Document(
        id="doc-qc-grounding",
        filename="quantum_computing_foundations.pdf",
        title="Quantum Computing Foundations",
        page_count=20,
        file_hash="hash_qc_grounding_1",
        file_size_bytes=4096,
        file_path="local://quantum_computing_foundations.pdf"
    )
    db_session.add(doc)

    # Add KnowledgeChunks
    c1 = KnowledgeChunk(
        id="chunk-qc-1",
        document_id=doc.id,
        page_number=1,
        chunk_index=0,
        content="Qubits can exist in a superposition of |0> and |1> states represented on the Bloch Sphere.",
        chunk_type="definition",
        topic="Qubits and Superposition",
        chapter_section="Chapter 1: Mathematical Foundations",
        related_concepts=["Bloch Sphere", "Superposition", "Hadamard Gate"],
        search_text="Qubits can exist in a superposition of |0> and |1> states."
    )
    c2 = KnowledgeChunk(
        id="chunk-qc-2",
        document_id=doc.id,
        page_number=5,
        chunk_index=1,
        content="Quantum Entanglement creates non-local correlations between particles exceeding classical limits.",
        chunk_type="section_header",
        topic="Quantum Entanglement & Bell States",
        chapter_section="Chapter 2: Quantum Teleportation",
        related_concepts=["Bell States", "EPR Paradox", "Entanglement"],
        search_text="Quantum Entanglement creates non-local correlations."
    )
    db_session.add_all([c1, c2])
    db_session.commit()

    target = (datetime.now(timezone.utc).date() + timedelta(days=8)).strftime("%Y-%m-%d")
    req = GeneratePlanRequest(
        topic_id=doc.id,
        target_date=target,
        hours_per_day=2.0
    )
    plan = generate_study_plan(req=req, user_id="physics_student", db=db_session)
    
    # Document title reflected
    assert "Quantum Computing Foundations" in plan["title"]
    assert plan["total_days"] == 8

    # Schedule topics grounded in the document chunks
    all_schedule_topics = " ".join(d["topic"] for d in plan["schedule"])
    all_schedule_concepts = [c for d in plan["schedule"] for c in d["key_concepts"]]

    assert "Chapter 1" in all_schedule_topics or "Qubits" in all_schedule_topics
    assert "Bloch Sphere" in all_schedule_concepts or "Superposition" in all_schedule_concepts

    # Day notes grounded in document chunks
    notes = generate_day_notes(
        req=DayNotesRequest(
            plan_id=plan["id"],
            day_number=1,
            topic_id=doc.id,
            day_topic="Qubits and Superposition",
            key_concepts=["Bloch Sphere", "Superposition"],
            force_regenerate=True
        ),
        db=db_session
    )
    assert "Quantum Computing Foundations" in notes["notes"]
    assert ("Bloch Sphere" in notes["notes"] or "Qubits" in notes["notes"])

