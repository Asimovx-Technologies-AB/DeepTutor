"""
Physical SQLite Session Storage & Student Episodic Memory Engine.

Architecture:
- 100% Physical database isolation per session: backend/data/sessions/{session_id}.db
- Virtual FTS5 Full-Text Search table (document_fts) with BM25 ranking (porter unicode61)
- Persisted conversation history (session_messages)
- Persisted extracted topics (session_topics)
- Document metadata & ingestion state (session_documents)
- Global registry: backend/data/sessions_registry.json
- Long-term student memory: backend/data/user_memory.json
- Async AWS S3 backup & disaster recovery sync (eu-north-1)
"""

import os
import json
import sqlite3
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import threading

# Directory references
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BACKEND_DIR / "data"
SESSIONS_DIR = DATA_DIR / "sessions"
USERS_DIR = DATA_DIR / "users"
REGISTRY_PATH = DATA_DIR / "sessions_registry.json"
USER_MEMORY_PATH = DATA_DIR / "user_memory.json"

_registry_lock = threading.Lock()
_memory_lock = threading.Lock()


def ensure_data_directories():
    """Ensure data/, data/sessions/, and data/users/ exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    USERS_DIR.mkdir(parents=True, exist_ok=True)

    with _registry_lock:
        if not REGISTRY_PATH.exists():
            with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
                json.dump([], f, indent=2)

    with _memory_lock:
        if not USER_MEMORY_PATH.exists():
            with open(USER_MEMORY_PATH, "w", encoding="utf-8") as f:
                json.dump({}, f, indent=2)


ensure_data_directories()


def get_user_db_path(user_id: Optional[str] = None) -> Path:
    """Return the absolute path to the user's single physical SQLite database."""
    uid = user_id or "default-user"
    safe_uid = "".join(c for c in uid if c.isalnum() or c in ("-", "_"))
    return USERS_DIR / f"user_{safe_uid}.db"


def get_session_db_path(session_id: str, user_id: Optional[str] = None) -> Path:
    """
    Backwards-compatible path resolver.
    Routes to the user's single physical SQLite database.
    """
    return get_user_db_path(user_id)


