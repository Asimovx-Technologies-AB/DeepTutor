"""
Central Intelligent Tutoring System (ITS) Orchestrator.

Implements the complete unified tutoring pipeline specified in the architecture:
STUDENT & COURSE -> CURRICULUM KNOWLEDGE MAP -> PERSONALIZED STUDY PLAN ->
LEARNING SESSION -> 5-DIMENSIONAL EXPLANATION -> PRACTICE -> RESPONSE ANALYSIS ->
[UNDERSTAND?]:
  - NO  -> Identify Knowledge Gap -> ADAPTIVE REMEDIATION (5 Levers) -> Re-practice
  - YES -> Update Progress -> MASTERY STATUS -> PROGRESS TRACKING ->
           [ASSESSMENT PASS?] -> Next Concept / Session -> [Ready for Exam?] -> EXAM READY
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from app.tutoring.assessment.practice_generator import practice_generator
from app.tutoring.assessment.response_evaluator import response_evaluator
from app.tutoring.curriculum.knowledge_map import knowledge_map_resolver
from app.tutoring.curriculum.syllabus_engine import syllabus_engine
from app.tutoring.models import (
    ConceptNode,
    CourseInput,
    CurriculumKnowledgeMap,
    EvaluationResult,
    ExamReadinessResult,
    ExplanationDimensions,
    FormativeQuestion,
    PersonalizedStudyPlan,
    ProgressSnapshot,
    RemediationPackage,
    SessionPlan,
    StudentModel,
    StudentProfile,
)
from app.tutoring.planning.study_planner import study_planner
from app.tutoring.progress.exam_readiness import exam_readiness_evaluator
from app.tutoring.progress.mastery_tracker import mastery_tracker
from app.tutoring.remediation.gap_identifier import gap_identifier
from app.tutoring.remediation.remediation_engine import remediation_engine
from app.tutoring.student.profile_manager import student_profile_manager
from app.tutoring.student.student_model import student_model_manager
from app.tutoring.teaching.explanation_engine import explanation_engine
from app.tutoring.teaching.session_runner import session_runner

logger = logging.getLogger(__name__)


class TutoringOrchestrator:
    """Central facade coordinating the end-to-end Intelligent Tutoring System."""

    def __init__(self) -> None:
        self.profile_mgr = student_profile_manager
        self.model_mgr = student_model_manager
        self.syllabus_engine = syllabus_engine
        self.knowledge_map = knowledge_map_resolver
        self.planner = study_planner
        self.explainer = explanation_engine
        self.session_runner = session_runner
        self.practice_gen = practice_generator
        self.evaluator = response_evaluator
        self.gap_identifier = gap_identifier
        self.remediation = remediation_engine
        self.mastery_tracker = mastery_tracker
        self.exam_readiness = exam_readiness_evaluator

        # In-memory session caches (keyed by course_id / plan_id)
        self._curriculum_cache: Dict[str, CurriculumKnowledgeMap] = {}
        self._plans_cache: Dict[str, PersonalizedStudyPlan] = {}

    def get_or_create_student(
        self,
        user_id: str,
        goal_level: str = "Undergraduate",
        learning_pace: str = "standard",
        prior_knowledge: str = "intermediate",
    ) -> Tuple[StudentProfile, StudentModel]:
        """Initializes or loads student profile and cognitive model."""
        profile = self.profile_mgr.get_profile(user_id)
        if goal_level:
            profile.goal_level = goal_level
        if learning_pace:
            profile.learning_pace = learning_pace
        if prior_knowledge:
            profile.prior_knowledge = prior_knowledge

        model = self.model_mgr.get_model(user_id)
        return profile, model

    async def build_curriculum(
        self,
        course_input: CourseInput,
        material_text: str = "",
        session_id_or_doc_id: Optional[str] = None,
    ) -> CurriculumKnowledgeMap:
        """
        Builds and validates the curriculum knowledge map from course input,
        enriching concepts with extracted assets from PostgreSQL document_chunks.
        """
        km = await self.syllabus_engine.generate_knowledge_map(course_input, material_text)

        # Enrich concepts with figure, table, and formula chunks
        enrich_target = session_id_or_doc_id or course_input.course_id
        self.knowledge_map.enrich_concepts_with_assets(km, enrich_target)

        # Cache
        self._curriculum_cache[course_input.course_id] = km
        return km

    def get_curriculum(self, course_id: str) -> Optional[CurriculumKnowledgeMap]:
        """Retrieves cached curriculum knowledge map."""
        return self._curriculum_cache.get(course_id)

    def create_study_plan(
        self,
        user_id: str,
        course_id: str,
        target_date: str = "",
        daily_minutes: int = 45,
    ) -> PersonalizedStudyPlan:
        """Constructs an adaptive multi-session study plan."""
        curriculum = self._curriculum_cache.get(course_id)
        if not curriculum:
            raise ValueError(f"Curriculum not found for course '{course_id}'. Build curriculum first.")

        profile = self.profile_mgr.get_profile(user_id)
        model = self.model_mgr.get_model(user_id)

        plan = self.planner.generate_plan(
            student_profile=profile,
            student_model=model,
            curriculum=curriculum,
            target_date=target_date,
            daily_minutes=daily_minutes,
        )
        self._plans_cache[plan.plan_id] = plan
        return plan

    async def teach_concept(
        self,
        user_id: str,
        course_id: str,
        concept_id: str,
        context_text: str = "",
    ) -> ExplanationDimensions:
        """Generates 5-dimensional pedagogical explanation for the target concept."""
        curriculum = self._curriculum_cache.get(course_id)
        concept = self.knowledge_map.get_concept_by_id(curriculum, concept_id) if curriculum else None

        if not concept:
            concept = ConceptNode(
                concept_id=concept_id,
                title=concept_id.replace("_", " ").title(),
                description=f"Core conceptual study of {concept_id}",
            )

        profile = self.profile_mgr.get_profile(user_id)
        model = self.model_mgr.get_model(user_id)

        return await self.explainer.generate_explanation(
            concept=concept,
            student_profile=profile,
            student_model=model,
            context_text=context_text,
        )

    async def generate_formative_question(
        self,
        user_id: str,
        course_id: str,
        concept_id: str,
        question_type: str = "conceptual",
    ) -> FormativeQuestion:
        """Generates targeted formative assessment question testing principles and traps."""
        curriculum = self._curriculum_cache.get(course_id)
        concept = self.knowledge_map.get_concept_by_id(curriculum, concept_id) if curriculum else None

        if not concept:
            concept = ConceptNode(
                concept_id=concept_id,
                title=concept_id.replace("_", " ").title(),
                description=f"Conceptual study of {concept_id}",
            )

        profile = self.profile_mgr.get_profile(user_id)
        model = self.model_mgr.get_model(user_id)

        return await self.practice_gen.generate_question(
            concept=concept,
            student_profile=profile,
            student_model=model,
            question_type=question_type,
        )

    async def process_student_response(
        self,
        user_id: str,
        course_id: str,
        concept_id: str,
        question: FormativeQuestion,
        student_answer: str,
        consecutive_failures: int = 1,
    ) -> Tuple[EvaluationResult, Optional[RemediationPackage], Optional[ProgressSnapshot]]:
        """
        Executes the assessment & decision branch:
        [STUDENT ANSWER] -> [RESPONSE ANALYSIS] -> [UNDERSTAND?]
          - NO  -> Identify Knowledge Gap -> ADAPTIVE REMEDIATION (5 Levers)
          - YES -> Update Progress -> MASTERY STATUS -> PROGRESS TRACKING
        """
        profile = self.profile_mgr.get_profile(user_id)
        model = self.model_mgr.get_model(user_id)
        curriculum = self._curriculum_cache.get(course_id)
        concept = self.knowledge_map.get_concept_by_id(curriculum, concept_id) if curriculum else None

        if not concept:
            concept = ConceptNode(
                concept_id=concept_id,
                title=concept_id.replace("_", " ").title(),
                description=f"Study of {concept_id}",
            )

        # 1. Evaluate student response
        eval_result = await self.evaluator.evaluate_response(
            question=question,
            student_answer=student_answer,
            student_profile=profile,
        )

        # 2. Record attempt in student model
        model = self.mastery_tracker.record_attempt(
            student_model=model,
            concept=concept,
            eval_result=eval_result,
        )
        self.model_mgr.save_model(model)

        remediation_pkg: Optional[RemediationPackage] = None
        snapshot: Optional[ProgressSnapshot] = None

        if not eval_result.is_understood:
            # Step: Identify Knowledge Gap
            diagnosis = self.gap_identifier.diagnose_gap(
                concept=concept,
                eval_result=eval_result,
                student_model=model,
                curriculum=curriculum,
                consecutive_failures=consecutive_failures,
            )

            # Step: ADAPTIVE REMEDIATION (Execute diagnosed lever)
            remediation_pkg = await self.remediation.generate_remediation(
                concept=concept,
                gap_diagnosis=diagnosis["gap_summary"],
                lever=diagnosis["recommended_lever"],
                student_profile=profile,
                scaffolding_step=consecutive_failures,
            )
        else:
            # Step: Update Progress -> MASTERY STATUS -> PROGRESS TRACKING
            if curriculum:
                snapshot = self.mastery_tracker.get_progress_snapshot(
                    student_model=model,
                    curriculum=curriculum,
                )

        return eval_result, remediation_pkg, snapshot

    def check_exam_readiness(
        self,
        user_id: str,
        course_id: str,
        plan_id: Optional[str] = None,
    ) -> ExamReadinessResult:
        """Evaluates overall course exam readiness."""
        curriculum = self._curriculum_cache.get(course_id)
        if not curriculum:
            return ExamReadinessResult(
                is_ready=False,
                readiness_score=0.0,
                weak_areas_to_review=[],
                recommendation_summary="Curriculum not initialized.",
            )

        model = self.model_mgr.get_model(user_id)
        plan = self._plans_cache.get(plan_id) if plan_id else None

        if not plan:
            plan = PersonalizedStudyPlan(
                plan_id="virtual",
                student_id=user_id,
                course_id=course_id,
            )

        return self.exam_readiness.evaluate_readiness(
            curriculum=curriculum,
            student_model=model,
            study_plan=plan,
        )


tutoring_orchestrator = TutoringOrchestrator()
