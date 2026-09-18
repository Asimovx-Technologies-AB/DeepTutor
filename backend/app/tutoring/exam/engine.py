"""
Exam Session Manager & Report Engine
=====================================
Manages structured exam state (session_metadata["exam_session"]),
answer evaluation, and deterministic exam report generation.

All exam analytics are computed from stored state, never from LLM
conversation history.
"""

import re
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple
from sqlalchemy.orm import Session as DbSession
from app.models.session import StudySession

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exam-report intent detection (deterministic, regex-first)
# ---------------------------------------------------------------------------

_EXAM_REPORT_PATTERNS = [
    re.compile(r"\b(?:exam\s+report|my\s+report|my\s+exam\s+report|show\s+(?:my\s+)?(?:exam\s+)?report)\b", re.IGNORECASE),
    re.compile(r"\b(?:analyze\s+my\s+(?:response|exam|answers?|performance|result))\b", re.IGNORECASE),
    re.compile(r"\b(?:give\s+me\s+(?:a\s+|my\s+)?(?:exam\s+)?report)\b", re.IGNORECASE),
    re.compile(r"\b(?:how\s+did\s+i\s+(?:perform|do)|my\s+(?:performance|score|result|marks))\b", re.IGNORECASE),
    re.compile(r"\b(?:what\s+is\s+my\s+score|show\s+my\s+performance|my\s+exam\s+result)\b", re.IGNORECASE),
    re.compile(r"\b(?:i\s+want\s+(?:my\s+)?exam\s+report)\b", re.IGNORECASE),
    re.compile(r"\b(?:give\s+me\s+my\s+exam\s+result)\b", re.IGNORECASE),
]


def is_exam_report_intent(raw_query: str) -> bool:
    """Fast deterministic check for exam-report requests."""
    q = raw_query.strip()
    return any(p.search(q) for p in _EXAM_REPORT_PATTERNS)


# ---------------------------------------------------------------------------
# Exam-start intent detection (deterministic, regex-first)
# ---------------------------------------------------------------------------

_EXAM_START_PATTERNS = [
    re.compile(r"\b(?:make|create|generate|start|conduct|take|give\s+me|set\s+up)\s+(?:me\s+)?(?:an?\s+)?(?:written\s+|theory\s+|subjective\s+|descriptive\s+)?exam\b", re.IGNORECASE),
    re.compile(r"\b(?:exam\s+for\s+me|test\s+me\s+with\s+(?:an?\s+)?exam)\b", re.IGNORECASE),
    re.compile(r"\b(?:give\s+me\s+\d+\s+questions?\s+(?:in\s+)?one\s+by\s+one)\b", re.IGNORECASE),
    re.compile(r"\b(?:one\s+by\s+one\s+exam|exam\s+(?:in\s+)?one\s+by\s+one)\b", re.IGNORECASE),
    re.compile(r"\b(?:start\s+exam|take\s+(?:an?\s+)?exam|exam\s+mode)\b", re.IGNORECASE),
    re.compile(r"\b(?:conduct\s+(?:an?\s+)?exam)\b", re.IGNORECASE),
    re.compile(r"\b(?:make|create|generate|start|conduct)\s+(?:an?\s+)?(?:exam|test)\s+(?:on|with|for)\s+\d+\s+questions?\b", re.IGNORECASE),
    re.compile(r"\b(?:exam\s+on\s+\d+\s+questions?|exam\s+with\s+\d+\s+questions?)\b", re.IGNORECASE),
    re.compile(r"\b(?:written\s+exam|theory\s+exam|subjective\s+exam|descriptive\s+exam|essay\s+exam)\b", re.IGNORECASE),
    re.compile(r"\b(?:i\s+)?(?:dont|don't)\s+want\s+(?:a\s+)?quiz.*(?:written\s+exam|exam)\b", re.IGNORECASE),
    re.compile(r"\b(?:want|give\s+me)\s+(?:a\s+)?written\s+exam\b", re.IGNORECASE),
]


def is_exam_start_intent(raw_query: str) -> bool:
    """Deterministic check for requests to start an interactive exam."""
    q = raw_query.strip().lower()
    # Explicit override when student says "not a quiz" or "dont want quiz" and asks for questions/exam/written exam
    if any(nq in q for nq in ["not a quiz", "not quiz", "no quiz", "dont want quiz", "don't want quiz", "no mcq", "not mcq"]) and ("exam" in q or "question" in q or "test" in q):
        return True
    if any(we in q for we in ["written exam", "theory exam", "subjective exam", "descriptive exam", "essay exam"]):
        return True
    return any(p.search(raw_query) for p in _EXAM_START_PATTERNS)


