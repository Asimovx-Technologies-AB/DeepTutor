import pytest
from app.tutoring.curriculum.synthesizer import CurriculumSynthesizer


def test_fallback_curriculum_synthesis():
    doc_title = "Introduction to Deep Learning"
    chunks = [
        {"content": "Supervised learning trains models on labeled datasets.", "topic": "Supervised Learning", "page_number": 1},
        {"content": "Neural networks use backpropagation and gradient descent.", "topic": "Neural Networks", "page_number": 5},
        {"content": "Convolutional networks are ideal for computer vision.", "topic": "Computer Vision", "page_number": 12},
    ]
    toc = ["Chapter 1: Supervised Learning", "Chapter 2: Neural Networks", "Chapter 3: Computer Vision"]

    res = CurriculumSynthesizer._fallback_curriculum_synthesis(doc_title, chunks, toc)

    assert res is not None
    assert "important_topics" in res
    assert len(res["important_topics"]) >= 3
    assert res["document_title"] == doc_title
    assert "welcome_briefing_markdown" in res
    assert "Important Topics in" in res["welcome_briefing_markdown"]

    first_topic = res["important_topics"][0]
    assert "title" in first_topic
    assert "summary" in first_topic
    assert "difficulty" in first_topic
    assert "suggested_question" in first_topic


def test_curriculum_synthesizer_interface():
    doc_title = "Modern Operating Systems"
    chunks = [
        {"content": "Process scheduling algorithms include Round Robin and Priority scheduling.", "topic": "Process Scheduling", "page_number": 3},
        {"content": "Virtual memory management uses paging and segmentation.", "topic": "Virtual Memory", "page_number": 8},
    ]

    res = CurriculumSynthesizer.synthesize_curriculum(doc_title, chunks, ["Processes", "Memory Management"])
    assert res is not None
    assert len(res["important_topics"]) >= 2
    assert res["recommended_starting_topic"] is not None
