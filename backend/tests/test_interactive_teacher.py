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
    Simulate complete multi-turn interactive session matching the Teacher Mode Response Format specification:
    Turn 1: 'Teach me SVM' -> First subtopic + Visual + 'Would you like me to continue to the next subtopic?'
    Turn 2: Student responds 'Continue' -> Advances to subtopic 2 + Progressive Visual + Confirmation
    Turn 3: Student asks doubt 'Why exactly do we need to maximize the margin?' -> Pauses/answers doubt without advancing subtopic
    Turn 4: Student says 'continue' -> Resumes / advances to next subtopic
    Turn 5: Student says 'Explain again' -> Simpler re-explanation of current subtopic with diagram
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

    assert ("SVM" in resp_turn1["content"] or "Support Vector Machine" in resp_turn1["content"])
    assert ("**Visual:**" in resp_turn1["content"] or "Visual:" in resp_turn1["content"] or "```" in resp_turn1["content"])
    assert "Would you like me to continue to the next subtopic?" in resp_turn1["content"]
    assert len(resp_turn1["suggested_questions"]) >= 2

    # Verify state was saved to database
    db_session.refresh(study_sess)
    state1_dict = study_sess.session_metadata.get("teacher_state")
    assert state1_dict is not None
    assert state1_dict["mode"] == "teacher"
    assert "SVM" in state1_dict["topic"]
    assert state1_dict["current_subtopic_index"] == 0
    assert state1_dict["awaiting_user_confirmation"] is True
    assert state1_dict.get("diagram_state") is not None
    assert len(state1_dict["subtopics"]) >= 2

    # --- TURN 2: Student Confirms to Continue ---
    meta_turn2 = QueryMetadata(
        raw_query="Continue",
        language="english",
        normalized_query="Continue",
        resolved_query="Continue",
        intent="TEACH_TOPIC",
        target_topic="SVM",
    )
    context_turn2 = {"history": [{"role": "user", "content": "Teach me SVM"}], "teacher_state": state1_dict, "user_id": "test_user"}

    resp_turn2 = InteractiveTeacherEngine.execute_teacher_turn(
        session=db_session,
        session_id=session_id,
        raw_query="Continue",
        query_meta=meta_turn2,
        context=context_turn2,
        doc_id=None,
    )

    assert ("Progressive Visual:" in resp_turn2["content"] or "Visual:" in resp_turn2["content"])
    assert "Would you like me to continue to the next subtopic?" in resp_turn2["content"]

    db_session.refresh(study_sess)
    state2_dict = study_sess.session_metadata.get("teacher_state")
    assert state2_dict is not None
    # Subtopic 1 should now be in completed_subtopics
    assert len(state2_dict["completed_subtopics"]) >= 1
    # Subtopic index should have progressed
    assert state2_dict["current_subtopic_index"] == 1

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

    assert "Would you like me to continue to the next subtopic?" in resp_turn3["content"]
    db_session.refresh(study_sess)
    state3_dict = study_sess.session_metadata.get("teacher_state")
    assert len(state3_dict["student_doubts"]) >= 1
    # Subtopic index must NOT advance while answering a doubt
    assert state3_dict["current_subtopic_index"] == state2_dict["current_subtopic_index"]

    # --- TURN 4: Student Resumes / Confirms ---
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
    assert state4_dict["current_subtopic_index"] >= 1
    assert "Would you like me to continue to the next subtopic?" in resp_turn4["content"]

    # --- TURN 5: Student Says 'Explain again' -> Simpler Re-explanation ---
    reexplain_query = "Explain again simply please"
    meta_turn5 = QueryMetadata(
        raw_query=reexplain_query,
        language="english",
        normalized_query=reexplain_query,
        resolved_query=reexplain_query,
        intent="TEACH_TOPIC",
        target_topic="SVM",
    )
    context_turn5 = {"history": [], "teacher_state": state4_dict, "user_id": "test_user"}

    resp_turn5 = InteractiveTeacherEngine.execute_teacher_turn(
        session=db_session,
        session_id=session_id,
        raw_query=reexplain_query,
        query_meta=meta_turn5,
        context=context_turn5,
        doc_id=None,
    )

    assert "Would you like me to continue to the next subtopic?" in resp_turn5["content"]
    db_session.refresh(study_sess)
    state5_dict = study_sess.session_metadata.get("teacher_state")
    # Must remain on the current subtopic without advancing
    assert state5_dict["current_subtopic_index"] == state4_dict["current_subtopic_index"]


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


