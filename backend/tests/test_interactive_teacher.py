import pytest
from sqlalchemy.orm import Session
from app.models.session import StudySession, CurriculumTopic, ChatMessage
from app.models.chunk import KnowledgeChunk
from app.models.document import Document
from app.models.assets import DocumentAsset
from app.tutoring.analyzer.understanding import QueryUnderstanding
from app.tutoring.router.query_router import QueryRouter
from app.tutoring.teaching.interactive_teacher import InteractiveTeacherEngine
from app.schemas.tutoring import (
    TeacherSessionState,
    TeachingPlan,
    LearningUnit,
    TeacherTurnActionEnum,
    StudentUnderstandingLevelEnum,
    TeacherStageEnum,
    PauseContext,
    VisualLearningState,
    QueryMetadata,
)
from app.tutoring.orchestrator import TutoringQueryOrchestrator


def test_topic_extraction_topic_agnostic():
    """Verify dynamic topic extraction across diverse, non-hardcoded subjects."""
    test_cases = [
        ("Act as a teacher and teach me SVM", "SVM"),
        ("Teach me SVM", "SVM"),
        ("Teach me Decision Tree", "Decision Tree"),
        ("Teach me TCP", "TCP"),
        ("Teach me Newton's Laws", "Newton's Laws"),
        ("teach me about Photosynthesis step by step", "Photosynthesis"),
        ("I want to learn SQL Joins", "SQL Joins"),
        ("Help me learn Organic Chemistry", "Organic Chemistry"),
    ]
    for raw_input, expected_topic in test_cases:
        extracted = QueryUnderstanding.extract_teach_topic(raw_input)
        assert extracted is not None, f"Failed to extract topic from '{raw_input}'"
        assert expected_topic.lower() in extracted.lower(), f"Expected '{expected_topic}' in '{extracted}'"


def test_normal_qa_isolation():
    """Verify standard Q&A queries remain unchanged and do not trigger TEACH_TOPIC."""
    normal_queries = [
        "What is SVM?",
        "Explain Decision Trees",
        "Define TCP protocol",
        "How does backpropagation work?",
    ]
    for q in normal_queries:
        extracted = QueryUnderstanding.extract_teach_topic(q)
        assert extracted is None, f"Query '{q}' should NOT be extracted as a teacher topic!"


def test_query_router_teacher_mode():
    """Verify TEACH_TOPIC intent routes to TEACHER_MODE_PIPELINE."""
    meta = QueryMetadata(
        raw_query="Teach me SVM",
        language="english",
        normalized_query="Teach me SVM",
        resolved_query="Teach me SVM",
        intent="TEACH_TOPIC",
        target_topic="SVM",
    )
    dest, strat = QueryRouter.route_query(meta, has_active_document=True)
    assert dest == "TEACHER_MODE_PIPELINE"
    assert strat == "thematic"


def test_dynamic_plan_generation_no_hardcoding():
    """Verify teaching plans are generated dynamically and contain structured LearningUnits."""
    chunks = [
        KnowledgeChunk(
            id="c1",
            document_id="doc1",
            page_number=1,
            content="Support Vector Machines (SVM) aim to find the optimal hyperplane that maximizes the margin between classes.",
            topic="SVM",
            chapter_section="Classification",
        ),
        KnowledgeChunk(
            id="c2",
            document_id="doc1",
            page_number=2,
            content="Support vectors are data points closest to the hyperplane. Kernels map non-linear data to higher dimensions.",
            topic="SVM",
            chapter_section="Kernel Methods",
        ),
    ]

    plan = InteractiveTeacherEngine.generate_dynamic_plan("SVM", chunks)
    assert isinstance(plan, TeachingPlan)
    assert plan.topic == "SVM"
    assert len(plan.learning_units) >= 2
    for unit in plan.learning_units:
        assert isinstance(unit, LearningUnit)
        assert unit.concept
        assert unit.objective
        assert unit.status in ("pending", "in_progress", "completed", "skipped", "weak")