def extract_exam_params(raw_query: str, default_topic: Optional[str] = None) -> Dict[str, Any]:
    """Extract requested question count, topic, and exam type from student prompt."""
    q_lower = raw_query.strip().lower()
    exam_type = "mcq"
    if any(k in q_lower for k in [
        "written exam", "written test", "theory exam", "subjective exam",
        "descriptive exam", "essay exam", "open ended", "open-ended",
        "no mcq", "not mcq", "written question", "written questions",
        "subjective question", "subjective questions"
    ]) or re.search(r"\b(?:dont|don't)\s+want\s+(?:a\s+)?quiz.*(?:written|essay|theory|subjective)\b", q_lower):
        exam_type = "written"

    count = 3
    count_match = re.search(r"\b(\d+)\s*(?:questions?|items?|mcqs?)\b", raw_query, re.IGNORECASE)
    if count_match:
        try:
            count = max(1, min(int(count_match.group(1)), 10))
        except (ValueError, TypeError):
            count = 3

    topic = None
    for pattern in [
        r"\b(?:exam|questions?)\s+(?:on|about|for|regarding|in)\s+([^,.\n]+)",
        r"\b(?:on|about|for)\s+([a-zA-Z0-9_\s-]+?)(?:\s+(?:give|with|in|after|exam|\b)|$)",
    ]:
        m = re.search(pattern, raw_query, re.IGNORECASE)
        if m and m.group(1):
            cand = m.group(1).strip()
            cand = re.sub(r"\b(?:please|pls|give me|make|now|quick|fast|thanks|me|a|an|one by one|written|exam)\b", "", cand, flags=re.IGNORECASE).strip()
            # If cand is purely numbers or numbers + questions (e.g. "3 questions"), it is NOT a topic name
            if re.match(r"^\d+\s*(?:questions?|items?|mcqs?)?$", cand, re.IGNORECASE):
                continue
            if len(cand) > 2 and cand.lower() not in ("me", "this", "it", "one by one", "the document", "the material", "not a quiz"):
                topic = cand
                break

    if not topic and default_topic:
        topic = default_topic

    return {
        "question_count": count,
        "topic": topic or "Core Assessment",
        "exam_type": exam_type,
    }


# ---------------------------------------------------------------------------
# ExamQuestionGenerator
# ---------------------------------------------------------------------------