def test_decision_tree_full_spec_progression(db_session: Session):
    """
    Test the exact Decision Tree pedagogical progression from the user specification:
    1. Teach me Decision Tree -> Root Node + Visual + Confirmation
    2. Yes -> Branch + Progressive Visual (Root + Branch) + Confirmation
    3. Yes -> Decision Node + Progressive Visual + Confirmation
    4. Yes -> Leaf Node + Progressive Visual + Confirmation
    5. Yes -> Complete Figure + '🎯 You have completed all the subtopics of Decision Tree.' + 'Would you like to take the final exam now?'
    6. Yes -> Final Exam generated
    7. Submit answers -> Final Exam Evaluation with Score and Weak Areas
    """
    session_id = "test_dt_full_session_999"
    study_sess = StudySession(
        id=session_id,
        title="Decision Tree Session",
        subject="Machine Learning",
        status="active",
        session_metadata={},
    )
    db_session.add(study_sess)
    db_session.commit()

    # Step 1: Root Node
    meta = QueryMetadata(
        raw_query="Teach me Decision Tree",
        normalized_query="Teach me Decision Tree",
        resolved_query="Teach me Decision Tree",
        intent="TEACH_TOPIC",
        target_topic="Decision Tree"
    )
    resp1 = InteractiveTeacherEngine.execute_teacher_turn(
        session=db_session, session_id=session_id, raw_query="Teach me Decision Tree",
        query_meta=meta, context={"history": [], "teacher_state": None}, doc_id=None
    )
    assert "Root Node" in resp1["content"]
    assert "Would you like me to continue to the next subtopic?" in resp1["content"]
    assert ("**Visual:**" in resp1["content"] or "Visual:" in resp1["content"])

    db_session.refresh(study_sess)
    state = study_sess.session_metadata["teacher_state"]
    assert state["current_subtopic_index"] == 0

    # Step 2: Branch
    meta_yes = QueryMetadata(raw_query="Yes", normalized_query="Yes", resolved_query="Yes", intent="TEACH_TOPIC", target_topic="Decision Tree")
    resp2 = InteractiveTeacherEngine.execute_teacher_turn(
        session=db_session, session_id=session_id, raw_query="Yes",
        query_meta=meta_yes, context={"history": [], "teacher_state": state}, doc_id=None
    )
    assert "Branch" in resp2["content"]
    assert ("Progressive Visual:" in resp2["content"] or "Visual:" in resp2["content"])
    assert "Would you like me to continue to the next subtopic?" in resp2["content"]

    db_session.refresh(study_sess)
    state = study_sess.session_metadata["teacher_state"]
    assert state["current_subtopic_index"] == 1

    # Step 3: Decision Node
    meta_cont = QueryMetadata(raw_query="Continue", normalized_query="Continue", resolved_query="Continue", intent="TEACH_TOPIC", target_topic="Decision Tree")
    resp3 = InteractiveTeacherEngine.execute_teacher_turn(
        session=db_session, session_id=session_id, raw_query="Continue",
        query_meta=meta_cont, context={"history": [], "teacher_state": state}, doc_id=None
    )
    assert "Decision" in resp3["content"]
    assert "Would you like me to continue to the next subtopic?" in resp3["content"]

    db_session.refresh(study_sess)
    state = study_sess.session_metadata["teacher_state"]
    assert state["current_subtopic_index"] == 2

    # Step 4: Adaptive Checkpoint Exam (triggered after 3 completed subtopics)
    meta_next = QueryMetadata(raw_query="Next", normalized_query="Next", resolved_query="Next", intent="TEACH_TOPIC", target_topic="Decision Tree")
    resp4 = InteractiveTeacherEngine.execute_teacher_turn(
        session=db_session, session_id=session_id, raw_query="Next",
        query_meta=meta_next, context={"history": [], "teacher_state": state}, doc_id=None
    )
    assert "Checkpoint Exam" in resp4["content"]

    db_session.refresh(study_sess)
    state = study_sess.session_metadata["teacher_state"]
    assert state["checkpoint_exam_started"] is True

    # Step 5: Student confirms/answers Checkpoint Exam -> Advances to Leaf Node
    meta_cont_cp = QueryMetadata(raw_query="continue", normalized_query="continue", resolved_query="continue", intent="TEACH_TOPIC", target_topic="Decision Tree")
    resp5 = InteractiveTeacherEngine.execute_teacher_turn(
        session=db_session, session_id=session_id, raw_query="continue",
        query_meta=meta_cont_cp, context={"history": [], "teacher_state": state}, doc_id=None
    )
    assert "Leaf" in resp5["content"]
    assert "Would you like me to continue to the next subtopic?" in resp5["content"]

    db_session.refresh(study_sess)
    state = study_sess.session_metadata["teacher_state"]
    assert state["current_subtopic_index"] == 3
    assert state["checkpoint_exam_completed"] is True

    # Step 6: Complete Figure & Exam Prompt
    meta_ahead = QueryMetadata(raw_query="Go ahead", normalized_query="Go ahead", resolved_query="Go ahead", intent="TEACH_TOPIC", target_topic="Decision Tree")
    resp6 = InteractiveTeacherEngine.execute_teacher_turn(
        session=db_session, session_id=session_id, raw_query="Go ahead",
        query_meta=meta_ahead, context={"history": [], "teacher_state": state}, doc_id=None
    )
    assert ("completed all the subtopics" in resp6["content"] or "Topic Completed" in resp6["content"])
    assert "Would you like to take the final exam now?" in resp6["content"]

    db_session.refresh(study_sess)
    state = study_sess.session_metadata["teacher_state"]
    assert state["exam_available"] is True

    # Step 7: Start Final Exam
    meta_exam_yes = QueryMetadata(raw_query="Yes", normalized_query="Yes", resolved_query="Yes", intent="TEACH_TOPIC", target_topic="Decision Tree")
    resp7 = InteractiveTeacherEngine.execute_teacher_turn(
        session=db_session, session_id=session_id, raw_query="Yes",
        query_meta=meta_exam_yes, context={"history": [], "teacher_state": state}, doc_id=None
    )
    assert "final exam" in resp7["content"].lower()

    db_session.refresh(study_sess)
    state = study_sess.session_metadata["teacher_state"]
    assert state["exam_started"] is True

    # Step 8: Submit Answers & Evaluation
    meta_sub = QueryMetadata(raw_query="1. B, 2. A, 3. Root splits data down to leaves, 4. Follows condition", normalized_query="answers", resolved_query="answers", intent="TEACH_TOPIC", target_topic="Decision Tree")
    resp8 = InteractiveTeacherEngine.execute_teacher_turn(
        session=db_session, session_id=session_id, raw_query="1. B, 2. A, 3. Root splits data down to leaves, 4. Follows condition",
        query_meta=meta_sub, context={"history": [], "teacher_state": state}, doc_id=None
    )
    assert "Final Exam Result" in resp8["content"]
    assert "Score:" in resp8["content"] or "Score" in resp8["content"]


