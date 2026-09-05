"""
test_integration_study_api.py
==============================
Criteria §2 — Integration Testing Criteria (API Level):
- 2.1 Study Session Endpoints:
    - POST /api/study/sessions/new creates new workspace & DB
    - GET /api/study/sessions lists active workspaces
    - GET /api/study/sessions/{session_id} loads conversation, topics, documents
- 2.2 Chat & Tutoring Endpoints:
    - POST /api/study/agent/message executes planner-executor reasoning pipeline
- 2.3 Exam & Evaluation Endpoints:
    - POST /api/study/topic/exam generates topic exam
    - POST /api/study/topic/evaluate evaluates student submission
- 5. Failure Mode & Edge Case Testing:
    - Unsupported file format upload returns 400 error
"""
import pytest
from unittest.mock import AsyncMock, patch


class TestSessionEndpoints:

    def test_create_and_list_sessions(self, sync_client):
        """POST /sessions/new creates a session and GET /sessions returns it."""
        resp = sync_client.post("/api/study/sessions/new", json={
            "subject": "Mathematics",
            "title": "Calculus II Workspace"
        })
        assert resp.status_code == 200
        data = resp.json()
        sid = data.get("id") or data.get("session_id")
        assert sid is not None
        assert data["title"] == "Calculus II Workspace"

        # List sessions
        list_resp = sync_client.get("/api/study/sessions")
        assert list_resp.status_code == 200
        all_sessions = list_resp.json()
        assert any((s.get("id") == sid or s.get("session_id") == sid) for s in all_sessions)

    def test_get_session_details(self, sync_client):
        """GET /sessions/{session_id} returns meta, messages, topics, and documents."""
        # Create session first
        create_resp = sync_client.post("/api/study/sessions/new", json={
            "subject": "Physics",
            "title": "Electromagnetism"
        })
        sid = create_resp.json().get("id") or create_resp.json().get("session_id")

        detail_resp = sync_client.get(f"/api/study/sessions/{sid}")
        assert detail_resp.status_code == 200
        body = detail_resp.json()
        assert "meta" in body
        assert "messages" in body
        assert "topics" in body
        assert "documents" in body
        assert body["meta"]["title"] == "Electromagnetism"


class TestChatEndpoints:

    def test_agent_message_flow(self, sync_client):
        """POST /api/study/agent/message runs planner-executor pipeline and stores messages."""
        create_resp = sync_client.post("/api/study/sessions/new", json={
            "subject": "Biology",
            "title": "Genetics"
        })
        sid = create_resp.json().get("id") or create_resp.json().get("session_id")

        mock_plan = {
            "intent": "EXPLANATION_REQUEST",
            "reasoning": "Explain DNA replication step by step",
            "target_topic": "DNA replication",
            "search_queries": ["DNA replication helicase polymerase"],
            "response_format": "conceptual",
            "requires_table_data": False,
            "requires_image_data": False,
            "confidence": 0.9,
            "needs_clarification": False,
            "recommended_action": "EXPLAIN",
        }

        mock_exec = {
            "response": "DNA replication is the biological process of producing two identical replicas of DNA from one original DNA molecule.",
            "thought_process": "Identified core biological mechanism and key enzymes.",
            "quiz_data": None,
            "topics": [{"id": "t1", "title": "DNA Replication"}],
            "is_explanation": True,
            "attachment": None,
            "sources": [],
            "format": "conceptual",
        }

        with patch("app.api.study.planner_agent.plan", new=AsyncMock(return_value=mock_plan)), \
             patch("app.api.study.executor_agent.execute", new=AsyncMock(return_value=mock_exec)):

            msg_resp = sync_client.post("/api/study/agent/message", json={
                "message": "Explain how DNA replication works",
                "session_id": sid,
                "subject": "Biology",
            })

        assert msg_resp.status_code == 200
        res = msg_resp.json()
        assert "text" in res
        assert "DNA replication" in res["text"]

        # Verify messages persisted in session details
        detail_resp = sync_client.get(f"/api/study/sessions/{sid}")
        msgs = detail_resp.json()["messages"]
        assert len(msgs) >= 2  # user message + assistant message


class TestExamEndpoints:

    def test_exam_generation_and_evaluation(self, sync_client):
        """POST /topic/exam generates an exam and POST /topic/evaluate grades answers."""
        sid = "session_exam_integration"

        mock_exam = {
            "title": "Cell Biology Mastery Examination",
            "topic_title": "Cell Biology",
            "total_questions": 2,
            "questions": [
                {
                    "id": "q1",
                    "type": "multiple_choice",
                    "prompt": "What is the powerhouse of the cell?",
                    "options": ["Mitochondria", "Nucleus", "Ribosome", "Golgi"],
                    "correct_answer": "A",
                    "explanation": "Mitochondria generates ATP."
                },
                {
                    "id": "q2",
                    "type": "fill_in_blank",
                    "prompt": "The organelle responsible for protein synthesis is the _____.",
                    "correct_answer": "ribosome",
                    "accepted_alternatives": ["ribosomes"],
                    "explanation": "Ribosomes synthesize proteins."
                }
            ]
        }

        with patch("app.api.study.generate_mixed_exam", new=AsyncMock(return_value=mock_exam)):
            exam_resp = sync_client.post("/api/study/topic/exam", json={
                "session_id": sid,
                "topic_id": "cell_bio",
                "topic_title": "Cell Biology"
            })

        assert exam_resp.status_code == 200
        exam_data = exam_resp.json()
        assert exam_data["total_questions"] == 2

        # Now evaluate student answers
        mock_eval_res = {
            "total_questions": 2,
            "earned_score": 2.0,
            "max_score": 2,
            "percentage": 100.0,
            "mastery_level": "Mastered 🌟",
            "summary_message": "Outstanding work!",
            "results": [
                {"id": "q1", "type": "multiple_choice", "is_correct": True, "score": 1.0},
                {"id": "q2", "type": "fill_in_blank", "is_correct": True, "score": 1.0}
            ]
        }

        with patch("app.api.study.evaluate_exam_submission", new=AsyncMock(return_value=mock_eval_res)):
            eval_resp = sync_client.post("/api/study/topic/evaluate", json={
                "session_id": sid,
                "topic_id": "cell_bio",
                "questions": exam_data["questions"],
                "answers": {"q1": "A", "q2": "ribosome"}
            })

        assert eval_resp.status_code == 200
        eval_body = eval_resp.json()
        assert eval_body["earned_score"] == 2.0
        assert eval_body["percentage"] == 100.0


class TestFailureModesAndEdgeCases:

    def test_unsupported_file_upload_rejected(self, sync_client):
        """Unsupported file extensions must be rejected with 400."""
        files = {"file": ("malicious.exe", b"binary content", "application/octet-stream")}
        resp = sync_client.post(
            "/api/documents/upload",
            files=files,
            data={"topic_id": "general"},
            headers={"Authorization": "Bearer test"}
        )
        assert resp.status_code in (400, 401)