class ExamQuestionGenerator:
    """
    Generates grounded multiple-choice exam questions with exactly 4 options
    and a clear correct answer.
    """

    SYSTEM_PROMPT = """You are DeepTutor, generating a rigorous, grounded academic concept exam.
Output STRICT JSON matching this schema:
{
  "questions": [
    {
      "question": "Clear, direct conceptual question grounded strictly in the material",
      "options": ["Option A text", "Option B text", "Option C text", "Option D text"],
      "correct_answer": "Option text matching one of the options exactly",
      "explanation": "Brief 1-sentence pedagogical explanation of why this option is correct"
    }
  ]
}
Rules:
1. Provide exactly 4 options per question.
2. The correct_answer string must match one of the 4 options verbatim.
3. Questions must test conceptual understanding, definitions, or mechanisms from the topic.
4. Return ONLY valid JSON, no markdown codeblocks or conversational text.
"""

    WRITTEN_SYSTEM_PROMPT = """You are DeepTutor, generating a rigorous, grounded academic written exam.
Create open-ended, analytical, or descriptive questions that require the student to explain, derive, compare, or articulate principles in words.

Output STRICT JSON matching this schema:
{
  "questions": [
    {
      "question": "Clear, direct descriptive/analytical question grounded strictly in the material",
      "reference_answer": "Complete, exemplary model answer explaining the concept accurately",
      "rubric_points": ["Key concept 1 that must be mentioned", "Key concept 2", "Key concept 3"],
      "max_marks": 5
    }
  ]
}
RULES:
1. Do NOT generate multiple-choice options. Leave options empty.
2. Formulate questions that test deep conceptual understanding, architectural reasoning, or mathematical intuition.
3. Keep questions focused directly on the topic.
4. Return ONLY valid JSON, no markdown codeblocks or conversational text.
"""

    @classmethod
    def generate(
        cls,
        topic: str,
        retrieved_chunks: List[Dict[str, Any]],
        question_count: int = 3,
        exam_type: str = "mcq",
    ) -> List[Dict[str, Any]]:
        if exam_type == "written":
            return cls.generate_written(topic, retrieved_chunks, question_count)

        from app.services.llm_service import default_llm_service
        import json

        context_text = ""
        for idx, chunk in enumerate(retrieved_chunks[:6], 1):
            text = chunk.get("content") or chunk.get("text") or ""
            context_text += f"\n[Excerpt {idx}]:\n{text[:1200]}\n"

        prompt = (
            f"Topic: {topic}\n"
            f"Required Questions: {question_count}\n\n"
            f"Reference Material:\n{context_text if context_text.strip() else 'Core topic principles and standard academic formulations.'}\n\n"
            f"Generate exactly {question_count} multiple-choice exam questions in JSON format."
        )

        try:
            raw_response = default_llm_service.generate(prompt, cls.SYSTEM_PROMPT)
            if raw_response:
                clean_json = raw_response.strip()
                if "```json" in clean_json:
                    clean_json = clean_json.split("```json")[1].split("```")[0].strip()
                elif "```" in clean_json:
                    clean_json = clean_json.split("```")[1].split("```")[0].strip()
                data = json.loads(clean_json)
                q_list = data.get("questions", [])
                validated = []
                for q in q_list:
                    opts = q.get("options", [])
                    if len(opts) >= 2 and q.get("question") and q.get("correct_answer"):
                        validated.append({
                            "question": q["question"],
                            "options": opts[:4],
                            "correct_answer": q["correct_answer"],
                            "reference_answer": q["correct_answer"],
                            "topic": topic,
                            "max_marks": 1,
                            "question_type": "mcq",
                        })
                if len(validated) >= 1:
                    return validated[:question_count]
        except Exception as err:
            logger.warning("ExamQuestionGenerator LLM call failed or parsed invalid JSON: %s", err)

        # High quality fallback questions
        fallback = [
            {
                "question": f"Which of the following best captures the foundational principle of {topic}?",
                "options": [
                    f"Direct computational transformation specific to {topic}",
                    f"Arbitrary heuristic scoring independent of {topic}",
                    "Static unparameterized memory lookups without optimization",
                    "Random gradient perturbation without objective loss"
                ],
                "correct_answer": f"Direct computational transformation specific to {topic}",
                "reference_answer": f"Direct computational transformation specific to {topic}",
                "topic": topic,
                "max_marks": 1,
                "question_type": "mcq",
            },
            {
                "question": f"What primary advantage does {topic} provide compared to conventional baselines?",
                "options": [
                    "Enhanced structural efficiency and targeted representation learning",
                    "Elimination of all training dependencies and parameters",
                    "Exponential compute complexity with identical outputs",
                    "Restriction to single-dimensional non-differentiable signals"
                ],
                "correct_answer": "Enhanced structural efficiency and targeted representation learning",
                "reference_answer": "Enhanced structural efficiency and targeted representation learning",
                "topic": topic,
                "max_marks": 1,
                "question_type": "mcq",
            },
            {
                "question": f"When implementing or analyzing {topic}, which factor requires primary validation?",
                "options": [
                    "Consistent convergence and alignment with theoretical guarantees",
                    "Disregard of all training loss and error gradients",
                    "Strict exclusion of validation metrics during evaluation",
                    "Bypassing data normalization without tracking drift"
                ],
                "correct_answer": "Consistent convergence and alignment with theoretical guarantees",
                "reference_answer": "Consistent convergence and alignment with theoretical guarantees",
                "topic": topic,
                "max_marks": 1,
                "question_type": "mcq",
            }
        ]
        return fallback[:question_count]

    @classmethod
    def generate_written(
        cls,
        topic: str,
        retrieved_chunks: List[Dict[str, Any]],
        question_count: int = 3,
    ) -> List[Dict[str, Any]]:
        from app.services.llm_service import default_llm_service
        import json

        context_text = ""
        for idx, chunk in enumerate(retrieved_chunks[:6], 1):
            text = chunk.get("content") or chunk.get("text") or ""
            context_text += f"\n[Excerpt {idx}]:\n{text[:1200]}\n"

        prompt = (
            f"Topic: {topic}\n"
            f"Required Questions: {question_count}\n\n"
            f"Reference Material:\n{context_text if context_text.strip() else 'Core topic principles and standard academic formulations.'}\n\n"
            f"Generate exactly {question_count} open-ended descriptive/written exam questions in JSON format."
        )

        try:
            raw_response = default_llm_service.generate(prompt, cls.WRITTEN_SYSTEM_PROMPT)
            if raw_response:
                clean_json = raw_response.strip()
                if "```json" in clean_json:
                    clean_json = clean_json.split("```json")[1].split("```")[0].strip()
                elif "```" in clean_json:
                    clean_json = clean_json.split("```")[1].split("```")[0].strip()
                data = json.loads(clean_json)
                q_list = data.get("questions", [])
                validated = []
                for q in q_list:
                    if q.get("question"):
                        ref = q.get("reference_answer") or q.get("correct_answer") or f"Comprehensive explanation of {topic}."
                        rubric = q.get("rubric_points", ["Conceptual accuracy", "Key mechanisms", "Practical significance"])
                        validated.append({
                            "question": q["question"],
                            "options": [],
                            "correct_answer": ref,
                            "reference_answer": ref,
                            "rubric_points": rubric,
                            "topic": topic,
                            "max_marks": q.get("max_marks", 5),
                            "question_type": "written",
                        })
                if len(validated) >= 1:
                    return validated[:question_count]
        except Exception as err:
            logger.warning("ExamQuestionGenerator generate_written failed: %s", err)

        # High-quality fallback written questions
        fallback = [
            {
                "question": f"Explain the foundational mechanism and conceptual architecture of {topic}. What key challenge does it address, and how does it function step by step?",
                "options": [],
                "correct_answer": f"A comprehensive explanation of {topic} covering its core mechanism, mathematical/logical formulation, and primary advantage over baseline approaches.",
                "reference_answer": f"{topic} addresses representation and processing limitations by applying structured transformations to input data, ensuring targeted alignment and robust generalization.",
                "rubric_points": ["Core definition and principle", "Underlying mechanism/operations", "Primary advantages and practical significance"],
                "topic": topic,
                "max_marks": 5,
                "question_type": "written",
            },
            {
                "question": f"Analyze the constituent components and operational workflow of {topic}. How do its elements interact during execution?",
                "options": [],
                "correct_answer": f"Detailed step-by-step description of {topic}'s internal components, their computational dependencies, and output formulation.",
                "reference_answer": f"The constituent elements of {topic} process inputs through parameterized stages, projecting representations into target spaces and combining signals via normalized weightings.",
                "rubric_points": ["Component identification", "Step-by-step interaction", "Output synthesis"],
                "topic": topic,
                "max_marks": 5,
                "question_type": "written",
            },
            {
                "question": f"Discuss the design trade-offs, potential failure modes, and practical considerations when implementing {topic}.",
                "options": [],
                "correct_answer": f"Analysis of computational complexity, stability, hyperparameter sensitivity, and mitigation strategies for {topic}.",
                "reference_answer": f"Key trade-offs include memory overhead and computational cost, which are balanced through scaling, regularization, and dimension reduction.",
                "rubric_points": ["Trade-off analysis", "Bottlenecks or failure modes", "Optimization/mitigation strategies"],
                "topic": topic,
                "max_marks": 5,
                "question_type": "written",
            },
        ]
        return fallback[:question_count]