def test_stateful_turn_progression(db_session: Session):
    """
    Simulate complete multi-turn interactive session:
    Turn 1: 'Teach me SVM' -> First concept + checkpoint question
    Turn 2: Student responds 'B' -> Evaluation + progression to concept 2
    Turn 3: Student asks doubt 'Why is margin maximized?' -> Pauses lesson, answers doubt
    Turn 4: Student says 'continue' -> Resumes previous concept question
    Turn 5: Student answers incorrectly -> Adaptive re-explanation
    """
    session_id = "test_teacher_session_123"

    # Setup database session record
    study_sess = StudySession(
        id=session_id,
        title="SVM Tutoring",
        subject="Machine Learning",
        status="active",
        session_metadata={},
    )
    db_session.add(study_sess)
    db_session.commit()

    # --- TURN 1: Initiation ---
    meta_turn1 = QueryMetadata(
        raw_query="Act as a teacher and teach me SVM",
        language="english",
        normalized_query="Act as a teacher and teach me SVM",
        resolved_query="Act as a teacher and teach me SVM",
        intent="TEACH_TOPIC",
        target_topic="SVM",
    )
    context_turn1 = {"history": [], "teacher_state": None, "user_id": "test_user"}

    resp_turn1 = InteractiveTeacherEngine.execute_teacher_turn(
        session=db_session,
        session_id=session_id,
        raw_query="Act as a teacher and teach me SVM",
        query_meta=meta_turn1,
        context=context_turn1,
        doc_id=None,
    )

    assert "SVM" in resp_turn1["content"]
    assert "### 💡 Interactive Checkpoint" in resp_turn1["content"]
    assert len(resp_turn1["suggested_questions"]) >= 2

    # Verify state was saved to database
    db_session.refresh(study_sess)
    state1_dict = study_sess.session_metadata.get("teacher_state")
    assert state1_dict is not None
    assert state1_dict["mode"] == "teacher"
    assert state1_dict["topic"] == "SVM"
    assert state1_dict["current_stage"] in (TeacherStageEnum.CHECKPOINT.value, "checkpoint_question")
    assert len(state1_dict["teaching_plan"]["learning_units"]) >= 2

    # --- TURN 2: Student Answers Checkpoint ---
    meta_turn2 = QueryMetadata(
        raw_query="B",
        language="english",
        normalized_query="B",
        resolved_query="B",
        intent="TEACH_TOPIC",
        target_topic="SVM",
    )
    context_turn2 = {"history": [{"role": "user", "content": "Teach me SVM"}], "teacher_state": state1_dict, "user_id": "test_user"}

    resp_turn2 = InteractiveTeacherEngine.execute_teacher_turn(
        session=db_session,
        session_id=session_id,
        raw_query="B",
        query_meta=meta_turn2,
        context=context_turn2,
        doc_id=None,
    )

    db_session.refresh(study_sess)
    state2_dict = study_sess.session_metadata.get("teacher_state")
    assert state2_dict is not None
    # Concept 1 should now be completed
    assert len(state2_dict["completed_concepts"]) >= 1
    # Unit index should have progressed
    assert state2_dict["current_unit_index"] >= 1

    # --- TURN 3: Student Asks Doubt (Interruption) ---
    doubt_query = "Why exactly do we need to maximize the margin?"
    meta_turn3 = QueryMetadata(
        raw_query=doubt_query,
        language="english",
        normalized_query=doubt_query,
        resolved_query=doubt_query,
        intent="TEACH_TOPIC",
        target_topic="SVM",
    )
    context_turn3 = {"history": [], "teacher_state": state2_dict, "user_id": "test_user"}

    resp_turn3 = InteractiveTeacherEngine.execute_teacher_turn(
        session=db_session,
        session_id=session_id,
        raw_query=doubt_query,
        query_meta=meta_turn3,
        context=context_turn3,
        doc_id=None,
    )

    db_session.refresh(study_sess)
    state3_dict = study_sess.session_metadata.get("teacher_state")
    assert state3_dict["paused"] is True
    assert state3_dict["pause_reason"] == "student_doubt"
    assert len(state3_dict["student_doubts"]) == 1
    assert state3_dict["previous_state"] is not None
    # Unit index must NOT advance while resolving a doubt
    assert state3_dict["current_unit_index"] == state2_dict["current_unit_index"]

    # --- TURN 4: Student Resumes ---
    resume_query = "Got it, continue"
    meta_turn4 = QueryMetadata(
        raw_query=resume_query,
        language="english",
        normalized_query=resume_query,
        resolved_query=resume_query,
        intent="TEACH_TOPIC",
        target_topic="SVM",
    )
    context_turn4 = {"history": [], "teacher_state": state3_dict, "user_id": "test_user"}

    resp_turn4 = InteractiveTeacherEngine.execute_teacher_turn(
        session=db_session,
        session_id=session_id,
        raw_query=resume_query,
        query_meta=meta_turn4,
        context=context_turn4,
        doc_id=None,
    )

    db_session.refresh(study_sess)
    state4_dict = study_sess.session_metadata.get("teacher_state")
    # Paused flag must be cleared
    assert state4_dict["paused"] is False
    assert state4_dict["current_stage"] in (TeacherStageEnum.CHECKPOINT.value, "checkpoint_question")

    # --- TURN 5: Student Answers Incorrectly -> Adaptive Re-explanation ---
    wrong_query = "A"
    meta_turn5 = QueryMetadata(
        raw_query=wrong_query,
        language="english",
        normalized_query=wrong_query,
        resolved_query=wrong_query,
        intent="TEACH_TOPIC",
        target_topic="SVM",
    )
    context_turn5 = {"history": [], "teacher_state": state4_dict, "user_id": "test_user"}

    resp_turn5 = InteractiveTeacherEngine.execute_teacher_turn(
        session=db_session,
        session_id=session_id,
        raw_query=wrong_query,
        query_meta=meta_turn5,
        context=context_turn5,
        doc_id=None,
    )

    db_session.refresh(study_sess)
    state5_dict = study_sess.session_metadata.get("teacher_state")
    assert state5_dict["current_stage"] in (TeacherStageEnum.REEXPLAINING.value, "adaptive_reexplain")
    assert "Not quite" in resp_turn5["content"] or "misconception" in resp_turn5["content"].lower() or "angle" in resp_turn5["content"].lower() or "Interactive Checkpoint" in resp_turn5["content"]


