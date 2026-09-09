"""
test_unhallucinated_query_reasoning.py
======================================
Tests to ensure queries in empty workspaces do NOT hallucinate fake subjects (e.g. 'The Topic')
and that the LLM performs step-by-step reasoning for user queries.
"""
import pytest
from app.services.study_agents import (
    normalize_subject_title,
    extract_subject_from_query,
    is_academic_question_or_query,
    executor_agent
)


def test_normalize_subject_title_filters_generic_phrases():
    assert normalize_subject_title("what is the topic") == "General Study"
    assert normalize_subject_title("the topic") == "General Study"
    assert normalize_subject_title("this topic") == "General Study"
    assert normalize_subject_title("current subject") == "General Study"
    assert normalize_subject_title("machine learning") == "Machine Learning"
    assert normalize_subject_title("ml") == "Machine Learning"


def test_is_academic_question_or_query():
    assert is_academic_question_or_query("what is the topic") is True
    assert is_academic_question_or_query("what is physics?") is True
    assert is_academic_question_or_query("explain calculus") is True
    assert is_academic_question_or_query("Machine Learning") is False


@pytest.mark.asyncio
async def test_executor_agent_empty_workspace_meta_query():
    result = await executor_agent.execute(
        user_query="what is the topic",
        plan={"confidence": 0.9},
        session_id="test_empty_session_123",
        user_id="test_user",
        subject="General Study"
    )
    assert "The Topic" not in result["response"]
    assert "Welcome to **The Topic**" not in result["response"]
    assert result["thought_process"] != ""


def test_is_material_topics_query_detection():
    from app.services.study_agents import is_material_topics_query
    # Exact and fuzzy typo checks
    assert is_material_topics_query("what is the topic for the meterial") is True
    assert is_material_topics_query("topic for the meterial") is True
    assert is_material_topics_query("what is the topic for the material") is True
    assert is_material_topics_query("topics in this material") is True
    assert is_material_topics_query("what are the topics in this material?") is True
    assert is_material_topics_query("list the topics in this pdf") is True
    assert is_material_topics_query("what does this document cover?") is True
    assert is_material_topics_query("what can i learn from this material?") is True
    assert is_material_topics_query("syllabus of this material") is True

    # Standard conceptual questions should NOT match
    assert is_material_topics_query("what is svm ?") is False
    assert is_material_topics_query("how does kernel trick work") is False
    assert is_material_topics_query("difference between knn and svm") is False


@pytest.mark.asyncio
async def test_planner_agent_plans_material_topics():
    from app.services.study_agents import planner_agent
    plan = await planner_agent.plan("what is the topic for the meterial", subject="Machine Learning")
    assert plan.get("response_format") == "material_topics"
    assert plan.get("is_material_topics_query") is True


@pytest.mark.asyncio
async def test_executor_agent_material_topics_with_session_topics(monkeypatch):
    from app.services import study_agents

    # Mock session documents and topics
    monkeypatch.setattr(
        study_agents,
        "get_session_documents",
        lambda sid: [{"id": "doc_1", "filename": "Machine_Learning_Fundamentals.pdf"}]
    )
    monkeypatch.setattr(
        study_agents,
        "get_session_topics",
        lambda sid: [
            {
                "id": "t1",
                "title": "1. Introduction to Supervised Learning",
                "summary": "Core concepts of labeled datasets and models.",
                "difficulty": "beginner",
                "key_concepts": ["Regression", "Classification", "Loss"]
            },
            {
                "id": "t2",
                "title": "2. Support Vector Machines",
                "summary": "Hyperplanes and maximal margin classification.",
                "difficulty": "intermediate",
                "key_concepts": ["Hyperplane", "Support Vectors", "Kernel Trick"]
            }
        ]
    )
    monkeypatch.setattr(
        study_agents,
        "get_all_chunks",
        lambda sid, limit=8: [{"chunk_id": "c1", "page": 1, "content": "Sample content"}]
    )

    plan = {"response_format": "material_topics", "is_material_topics_query": True}
    result = await study_agents.executor_agent.execute(
        user_query="what is the topic for the meterial",
        plan=plan,
        session_id="session_with_topics",
        subject="Machine Learning"
    )

    resp = result["response"]
    # Verify professional, structured response
    assert "Machine_Learning_Fundamentals.pdf" in resp
    assert "| # | Topic | Key Focus & Concepts | Difficulty |" in resp
    assert "Introduction to Supervised Learning" in resp
    assert "Support Vector Machines" in resp
    assert "Beginner" in resp
    assert "Intermediate" in resp
    # Verify closing question
    assert "Would you like to start with Topic 1" in resp
    # Verify zero emojis
    assert "⚠️" not in resp
    assert "📌" not in resp
    assert "💡" not in resp
    assert "Out of Material Scope" not in resp
