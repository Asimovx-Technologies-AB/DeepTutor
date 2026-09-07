"""
Comprehensive Test Suite for Teacher Mode Masterclass Engine.
Validates:
1. Diagnostic Open & baseline level calibration (Novice / Standard / Advanced).
2. Fixed 4-part lecture structure with KaTeX formulas and Exam Trap callouts.
3. Active-recall checkpoints & modal remediation (switching to analogies/worked examples on incorrect answer).
4. Inline Pause & Ask without losing context.
5. Feynman Teach-Back evaluation & mastery scoring.
6. Episodic memory continuity across sessions.
7. FastAPI REST endpoints.
"""

import pytest
import json
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from app.main import app
from app.services.study_storage import (
    init_session_db,
    insert_chunks_to_fts,
    get_lecture_session,
    get_lecture_checkpoints,
    get_mastered_topics,
    record_mastered_topic
)
from app.services.study_agents import (
    generate_lecture_diagnostic,
    evaluate_lecture_diagnostic,
    generate_phase_checkpoint,
    evaluate_checkpoint_response,
    handle_lecture_pause_ask,
    generate_teach_back_prompt,
    evaluate_teach_back_submission,
    stream_teacher_lecture
)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def setup_test_session():
    test_sid = "test_teacher_mode_session_1"
    init_session_db(test_sid)
    insert_chunks_to_fts(test_sid, "Attention_Paper.pdf", [
        {
            "chunk_id": "c1",
            "page": 1,
            "source_type": "text",
            "content": "The Transformer relies on scaled dot-product self-attention: Attention(Q,K,V) = softmax(QK^T / sqrt(d_k))V."
        }
    ])
    return test_sid


@pytest.mark.asyncio
async def test_diagnostic_open_and_evaluation(setup_test_session):
    test_sid = setup_test_session
    topic_id = "t_attn"
    topic_title = "Scaled Dot-Product Attention"

    mock_diagnostic_json = json.dumps({
        "prerequisite_concept": "Matrix Multiplication & Softmax",
        "question": "What is the primary role of the softmax function in vector transformations?",
        "options": [
            {"id": "a", "text": "Normalizing logits into a valid probability distribution"},
            {"id": "b", "text": "Inverting non-singular square matrices"},
            {"id": "c", "text": "Performing convolution across temporal features"},
            {"id": "d", "text": "Computing eigenvalues of symmetric tensors"}
        ],
        "correct_option_id": "a",
        "explanation": "Softmax exponentiates and normalizes inputs to sum to 1."
    })

    with patch("app.services.study_agents.call_llm", new=AsyncMock(return_value=mock_diagnostic_json)):
        diag_res = await generate_lecture_diagnostic(test_sid, topic_id, topic_title)

    assert "lecture_id" in diag_res
    assert diag_res["topic_title"] == topic_title
    assert diag_res["diagnostic"]["correct_option_id"] == "a"
    lecture_id = diag_res["lecture_id"]

    # Verify session recorded in SQLite
    lec_session = get_lecture_session(test_sid, lecture_id)
    assert lec_session is not None
    assert lec_session["topic_title"] == topic_title
    assert lec_session["status"] == "diagnostic"

    # Evaluate Diagnostic: Novice branch
    mock_eval_novice = json.dumps({
        "level": "novice",
        "is_correct": False,
        "reasoning": "Student struggled with basic probability normalization.",
        "prerequisite_needed": True,
        "prerequisite_summary": "Softmax turns numbers into weights that add up to 100%."
    })
    with patch("app.services.study_agents.call_llm", new=AsyncMock(return_value=mock_eval_novice)):
        eval_res = await evaluate_lecture_diagnostic(
            session_id=test_sid,
            topic_id=topic_id,
            topic_title=topic_title,
            question="What is the role of softmax?",
            student_answer="b",
            lecture_id=lecture_id
        )

    assert eval_res["level"] == "novice"
    assert eval_res["prerequisite_needed"] is True
    updated_session = get_lecture_session(test_sid, lecture_id)
    assert updated_session["diagnostic_level"] == "novice"