def test_topic_switch_during_active_session(db_session: Session):
    """Verify switching topic from SVM to Decision Tree re-plans cleanly without error."""
    session_id = "test_switch_session_456"
    study_sess = StudySession(
        id=session_id,
        title="ML Session",
        subject="AI",
        status="active",
        session_metadata={
            "teacher_state": {
                "session_id": session_id,
                "mode": "teacher",
                "topic": "SVM",
                "current_unit_index": 1,
                "completed_concepts": ["Hyperplane"],
                "current_stage": "checkpoint_question",
            }
        },
    )
    db_session.add(study_sess)
    db_session.commit()

    switch_query = "Actually teach me Decision Trees instead"
    meta_switch = QueryMetadata(
        raw_query=switch_query,
        language="english",
        normalized_query=switch_query,
        resolved_query=switch_query,
        intent="TEACH_TOPIC",
        target_topic="Decision Trees",
    )
    context = {"history": [], "teacher_state": study_sess.session_metadata["teacher_state"], "user_id": "test_user"}

    resp = InteractiveTeacherEngine.execute_teacher_turn(
        session=db_session,
        session_id=session_id,
        raw_query=switch_query,
        query_meta=meta_switch,
        context=context,
        doc_id=None,
    )

    db_session.refresh(study_sess)
    updated_state = study_sess.session_metadata["teacher_state"]
    assert "decision tree" in updated_state["topic"].lower()
    assert updated_state["current_unit_index"] == 0