def test_user_declining_advancement(db_session: Session):
    """Verify that when user says 'no', tutor remains on current subtopic without advancing."""
    session_id = "test_decline_session_555"
    study_sess = StudySession(
        id=session_id, title="Tree Session", subject="AI", status="active",
        session_metadata={"teacher_state": {
            "session_id": session_id,
            "mode": "teacher",
            "topic": "Decision Tree",
            "subtopics": ["Root Node", "Branch", "Decision Node", "Leaf Node"],
            "current_subtopic_index": 1,
            "current_subtopic": "Branch",
            "awaiting_user_confirmation": True,
        }}
    )
    db_session.add(study_sess)
    db_session.commit()

    meta = QueryMetadata(
        raw_query="No, not yet",
        normalized_query="No, not yet",
        resolved_query="No, not yet",
        intent="TEACH_TOPIC",
        target_topic="Decision Tree"
    )
    resp = InteractiveTeacherEngine.execute_teacher_turn(
        session=db_session, session_id=session_id, raw_query="No, not yet",
        query_meta=meta, context={"history": [], "teacher_state": study_sess.session_metadata["teacher_state"]}, doc_id=None
    )
    assert "stay on" in resp["content"].lower() or "Branch" in resp["content"]
    db_session.refresh(study_sess)
    state = study_sess.session_metadata["teacher_state"]
    # Must NOT advance
    assert state["current_subtopic_index"] == 1


