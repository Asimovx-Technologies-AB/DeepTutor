"""
Intelligent Tutoring System (ITS) Data Models.

Defines all structures representing the complete pedagogical tutoring loop:
- Student Profile & Persona (Goals, Pace, Preferences)
- Student Knowledge Model (Weaknesses, Strengths, Misconceptions, Mastery State)
- Curriculum Knowledge Map (Topics -> Subtopics -> Concepts + Prereq DAG + Asset Links)
- Personalized Study Plan (Session sequencing)
- 5-Dimensional Explanation Engine (Visuals, History/Context, Analogies, Examples, Theory)
- Formative Assessment & Response Analysis
- Adaptive Remediation (5 Levers: Alt Expl, Simpler Analogy, Visuals, Hint, Breakdown)
- Progress Tracking & Exam Readiness
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


# ─── 1. Student Persona & Knowledge State ─────────────────────────────────────


@dataclass
class StudentProfile:
    """User profile capturing pedagogical persona, goals, and learning style."""

    user_id: str
    goal_level: str = "Undergraduate"        # "High School", "Undergraduate", "Graduate", "Exam Prep"
    learning_pace: str = "standard"          # "accelerated", "standard", "thorough"
    prior_knowledge: str = "intermediate"    # "beginner", "intermediate", "advanced"
    preferences: Dict[str, float] = field(
        default_factory=lambda: {
            "visual": 0.8,
            "analogy": 0.9,
            "history": 0.6,
            "example": 0.9,
            "theory": 0.7,
        }
    )


@dataclass
class StudentModel:
    """Dynamic cognitive state of the learner."""

    user_id: str
    weaknesses: List[Dict[str, Any]] = field(default_factory=list)
    strengths: List[Dict[str, Any]] = field(default_factory=list)
    misconceptions: List[Dict[str, Any]] = field(default_factory=list)
    concept_mastery: Dict[str, float] = field(default_factory=dict)
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ─── 2. Curriculum Knowledge Map ──────────────────────────────────────────────


@dataclass
class ConceptNode:
    """Atomic conceptual learning unit within the curriculum."""

    concept_id: str
    title: str
    description: str
    prerequisites: List[str] = field(default_factory=list)
    knowledge_box_ids: List[str] = field(default_factory=list)
    difficulty: str = "intermediate"         # "foundational", "intermediate", "advanced"
    key_terms: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SubtopicNode:
    """Subtopic modular grouping of related concepts."""

    subtopic_id: str
    title: str
    concepts: List[ConceptNode] = field(default_factory=list)


@dataclass
class TopicNode:
    """Major curriculum topic or syllabus unit."""

    topic_id: str
    title: str
    summary: str
    subtopics: List[SubtopicNode] = field(default_factory=list)


@dataclass
class CourseInput:
    """Course inputs ingested to generate the curriculum knowledge map."""

    course_id: str
    course_info: str
    learning_objectives: List[str] = field(default_factory=list)
    assessment_criteria: str = ""
    uploaded_materials: List[str] = field(default_factory=list)
    subject: str = "General"


@dataclass
class CurriculumKnowledgeMap:
    """Structured graph representation of the course curriculum."""

    course_id: str
    subject: str
    title: str
    topics: List[TopicNode] = field(default_factory=list)
    dependency_graph: Dict[str, List[str]] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ─── 3. Personalized Study Plan ───────────────────────────────────────────────


@dataclass
class SessionPlan:
    """A single scheduled learning session within the study plan."""

    session_number: int
    title: str
    target_concepts: List[str]
    estimated_minutes: int = 45
    status: str = "pending"                  # "pending", "in_progress", "completed"
    completed_at: Optional[datetime] = None


@dataclass
class PersonalizedStudyPlan:
    """Sequenced study plan tailored to student pace and deadlines."""

    plan_id: str
    student_id: str
    course_id: str
    sessions: List[SessionPlan] = field(default_factory=list)
    target_date: str = ""
    is_exam_ready: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ─── 4. Pedagogical Explanation Dimensions ───────────────────────────────────


@dataclass
class ExplanationDimensions:
    """5-dimensional pedagogical teaching asset."""

    concept_id: str
    concept_title: str
    visual_description: str
    historical_context: str
    analogy: str
    examples: str
    detail_theory: str
    figures: List[Dict[str, Any]] = field(default_factory=list)
    tables: List[Dict[str, Any]] = field(default_factory=list)
    formulas: List[Dict[str, Any]] = field(default_factory=list)


# ─── 5. Formative Assessment & Evaluation ─────────────────────────────────────


@dataclass
class FormativeQuestion:
    """Targeted practice question testing conceptual mastery and pitfalls."""

    question_id: str
    concept_id: str
    prompt: str
    question_type: str = "conceptual"        # "conceptual", "application", "step_problem"
    rubric: str = ""
    common_pitfalls: List[str] = field(default_factory=list)
    hints: List[str] = field(default_factory=list)


@dataclass
class EvaluationResult:
    """Evaluation of student's response with gap diagnosis."""

    is_understood: bool
    score: float                             # 0.0 to 1.0
    diagnosed_gap: Optional[str] = None
    misconception: Optional[str] = None
    feedback: str = ""
    next_action: str = "advance"             # "advance", "remediate", "next_question"


# ─── 6. Adaptive Remediation ──────────────────────────────────────────────────


class RemediationLever(str, Enum):
    """The 5 adaptive remediation modalities from the architecture diagram."""

    ALTERNATIVE_EXPLANATION = "alternative_explanation"
    SIMPLER_ANALOGY = "simpler_analogy"
    VISUALS = "visuals"
    HINT = "hint"
    BREAKDOWN = "breakdown"


@dataclass
class RemediationPackage:
    """Remedial content tailored to fix a specific diagnosed knowledge gap."""

    lever_used: RemediationLever
    content: str
    scaffolding_step: int = 1
    suggested_follow_up: str = ""


# ─── 7. Progress Tracking & Exam Readiness ────────────────────────────────────


@dataclass
class ProgressSnapshot:
    """Live state of student learning progress."""

    retained: List[Dict[str, Any]] = field(default_factory=list)
    in_progress: List[Dict[str, Any]] = field(default_factory=list)
    weak_areas: List[Dict[str, Any]] = field(default_factory=list)
    strengths: List[Dict[str, Any]] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


@dataclass
class ExamReadinessResult:
    """Overall assessment gatekeeper determining exam readiness."""

    is_ready: bool
    readiness_score: float                   # 0.0 to 100.0%
    weak_areas_to_review: List[str] = field(default_factory=list)
    recommendation_summary: str = ""