def test_navigation_skip_and_backtrack(db_session: Session):
    """Verify skip advances without marking unit as mastered, and backtrack restores previous concept."""
    session_id = "test_nav_session_789"
    plan = TeachingPlan(
        topic="SVM",
        overall_goal="Master SVM",
        learning_units=[
            LearningUnit(id="u1", concept="Concept 1", objective="Obj 1", status="completed"),
            LearningUnit(id="u2", concept="Concept 2", objective="Obj 2", status="in_progress"),
            LearningUnit(id="u3", concept="Concept 3", objective="Obj 3", status="pending"),
        ]
    )
    study_sess = StudySession(
        id=session_id,
        title="SVM Tutoring",
        subject="AI",
        status="active",
        session_metadata={
            "teacher_state": {
                "session_id": session_id,
                "mode": "teacher",
                "topic": "SVM",
                "current_unit_index": 1,
                "current_unit_id": "u2",
                "current_concept": "Concept 2",
                "completed_concepts": ["Concept 1"],
                "completed_learning_units": ["u1"],
                "teaching_plan": plan.model_dump(),
                "current_stage": TeacherStageEnum.CHECKPOINT.value,
            }
        },
    )
    db_session.add(study_sess)
    db_session.commit()

    # 1. Skip Concept 2
    skip_meta = QueryMetadata(
        raw_query="skip this concept",
        language="english",
        normalized_query="skip this concept",
        resolved_query="skip this concept",
        intent="TEACH_TOPIC",
        target_topic="SVM",
    )
    context = {"history": [], "teacher_state": study_sess.session_metadata["teacher_state"], "user_id": "u1"}
    resp_skip = InteractiveTeacherEngine.execute_teacher_turn(
        session=db_session,
        session_id=session_id,
        raw_query="skip this concept",
        query_meta=skip_meta,
        context=context,
        doc_id=None,
    )
    db_session.refresh(study_sess)
    state_after_skip = study_sess.session_metadata["teacher_state"]
    assert state_after_skip["current_unit_index"] == 2
    assert state_after_skip["current_concept"] == "Concept 3"
    # Skipped concept must NOT be in completed_concepts
    assert "Concept 2" not in state_after_skip["completed_concepts"]

    # 2. Backtrack to Concept 2
    back_meta = QueryMetadata(
        raw_query="go back to previous concept",
        language="english",
        normalized_query="go back to previous concept",
        resolved_query="go back to previous concept",
        intent="TEACH_TOPIC",
        target_topic="SVM",
    )
    context_back = {"history": [], "teacher_state": state_after_skip, "user_id": "u1"}
    resp_back = InteractiveTeacherEngine.execute_teacher_turn(
        session=db_session,
        session_id=session_id,
        raw_query="go back to previous concept",
        query_meta=back_meta,
        context=context_back,
        doc_id=None,
    )
    db_session.refresh(study_sess)
    state_after_back = study_sess.session_metadata["teacher_state"]
    assert state_after_back["current_unit_index"] == 1
    assert state_after_back["current_concept"] == "Concept 2"