def test_specific_portion_request():
    """Verify topic and portion extraction when user asks to explain a specific portion."""
    topic, portion = InteractiveTeacherEngine.extract_teach_topic_and_portion("Teach me Root Node of Decision Tree")
    assert "decision tree" in topic.lower()
    assert "root node" in portion.lower()

    topic2, portion2 = InteractiveTeacherEngine.extract_teach_topic_and_portion("Explain Decision Node in Decision Tree")
    assert "decision tree" in topic2.lower()
    assert "decision node" in portion2.lower()


def test_explain_this_topic_and_teach_this_chapter():
    """Verify activation phrases 'Explain this topic' and 'Teach me this chapter' are recognized."""
    from app.tutoring.analyzer.understanding import QueryUnderstanding
    extracted1 = QueryUnderstanding.extract_teach_topic("Explain this topic")
    assert extracted1 == "this topic"

    extracted2 = QueryUnderstanding.extract_teach_topic("Teach me this chapter")
    assert extracted2 == "this chapter"

    extracted3 = QueryUnderstanding.extract_teach_topic("Start teaching")
    assert extracted3 == "this topic"


def test_specific_portion_teaches_only_that_portion(db_session: Session):
    """
    Verify that when the user asks to teach/explain a specific portion (e.g. Root Node of Decision Tree),
    the tutor creates a dedicated plan ONLY for that portion rather than dumping the whole topic curriculum.
    """
    session_id = "test_portion_session_111"
    study_sess = StudySession(
        id=session_id,
        title="Portion Session",
        subject="AI",
        status="active",
        session_metadata={},
    )
    db_session.add(study_sess)
    db_session.commit()

    meta = QueryMetadata(
        raw_query="Teach me Root Node of Decision Tree",
        normalized_query="Teach me Root Node of Decision Tree",
        resolved_query="Teach me Root Node of Decision Tree",
        intent="TEACH_TOPIC",
        target_topic="Decision Tree",
    )
    resp = InteractiveTeacherEngine.execute_teacher_turn(
        session=db_session,
        session_id=session_id,
        raw_query="Teach me Root Node of Decision Tree",
        query_meta=meta,
        context={"history": [], "teacher_state": None},
        doc_id=None,
    )

    db_session.refresh(study_sess)
    state = study_sess.session_metadata["teacher_state"]
    # Verify ONLY the requested portion is in subtopics
    assert len(state["subtopics"]) == 1
    assert state["subtopics"][0] == "Root Node"
    assert "Root Node" in resp["content"]
    assert "Would you like me to continue to the next subtopic?" in resp["content"]


def test_dynamic_varied_headings(db_session: Session):
    """Verify that headings across subtopics are content-specific, varied, and never duplicated."""
    session_id = "test_headings_sess"
    study_sess = StudySession(
        id=session_id, title="Headings Session", subject="ML", status="active",
        session_metadata={},
    )
    db_session.add(study_sess)
    db_session.commit()

    meta1 = QueryMetadata(raw_query="Teach me SVM", normalized_query="Teach me SVM", resolved_query="Teach me SVM", intent="TEACH_TOPIC", target_topic="SVM")
    resp1 = InteractiveTeacherEngine.execute_teacher_turn(
        session=db_session, session_id=session_id, raw_query="Teach me SVM",
        query_meta=meta1, context={"history": [], "teacher_state": None}, doc_id=None,
    )
    db_session.refresh(study_sess)
    state1 = study_sess.session_metadata["teacher_state"]
    assert len(state1["used_subtopic_headings"]) == 1
    heading1 = state1["used_subtopic_headings"][0]
    assert "###" in resp1["content"]

    # Turn 2
    meta2 = QueryMetadata(raw_query="continue", normalized_query="continue", resolved_query="continue", intent="TEACH_TOPIC", target_topic="SVM")
    resp2 = InteractiveTeacherEngine.execute_teacher_turn(
        session=db_session, session_id=session_id, raw_query="continue",
        query_meta=meta2, context={"history": [], "teacher_state": state1}, doc_id=None,
    )
    db_session.refresh(study_sess)
    state2 = study_sess.session_metadata["teacher_state"]
    assert len(state2["used_subtopic_headings"]) == 2
    heading2 = state2["used_subtopic_headings"][1]

    # Verify headings are different and neither is generic "Understanding SVM"
    assert heading1 != heading2
    assert heading1.lower() != "svm"
    assert heading2.lower() != "svm"


