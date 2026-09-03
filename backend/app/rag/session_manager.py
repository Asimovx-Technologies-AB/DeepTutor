"""
Multi-Session Workspace and Physical SQLite Database Manager.
Ensures 100% physical database and context isolation per course session.
Each study session has its own dedicated SQLite database: backend/data/sessions/{session_id}.db
"""
import os
import json
import sqlite3
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.rag.sqlite_fts_store import close_session_store

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

SESSIONS_DIR = DATA_DIR / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
INDEX_FILE = SESSIONS_DIR / "sessions_registry.json"


class SessionManager:
    """Manages the lifecycle, metadata, and physical databases for study sessions."""

    def __init__(self):
        self._init_registry()

    def _init_registry(self):
        if not INDEX_FILE.exists():
            with open(INDEX_FILE, "w", encoding="utf-8") as f:
                json.dump({}, f, indent=2)

    def _read_registry(self) -> Dict[str, Dict[str, Any]]:
        try:
            with open(INDEX_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _write_registry(self, data: Dict[str, Dict[str, Any]]):
        with open(INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def get_session_db_path(self, session_id: str) -> Path:
        """Returns the physical SQLite DB file path for a session."""
        return SESSIONS_DIR / f"{session_id}.db"

    def init_session_database(self, session_id: str):
        """Initializes a brand-new physical SQLite database with FTS5 table for the session."""
        db_path = self.get_session_db_path(session_id)
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS document_fts USING fts5(
                chunk_id UNINDEXED,
                doc_id,
                page UNINDEXED,
                source_type,
                content,
                tokenize='porter unicode61'
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS session_messages (
                id TEXT PRIMARY KEY,
                role TEXT,
                text TEXT,
                thought_process TEXT,
                quiz_data_json TEXT,
                topics_json TEXT,
                attachment_json TEXT,
                is_explanation INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        # Backward-compatible column migration
        try:
            cursor.execute("ALTER TABLE session_messages ADD COLUMN topics_json TEXT")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE session_messages ADD COLUMN attachment_json TEXT")
        except Exception:
            pass
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS session_topics (
                id TEXT PRIMARY KEY,
                title TEXT,
                summary TEXT,
                difficulty TEXT,
                key_concepts_json TEXT,
                estimated_study_time TEXT
            );
        """)
        conn.commit()
        conn.close()

    def create_session(self, subject: Optional[str] = None, title: Optional[str] = None) -> Dict[str, Any]:
        """Creates a new session and initializes its isolated SQLite database."""
        session_id = f"session_{int(datetime.now().timestamp() * 1000)}"
        self.init_session_database(session_id)

        clean_sub = (subject or "General Study").strip()
        clean_title = (title or f"{clean_sub} Study Session").strip()

        registry = self._read_registry()
        session_meta = {
            "session_id": session_id,
            "title": clean_title,
            "subject": clean_sub,
            "created_at": datetime.now().isoformat(),
            "last_active": datetime.now().isoformat(),
            "topics_count": 0,
            "messages_count": 0,
        }
        registry[session_id] = session_meta
        self._write_registry(registry)
        return session_meta

    def list_sessions(self) -> List[Dict[str, Any]]:
        """Returns all sessions ordered by last active descending."""
        registry = self._read_registry()
        sessions = list(registry.values())
        sessions.sort(key=lambda s: s.get("last_active", ""), reverse=True)
        return sessions

    def get_session_meta(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Gets metadata for a specific session."""
        registry = self._read_registry()
        return registry.get(session_id)

    def update_session_meta(self, session_id: str, updates: Dict[str, Any]):
        """Updates metadata such as title, subject, or counts, creating entry if not present."""
        registry = self._read_registry()
        if session_id not in registry:
            clean_sub = updates.get("subject") or "General Study"
            clean_title = updates.get("title") or f"{clean_sub} Study Session"
            registry[session_id] = {
                "session_id": session_id,
                "title": clean_title,
                "subject": clean_sub,
                "created_at": datetime.now().isoformat(),
                "last_active": datetime.now().isoformat(),
                "topics_count": 0,
                "messages_count": 0,
            }
        registry[session_id].update(updates)
        registry[session_id]["last_active"] = datetime.now().isoformat()
        self._write_registry(registry)

    def delete_session(self, session_id: str) -> bool:
        """Permanently deletes a session, its metadata, and its physical SQLite DB file."""
        registry = self._read_registry()
        if session_id in registry:
            del registry[session_id]
            self._write_registry(registry)

        close_session_store(session_id)

        db_path = self.get_session_db_path(session_id)
        if db_path.exists():
            try:
                os.remove(db_path)
            except Exception as e:
                print(f"[SessionManager] Error deleting DB {db_path}: {e}")
        return True


    def save_session_state(
        self,
        session_id: str,
        messages: Optional[List[Dict[str, Any]]] = None,
        topics: Optional[List[Dict[str, Any]]] = None,
        subject: Optional[str] = None,
        title: Optional[str] = None,
    ):
        """Persists chat messages and extracted topics directly into the session's SQLite database."""
        db_path = self.get_session_db_path(session_id)
        if not db_path.exists():
            self.init_session_database(session_id)

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        if messages is not None:
            cursor.execute("DELETE FROM session_messages")
            for m in messages:
                cursor.execute(
                    """
                    INSERT INTO session_messages (id, role, text, thought_process, quiz_data_json, topics_json, attachment_json, is_explanation)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        m.get("id", ""),
                        m.get("role", "assistant"),
                        m.get("text", ""),
                        m.get("thoughtProcess", ""),
                        json.dumps(m.get("quizData")) if m.get("quizData") else None,
                        json.dumps(m.get("topics")) if m.get("topics") else None,
                        json.dumps(m.get("attachment")) if m.get("attachment") else None,
                        1 if m.get("isExplanation") else 0,
                    ),
                )

        if topics is not None:
            cursor.execute("DELETE FROM session_topics")
            for t in topics:
                cursor.execute(
                    """
                    INSERT INTO session_topics (id, title, summary, difficulty, key_concepts_json, estimated_study_time)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        t.get("id", ""),
                        t.get("title", ""),
                        t.get("summary", ""),
                        t.get("difficulty", "Beginner"),
                        json.dumps(t.get("key_concepts", [])),
                        t.get("estimated_study_time", "15 mins"),
                    ),
                )

        conn.commit()
        conn.close()

        # Update registry counts
        updates: Dict[str, Any] = {}
        if messages is not None:
            updates["messages_count"] = len(messages)
        if topics is not None:
            updates["topics_count"] = len(topics)
        if subject:
            updates["subject"] = subject
        if title:
            updates["title"] = title

        self.update_session_meta(session_id, updates)

        # Cloud Backup: Sync session DB & registry to AWS S3 in background thread
        try:
            import threading
            from app.core.s3_client import s3_storage
            if s3_storage.is_configured():
                threading.Thread(target=s3_storage.upload_file, args=(str(db_path), f"data_backups/{session_id}.db"), daemon=True).start()
                threading.Thread(target=s3_storage.upload_file, args=(str(INDEX_FILE), "data_backups/sessions_registry.json"), daemon=True).start()
        except Exception:
            pass

    def load_session_state(self, session_id: str) -> Dict[str, Any]:
        """Loads all saved messages, topics, and metadata from the session's SQLite database."""
        db_path = self.get_session_db_path(session_id)
        if not db_path.exists():
            self.init_session_database(session_id)

        meta = self.get_session_meta(session_id) or {
            "session_id": session_id,
            "title": "Study Session",
            "subject": "General",
        }

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Ensure columns exist in case of older db files
        try:
            cursor.execute("ALTER TABLE session_messages ADD COLUMN topics_json TEXT")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE session_messages ADD COLUMN attachment_json TEXT")
        except Exception:
            pass

        # Load messages
        cursor.execute("SELECT * FROM session_messages ORDER BY rowid ASC")
        rows = cursor.fetchall()
        messages = []
        for r in rows:
            quiz_data = None
            if r["quiz_data_json"]:
                try:
                    quiz_data = json.loads(r["quiz_data_json"])
                except Exception:
                    pass

            topics_data = None
            try:
                if "topics_json" in r.keys() and r["topics_json"]:
                    topics_data = json.loads(r["topics_json"])
            except Exception:
                pass

            attachment_data = None
            try:
                if "attachment_json" in r.keys() and r["attachment_json"]:
                    attachment_data = json.loads(r["attachment_json"])
            except Exception:
                pass

            messages.append({
                "id": r["id"],
                "role": r["role"],
                "text": r["text"],
                "thoughtProcess": r["thought_process"],
                "quizData": quiz_data,
                "topics": topics_data,
                "attachment": attachment_data,
                "isExplanation": bool(r["is_explanation"]),
            })

        # Load topics
        cursor.execute("SELECT * FROM session_topics ORDER BY rowid ASC")
        t_rows = cursor.fetchall()
        topics = []
        for tr in t_rows:
            key_concepts = []
            if tr["key_concepts_json"]:
                try:
                    key_concepts = json.loads(tr["key_concepts_json"])
                except Exception:
                    pass
            topics.append({
                "id": tr["id"],
                "title": tr["title"],
                "summary": tr["summary"],
                "difficulty": tr["difficulty"],
                "key_concepts": key_concepts,
                "estimated_study_time": tr["estimated_study_time"],
            })

        conn.close()

        return {
            "meta": meta,
            "messages": messages,
            "topics": topics,
        }

    def get_session_state(self, session_id: str) -> Dict[str, Any]:
        """Alias for load_session_state."""
        return self.load_session_state(session_id)


# Singleton instance
session_manager = SessionManager()