def test_prerequisite_gap_detection_and_resolution(db_session: Session):
    """Verify that when a prerequisite gap is detected, the engine teaches the prerequisite and returns to the main checkpoint."""
    session_id = "test_prereq_session_101"
    study_sess = StudySession(
        id=session_id,
        title="SVM Tutoring",
        subject="AI",
        status="active",
        session_metadata={},
    )
    db_session.add(study_sess)
    db_session.commit()

    # Step A: Evaluate student answer returning PREREQUISITE_GAP
    eval_gap = {
        "understanding": "PREREQUISITE_GAP",
        "feedback": "Student is missing intuition on linear equations and sign checks.",
        "recommended_strategy": "prerequisite_review",
    }
    prereq_resp = InteractiveTeacherEngine._generate_prerequisite_explanation(
        topic="SVM",
        current_concept="Hyperplane Optimization",
        gap_details=eval_gap["feedback"]
    )
    assert len(prereq_resp["text"]) > 20
    assert len(prereq_resp["options"]) >= 2

    # Step B: Verify state transitions
    curr_state = TeacherSessionState(
        session_id=session_id,
        topic="SVM",
        current_unit_id="u1",
        current_concept="Hyperplane Optimization",
        current_stage=TeacherStageEnum.PREREQUISITE_REVIEW.value,
        current_question=prereq_resp["question"],
    )
    InteractiveTeacherEngine.persist_state(db_session, session_id, curr_state)
    db_session.refresh(study_sess)
    assert study_sess.session_metadata["teacher_state"]["current_stage"] == TeacherStageEnum.PREREQUISITE_REVIEW.value


def test_dynamic_coverage_and_topic_completion():
    """Verify that dynamic coverage audit and final synthesis/assessment/learning report run upon completion."""
    plan = TeachingPlan(
        topic="SVM",
        overall_goal="Master SVM",
        learning_units=[
            LearningUnit(id="u1", concept="Hyperplanes", objective="Understand separation", status="completed"),
            LearningUnit(id="u2", concept="Maximum Margin", objective="Understand optimization", status="completed"),
        ]
    )
    is_covered, extra_unit = InteractiveTeacherEngine._evaluate_topic_coverage(
        topic="SVM",
        teaching_plan=plan,
        completed_concepts=["Hyperplanes", "Maximum Margin"],
        matching_chunks=[],
        doubts=[],
        misconceptions=[],
    )
    assert isinstance(is_covered, bool)
    if not is_covered:
        assert extra_unit is not None
        assert isinstance(extra_unit, LearningUnit)

    # Generate final synthesis & report
    synthesis = InteractiveTeacherEngine._generate_topic_synthesis(
        topic="SVM",
        teaching_plan=plan,
        completed_concepts=["Hyperplanes", "Maximum Margin"],
        doubts=[],
    )
    assert "Master Mental Model" in synthesis or "SVM" in synthesis
    assert "Personalized Learning Report" in synthesis or "Report" in synthesis


def test_figure_handling_and_vlm_fallback(db_session: Session):
    """Verify figure discovery from DocumentAsset and graceful fallback without crashing if absent."""
    unit_with_asset = LearningUnit(
        id="u1",
        concept="SVM Margin Geometry",
        objective="Understand boundary spacing",
        source_pages=[1],
    )
    # 1. When no document_id or asset exists -> falls back cleanly to None without error
    asset = InteractiveTeacherEngine._find_relevant_visual_asset(db_session, None, unit_with_asset)
    assert asset is None

    # 2. When asset is present in DB
    doc_asset = DocumentAsset(
        id="asset-svm-1",
        document_id="doc_svm_test",
        asset_type="figure",
        page_number=1,
        caption="SVM Maximum Margin Decision Boundary",
        image_storage_path="/static/assets/svm_margin.png",
    )
    db_session.add(doc_asset)
    db_session.commit()

    found_asset = InteractiveTeacherEngine._find_relevant_visual_asset(db_session, "doc_svm_test", unit_with_asset)
    assert found_asset is not None
    assert "svm_margin.png" in found_asset["url"]
    assert "SVM Maximum Margin" in found_asset["caption"]


def test_topic_grounding_material_guard(db_session: Session):
    """Verify that if topic does not exist in uploaded material, it returns grounding check guardrail."""
    doc_id = "doc_unrelated_123"
    is_grounded, matching_chunks, topic = InteractiveTeacherEngine.verify_topic_grounding(
        session=db_session,
        topic="Quantum Computing",
        document_id=doc_id,
    )
    assert is_grounded is False
    assert len(matching_chunks) == 0

