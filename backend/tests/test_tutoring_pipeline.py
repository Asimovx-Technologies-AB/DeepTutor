"""
Unit and Integration Tests for the Intelligent Tutoring System (ITS) Pipeline.

Covers:
1. Student Profile & Diagnostic Student Model (BKT updates)
2. Curriculum Syllabus Engine (Hierarchical Breakdown & Prereq DAG)
3. Knowledge Map Resolver (DAG validation, topological sort, asset linking)
4. Personalized Study Planner (Adaptive Session Sequencing 1..N)
5. 5-Dimensional Explanation Engine (Visuals, History, Analogies, Examples, Theory)
6. Formative Assessment (Question generation & Response Evaluator / UNDERSTAND? decision)
7. Adaptive Remediation (5 Levers: Alt Expl, Simpler Analogy, Visuals, Hint, Breakdown)
8. Mastery Tracking & Progress Snapshot (Retained, In Progress, Weak Areas, Strengths)
9. Exam Readiness Gatekeeper (Ready for Exam? decision diamond)
10. Tutoring Orchestrator end-to-end flow
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from app.tutoring.assessment.practice_generator import PracticeGenerator
from app.tutoring.assessment.response_evaluator import ResponseEvaluator
from app.tutoring.curriculum.knowledge_map import KnowledgeMapResolver
from app.tutoring.curriculum.syllabus_engine import SyllabusEngine
from app.tutoring.models import (
    ConceptNode,
    CourseInput,
    CurriculumKnowledgeMap,
    EvaluationResult,
    FormativeQuestion,
    PersonalizedStudyPlan,
    RemediationLever,
    SessionPlan,
    StudentModel,
    StudentProfile,
    SubtopicNode,
    TopicNode,
)
from app.tutoring.orchestrator import TutoringOrchestrator
from app.tutoring.planning.study_planner import StudyPlanner
from app.tutoring.progress.exam_readiness import ExamReadinessEvaluator
from app.tutoring.progress.mastery_tracker import MasteryTracker
from app.tutoring.remediation.gap_identifier import GapIdentifier
from app.tutoring.remediation.remediation_engine import RemediationEngine
from app.tutoring.student.profile_manager import StudentProfileManager
from app.tutoring.student.student_model import StudentModelManager
from app.tutoring.teaching.explanation_engine import ExplanationEngine


# ─── 1. Student Profile & Persona Tests ──────────────────────────────────────


def test_student_profile_manager():
    mgr = StudentProfileManager()
    profile = mgr.get_profile("test_user_001")
    assert profile.user_id == "test_user_001"
    assert profile.goal_level == "Undergraduate"
    assert "visual" in profile.preferences

    # Update profile
    profile.learning_pace = "accelerated"
    profile.prior_knowledge = "advanced"
    mgr.save_profile(profile)

    loaded = mgr.get_profile("test_user_001")
    assert loaded.learning_pace == "accelerated"
    assert loaded.prior_knowledge == "advanced"


def test_student_model_bkt_updates():
    mgr = StudentModelManager()
    model = mgr.get_model("test_user_002")
    assert model.user_id == "test_user_002"

    # Initially concept has default prior mastery (0.50)
    # Correct response should increase mastery
    model = mgr.update_mastery(model, "concept_calculus_1", is_correct=True, score=0.9)
    mastery_1 = model.concept_mastery["concept_calculus_1"]
    assert mastery_1 > 0.50

    # Another correct response increases it further
    model = mgr.update_mastery(model, "concept_calculus_1", is_correct=True, score=1.0)
    mastery_2 = model.concept_mastery["concept_calculus_1"]
    assert mastery_2 > mastery_1

    # Incorrect response lowers mastery
    model = mgr.update_mastery(model, "concept_calculus_1", is_correct=False, score=0.2)
    mastery_3 = model.concept_mastery["concept_calculus_1"]
    assert mastery_3 < mastery_2


# ─── 2. Curriculum & Knowledge Map Tests ─────────────────────────────────────


@pytest.mark.asyncio
async def test_syllabus_engine_heuristic_fallback():
    engine = SyllabusEngine()
    course_in = CourseInput(
        course_id="cs101",
        course_info="Introduction to Algorithms and Data Structures",
        subject="Computer Science",
        learning_objectives=["Understand asymptotic complexity", "Master binary search"],
    )

    # Test fallback path
    fallback = engine._heuristic_fallback(course_in, "Binary Search and Big-O notation fundamentals.")
    assert "topics" in fallback
    assert len(fallback["topics"]) > 0
    assert fallback["topics"][0]["subtopics"][0]["concepts"][0]["concept_id"] == "c_1"


def test_knowledge_map_dag_validation_and_topological_sort():
    resolver = KnowledgeMapResolver()

    # Create 3 concepts: c1 (base) -> c2 (depends on c1) -> c3 (depends on c2)
    c1 = ConceptNode(concept_id="c1", title="Limits", description="Basics of limits", prerequisites=[])
    c2 = ConceptNode(concept_id="c2", title="Derivatives", description="Rate of change", prerequisites=["c1"])
    c3 = ConceptNode(concept_id="c3", title="Integrals", description="Area under curve", prerequisites=["c2"])

    st = SubtopicNode(subtopic_id="st1", title="Calculus Foundations", concepts=[c1, c2, c3])
    topic = TopicNode(topic_id="t1", title="Calculus", summary="Core calculus", subtopics=[st])

    km = CurriculumKnowledgeMap(
        course_id="math101",
        subject="Mathematics",
        title="Introductory Calculus",
        topics=[topic],
        dependency_graph={"c2": ["c1"], "c3": ["c2"]},
    )

    # 1. Validation
    errors = resolver.validate_dag(km)
    assert len(errors) == 0

    # 2. Topological sort order must be c1 -> c2 -> c3
    seq = resolver.get_topological_sequence(km)
    ids = [node.concept_id for node in seq]
    assert ids == ["c1", "c2", "c3"]

    # 3. Prerequisites check
    prereqs_c3 = resolver.get_prerequisites(km, "c3")
    assert len(prereqs_c3) == 1
    assert prereqs_c3[0].concept_id == "c2"

    # 4. Unlocked check
    unlocked_c1 = resolver.get_unlocked_concepts(km, "c1")
    assert len(unlocked_c1) == 1
    assert unlocked_c1[0].concept_id == "c2"


def test_knowledge_map_cycle_detection():
    resolver = KnowledgeMapResolver()
    c1 = ConceptNode(concept_id="c1", title="Node 1", description="", prerequisites=["c2"])
    c2 = ConceptNode(concept_id="c2", title="Node 2", description="", prerequisites=["c1"])
    st = SubtopicNode(subtopic_id="st1", title="Cycle Unit", concepts=[c1, c2])
    topic = TopicNode(topic_id="t1", title="Cycle Topic", summary="", subtopics=[st])

    km = CurriculumKnowledgeMap(
        course_id="cycle_course",
        subject="Logic",
        title="Cycle Test",
        topics=[topic],
        dependency_graph={"c1": ["c2"], "c2": ["c1"]},
    )

    errors = resolver.validate_dag(km)
    assert any("cycle" in err.lower() for err in errors)


# ─── 3. Personalized Study Planner Tests ─────────────────────────────────────


def test_study_planner_sequencing():
    planner = StudyPlanner()
    profile = StudentProfile(user_id="u_plan", learning_pace="standard")
    model = StudentModel(user_id="u_plan")

    c1 = ConceptNode(concept_id="c1", title="Concept 1", description="")
    c2 = ConceptNode(concept_id="c2", title="Concept 2", description="", prerequisites=["c1"])
    c3 = ConceptNode(concept_id="c3", title="Concept 3", description="", prerequisites=["c2"])
    c4 = ConceptNode(concept_id="c4", title="Concept 4", description="", prerequisites=["c3"])

    st = SubtopicNode(subtopic_id="st1", title="Unit 1", concepts=[c1, c2, c3, c4])
    topic = TopicNode(topic_id="t1", title="Topic 1", summary="", subtopics=[st])
    km = CurriculumKnowledgeMap(
        course_id="course_plan",
        subject="Physics",
        title="Classical Mechanics",
        topics=[topic],
        dependency_graph={"c2": ["c1"], "c3": ["c2"], "c4": ["c3"]},
    )

    # Standard pace groups 2 concepts per session
    plan = planner.generate_plan(profile, model, km, daily_minutes=45)
    assert len(plan.sessions) == 2
    assert plan.sessions[0].session_number == 1
    assert plan.sessions[0].target_concepts == ["c1", "c2"]
    assert plan.sessions[0].status == "in_progress"
    assert plan.sessions[1].session_number == 2
    assert plan.sessions[1].target_concepts == ["c3", "c4"]
    assert plan.sessions[1].status == "pending"

    # Advance session
    nxt = planner.mark_session_completed(plan, session_number=1)
    assert nxt is not None
    assert nxt.session_number == 2
    assert nxt.status == "in_progress"
    assert plan.sessions[0].status == "completed"


# ─── 4. 5-Dimensional Explanation Engine Tests ───────────────────────────────


@pytest.mark.asyncio
async def test_explanation_dimensions():
    engine = ExplanationEngine()
    concept = ConceptNode(
        concept_id="c_eigen",
        title="Eigenvectors and Eigenvalues",
        description="Linear transformations that scale vectors without rotating their direction.",
        difficulty="intermediate",
        key_terms=["transformation", "scaling", "matrix"],
    )
    profile = StudentProfile(user_id="u_exp", goal_level="Undergraduate")

    # Mock LLM response with valid JSON containing all 5 dimensions
    mock_llm_json = """{
        "visual_description": "A 2D coordinate plane with arrows stretched along invariant axes.",
        "historical_context": "Originated with Euler in studying rigid body motion.",
        "analogy": "Like stretching a rubber sheet along its natural bias.",
        "examples": "For matrix A = [[2, 0], [0, 3]], vector [1, 0] is scaled by factor 2.",
        "detail_theory": "$$A \\\\mathbf{v} = \\\\lambda \\\\mathbf{v}$$ where $\\\\lambda$ is the eigenvalue."
    }"""

    with patch.object(engine.llm, "generate", new=AsyncMock(return_value=mock_llm_json)):
        dimensions = await engine.generate_explanation(concept, profile)

    assert dimensions.concept_id == "c_eigen"
    assert "axes" in dimensions.visual_description
    assert "Euler" in dimensions.historical_context
    assert "rubber sheet" in dimensions.analogy
    assert "vector [1, 0]" in dimensions.examples
    assert "A" in dimensions.detail_theory


# ─── 5. Formative Assessment & Evaluator Tests ────────────────────────────────


@pytest.mark.asyncio
async def test_practice_generator_and_evaluator():
    practice_gen = PracticeGenerator()
    evaluator = ResponseEvaluator()

    concept = ConceptNode(
        concept_id="c_momentum",
        title="Conservation of Momentum",
        description="Total momentum of an isolated system remains constant.",
    )
    profile = StudentProfile(user_id="u_assess")

    mock_q_json = """{
        "prompt": "Explain what happens to total momentum during an inelastic collision between two carts.",
        "question_type": "conceptual",
        "rubric": "Total momentum is conserved; kinetic energy is converted to thermal energy.",
        "common_pitfalls": ["Assuming momentum is lost when kinetic energy decreases"],
        "hints": ["Consider external forces vs internal forces."]
    }"""

    with patch.object(practice_gen.llm, "generate", new=AsyncMock(return_value=mock_q_json)):
        question = await practice_gen.generate_question(concept, profile)

    assert question.concept_id == "c_momentum"
    assert "inelastic collision" in question.prompt
    assert len(question.common_pitfalls) > 0

    # Evaluate student answer: correct case
    mock_eval_correct = """{
        "is_understood": true,
        "score": 0.95,
        "diagnosed_gap": null,
        "misconception": null,
        "feedback": "Flawless articulation of momentum invariance.",
        "next_action": "advance"
    }"""

    with patch.object(evaluator.llm, "generate", new=AsyncMock(return_value=mock_eval_correct)):
        res_pass = await evaluator.evaluate_response(
            question,
            "Total momentum remains conserved because no external net force acts on the two-cart system.",
        )

    assert res_pass.is_understood is True
    assert res_pass.score >= 0.85
    assert res_pass.next_action == "advance"

    # Evaluate student answer: incorrect case (UNDERSTAND? = NO)
    mock_eval_fail = """{
        "is_understood": false,
        "score": 0.35,
        "diagnosed_gap": "Confusion between kinetic energy and linear momentum",
        "misconception": "Believing momentum is destroyed when objects stick together",
        "feedback": "Momentum is strictly conserved even in completely inelastic collisions.",
        "next_action": "remediate"
    }"""

    with patch.object(evaluator.llm, "generate", new=AsyncMock(return_value=mock_eval_fail)):
        res_fail = await evaluator.evaluate_response(
            question,
            "Momentum is lost because the carts stick together and slow down.",
        )

    assert res_fail.is_understood is False
    assert res_fail.score < 0.60
    assert res_fail.next_action == "remediate"
    assert "Confusion" in res_fail.diagnosed_gap


# ─── 6. Adaptive Remediation Levers Tests ─────────────────────────────────────


@pytest.mark.asyncio
async def test_adaptive_remediation_levers():
    gap_id = GapIdentifier()
    remediation = RemediationEngine()

    concept = ConceptNode(concept_id="c_relativity", title="Special Relativity", description="")
    profile = StudentProfile(user_id="u_remed")
    model = StudentModel(user_id="u_remed")

    eval_result = EvaluationResult(
        is_understood=False,
        score=0.4,
        diagnosed_gap="Invariant speed of light conflicts with Galilean relativity",
        misconception="Believing velocities always add linearly (v + c)",
    )

    # Diagnose gap -> should recommend SIMPLER_ANALOGY due to misconception
    diag = gap_id.diagnose_gap(concept, eval_result, model, consecutive_failures=1)
    assert diag["recommended_lever"] == RemediationLever.SIMPLER_ANALOGY

    # Generate remediation package with SIMPLER_ANALOGY
    mock_remed_text = (
        "Think of light like the universal speed limit on a digital scoreboard: "
        "no matter how fast you run toward the scoreboard, the display still updates at the exact same clock frequency."
    )

    with patch.object(remediation.llm, "generate", new=AsyncMock(return_value=mock_remed_text)):
        pkg = await remediation.generate_remediation(
            concept=concept,
            gap_diagnosis=diag["gap_summary"],
            lever=diag["recommended_lever"],
            student_profile=profile,
            scaffolding_step=1,
        )

    assert pkg.lever_used == RemediationLever.SIMPLER_ANALOGY
    assert "scoreboard" in pkg.content
    assert pkg.scaffolding_step == 1


# ─── 7. Progress Tracking & Exam Readiness Gatekeeper Tests ───────────────────


def test_progress_tracking_and_exam_readiness():
    mastery_tracker = MasteryTracker()
    exam_readiness = ExamReadinessEvaluator()

    profile = StudentProfile(user_id="u_gate")
    model = StudentModel(user_id="u_gate")

    c1 = ConceptNode(concept_id="c1", title="Unit 1 Foundations", description="")
    c2 = ConceptNode(concept_id="c2", title="Unit 2 Advanced", description="", prerequisites=["c1"])
    st = SubtopicNode(subtopic_id="st1", title="Core", concepts=[c1, c2])
    topic = TopicNode(topic_id="t1", title="Syllabus", summary="", subtopics=[st])
    km = CurriculumKnowledgeMap(
        course_id="course_exam",
        subject="Chemistry",
        title="Organic Chemistry",
        topics=[topic],
        dependency_graph={"c2": ["c1"]},
    )
    plan = PersonalizedStudyPlan(plan_id="p1", student_id="u_gate", course_id="course_exam")

    # Initial state: student has 0 mastery -> Exam Readiness should be False
    res_not_ready = exam_readiness.evaluate_readiness(km, model, plan)
    assert res_not_ready.is_ready is False
    assert len(res_not_ready.weak_areas_to_review) > 0
    assert "NOT READY" in res_not_ready.recommendation_summary

    # Student masters c1 and c2
    eval_pass = EvaluationResult(is_understood=True, score=0.95)
    model = mastery_tracker.record_attempt(model, c1, eval_pass)
    model = mastery_tracker.record_attempt(model, c2, eval_pass)

    # Force mastery values above threshold for testing
    model.concept_mastery["c1"] = 0.90
    model.concept_mastery["c2"] = 0.92

    # Assessment Pass checks
    assert mastery_tracker.check_assessment_pass(model, "c1") is True
    assert mastery_tracker.check_assessment_pass(model, "c2") is True

    # Progress Snapshot
    snapshot = mastery_tracker.get_progress_snapshot(model, km)
    assert len(snapshot.retained) == 2
    assert len(snapshot.weak_areas) == 0

    # Exam Readiness should now be True (EXAM READY)
    res_ready = exam_readiness.evaluate_readiness(km, model, plan)
    assert res_ready.is_ready is True
    assert res_ready.readiness_score >= 80.0
    assert "EXAM READY" in res_ready.recommendation_summary


# ─── 8. Tutoring Orchestrator End-to-End Tests ────────────────────────────────


@pytest.mark.asyncio
async def test_tutoring_orchestrator_flow():
    orchestrator = TutoringOrchestrator()
    user_id = "test_e2e_student"
    course_id = "e2e_quantum"

    # 1. Init Student
    profile, model = orchestrator.get_or_create_student(user_id, learning_pace="standard")
    assert profile.user_id == user_id

    # 2. Build Curriculum
    course_in = CourseInput(
        course_id=course_id,
        course_info="Quantum Mechanics Principles",
        subject="Physics",
        learning_objectives=["Wave-particle duality", "Schrodinger equation"],
    )
    km = await orchestrator.build_curriculum(course_in)
    assert km.course_id == course_id
    assert len(km.topics) > 0

    # 3. Create Study Plan
    plan = orchestrator.create_study_plan(user_id, course_id, daily_minutes=45)
    assert plan.course_id == course_id
    assert len(plan.sessions) > 0

    # 4. Teach Concept
    first_concept_id = plan.sessions[0].target_concepts[0]
    explanation = await orchestrator.teach_concept(user_id, course_id, first_concept_id)
    assert explanation.concept_id == first_concept_id
    assert explanation.visual_description != ""
    assert explanation.analogy != ""

    # 5. Formative Practice
    question = await orchestrator.generate_formative_question(user_id, course_id, first_concept_id)
    assert question.concept_id == first_concept_id

    # 6. Submit Answer (Fail -> Remediation)
    eval_res, remed, snap = await orchestrator.process_student_response(
        user_id=user_id,
        course_id=course_id,
        concept_id=first_concept_id,
        question=question,
        student_answer="I don't know",
        consecutive_failures=1,
    )
    assert eval_res.is_understood is False
    assert remed is not None
    assert remed.lever_used in [
        RemediationLever.ALTERNATIVE_EXPLANATION,
        RemediationLever.SIMPLER_ANALOGY,
        RemediationLever.VISUALS,
        RemediationLever.HINT,
        RemediationLever.BREAKDOWN,
    ]


# ─── 9. Advanced Graph Analytics & Psychometrics Tests ────────────────────────


def test_advanced_graph_analytics():
    resolver = KnowledgeMapResolver()
    c1 = ConceptNode(concept_id="c1", title="Limits", description="")
    c2 = ConceptNode(concept_id="c2", title="Derivatives", description="", prerequisites=["c1"])
    c3 = ConceptNode(concept_id="c3", title="Integrals", description="", prerequisites=["c2"])
    c4 = ConceptNode(concept_id="c4", title="Calculus 3", description="", prerequisites=["c3"])

    st = SubtopicNode(subtopic_id="st1", title="Math", concepts=[c1, c2, c3, c4])
    topic = TopicNode(topic_id="t1", title="Math", summary="", subtopics=[st])
    km = CurriculumKnowledgeMap(
        course_id="math_adv",
        subject="Math",
        title="Calculus",
        topics=[topic],
        dependency_graph={
            "c2": ["c1"],
            "c3": ["c1", "c2"],  # c1 is redundant because c1 -> c2 -> c3
            "c4": ["c2", "c3"],  # c2 is redundant because c2 -> c3 -> c4
        },
    )

    # 1. Transitive Reduction: prunes redundant transitive bypass edges
    reduced = resolver.transitive_reduction(km)
    assert "c1" not in reduced.get("c3", [])
    assert "c2" in reduced.get("c3", [])

    # 2. Critical Path Analysis: longest path depth
    max_depth, path = resolver.compute_critical_path(km)
    assert max_depth == 4  # c1 -> c2 -> c3 -> c4
    assert path[0] == "c1"
    assert path[-1] == "c4"

    # 3. Concept Centrality: foundational keystone concepts have highest downstream influence
    centrality = resolver.compute_concept_centrality(km)
    assert centrality["c1"] > centrality["c4"]


def test_advanced_bkt_and_retention():
    mgr = StudentModelManager()
    model = StudentModel(user_id="u_bkt")

    # Correct response increases mastery monotonically
    p1 = mgr.compute_bkt_update(0.50, is_correct=True, score=1.0)
    assert p1 > 0.50

    p2 = mgr.compute_bkt_update(p1, is_correct=True, score=1.0)
    assert p2 > p1

    # Slip / incorrect decreases mastery
    p3 = mgr.compute_bkt_update(p2, is_correct=False, score=0.0)
    assert p3 < p2

    # Ebbinghaus retention decay over 30 days
    model.concept_mastery["c_decay"] = 0.85
    r_immediate = mgr.estimate_retention(model, "c_decay", elapsed_days=0.0)
    r_30_days = mgr.estimate_retention(model, "c_decay", elapsed_days=30.0)
    assert r_immediate == 0.85
    assert r_30_days < r_immediate
    assert r_30_days > 0.0

