import pytest
from app.models.document import Document
from app.models.session import StudySession, CurriculumTopic
from app.api.study import (
    evaluate_topic_exam,
    export_notes_markdown,
    get_student_memory,
    add_student_memory_fact,
    clear_student_memory,
    start_lecture_diagnostic,
    submit_lecture_diagnostic,
    pause_lecture_and_ask,
    get_teach_back_prompt,
    submit_teach_back,
    generate_lecture_checkpoint,
    submit_lecture_checkpoint
)


def test_exam_evaluation_flow(db_session):
    """Tests the automated scoring and feedback engine for Learn Page topic exams."""
    sess = StudySession(id="sess-exam-1", title="ML Exam", subject="ML")
    topic = CurriculumTopic(id="top-exam-1", session_id=sess.id, title="SVM", mastered=False)
    db_session.add(sess)
    db_session.add(topic)
    db_session.commit()

    questions = [
        {
            "id": "q1",
            "question": "What does SVM maximize?",
            "options": ["The geometric margin", "The loss function", "The training time", "The noise"],
            "correct_index": 0,
            "explanation": "SVM finds the maximum margin hyperplane."
        },
        {
            "id": "q2",
            "question": "What are support vectors?",
            "options": ["Random points", "Points on the margin boundary", "Outliers only", "Hyperplane weights"],
            "correct_index": 1,
            "explanation": "Support vectors lie directly on the margin."
        }
    ]

    # Student answers both correctly
    eval_res = evaluate_topic_exam(
        payload={
            "session_id": sess.id,
            "topic_id": topic.id,
            "questions": questions,
            "answers": {"q1": "The geometric margin", "q2": "Points on the margin boundary"}
        },
        db=db_session
    )

    assert eval_res["status"] == "success"
    assert eval_res["total_questions"] == 2
    assert eval_res["score"] == 2
    assert eval_res["percentage"] == 100.0
    assert eval_res["mastery_level"] == "Advanced Mastery"
    assert eval_res["evaluations"][0]["is_correct"] is True
    assert eval_res["evaluations"][1]["is_correct"] is True

    # Check that topic was automatically marked mastered
    updated_topic = db_session.query(CurriculumTopic).filter(CurriculumTopic.id == topic.id).first()
    assert updated_topic.mastered is True


def test_notes_markdown_export():
    """Tests exporting synthesized study notes as a downloadable Markdown blob."""
    md_text = "# Socratic Study Notes\n\n## Core Concept\n- Maximum margin hyperplane\n"
    response = export_notes_markdown(payload={"markdown": md_text, "title": "SVM Study Guide"})
    
    assert response.status_code == 200
    assert response.media_type == "text/markdown"
    assert "attachment; filename=\"svm_study_guide.md\"" in response.headers["Content-Disposition"]
    assert b"Maximum margin hyperplane" in response.body


def test_student_memory_lifecycle():
    """Tests the student long-term memory retrieval, addition, and clearing."""
    uid = "test-student-42"
    clear_student_memory(user_id=uid)

    # Initial fetch
    mem = get_student_memory(user_id=uid)
    assert mem["user_id"] == uid

    # Add a learned fact
    add_student_memory_fact(user_id=uid, fact_data={"fact": "Prefers step-by-step calculus derivations"})
    updated = get_student_memory(user_id=uid)
    assert "Prefers step-by-step calculus derivations" in updated["facts"]

    # Clear memory
    clear_student_memory(user_id=uid)
    cleared = get_student_memory(user_id=uid)
    assert "Prefers step-by-step calculus derivations" not in cleared["facts"]


def test_teacher_mode_suite(db_session):
    """Tests the interactive teacher mode suite: diagnostic, pause & ask, checkpoint, and teach-back."""
    sess = StudySession(id="sess-teach-1", title="Lecture Workspace", subject="Physics")
    db_session.add(sess)
    db_session.commit()

    # 1. Start Diagnostic
    diag_start = start_lecture_diagnostic(
        payload={"session_id": sess.id, "topic_title": "Quantum Mechanics"},
        db=db_session
    )
    assert diag_start["status"] == "success"
    assert "lecture_id" in diag_start
    assert len(diag_start["diagnostic"]["options"]) == 4

    # 2. Submit Diagnostic
    diag_sub = submit_lecture_diagnostic(payload={
        "lecture_id": diag_start["lecture_id"],
        "student_answer": diag_start["diagnostic"]["options"][0]
    })
    assert diag_sub["status"] == "success"
    assert diag_sub["level"] == "standard"

    # 3. Checkpoint generate & submit
    chk = generate_lecture_checkpoint(payload={"topic_title": "Quantum Mechanics", "phase_name": "Wavefunctions"})
    assert chk["status"] == "success"
    assert len(chk["options"]) == 4

    chk_sub = submit_lecture_checkpoint(payload={"student_response": "0"})
    assert chk_sub["is_correct"] is True

    # 4. Teach-Back prompt & submit
    tb_prompt = get_teach_back_prompt(payload={"topic_title": "Quantum Mechanics", "lecture_id": diag_start["lecture_id"]})
    assert tb_prompt["status"] == "success"
    assert "prompt" in tb_prompt

    tb_sub = submit_teach_back(payload={
        "lecture_id": diag_start["lecture_id"],
        "topic_title": "Quantum Mechanics",
        "submission_text": "Quantum mechanics describes particles as probability wavefunctions where the square of the amplitude represents the probability density."
    })
    assert tb_sub["status"] == "success"
    assert tb_sub["evaluation"]["score"] >= 90
    assert tb_sub["evaluation"]["grade"] == "Mastery"