# ---------------------------------------------------------------------------
# ExamSessionManager
# ---------------------------------------------------------------------------

class ExamSessionManager:
    """
    Manages the structured exam session stored in
    ``StudySession.session_metadata["exam_session"]``.
    """

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    @classmethod
    def get_active_exam(cls, db: DbSession, session_id: str) -> Optional[Dict[str, Any]]:
        """Return the active (in_progress) exam session, or None."""
        exam = cls._load_exam(db, session_id)
        if exam and exam.get("status") == "in_progress":
            return exam
        return None

    @classmethod
    def get_latest_exam(cls, db: DbSession, session_id: str) -> Optional[Dict[str, Any]]:
        """Return the latest exam session (active or completed), or None."""
        return cls._load_exam(db, session_id)

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    @classmethod
    def save_exam_session(cls, db: DbSession, session_id: str, exam_dict: Dict[str, Any]) -> None:
        """Persist exam session dict into session_metadata."""
        sess = db.query(StudySession).filter(StudySession.id == session_id).first()
        if not sess:
            logger.warning("save_exam_session: session %s not found", session_id)
            return
        meta = dict(sess.session_metadata or {})
        meta["exam_session"] = exam_dict
        sess.session_metadata = meta
        try:
            db.commit()
        except Exception as err:
            db.rollback()
            logger.error("Failed to persist exam session: %s", err)

    @classmethod
    def create_exam_session(
        cls,
        db: DbSession,
        session_id: str,
        subject: str,
        topic: str,
        questions: List[Dict[str, Any]],
        exam_type: str = "mcq",
    ) -> Dict[str, Any]:
        """
        Create a new exam session from a list of question dicts.

        Each question dict should contain at minimum:
            question, options, correct_answer
        Optional: topic, subtopic, max_marks, reference_answer, rubric_points, question_type
        """
        exam_questions = []
        for idx, q in enumerate(questions, 1):
            q_type = q.get("question_type", ("written" if exam_type == "written" else "mcq"))
            ref_ans = q.get("reference_answer") or q.get("correct_answer") or ""
            exam_questions.append({
                "question_id": str(uuid.uuid4()),
                "question_index": idx,
                "question": q.get("question", ""),
                "options": q.get("options", []),
                "correct_answer": q.get("correct_answer", ref_ans),
                "reference_answer": ref_ans,
                "rubric_points": q.get("rubric_points", []),
                "question_type": q_type,
                "user_answer": None,
                "feedback": None,
                "is_correct": None,
                "marks": 0,
                "max_marks": q.get("max_marks", (5 if q_type == "written" else 1)),
                "topic": q.get("topic", topic),
                "subtopic": q.get("subtopic", ""),
            })

        exam = {
            "exam_id": str(uuid.uuid4()),
            "exam_type": exam_type,
            "subject": subject,
            "topic": topic,
            "questions": exam_questions,
            "total_questions": len(exam_questions),
            "current_question_index": 1,
            "attempted_questions": 0,
            "correct_answers": 0,
            "incorrect_answers": 0,
            "unanswered_questions": len(exam_questions),
            "total_marks": sum(q["max_marks"] for q in exam_questions),
            "obtained_marks": 0,
            "percentage": 0.0,
            "accuracy": 0.0,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "status": "in_progress",
        }
        cls.save_exam_session(db, session_id, exam)
        return exam

    # ------------------------------------------------------------------
    # Answer handling
    # ------------------------------------------------------------------

    @classmethod
    def submit_answer(
        cls,
        db: DbSession,
        session_id: str,
        user_answer_text: str,
    ) -> Dict[str, Any]:
        """
        Evaluate the user's answer against the current exam question.

        Returns a dict with:
            result, question, correct_answer, reference_answer, user_answer,
            is_correct, marks, feedback, next_question (or None if exam is done),
            exam_status, score_so_far, question_type
        """
        exam = cls.get_active_exam(db, session_id)
        if not exam:
            return {"error": "no_active_exam", "message": "There is no active exam to submit an answer for."}

        current_idx = exam.get("current_question_index", 1)
        questions = exam.get("questions", [])

        # Find current question (1-based index)
        current_q = None
        for q in questions:
            if q.get("question_index") == current_idx:
                current_q = q
                break

        if not current_q:
            return {"error": "question_not_found", "message": f"Question {current_idx} not found in exam."}

        # Evaluate answer (branch on written vs MCQ)
        q_type = current_q.get("question_type", "mcq")
        is_written = q_type == "written" or exam.get("exam_type") == "written"

        if is_written:
            is_correct, marks, feedback = cls._evaluate_written_answer(user_answer_text, current_q)
        else:
            is_correct = cls._evaluate_answer(user_answer_text, current_q)
            marks = current_q["max_marks"] if is_correct else 0
            feedback = "Correct! Well done." if is_correct else f"Incorrect. The correct answer is: {current_q.get('correct_answer', '')}"

        # Update question state
        current_q["user_answer"] = user_answer_text
        current_q["is_correct"] = is_correct
        current_q["marks"] = marks
        current_q["feedback"] = feedback

        # Update exam aggregates
        exam["attempted_questions"] += 1
        exam["unanswered_questions"] = max(0, exam["unanswered_questions"] - 1)
        if is_correct:
            exam["correct_answers"] += 1
        else:
            exam["incorrect_answers"] += 1
        exam["obtained_marks"] += marks

        total_marks = exam["total_marks"] or 1
        exam["percentage"] = round((exam["obtained_marks"] / total_marks) * 100, 1)
        attempted = exam["attempted_questions"] or 1
        exam["accuracy"] = round((exam["correct_answers"] / attempted) * 100, 1)

        # Advance to next question or complete
        next_question = None
        if current_idx < exam["total_questions"]:
            exam["current_question_index"] = current_idx + 1
            for q in questions:
                if q.get("question_index") == current_idx + 1:
                    next_question = q
                    break
        else:
            exam["status"] = "completed"
            exam["completed_at"] = datetime.now(timezone.utc).isoformat()

        cls.save_exam_session(db, session_id, exam)

        return {
            "result": "correct" if is_correct else "incorrect",
            "question": current_q["question"],
            "correct_answer": current_q["correct_answer"],
            "reference_answer": current_q.get("reference_answer", current_q["correct_answer"]),
            "feedback": feedback,
            "user_answer": user_answer_text,
            "is_correct": is_correct,
            "marks": marks,
            "max_marks": current_q["max_marks"],
            "next_question": next_question,
            "exam_status": exam["status"],
            "score_so_far": f"{exam['obtained_marks']}/{exam['total_marks']}",
            "question_type": q_type,
        }

    # ------------------------------------------------------------------
    # Report generation
    # ------------------------------------------------------------------

    @classmethod
    def generate_exam_report(cls, exam: Dict[str, Any]) -> str:
        """
        Generate a comprehensive markdown exam report from structured state.
        Uses ONLY stored exam data, never invents performance data.
        """
        questions = exam.get("questions", [])
        total = exam.get("total_questions", 0)
        attempted = exam.get("attempted_questions", 0)
        correct = exam.get("correct_answers", 0)
        incorrect = exam.get("incorrect_answers", 0)
        unanswered = exam.get("unanswered_questions", 0)
        obtained = exam.get("obtained_marks", 0)
        total_marks = exam.get("total_marks", 0)
        percentage = exam.get("percentage", 0.0)
        accuracy = exam.get("accuracy", 0.0)
        subject = exam.get("subject", "")
        topic = exam.get("topic", "")
        exam_type = exam.get("exam_type", "mcq")
        exam_label = "Written Exam" if exam_type == "written" else "Exam"

        lines = [
            f"# 📊 {exam_label} Report: {topic or subject or 'Assessment'}",
            "",
            "## Overall Performance",
            f"- **Score**: {obtained} / {total_marks}",
            f"- **Percentage**: {percentage}%",
            f"- **Accuracy**: {accuracy}%",
            f"- **Questions Attempted**: {attempted} / {total}",
            f"- **Correct**: ✅ {correct}",
            f"- **Incorrect**: ❌ {incorrect}",
            f"- **Unanswered**: ⬜ {unanswered}",
            "",
        ]

        # Question-wise Analysis
        lines.append("## Question-wise Analysis")
        lines.append("")
        for q in questions:
            idx = q.get("question_index", "?")
            is_q_written = q.get("question_type") == "written" or exam_type == "written"
            result_icon = "✅" if q.get("is_correct") else ("❌" if q.get("user_answer") is not None else "⬜")
            
            if is_q_written:
                lines.append(f"### Question {idx} (Written)")
                lines.append(f"**Q**: {q.get('question', '')}")
                if q.get("user_answer") is not None:
                    lines.append(f"- **Your Written Answer**:\n  > {q['user_answer']}")
                else:
                    lines.append("- **Your Written Answer**: *(not attempted)*")
                if q.get("feedback"):
                    lines.append(f"- **Examiner Feedback**: {q['feedback']}")
                lines.append(f"- **Model Reference Answer**:\n  > {q.get('reference_answer') or q.get('correct_answer', '')}")
                lines.append(f"- **Marks Awarded**: **{q.get('marks', 0)} / {q.get('max_marks', 5)}** ({result_icon} {'Pass/Good' if q.get('is_correct') else ('Needs Improvement' if q.get('user_answer') is not None else 'Unanswered')})")
                lines.append("")
            else:
                lines.append(f"### Question {idx}")
                lines.append(f"**Q**: {q.get('question', '')}")
                if q.get("user_answer") is not None:
                    lines.append(f"- **Your Answer**: {q['user_answer']}")
                else:
                    lines.append("- **Your Answer**: *(not attempted)*")
                lines.append(f"- **Correct Answer**: {q.get('correct_answer', '')}")
                lines.append(f"- **Result**: {result_icon} {'Correct' if q.get('is_correct') else ('Incorrect' if q.get('user_answer') is not None else 'Unanswered')}")
                lines.append(f"- **Marks**: {q.get('marks', 0)} / {q.get('max_marks', 1)}")
                lines.append("")

        # Topic-wise Performance
        topic_stats: Dict[str, Dict[str, int]] = {}
        for q in questions:
            t = q.get("topic") or q.get("subtopic") or "General"
            if t not in topic_stats:
                topic_stats[t] = {"attempted": 0, "correct": 0, "incorrect": 0, "marks": 0, "max_marks": 0}
            if q.get("user_answer") is not None:
                topic_stats[t]["attempted"] += 1
                if q.get("is_correct"):
                    topic_stats[t]["correct"] += 1
                else:
                    topic_stats[t]["incorrect"] += 1
            topic_stats[t]["marks"] += q.get("marks", 0)
            topic_stats[t]["max_marks"] += q.get("max_marks", 1)

        lines.append("## Topic-wise Performance")
        lines.append("")
        lines.append("| Topic | Attempted | Correct | Incorrect | Accuracy | Marks |")
        lines.append("| :--- | :---: | :---: | :---: | :---: | :---: |")
        for t, s in topic_stats.items():
            t_acc = round((s["correct"] / s["attempted"] * 100), 1) if s["attempted"] > 0 else 0
            lines.append(f"| {t} | {s['attempted']} | {s['correct']} | {s['incorrect']} | {t_acc}% | {s['marks']}/{s['max_marks']} |")
        lines.append("")

        # Mistake / Review Analysis
        mistakes = [q for q in questions if q.get("user_answer") is not None and not q.get("is_correct")]
        lines.append("## Mistake Analysis")
        lines.append("")
        if mistakes:
            for q in mistakes:
                is_q_written = q.get("question_type") == "written" or exam_type == "written"
                if is_q_written:
                    lines.append(f"- **Q{q.get('question_index', '?')}** ({q.get('topic', '')}): Scored {q.get('marks', 0)}/{q.get('max_marks', 5)}. Note: {q.get('feedback', 'Review the model reference answer.')}")
                else:
                    lines.append(f"- **Q{q.get('question_index', '?')}** ({q.get('topic', '')}): You answered \"{q.get('user_answer', '')}\" but the correct answer is \"{q.get('correct_answer', '')}\".")
        else:
            lines.append("🎉 No mistakes — excellent performance across all attempted questions!")
        lines.append("")

        # Strengths
        strong_topics = [t for t, s in topic_stats.items() if s["attempted"] > 0 and (s["correct"] / s["attempted"]) >= 0.7]
        lines.append("## Strengths")
        lines.append("")
        if strong_topics:
            for t in strong_topics:
                lines.append(f"- ✅ **{t}**: Strong performance ({topic_stats[t]['correct']}/{topic_stats[t]['attempted']} passed)")
        else:
            lines.append("- Keep practicing — you'll build strong areas with more attempts.")
        lines.append("")

        # Areas to Improve
        weak_topics = [t for t, s in topic_stats.items() if s["attempted"] > 0 and (s["correct"] / s["attempted"]) < 0.7]
        lines.append("## Areas to Improve")
        lines.append("")
        if weak_topics:
            for t in weak_topics:
                lines.append(f"- 📖 **{t}**: Needs revision ({topic_stats[t]['correct']}/{topic_stats[t]['attempted']} correct)")
        else:
            lines.append("- 🎉 No significant weak areas detected.")
        lines.append("")

        # Recommended Revision
        lines.append("## Recommended Revision")
        lines.append("")
        if weak_topics:
            lines.append("Focus your revision on these topics:")
            for t in weak_topics:
                lines.append(f"1. **{t}** — Review core concepts and practice more questions.")
        elif unanswered > 0:
            lines.append("- Complete all unanswered questions to get a full assessment of your strengths and weaknesses.")
        else:
            lines.append("- 🏆 Excellent! Consider moving on to advanced topics or attempting a more challenging assessment.")
        lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @classmethod
    def _load_exam(cls, db: DbSession, session_id: str) -> Optional[Dict[str, Any]]:
        sess = db.query(StudySession).filter(StudySession.id == session_id).first()
        if not sess or not sess.session_metadata:
            return None
        return sess.session_metadata.get("exam_session")

    @classmethod
    def _evaluate_answer(cls, user_answer: str, question: Dict[str, Any]) -> bool:
        """
        Compare user_answer against the question's correct_answer.
        Supports: exact text match, letter match (A/B/C/D), index match (0/1/2/3).
        """
        correct = question.get("correct_answer", "")
        options = question.get("options", [])
        user_clean = user_answer.strip()

        # Exact text match (case-insensitive)
        if user_clean.lower() == str(correct).strip().lower():
            return True

        # Try numeric match (user typed e.g. "60" matching correct_answer "60")
        try:
            if float(user_clean) == float(str(correct).strip()):
                return True
        except (ValueError, TypeError):
            pass

        # Letter match: user typed "A", "B", "C", "D"
        if len(user_clean) == 1 and user_clean.upper() in "ABCDEFGHIJ":
            letter_idx = ord(user_clean.upper()) - ord("A")
            correct_idx = None
            for i, opt in enumerate(options):
                if str(opt).strip().lower() == str(correct).strip().lower():
                    correct_idx = i
                    break
            if correct_idx is not None and letter_idx == correct_idx:
                return True

        # Index match: user typed "0", "1", "2", "3"
        if user_clean.isdigit():
            idx = int(user_clean)
            correct_idx = None
            for i, opt in enumerate(options):
                if str(opt).strip().lower() == str(correct).strip().lower():
                    correct_idx = i
                    break
            if correct_idx is not None and idx == correct_idx:
                return True

        # Partial match: user answer is contained in correct or vice versa
        if len(user_clean) > 2 and (user_clean.lower() in str(correct).lower() or str(correct).lower() in user_clean.lower()):
            return True

        return False

    @classmethod
    def _evaluate_written_answer(
        cls,
        user_answer: str,
        question: Dict[str, Any],
    ) -> Tuple[bool, int, str]:
        """
        Evaluate a student's written/subjective response against reference answer and rubric.
        Returns (is_correct, marks, feedback).
        """
        from app.services.llm_service import default_llm_service
        import json

        q_text = question.get("question", "")
        ref_text = question.get("reference_answer") or question.get("correct_answer") or ""
        rubric = question.get("rubric_points", [])
        max_marks = question.get("max_marks", 5)

        clean_user = user_answer.strip()
        if not clean_user:
            return False, 0, "No answer provided."

        prompt = (
            f"Question: {q_text}\n"
            f"Reference Model Answer: {ref_text}\n"
            f"Grading Rubric Criteria: {json.dumps(rubric) if rubric else 'Core conceptual accuracy, mechanism explanation, key terms'}\n"
            f"Student Written Answer: {clean_user}\n"
            f"Maximum Marks: {max_marks}\n\n"
            f"Evaluate the student's written answer fairly and constructively based on how well it addresses the rubric criteria.\n"
            f"Return a valid JSON object strictly matching this format:\n"
            f'{{"marks": <integer between 0 and {max_marks}>, "feedback": "<concise constructive feedback in 2 sentences on strengths and omissions>"}}'
        )

        system_prompt = (
            "You are an academic examiner evaluating a student's written response to an exam question. "
            "Be fair, rigorous, and constructive. Return ONLY a valid JSON object."
        )

        try:
            raw = default_llm_service.generate(prompt, system_prompt)
            if raw:
                clean_json = raw.strip()
                if "```json" in clean_json:
                    clean_json = clean_json.split("```json")[1].split("```")[0].strip()
                elif "```" in clean_json:
                    clean_json = clean_json.split("```")[1].split("```")[0].strip()
                data = json.loads(clean_json)
                marks = int(data.get("marks", 0))
                marks = max(0, min(max_marks, marks))
                feedback = data.get("feedback", "Good explanation addressing the prompt.")
                is_correct = marks >= max(1, round(max_marks * 0.5))
                return is_correct, marks, feedback
        except Exception as err:
            logger.warning("Written answer LLM grading failed: %s", err)

        # Heuristic fallback grading if LLM service fails or in offline tests
        words_student = set(re.findall(r"\w+", clean_user.lower()))
        words_ref = set(re.findall(r"\w+", ref_text.lower()))
        stop_words = {"the", "a", "an", "is", "are", "and", "or", "in", "of", "to", "for", "with", "that", "this", "by", "from", "at", "as", "on"}
        sig_ref = words_ref - stop_words
        overlap = words_student & sig_ref
        ratio = len(overlap) / max(len(sig_ref), 1)

        rubric_hits = 0
        for r_pt in rubric:
            pt_words = set(re.findall(r"\w+", r_pt.lower())) - stop_words
            if pt_words and len(words_student & pt_words) >= 1:
                rubric_hits += 1

        rubric_ratio = rubric_hits / max(len(rubric), 1) if rubric else ratio
        score_factor = 0.6 * rubric_ratio + 0.4 * min(1.0, ratio * 1.5)
        marks = int(round(score_factor * max_marks))
        marks = max(1 if len(clean_user) > 20 else 0, min(max_marks, marks))
        is_correct = marks >= max(1, round(max_marks * 0.5))

        if is_correct:
            feedback = f"Good grasp of key concepts. Covered {rubric_hits}/{len(rubric) if rubric else 'key'} criteria with relevant explanation."
        else:
            feedback = "Partial explanation. Covered some points, but missed critical aspects outlined in the reference criteria."

        return is_correct, marks, feedback

