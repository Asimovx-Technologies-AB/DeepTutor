"""
Comprehensive End-to-End Test Suite for DeepTutor AI Study Room & GraphRAG Platform.
"""

import pytest
import asyncio
from pathlib import Path
from app.services.study_storage import (
    init_session_db,
    insert_chunks_to_fts,
    search_fts_chunks,
    save_session_message,
    get_session_messages,
    save_session_topics,
    get_session_topics,
    list_registry_sessions,
    register_or_update_session,
    delete_registry_session,
    get_student_memory,
    add_student_memory_fact,
    reset_student_memory,
)
from app.services.study_curriculum import fast_guardrail_check, extract_topics_and_validate
from app.services.study_agents import (
    planner_agent,
    executor_agent,
    generate_core_idea,
    generate_mixed_exam,
    evaluate_exam_submission,
)


@pytest.mark.asyncio
async def test_session_db_and_fts5():
    test_sid = "test_study_sid_123"
    try:
        db_path = init_session_db(test_sid)
        assert db_path.exists()

        chunks = [
            {
                "chunk_id": "c1",
                "page": 1,
                "source_type": "text",
                "content": "Gradient descent minimizes the objective function by taking steps proportional to the negative gradient."
            },
            {
                "chunk_id": "c2",
                "page": 2,
                "source_type": "text",
                "content": "Newton's method uses the Hessian matrix of second-order derivatives to find stationary points."
            }
        ]
        insert_chunks_to_fts(test_sid, "doc_1", chunks)

        # BM25 Search
        res = search_fts_chunks(test_sid, "gradient descent")
        assert len(res) >= 1
        assert "proportional to the negative gradient" in res[0]["content"]

        # Topic CRUD
        topics = [
            {
                "id": "t1",
                "title": "Optimization Basics",
                "summary": "First-order optimization methods",
                "difficulty": "Beginner",
                "key_concepts": ["Gradient", "Step size"],
                "estimated_study_time": "15 mins"
            }
        ]
        save_session_topics(test_sid, topics)
        loaded_topics = get_session_topics(test_sid)
        assert len(loaded_topics) == 1
        assert loaded_topics[0]["title"] == "Optimization Basics"

        # Message CRUD
        save_session_message(test_sid, "m1", "user", "What is gradient descent?")
        save_session_message(test_sid, "m2", "assistant", "Gradient descent is a first-order optimization algorithm.", thought_process="Retrieved chunk c1.")
        msgs = get_session_messages(test_sid)
        assert len(msgs) == 2
        assert msgs[1]["thought_process"] == "Retrieved chunk c1."
    finally:
        delete_registry_session(test_sid)


def test_guardrails():
    # Non-academic resume
    resume_text = "Curriculum Vitae: John Doe. Work experience at Tech Corp. Education history: B.S. in CS."
    ok, cat, reason = fast_guardrail_check(resume_text)
    assert not ok
    assert cat == "PERSONAL"

    # Academic text
    academic_text = "Chapter 4: Linear Algebra and Eigenvalues. Let A be an n-by-n square matrix with eigenvectors v."
    ok, cat, _ = fast_guardrail_check(academic_text)
    assert ok
    assert cat == "STUDY_MATERIAL"


@pytest.mark.asyncio
async def test_planner_and_executor():
    test_sid = "test_planner_sid_456"
    try:
        init_session_db(test_sid)
        insert_chunks_to_fts(test_sid, "doc_opt", [
            {
                "chunk_id": "opt1",
                "page": 1,
                "source_type": "text",
                "content": "Backpropagation computes the gradient of the loss function with respect to the weights of the network."
            }
        ])

        # Planner
        plan = await planner_agent.plan("Explain backpropagation in neural networks", "Machine Learning")
        assert "bm25_queries" in plan
        assert plan.get("confidence", 0) > 0

        # Executor
        exec_res = await executor_agent.execute(
            user_query="Explain backpropagation in neural networks",
            plan=plan,
            session_id=test_sid,
            subject="Machine Learning"
        )
        assert "response" in exec_res
        assert "thought_process" in exec_res
        assert len(exec_res["response"]) > 20
    finally:
        delete_registry_session(test_sid)


@pytest.mark.asyncio
async def test_normal_mode_and_exam():
    test_sid = "test_exam_sid_789"
    try:
        init_session_db(test_sid)
        insert_chunks_to_fts(test_sid, "doc_exam", [
            {
                "chunk_id": "e1",
                "page": 1,
                "source_type": "text",
                "content": "In supervised learning, the model is trained on labeled pairs (x, y) where the loss function measures discrepancy."
            }
        ])

        # Normal Mode Core Idea
        core_idea = await generate_core_idea(test_sid, "t1", "Supervised Learning", "Overview of labeled training.")
        assert "big_picture" in core_idea
        assert "core_principle" in core_idea
        assert "key_takeaways" in core_idea
        assert "common_pitfalls" in core_idea

        # Exam Generation
        exam = await generate_mixed_exam(test_sid, "t1", "Supervised Learning")
        assert "questions" in exam
        assert len(exam["questions"]) >= 3

        # Exam Evaluation
        answers = {q["id"]: "supervised learning minimizes empirical risk" for q in exam["questions"]}
        eval_res = await evaluate_exam_submission(test_sid, "t1", exam["questions"], answers)
        assert "percentage" in eval_res
        assert "mastery_badge" in eval_res
        assert len(eval_res["evaluations"]) == len(exam["questions"])
    finally:
        delete_registry_session(test_sid)


def test_episodic_memory():
    uid = "test_student_user_999"
    try:
        prof = add_student_memory_fact(uid, goal="Master Machine Learning", weakness="Lagrangian duality")
        assert "Master Machine Learning" in prof["goals"]
        assert "Lagrangian duality" in prof["weaknesses"]

        loaded = get_student_memory(uid)
        assert loaded["user_id"] == uid
        assert "Lagrangian duality" in loaded["weaknesses"]
    finally:
        reset_student_memory(uid)