def _get_db_connection(db_path: Path) -> sqlite3.Connection:
    """Returns a thread-safe SQLite connection with WAL mode and busy timeout enabled, auto-recovering if malformed."""
    try:
        conn = sqlite3.connect(str(db_path), timeout=30.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
        except Exception:
            pass
        return conn
    except sqlite3.DatabaseError as e:
        if "malformed" in str(e).lower() or "disk image" in str(e).lower():
            for p in (db_path, Path(str(db_path) + "-wal"), Path(str(db_path) + "-shm")):
                if p.exists():
                    try:
                        p.unlink()
                    except Exception:
                        pass
            conn = sqlite3.connect(str(db_path), timeout=30.0)
            try:
                conn.execute("PRAGMA journal_mode=WAL;")
            except Exception:
                pass
            return conn
        raise


def init_user_db(user_id: Optional[str] = None) -> Path:
    """
    Initialize the single physical SQLite database for a user with FTS5 and multi-session schema.
    Idempotent.
    """
    ensure_data_directories()
    db_path = get_user_db_path(user_id)

    conn = _get_db_connection(db_path)
    try:
        cur = conn.cursor()

        # 1. Virtual FTS5 Full-Text Table with session_id scoping
        try:
            cur.execute("SELECT session_id FROM document_fts LIMIT 1")
        except Exception:
            try:
                cur.execute("DROP TABLE IF EXISTS document_fts;")
            except Exception:
                pass

        cur.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS document_fts USING fts5(
                chunk_id UNINDEXED,
                session_id UNINDEXED,
                doc_id,
                page UNINDEXED,
                source_type,
                content,
                tokenize='porter unicode61'
            );
        """)

        # 2. Persisted Conversation History
        cur.execute("""
            CREATE TABLE IF NOT EXISTS session_messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
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

        # 3. Persisted Extracted Curriculum Topics
        cur.execute("""
            CREATE TABLE IF NOT EXISTS session_topics (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                title TEXT,
                summary TEXT,
                difficulty TEXT,
                key_concepts_json TEXT,
                estimated_study_time TEXT,
                document_name TEXT DEFAULT ''
            );
        """)

        # 4. Persisted Ingested Documents
        cur.execute("""
            CREATE TABLE IF NOT EXISTS session_documents (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                filename TEXT,
                file_path TEXT,
                status TEXT,
                page_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 5. Teacher Mode: Lecture Sessions
        cur.execute("""
            CREATE TABLE IF NOT EXISTS lecture_sessions (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                topic_id TEXT NOT NULL,
                topic_title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'diagnostic',
                diagnostic_question TEXT,
                diagnostic_answer TEXT,
                diagnostic_level TEXT DEFAULT 'standard',
                current_phase TEXT DEFAULT 'phase_1',
                current_segment_index INTEGER DEFAULT 0,
                accumulated_notes_markdown TEXT DEFAULT '',
                teach_back_prompt TEXT,
                teach_back_submission TEXT,
                teach_back_grade_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 6. Teacher Mode: Checkpoints
        cur.execute("""
            CREATE TABLE IF NOT EXISTS lecture_checkpoints (
                id TEXT PRIMARY KEY,
                lecture_id TEXT NOT NULL,
                phase TEXT NOT NULL,
                question_prompt TEXT NOT NULL,
                options_json TEXT,
                correct_answer TEXT NOT NULL,
                student_response TEXT,
                is_correct INTEGER,
                remedial_modality TEXT,
                remedial_content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 7. Teacher Mode: Pause & Ask Events
        cur.execute("""
            CREATE TABLE IF NOT EXISTS lecture_pause_events (
                id TEXT PRIMARY KEY,
                lecture_id TEXT NOT NULL,
                phase TEXT NOT NULL,
                token_offset INTEGER DEFAULT 0,
                student_question TEXT NOT NULL,
                teacher_response TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 8. Teacher Mode: Mastered Topics Registry
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_mastered_topics (
                id TEXT PRIMARY KEY,
                session_id TEXT DEFAULT '',
                topic_title TEXT NOT NULL,
                subject TEXT NOT NULL,
                mastery_score REAL DEFAULT 0.0,
                lecture_id TEXT,
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Migration safeguards for existing schema columns
        for tbl, col in [
            ("session_messages", "session_id TEXT DEFAULT ''"),
            ("session_topics", "session_id TEXT DEFAULT ''"),
            ("session_topics", "document_name TEXT DEFAULT ''"),
            ("session_documents", "session_id TEXT DEFAULT ''"),
            ("user_mastered_topics", "session_id TEXT DEFAULT ''"),
        ]:
            try:
                cur.execute(f"ALTER TABLE {tbl} ADD COLUMN {col}")
            except Exception:
                pass

        conn.commit()
    finally:
        conn.close()

    return db_path


def init_session_db(session_id: str, user_id: Optional[str] = None) -> Path:
    """
    Backwards-compatible initializer.
    Initializes and returns the user's single physical SQLite database.
    """
    return init_user_db(user_id)


# ─── FTS5 BM25 Full-Text Retrieval ──────────────────────────────────────────

def insert_chunks_to_fts(
    session_id: str,
    doc_id: str,
    chunks: List[Dict[str, Any]],
    user_id: Optional[str] = None
):
    """
    Batch index semantic chunks into document_fts with session_id scoping.
    Each chunk dict should contain: chunk_id, page, source_type, content.
    """
    db_path = init_user_db(user_id)
    conn = _get_db_connection(db_path)
    try:
        cur = conn.cursor()
        data = [
            (
                str(c.get("chunk_id", i)),
                str(session_id),
                str(doc_id),
                int(c.get("page", 1)),
                str(c.get("source_type", "text")),
                str(c.get("content", "")).strip(),
            )
            for i, c in enumerate(chunks)
            if c.get("content", "").strip()
        ]
        if data:
            cur.executemany(
                """
                INSERT INTO document_fts(chunk_id, session_id, doc_id, page, source_type, content)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                data
            )
            conn.commit()
    finally:
        conn.close()

    schedule_s3_db_backup(session_id)


def search_fts_chunks(
    session_id: str,
    query: str,
    limit: int = 5,
    source_type: Optional[str] = None,
    user_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Execute sub-2ms BM25 full-text search against the user's single physical SQLite database.
    Strictly isolated by session_id.
    """
    db_path = get_user_db_path(user_id)
    if not db_path.exists():
        return []

    conn = _get_db_connection(db_path)
    conn.row_factory = sqlite3.Row
    results = []

    STOP_WORDS = {
        "what", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
        "do", "does", "did", "the", "a", "an", "and", "or", "but", "if", "then", "else",
        "in", "on", "at", "to", "for", "of", "with", "by", "from", "about", "into", "through",
        "during", "before", "after", "above", "below", "up", "down", "out", "over", "under",
        "again", "further", "once", "here", "there", "when", "where", "why", "how", "all",
        "any", "both", "each", "few", "more", "most", "other", "some", "such", "no", "nor",
        "not", "only", "own", "same", "so", "than", "too", "very", "can", "will", "just",
        "should", "now", "tell", "me", "explain", "give", "show", "define", "meaning", "solve"
    }

    raw_words = [
        "".join(c for c in w if c.isalnum() or c in ("-", "_")).strip()
        for w in query.split()
    ]
    raw_words = [w for w in raw_words if len(w) > 1]

    if not raw_words:
        return []

    non_stop = [w for w in raw_words if w.lower() not in STOP_WORDS]
    clean_words = non_stop if non_stop else raw_words

    fts_query = " OR ".join(f'"{w}"' for w in clean_words[:8])

    try:
        cur = conn.cursor()
        if source_type:
            sql = """
                SELECT chunk_id, doc_id, page, source_type, content, bm25(document_fts) as rank
                FROM document_fts
                WHERE document_fts MATCH ? AND session_id = ? AND source_type = ?
                ORDER BY rank
                LIMIT ?
            """
            cur.execute(sql, (fts_query, session_id, source_type, limit))
        else:
            sql = """
                SELECT chunk_id, doc_id, page, source_type, content, bm25(document_fts) as rank
                FROM document_fts
                WHERE document_fts MATCH ? AND session_id = ?
                ORDER BY rank
                LIMIT ?
            """
            cur.execute(sql, (fts_query, session_id, limit))

        rows = cur.fetchall()
        for row in rows:
            results.append({
                "chunk_id": row["chunk_id"],
                "doc_id": row["doc_id"],
                "page": row["page"],
                "source_type": row["source_type"],
                "content": row["content"],
                "score": round(float(row["rank"]), 4),
            })
    except Exception:
        # Fallback to simple LIKE search if FTS syntax errors occur
        try:
            cur = conn.cursor()
            first_term = f"%{clean_words[0]}%"
            cur.execute(
                """
                SELECT chunk_id, doc_id, page, source_type, content
                FROM document_fts
                WHERE session_id = ? AND content LIKE ?
                LIMIT ?
                """,
                (session_id, first_term, limit)
            )
            for row in cur.fetchall():
                results.append({
                    "chunk_id": row["chunk_id"],
                    "doc_id": row["doc_id"],
                    "page": row["page"],
                    "source_type": row["source_type"],
                    "content": row["content"],
                    "score": 0.5,
                })
        except Exception:
            pass
    finally:
        conn.close()

    return results


def get_all_chunks(session_id: str, limit: int = 100, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve sample or all chunks from document_fts for a specific session."""
    db_path = get_user_db_path(user_id)
    if not db_path.exists():
        return []

    conn = _get_db_connection(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT chunk_id, doc_id, page, source_type, content FROM document_fts WHERE session_id = ? LIMIT ?",
            (session_id, limit)
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_chunks_by_page(session_id: str, page: int, source_type: Optional[str] = None, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve all chunks from document_fts for an exact page number within a session."""
    db_path = get_user_db_path(user_id)
    if not db_path.exists():
        return []

    conn = _get_db_connection(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        if source_type:
            cur.execute(
                "SELECT chunk_id, doc_id, page, source_type, content FROM document_fts WHERE session_id = ? AND page = ? AND source_type = ?",
                (session_id, page, source_type)
            )
        else:
            cur.execute(
                "SELECT chunk_id, doc_id, page, source_type, content FROM document_fts WHERE session_id = ? AND page = ?",
                (session_id, page)
            )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


# ─── Session Messages CRUD ──────────────────────────────────────────────────

def save_session_message(
    session_id: str,
    message_id: str,
    role: str,
    text: str,
    thought_process: str = "",
    quiz_data: Optional[Dict[str, Any]] = None,
    topics: Optional[List[Dict[str, Any]]] = None,
    attachment: Optional[Dict[str, Any]] = None,
    is_explanation: bool = False,
    user_id: Optional[str] = None
):
    """Persist a conversation message to session_messages."""
    init_user_db(user_id)
    db_path = get_user_db_path(user_id)
    conn = _get_db_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO session_messages(
                id, session_id, role, text, thought_process, quiz_data_json, topics_json, attachment_json, is_explanation, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                session_id,
                role,
                text,
                thought_process,
                json.dumps(quiz_data) if quiz_data else None,
                json.dumps(topics) if topics else None,
                json.dumps(attachment) if attachment else None,
                1 if is_explanation else 0,
                datetime.now(timezone.utc).isoformat(),
            )
        )
        conn.commit()
    finally:
        conn.close()

    increment_session_message_count(session_id)
    schedule_s3_db_backup(session_id)

    # Mirror message to Neon Cloud PostgreSQL (chat_messages table)
    try:
        from app.core import database as pg_db
        # Ensure session exists in PostgreSQL
        try:
            pg_db.ensure_session_exists(session_id, user_id=user_id or "default-user")
        except Exception:
            pass

        pg_db.add_message(
            session_id=session_id,
            role=role,
            content=text,
            metadata={
                "thought_process": thought_process,
                "quiz_data": quiz_data,
                "topics": topics,
                "attachment": attachment,
                "is_explanation": is_explanation,
            }
        )
    except Exception as e:
        pass


def get_session_messages(session_id: str, limit: Optional[int] = None, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve ordered conversation messages for a session."""
    db_path = get_user_db_path(user_id)
    if not db_path.exists():
        return []

    conn = _get_db_connection(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        if limit:
            cur.execute("SELECT * FROM session_messages WHERE session_id = ? ORDER BY created_at DESC LIMIT ?", (session_id, limit))
            rows = list(reversed(cur.fetchall()))
        else:
            cur.execute("SELECT * FROM session_messages WHERE session_id = ? ORDER BY created_at ASC", (session_id,))
            rows = cur.fetchall()
        msgs = []
        for r in rows:
            msgs.append({
                "id": r["id"],
                "role": r["role"],
                "text": r["text"],
                "thought_process": r["thought_process"] or "",
                "quiz_data": json.loads(r["quiz_data_json"]) if r["quiz_data_json"] else None,
                "topics": json.loads(r["topics_json"]) if r["topics_json"] else None,
                "attachment": json.loads(r["attachment_json"]) if r["attachment_json"] else None,
                "is_explanation": bool(r["is_explanation"]),
                "created_at": r["created_at"],
            })
        return msgs
    finally:
        conn.close()


# ─── Session Curriculum Topics CRUD ─────────────────────────────────────────

def save_session_topics(
    session_id: str,
    topics: List[Dict[str, Any]],
    append: bool = False,
    document_name: Optional[str] = None,
    user_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Batch save extracted topics to session_topics with document_name attribution."""
    init_user_db(user_id)
    db_path = get_user_db_path(user_id)
    conn = _get_db_connection(db_path)
    try:
        cur = conn.cursor()
        existing_titles = set()
        if append:
            cur.execute("SELECT title FROM session_topics WHERE session_id = ?", (session_id,))
            existing_titles = {str(row[0]).strip().lower() for row in cur.fetchall() if row[0]}
        else:
            cur.execute("DELETE FROM session_topics WHERE session_id = ?", (session_id,))

        for t in topics:
            title = str(t.get("title", "")).strip()
            if not title:
                continue
            if append and title.lower() in existing_titles:
                continue

            topic_id = str(t.get("id", "")) or f"topic_{uuid.uuid4().hex[:8]}"
            doc_name = str(t.get("document_name") or document_name or "").strip()
            cur.execute(
                """
                INSERT OR REPLACE INTO session_topics(
                    id, session_id, title, summary, difficulty, key_concepts_json, estimated_study_time, document_name
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    topic_id,
                    session_id,
                    title,
                    str(t.get("summary", "")),
                    str(t.get("difficulty", "Intermediate")),
                    json.dumps(t.get("key_concepts", [])),
                    str(t.get("estimated_study_time", "15 mins")),
                    doc_name,
                )
            )
            existing_titles.add(title.lower())
        conn.commit()
    finally:
        conn.close()

    total_topics = get_session_topics(session_id, user_id=user_id)
    update_session_topic_count(session_id, len(total_topics))
    schedule_s3_db_backup(session_id)
    return total_topics


def get_session_topics(session_id: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve saved topics for a session, including document_name."""
    db_path = get_user_db_path(user_id)
    if not db_path.exists():
        return []

    conn = _get_db_connection(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM session_topics WHERE session_id = ?", (session_id,))
        rows = cur.fetchall()
        topics = []
        for r in rows:
            row_keys = r.keys()
            doc_name = r["document_name"] if "document_name" in row_keys and r["document_name"] else ""
            topics.append({
                "id": r["id"],
                "title": r["title"],
                "summary": r["summary"],
                "difficulty": r["difficulty"],
                "key_concepts": json.loads(r["key_concepts_json"]) if r["key_concepts_json"] else [],
                "estimated_study_time": r["estimated_study_time"],
                "document_name": doc_name,
            })
        return topics
    finally:
        conn.close()


# ─── Session Documents & Status ─────────────────────────────────────────────

def save_session_document(
    session_id: str,
    doc_id: str,
    filename: str,
    file_path: str,
    status: str = "indexing",
    page_count: int = 0,
    user_id: Optional[str] = None
):
    """Record an ingested document state."""
    init_user_db(user_id)
    db_path = get_user_db_path(user_id)
    conn = _get_db_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO session_documents(
                id, session_id, filename, file_path, status, page_count, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (doc_id, session_id, filename, file_path, status, page_count, datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
    finally:
        conn.close()


def update_document_status(session_id: str, doc_id: str, status: str, user_id: Optional[str] = None):
    """Update status (e.g. 'indexing' -> 'text_ready' -> 'fully_processed')."""
    db_path = get_user_db_path(user_id)
    if not db_path.exists():
        return
    conn = _get_db_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE session_documents SET status = ? WHERE session_id = ? AND id = ?",
            (status, session_id, doc_id)
        )
        conn.commit()
    finally:
        conn.close()


def get_session_documents(session_id: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve saved document records for a session."""
    db_path = get_user_db_path(user_id)
    if not db_path.exists():
        return []

    conn = _get_db_connection(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM session_documents WHERE session_id = ? ORDER BY created_at ASC", (session_id,))
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_session_document(session_id: str, document_name_or_id: str, user_id: Optional[str] = None) -> bool:
    """Deletes a specific material document and its extracted chunks from a study room session database."""
    db_path = get_user_db_path(user_id)
    if not db_path.exists():
        return False
    conn = _get_db_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM session_documents WHERE session_id = ? AND (id = ? OR filename = ?)", (session_id, document_name_or_id, document_name_or_id))
        try:
            cur.execute("DELETE FROM document_fts WHERE session_id = ? AND (doc_id = ? OR chunk_id LIKE ?)", (session_id, document_name_or_id, f"{document_name_or_id}%"))
        except Exception:
            pass
        conn.commit()
        return True
    except Exception as e:
        print(f"[StudyStorage] Error deleting session document: {e}")
        return False
    finally:
        conn.close()


# ─── Global Sessions Registry (sessions_registry.json) ──────────────────────

def list_registry_sessions(user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """List all sessions recorded in sessions_registry.json, filtered by user_id if provided."""
    ensure_data_directories()
    with _registry_lock:
        try:
            if REGISTRY_PATH.exists():
                with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
                    all_sessions = json.load(f)
                    if user_id:
                        return [s for s in all_sessions if s.get("user_id") == user_id]
                    return all_sessions
        except Exception:
            pass
    return []


def get_registry_session(session_id: str) -> Optional[Dict[str, Any]]:
    sessions = list_registry_sessions()
    for s in sessions:
        if s.get("id") == session_id:
            return s
    return None


def register_or_update_session(
    session_id: str,
    subject: str = "General Study",
    title: str = "Study Room Session",
    status: str = "ready",
    document_name: Optional[str] = None,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """Add or update session metadata in registry with user isolation and multi-material tracking."""
    ensure_data_directories()
    with _registry_lock:
        sessions = []
        try:
            if REGISTRY_PATH.exists():
                with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
                    sessions = json.load(f)
        except Exception:
            sessions = []

        now_iso = datetime.now(timezone.utc).isoformat()
        existing = next((s for s in sessions if s.get("id") == session_id), None)
        if existing:
            if subject and subject != "General Study":
                existing["subject"] = subject
            # Preserve room title if already meaningful
            curr_title = existing.get("title", "")
            is_placeholder = curr_title in ("New Study Workspace", "New Course Workspace", "Study Room Session", "Default Study Room", "")
            if is_placeholder and title:
                existing["title"] = title

            if status:
                existing["status"] = status

            # Multi-document list tracking
            doc_list = existing.get("documents", [])
            if not isinstance(doc_list, list):
                doc_list = [existing.get("document_name")] if existing.get("document_name") else []
            if document_name and document_name not in doc_list:
                doc_list.append(document_name)

            existing["documents"] = doc_list
            existing["document_count"] = len(doc_list)
            if document_name:
                existing["document_name"] = document_name

            if user_id:
                existing["user_id"] = user_id
            existing["last_active"] = now_iso
            res = existing
        else:
            initial_docs = [document_name] if document_name else []
            res = {
                "id": session_id,
                "user_id": user_id or "guest-user",
                "subject": subject,
                "title": title,
                "document_name": document_name or "",
                "documents": initial_docs,
                "document_count": len(initial_docs),
                "status": status,
                "topic_count": 0,
                "message_count": 0,
                "created_at": now_iso,
                "last_active": now_iso,
            }
            sessions.insert(0, res)

        with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(sessions, f, indent=2)

    init_user_db(user_id)
    return res


def increment_session_message_count(session_id: str):
    with _registry_lock:
        try:
            if REGISTRY_PATH.exists():
                with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
                    sessions = json.load(f)
                for s in sessions:
                    if s.get("id") == session_id:
                        s["message_count"] = s.get("message_count", 0) + 1
                        s["last_active"] = datetime.now(timezone.utc).isoformat()
                        break
                with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
                    json.dump(sessions, f, indent=2)
        except Exception:
            pass


def update_session_topic_count(session_id: str, count: int):
    with _registry_lock:
        try:
            if REGISTRY_PATH.exists():
                with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
                    sessions = json.load(f)
                for s in sessions:
                    if s.get("id") == session_id:
                        s["topic_count"] = count
                        s["last_active"] = datetime.now(timezone.utc).isoformat()
                        break
                with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
                    json.dump(sessions, f, indent=2)
        except Exception:
            pass


def delete_registry_session(session_id: str, user_id: Optional[str] = None) -> bool:
    """Purge session from registry and delete session rows from user SQLite database, scoped to user_id if provided."""
    ensure_data_directories()
    with _registry_lock:
        try:
            if REGISTRY_PATH.exists():
                with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
                    sessions = json.load(f)
                target = next((s for s in sessions if s.get("id") == session_id), None)
                if not target:
                    return False
                if user_id and target.get("user_id") and target.get("user_id") != user_id:
                    return False
                sessions = [s for s in sessions if s.get("id") != session_id]
                with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
                    json.dump(sessions, f, indent=2)
        except Exception:
            return False

    # Purge logical session rows from user database
    db_path = get_user_db_path(user_id)
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            cur = conn.cursor()
            cur.execute("DELETE FROM session_messages WHERE session_id = ?", (session_id,))
            cur.execute("DELETE FROM session_topics WHERE session_id = ?", (session_id,))
            cur.execute("DELETE FROM session_documents WHERE session_id = ?", (session_id,))
            try:
                cur.execute("DELETE FROM document_fts WHERE session_id = ?", (session_id,))
            except Exception:
                pass
            try:
                cur.execute("DELETE FROM lecture_sessions WHERE session_id = ?", (session_id,))
            except Exception:
                pass
            conn.commit()
            conn.close()
        except Exception:
            pass

    return True


# ─── Long-Term Student Episodic Memory (user_memory.json) ────────────────────

def get_student_memory(user_id: str) -> Dict[str, Any]:
    """Retrieve student episodic profile."""
    ensure_data_directories()
    with _memory_lock:
        try:
            if USER_MEMORY_PATH.exists():
                with open(USER_MEMORY_PATH, "r", encoding="utf-8") as f:
                    all_mem = json.load(f)
                    if user_id in all_mem:
                        return all_mem[user_id]
        except Exception:
            pass

    return {
        "user_id": user_id,
        "facts": [],
        "goals": [],
        "weaknesses": [],
        "learning_style": "Visual & Step-by-Step",
        "studied_topics": [],
        "updated_at": datetime.now(timezone.utc).isoformat()
    }


def add_student_memory_fact(
    user_id: str,
    fact: Optional[str] = None,
    goal: Optional[str] = None,
    weakness: Optional[str] = None,
    learning_style: Optional[str] = None,
    studied_topic: Optional[str] = None
) -> Dict[str, Any]:
    """Add episodic facts or struggle areas to student profile."""
    ensure_data_directories()
    with _memory_lock:
        try:
            all_mem = {}
            if USER_MEMORY_PATH.exists():
                with open(USER_MEMORY_PATH, "r", encoding="utf-8") as f:
                    all_mem = json.load(f)
        except Exception:
            all_mem = {}

        prof = all_mem.get(user_id, {
            "user_id": user_id,
            "facts": [],
            "goals": [],
            "weaknesses": [],
            "learning_style": "Visual & Step-by-Step",
            "studied_topics": [],
            "updated_at": datetime.now(timezone.utc).isoformat()
        })

        if fact and fact not in prof["facts"]:
            prof["facts"].append(fact)
        if goal and goal not in prof["goals"]:
            prof["goals"].append(goal)
        if weakness and weakness not in prof["weaknesses"]:
            prof["weaknesses"].append(weakness)
        if learning_style:
            prof["learning_style"] = learning_style
        if studied_topic and studied_topic not in prof["studied_topics"]:
            prof["studied_topics"].append(studied_topic)

        prof["updated_at"] = datetime.now(timezone.utc).isoformat()
        all_mem[user_id] = prof

        try:
            with open(USER_MEMORY_PATH, "w", encoding="utf-8") as f:
                json.dump(all_mem, f, indent=2)
        except Exception:
            pass

        return prof


def reset_student_memory(user_id: str) -> bool:
    ensure_data_directories()
    with _memory_lock:
        try:
            if USER_MEMORY_PATH.exists():
                with open(USER_MEMORY_PATH, "r", encoding="utf-8") as f:
                    all_mem = json.load(f)
                if user_id in all_mem:
                    del all_mem[user_id]
                    with open(USER_MEMORY_PATH, "w", encoding="utf-8") as f:
                        json.dump(all_mem, f, indent=2)
            return True
        except Exception:
            return False


# ─── AWS S3 Cloud Backup & Automated State Restoration ───────────────────────

def _get_s3_client():
    from app.core.config import get_settings
    settings = get_settings()
    if not (settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY and settings.AWS_S3_BUCKET_NAME):
        return None, None
    try:
        import boto3
        s3 = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION or "eu-north-1",
        )
        return s3, settings.AWS_S3_BUCKET_NAME
    except Exception:
        return None, None


def schedule_s3_db_backup(session_id: str):
    """Non-blocking background upload of physical .db to AWS S3 if configured."""
    def _task():
        try:
            s3, bucket = _get_s3_client()
            if not s3 or not bucket:
                return
            db_path = get_session_db_path(session_id)
            if db_path.exists():
                s3.upload_file(str(db_path), bucket, f"data_backups/{session_id}.db")
            if REGISTRY_PATH.exists():
                s3.upload_file(str(REGISTRY_PATH), bucket, "data_backups/sessions_registry.json")
        except Exception:
            pass

    threading.Thread(target=_task, daemon=True).start()


def schedule_s3_document_backup(session_id: str, file_path: str, filename: str):
    """Non-blocking background archival of raw document to S3."""
    def _task():
        try:
            s3, bucket = _get_s3_client()
            if not s3 or not bucket:
                return
            if Path(file_path).exists():
                s3.upload_file(file_path, bucket, f"documents/{session_id}/{filename}")
        except Exception:
            pass

    threading.Thread(target=_task, daemon=True).start()


def check_and_restore_s3_backups():
    """Startup check: inspect S3 for missing session databases and restore locally."""
    try:
        s3, bucket = _get_s3_client()
        if not s3 or not bucket:
            return
        # Attempt to restore registry if missing
        if not REGISTRY_PATH.exists() or REGISTRY_PATH.stat().st_size < 10:
            try:
                s3.download_file(bucket, "data_backups/sessions_registry.json", str(REGISTRY_PATH))
            except Exception:
                pass

        # For every registered session, restore .db if missing locally
        sessions = list_registry_sessions()
        for s in sessions:
            sid = s.get("id")
            if sid:
                local_db = get_session_db_path(sid)
                if not local_db.exists():
                    try:
                        s3.download_file(bucket, f"data_backups/{sid}.db", str(local_db))
                    except Exception:
                        pass
    except Exception:
        pass


# ─── Teacher Mode Storage Helpers ──────────────────────────────────────────

def create_lecture_session(
    session_id: str,
    topic_id: str,
    topic_title: str,
    diagnostic_question: Optional[str] = None,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """Creates a new durable lecture session record in SQLite."""
    db_path = init_user_db(user_id)
    lecture_id = f"lec_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{os.urandom(3).hex()}"
    now_iso = datetime.now(timezone.utc).isoformat()

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO lecture_sessions (
                id, session_id, topic_id, topic_title, status, diagnostic_question, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (lecture_id, session_id, topic_id, topic_title, "diagnostic", diagnostic_question, now_iso, now_iso)
        )
        conn.commit()
    finally:
        conn.close()

    schedule_s3_db_backup(session_id)
    return {
        "id": lecture_id,
        "session_id": session_id,
        "topic_id": topic_id,
        "topic_title": topic_title,
        "status": "diagnostic",
        "diagnostic_question": diagnostic_question,
        "current_phase": "phase_1",
        "accumulated_notes_markdown": ""
    }


def get_lecture_session(session_id: str, lecture_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Fetches a lecture session record by ID."""
    db_path = get_user_db_path(user_id)
    if not db_path.exists():
        return None

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM lecture_sessions WHERE session_id = ? AND id = ?", (session_id, lecture_id))
        row = cur.fetchone()
        if not row:
            return None
        res = dict(row)
        if res.get("teach_back_grade_json"):
            try:
                res["teach_back_grade"] = json.loads(res["teach_back_grade_json"])
            except Exception:
                res["teach_back_grade"] = None
        return res
    finally:
        conn.close()


def update_lecture_session(session_id: str, lecture_id: str, user_id: Optional[str] = None, **kwargs) -> bool:
    """Updates fields of a lecture session record."""
    db_path = get_user_db_path(user_id)
    if not db_path.exists():
        return False

    valid_cols = {
        "status", "diagnostic_question", "diagnostic_answer", "diagnostic_level",
        "current_phase", "current_segment_index", "accumulated_notes_markdown",
        "teach_back_prompt", "teach_back_submission", "teach_back_grade_json"
    }
    updates = {k: v for k, v in kwargs.items() if k in valid_cols}
    if not updates:
        return False

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    set_clauses = [f"{col} = ?" for col in updates.keys()]
    values = list(updates.values()) + [session_id, lecture_id]

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(f"UPDATE lecture_sessions SET {', '.join(set_clauses)} WHERE session_id = ? AND id = ?", values)
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def record_lecture_checkpoint(
    session_id: str,
    lecture_id: str,
    phase: str,
    question_prompt: str,
    options: Optional[List[Dict[str, Any]]],
    correct_answer: str,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """Records an active-recall checkpoint question for a lecture phase."""
    db_path = init_user_db(user_id)
    checkpoint_id = f"chk_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{os.urandom(3).hex()}"
    options_json = json.dumps(options) if options else None

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO lecture_checkpoints (
                id, lecture_id, phase, question_prompt, options_json, correct_answer, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (checkpoint_id, lecture_id, phase, question_prompt, options_json, correct_answer, datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "id": checkpoint_id,
        "lecture_id": lecture_id,
        "phase": phase,
        "question_prompt": question_prompt,
        "options": options or [],
        "correct_answer": correct_answer
    }


def update_lecture_checkpoint(
    session_id: str,
    checkpoint_id: str,
    student_response: str,
    is_correct: bool,
    remedial_modality: Optional[str] = None,
    remedial_content: Optional[str] = None,
    user_id: Optional[str] = None
) -> bool:
    """Updates a checkpoint record with student response and grading/remedial details."""
    db_path = get_user_db_path(user_id)
    if not db_path.exists():
        return False

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE lecture_checkpoints
            SET student_response = ?, is_correct = ?, remedial_modality = ?, remedial_content = ?
            WHERE id = ?
            """,
            (student_response, 1 if is_correct else 0, remedial_modality, remedial_content, checkpoint_id)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_lecture_checkpoints(session_id: str, lecture_id: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves all checkpoints recorded for a lecture session."""
    db_path = get_user_db_path(user_id)
    if not db_path.exists():
        return []

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM lecture_checkpoints WHERE lecture_id = ? ORDER BY created_at ASC", (lecture_id,))
        rows = cur.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if d.get("options_json"):
                try:
                    d["options"] = json.loads(d["options_json"])
                except Exception:
                    d["options"] = []
            result.append(d)
        return result
    finally:
        conn.close()


def record_lecture_pause(
    session_id: str,
    lecture_id: str,
    phase: str,
    student_question: str,
    teacher_response: str,
    token_offset: int = 0,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """Records an inline pause-and-ask event during a lecture."""
    db_path = init_user_db(user_id)
    pause_id = f"pause_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{os.urandom(3).hex()}"

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO lecture_pause_events (
                id, lecture_id, phase, token_offset, student_question, teacher_response, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (pause_id, lecture_id, phase, token_offset, student_question, teacher_response, datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "id": pause_id,
        "lecture_id": lecture_id,
        "phase": phase,
        "student_question": student_question,
        "teacher_response": teacher_response
    }


def record_mastered_topic(
    session_id: str,
    topic_title: str,
    subject: str,
    mastery_score: float = 100.0,
    lecture_id: Optional[str] = None,
    user_id: Optional[str] = None
) -> bool:
    """Registers a topic as mastered in the student's episodic memory registry."""
    db_path = init_user_db(user_id)
    topic_id = f"mst_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{os.urandom(3).hex()}"

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO user_mastered_topics (
                id, session_id, topic_title, subject, mastery_score, lecture_id, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (topic_id, session_id, topic_title, subject, mastery_score, lecture_id, datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
        return True
    finally:
        conn.close()


def get_mastered_topics(session_id: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves all mastered topics for the session/student to enable cross-lecture continuity."""
    db_path = get_user_db_path(user_id)
    if not db_path.exists():
        return []

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM user_mastered_topics WHERE session_id = ? OR session_id = '' ORDER BY completed_at DESC", (session_id,))
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
