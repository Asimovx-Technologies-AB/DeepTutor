"""
test_unit_database_crud.py
==========================
Criteria §1.3 & §5 — Database Operations (CRUD) & Concurrency / Locks:
- Session Management: Create, retrieve, update, and delete workspace study sessions.
- Message History: Proper serialization/deserialization of rich chat messages (thought_process, quiz_data, topics).
- User Memory / Episodic Profile: Add and read student memory facts, goals, weaknesses.
- Concurrency & SQLite Locks: Multi-threaded / concurrent state saves do not corrupt data or lock the DB.
"""
import uuid
import pytest
from concurrent.futures import ThreadPoolExecutor
from app.rag.session_manager import session_manager
from app.services.study_storage import (
    get_student_memory,
    add_student_memory_fact,
    reset_student_memory,
)


class TestSessionManagementCRUD:

    def test_create_and_get_session(self):
        """Creates a new workspace session and reads back metadata."""
        sess = session_manager.create_session(
            subject="Computer Science",
            title="Algorithms 101",
            user_id="user_test_crud_1",
        )
        assert sess is not None
        sid = sess["session_id"]
        assert sid.startswith("session_")
        assert sess["title"] == "Algorithms 101"
        assert sess["subject"] == "Computer Science"

        # Read back metadata
        meta = session_manager.get_session_meta(sid)
        assert meta is not None
        assert meta["title"] == "Algorithms 101"

    def test_update_session_metadata(self):
        """Updates title, subject, and active timestamps."""
        sess = session_manager.create_session(
            subject="History",
            title="Initial Title",
            user_id="user_test_crud_2",
        )
        sid = sess["session_id"]

        session_manager.update_session_meta(sid, {
            "title": "Modern History 1945+",
            "subject": "Modern History",
            "topics_count": 5,
            "messages_count": 12,
        })

        meta = session_manager.get_session_meta(sid)
        assert meta["title"] == "Modern History 1945+"
        assert meta["subject"] == "Modern History"
        assert meta["topics_count"] == 5
        assert meta["messages_count"] == 12

    def test_delete_session_removes_records_and_fts_file(self):
        """Deleting a session cascades through shared tables and removes the physical FTS file."""
        sess = session_manager.create_session(
            subject="Chemistry",
            title="Organic Chemistry",
            user_id="user_test_del",
        )
        sid = sess["session_id"]
        fts_path = session_manager.get_session_db_path(sid)
        assert fts_path.exists(), "FTS DB file should exist after creation"

        # Delete
        success = session_manager.delete_session(sid)
        assert success is True
        assert session_manager.get_session_meta(sid) is None
        assert not fts_path.exists(), "FTS DB file should be deleted"


class TestMessageHistorySerialization:

    def test_save_and_load_rich_messages(self):
        """Ensures messages with thought_process, quiz_data, and topics serialize properly."""
        sess = session_manager.create_session(
            subject="Physics",
            title="Quantum Mechanics",
            user_id="user_test_msg",
        )
        sid = sess["session_id"]

        m1_id = f"msg_{uuid.uuid4().hex}"
        m2_id = f"msg_{uuid.uuid4().hex}"
        t1_id = f"top_{uuid.uuid4().hex}"

        sample_messages = [
            {
                "id": m1_id,
                "role": "user",
                "text": "What is wave-particle duality?",
                "thoughtProcess": "",
                "quizData": None,
                "topics": None,
                "isExplanation": False,
            },
            {
                "id": m2_id,
                "role": "assistant",
                "text": "Wave-particle duality posits that matter exhibits both wave and particle properties.",
                "thoughtProcess": "1. Define concept. 2. Reference de Broglie hypothesis.",
                "quizData": {"question": "Who proposed matter waves?", "options": ["de Broglie", "Newton"], "answer": "de Broglie"},
                "topics": [{"id": "t1", "title": "de Broglie Hypothesis"}],
                "isExplanation": True,
            }
        ]

        sample_topics = [
            {
                "id": t1_id,
                "title": "Wave Mechanics",
                "summary": "Introduction to wave functions",
                "difficulty": "Intermediate",
                "key_concepts": ["Schrödinger Equation", "Wave packets"],
                "estimated_study_time": "20 mins",
            }
        ]

        session_manager.save_session_state(
            session_id=sid,
            messages=sample_messages,
            topics=sample_topics,
        )

        loaded = session_manager.load_session_state(sid)
        assert len(loaded["messages"]) == 2
        assert len(loaded["topics"]) == 1

        assistant_msg = loaded["messages"][1]
        assert assistant_msg["thoughtProcess"] == "1. Define concept. 2. Reference de Broglie hypothesis."
        assert assistant_msg["isExplanation"] is True
        assert assistant_msg["quizData"] is not None
        assert assistant_msg["quizData"]["answer"] == "de Broglie"
        assert assistant_msg["topics"][0]["title"] == "de Broglie Hypothesis"

        topic_0 = loaded["topics"][0]
        assert topic_0["title"] == "Wave Mechanics"
        assert "Schrödinger Equation" in topic_0["key_concepts"]


class TestUserEpisodicMemory:

    def test_add_and_retrieve_memory_facts(self):
        """Tests student profile and episodic memory persistence."""
        from app.rag.user_memory import user_memory_store
        uid = f"student_{uuid.uuid4().hex[:8]}"
        user_memory_store.clear_memory(uid)

        user_memory_store.set_learning_style(uid, "Visual learner preferring diagram-first breakdowns")
        user_memory_store.add_goal(uid, "Score 90% in Final Physics Exam")
        user_memory_store.record_weakness(uid, "Calculus integration in kinematics")
        user_memory_store.record_studied_topic(uid, "Kinematics", "Physics")

        memory = user_memory_store.get_memory(uid)
        assert memory is not None
        assert memory.learning_style == "Visual learner preferring diagram-first breakdowns"
        assert "Score 90% in Final Physics Exam" in memory.active_goals
        assert any("Calculus integration" in w for w in memory.weaknesses)
        assert any(t["title"] == "Kinematics" for t in memory.studied_topics)


class TestConcurrencyAndLocks:

    def test_concurrent_session_state_saves(self):
        """Simulates 10 concurrent writes to the same session to ensure no DB lock crashes."""
        sess = session_manager.create_session(
            subject="Math",
            title="Calculus Concurrent",
            user_id="user_concurrent",
        )
        sid = sess["session_id"]

        def _worker_write(idx: int):
            msgs = [{
                "id": f"msg_worker_{uuid.uuid4().hex}",
                "role": "user",
                "text": f"Concurrent message from worker {idx}",
                "thoughtProcess": f"Worker {idx} thought trace",
                "quizData": None,
                "topics": None,
                "isExplanation": False,
            }]
            session_manager.save_session_state(session_id=sid, messages=msgs)
            return True

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(_worker_write, i) for i in range(10)]
            results = [f.result() for f in futures]

        assert all(results)
        final_state = session_manager.load_session_state(sid)
        assert len(final_state["messages"]) == 1  # Last writer wins safely without deadlocks