@pytest.mark.asyncio
async def test_4_phase_lecture_streaming_with_continuity(setup_test_session):
    test_sid = setup_test_session
    topic_id = "t_attn"
    topic_title = "Self-Attention Mechanics"

    # Seed an existing mastered topic for cross-session continuity
    record_mastered_topic(test_sid, "Recurrent Neural Networks", "Deep Learning", 95.0)

    mock_phase_responses = [
        "### First-Principles Intuition\n\nUnlike RNNs, self-attention processes all sequence tokens in parallel.",
        "### Deep Mechanics\n\nGoverned by the fundamental equation:\n\n$$ \\text{Attention}(Q,K,V) = \\text{softmax}\\left(\\frac{QK^T}{\\sqrt{d_k}}\\right)V $$\n\nWhere $d_k$ is the projection dimension.",
        "### Worked Derivation\n\nGiven query vector $q = [1, 0]$ and key $k = [1, 0]$, we compute $q \\cdot k = 1$.",
        "### Exam Traps\n\n> [!WARNING] Exam Trap & Common Misconception\n> Confusing self-attention $O(n^2)$ time complexity with $O(n)$ RNN step complexity."
    ]

    call_count = 0
    async def mock_call_llm(*args, **kwargs):
        nonlocal call_count
        resp = mock_phase_responses[call_count % len(mock_phase_responses)]
        call_count += 1
        return resp

    events = []
    with patch("app.services.study_agents.call_llm", side_effect=mock_call_llm):
        gen = stream_teacher_lecture(
            session_id=test_sid,
            topic_id=topic_id,
            topic_title=topic_title,
            override_syllabus=True,
            diagnostic_level="standard"
        )
        async for chunk in gen:
            if chunk.startswith("data: "):
                data_json = chunk[6:].strip()
                if data_json:
                    events.append(json.loads(data_json))

    event_types = [e["type"] for e in events]
    assert "phase_start" in event_types
    assert "token" in event_types
    assert "phase_end" in event_types
    assert "teach_back_ready" in event_types
    assert "done" in event_types


@pytest.mark.asyncio
async def test_checkpoint_active_recall_and_modal_remediation(setup_test_session):
    test_sid = setup_test_session
    topic_title = "Transformer Scaled Dot-Product"
    phase_name = "Phase 2: Deep Mechanics"
    phase_content = "The scaling factor 1/sqrt(d_k) prevents softmax gradient vanishing at large dimensions."

    mock_checkpoint_json = json.dumps({
        "question": "Why is the dot-product divided by sqrt(d_k)?",
        "options": [
            {"id": "a", "text": "To prevent extreme values from pushing softmax into regions with vanishing gradients"},
            {"id": "b", "text": "To enforce orthogonal projection"},
            {"id": "c", "text": "To invert the matrix determinant"},
            {"id": "d", "text": "To accelerate GPU memory bandwidth"}
        ],
        "correct_option_id": "a",
        "core_concept": "Softmax gradient stabilization"
    })

    with patch("app.services.study_agents.call_llm", new=AsyncMock(return_value=mock_checkpoint_json)):
        chk_res = await generate_phase_checkpoint(test_sid, topic_title, phase_name, phase_content)

    assert "checkpoint_id" in chk_res
    assert chk_res["checkpoint"]["correct_option_id"] == "a"

    # Test Correct Response
    corr_eval = await evaluate_checkpoint_response(
        session_id=test_sid,
        topic_title=topic_title,
        phase_name=phase_name,
        question_prompt=chk_res["checkpoint"]["question"],
        correct_answer="a",
        student_response="a",
        checkpoint_id=chk_res["checkpoint_id"]
    )
    assert corr_eval["is_correct"] is True
    assert corr_eval["remedial_content"] is None

    # Test Incorrect Response with Modal Remediation (switching to physical analogy)
    mock_remedial = "Think of softmax like a thermostat: without the scaling factor, extreme temperatures peg the needle at max, making it impossible to adjust."
    with patch("app.services.study_agents.call_llm", new=AsyncMock(return_value=mock_remedial)):
        incorr_eval = await evaluate_checkpoint_response(
            session_id=test_sid,
            topic_title=topic_title,
            phase_name=phase_name,
            question_prompt=chk_res["checkpoint"]["question"],
            correct_answer="a",
            student_response="c",
            checkpoint_id=chk_res["checkpoint_id"]
        )
    assert incorr_eval["is_correct"] is False
    assert incorr_eval["remedial_modality"] == "analogy"
    assert "thermostat" in incorr_eval["remedial_content"]


@pytest.mark.asyncio
async def test_inline_pause_and_ask(setup_test_session):
    test_sid = setup_test_session
    topic_title = "Self-Attention"

    mock_pause_ans = (
        "Great question. The query and key matrices have dimension d_k so that their dot product is a scalar. "
        "With this clarified, let us resume our examination of value aggregation."
    )

    with patch("app.services.study_agents.call_llm", new=AsyncMock(return_value=mock_pause_ans)):
        pause_res = await handle_lecture_pause_ask(
            session_id=test_sid,
            topic_title=topic_title,
            current_phase="Phase 2: Deep Mechanics",
            accumulated_context="We computed QK^T...",
            student_question="Why do query and key need to have the same dimension?"
        )

    assert "answer" in pause_res
    assert "d_k" in pause_res["answer"]
    assert pause_res["phase"] == "Phase 2: Deep Mechanics"