def test_adaptive_exam_timing_large_topic(db_session: Session):
    """
    Verify adaptive exam timing for a large topic (> 6 subtopics):
    - Checkpoint exam triggers after 6 completed subtopics.
    - Continuing allows teaching subtopics 7+, culminating in final exam.
    """
    session_id = "test_large_topic_sess"
    large_subtopics = [
        "Concept A", "Concept B", "Concept C", "Concept D",
        "Concept E", "Concept F", "Concept G", "Concept H"
    ]
    study_sess = StudySession(
        id=session_id, title="Large Topic", subject="CS", status="active",
        session_metadata={"teacher_state": {
            "session_id": session_id,
            "mode": "teacher",
            "topic": "Distributed Systems",
            "main_topic": "Distributed Systems",
            "subtopics": large_subtopics,
            "current_subtopic_index": 5,
            "current_subtopic": "Concept F",
            "completed_subtopics": ["Concept A", "Concept B", "Concept C", "Concept D", "Concept E"],
            "awaiting_user_confirmation": True,
            "checkpoint_exam_completed": False,
        }},
    )
    db_session.add(study_sess)
    db_session.commit()

    # Confirming to advance past Concept F (which makes completed_count == 6)
    meta = QueryMetadata(raw_query="continue", normalized_query="continue", resolved_query="continue", intent="TEACH_TOPIC", target_topic="Distributed Systems")
    resp_cp = InteractiveTeacherEngine.execute_teacher_turn(
        session=db_session, session_id=session_id, raw_query="continue",
        query_meta=meta, context={"history": [], "teacher_state": study_sess.session_metadata["teacher_state"]}, doc_id=None,
    )

    # Checkpoint exam must be triggered at the 6-subtopic point!
    assert "Checkpoint Exam" in resp_cp["content"]
    db_session.refresh(study_sess)
    state = study_sess.session_metadata["teacher_state"]
    assert state["checkpoint_exam_started"] is True

    # Student confirms to proceed past checkpoint exam -> resumes to Concept G (subtopic 7)
    meta_resume = QueryMetadata(raw_query="continue", normalized_query="continue", resolved_query="continue", intent="TEACH_TOPIC", target_topic="Distributed Systems")
    resp_next = InteractiveTeacherEngine.execute_teacher_turn(
        session=db_session, session_id=session_id, raw_query="continue",
        query_meta=meta_resume, context={"history": [], "teacher_state": state}, doc_id=None,
    )
    assert "Concept G" in resp_next["content"]
    db_session.refresh(study_sess)
    state2 = study_sess.session_metadata["teacher_state"]
    assert state2["current_subtopic_index"] == 6
    assert state2["checkpoint_exam_completed"] is True


def test_progressive_visual_state_no_hardcoding():
    """Verify topic-agnostic progressive visual SVG layout and visual state tracking on non-CS topic."""
    elements = ["Light Absorption", "Electron Transport Chain", "ATP Synthesis"]
    relationships = ["Light Absorption -> Electron Transport Chain", "Electron Transport Chain -> ATP Synthesis"]

    svg = InteractiveTeacherEngine.synthesize_progressive_diagram(
        topic="Photosynthesis",
        subtopics=elements,
        current_index=2,
        diagram_elements=elements,
        diagram_relationships=relationships,
    )

    assert "<svg" in svg
    assert "</svg>" in svg
    assert "Photosynthesis" in svg
    assert "Light Absorption" in svg
    assert "ATP Synthesis" in svg
    assert "marker-end" in svg
    assert "New Concept" in svg




