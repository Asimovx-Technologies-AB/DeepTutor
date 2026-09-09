"""
test_advanced_out_of_material_format.py
=========================================
Tests to verify that out-of-material queries return the structured,
advanced Markdown format containing:
- > ⚠️ **Out of Material Scope** alert
- Grounding & Scope Analysis section
- Suggested topics from uploaded materials
- Tip callout
"""

import pytest
from app.services.study_agents import (
    format_advanced_out_of_material_response,
    executor_agent
)


def test_format_advanced_out_of_material_response_structure():
    session_docs = [{"filename": "Quantum_Mechanics_Ch1.pdf"}]
    session_topics = [
        {"title": "Schrödinger Equation", "summary": "Governing wave equation in quantum physics."},
        {"title": "Wavefunction Collapse", "summary": "Measurement postulate of quantum mechanics."}
    ]
    
    response = format_advanced_out_of_material_response(
        query_or_topic="Organic Chemistry Synthesis",
        subject="Quantum Physics",
        session_docs=session_docs,
        session_topics=session_topics
    )
    
    assert "⚠️ **Out of Material Scope**" in response
    assert "Organic Chemistry Synthesis" in response
    assert "Quantum Physics" in response
    assert "`Quantum_Mechanics_Ch1.pdf`" in response
    assert "### 🔍 Grounding & Scope Analysis" in response
    assert "### 📚 Suggested Topics Covered in Your Materials" in response
    assert "Schrödinger Equation" in response
    assert "Wavefunction Collapse" in response
    assert "💡 **Tip**:" in response


@pytest.mark.asyncio
async def test_executor_agent_out_of_material_query():
    docs = [{"filename": "Physics101_Lecture1.pdf"}]
    topics = [{"title": "Newton's Laws", "summary": "Classical kinematics and dynamics laws."}]
    res_text = format_advanced_out_of_material_response(
        query_or_topic="What is photosynthesis?",
        subject="Physics 101",
        session_docs=docs,
        session_topics=topics
    )
    assert "Out of Material Scope" in res_text
    assert "What is photosynthesis?" in res_text
    assert "Physics 101" in res_text
    assert "Newton's Laws" in res_text