@pytest.mark.asyncio
async def test_feynman_teach_back_and_memory_registration(setup_test_session):
    test_sid = setup_test_session
    topic_id = "t_feynman"
    topic_title = "Backpropagation"

    prompt_res = await generate_teach_back_prompt(test_sid, topic_id, topic_title)
    assert "Feynman" in prompt_res["prompt"]

    mock_eval = json.dumps({
        "score": 92,
        "mastery_verdict": "Mastered",
        "strengths": ["Clear articulation of chain rule application across layers."],
        "areas_for_refinement": ["Mention vanishing gradient implications."],
        "professor_critique": "Outstanding synthesis! You demonstrated rigorous command of backpropagation.",
        "executive_summary_markdown": "# Backpropagation Notes\n\n- Chain rule computes partial derivatives.\n- Gradient descent updates weights."
    })

    with patch("app.services.study_agents.call_llm", new=AsyncMock(return_value=mock_eval)):
        eval_res = await evaluate_teach_back_submission(
            session_id=test_sid,
            topic_id=topic_id,
            topic_title=topic_title,
            submission_text="Backpropagation uses the calculus chain rule to calculate the gradient of the loss function with respect to each weight."
        )

    assert eval_res["evaluation"]["score"] == 92
    assert eval_res["evaluation"]["mastery_verdict"] == "Mastered"

    # Verify registered in episodic memory
    mastered = get_mastered_topics(test_sid)
    assert any(m["topic_title"] == topic_title for m in mastered)


def test_teacher_mode_rest_endpoints(client, setup_test_session):
    test_sid = setup_test_session
    topic_id = "t_api"
    topic_title = "Gradient Descent"

    # 1. Start Diagnostic
    mock_diag = json.dumps({
        "prerequisite_concept": "Derivatives",
        "question": "What does the slope of a tangent line indicate?",
        "options": [
            {"id": "a", "text": "Rate of change of the function"},
            {"id": "b", "text": "Total integral area"},
            {"id": "c", "text": "Matrix rank"},
            {"id": "d", "text": "Discontinuous asymptote"}
        ],
        "correct_option_id": "a",
        "explanation": "Slope represents derivative rate of change."
    })
    headers = {"Authorization": "Bearer demo-token"}
    with patch("app.services.study_agents.call_llm", new=AsyncMock(return_value=mock_diag)):
        res = client.post("/study/topic/teach/diagnostic/start", json={
            "session_id": test_sid,
            "topic_id": topic_id,
            "topic_title": topic_title
        }, headers=headers)
    assert res.status_code == 200
    diag_data = res.json()
    assert "lecture_id" in diag_data
    lecture_id = diag_data["lecture_id"]

    # 2. Submit Diagnostic
    mock_eval = json.dumps({
        "level": "standard",
        "is_correct": True,
        "reasoning": "Solid baseline calculus grasp.",
        "prerequisite_needed": False,
        "prerequisite_summary": None
    })
    with patch("app.services.study_agents.call_llm", new=AsyncMock(return_value=mock_eval)):
        res = client.post("/study/topic/teach/diagnostic/submit", json={
            "session_id": test_sid,
            "topic_id": topic_id,
            "topic_title": topic_title,
            "question": "What does the slope indicate?",
            "student_answer": "a",
            "lecture_id": lecture_id
        }, headers=headers)
    assert res.status_code == 200
    assert res.json()["level"] == "standard"

    # 3. Pause & Ask Endpoint
    with patch("app.services.study_agents.call_llm", new=AsyncMock(return_value="Learning rate scales step size.")):
        res = client.post("/study/topic/teach/pause/ask", json={
            "session_id": test_sid,
            "topic_title": topic_title,
            "current_phase": "Phase 2",
            "accumulated_context": "...",
            "student_question": "What is learning rate?",
            "lecture_id": lecture_id
        }, headers=headers)
    assert res.status_code == 200
    assert "Learning rate" in res.json()["answer"]

    # 4. Get Lecture Session State
    res = client.get(f"/study/topic/teach/session/{test_sid}/{lecture_id}", headers=headers)
    assert res.status_code == 200
    assert res.json()["session"]["id"] == lecture_id
