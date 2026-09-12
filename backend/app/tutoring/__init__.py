"""
DeepTutor Intelligent Tutoring System (ITS) Package.

Modular, pedagogically sound tutoring pipeline:
1. Student Profile & Cognitive Model
2. Course Syllabus & Curriculum Knowledge Map (Prerequisite DAG + Document Assets)
3. Personalized Study Planner (Sequenced Sessions 1..N)
4. Interactive Teaching with 5 Pedagogical Dimensions (Visuals, History, Analogies, Examples, Theory)
5. Formative Assessment & Practice
6. Student Answer Diagnostic Evaluation (UNDERSTAND? decision)
7. Adaptive Remediation (5 Levers: Alt Expl, Simpler Analogy, Visuals, Hint, Breakdown)
8. Mastery Tracking & Exam Readiness Gatekeeper
"""
from app.tutoring.orchestrator import (
    TutoringOrchestrator,
    tutoring_orchestrator,
)

__all__ = [
    "TutoringOrchestrator",
    "tutoring_orchestrator",
]
