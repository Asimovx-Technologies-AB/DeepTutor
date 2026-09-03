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
REGISTRY_PATH = DATA_DIR / "sessions_registry.json"
USER_MEMORY_PATH = DATA_DIR / "user_memory.json"

_registry_lock = threading.Lock()
_memory_lock = threading.Lock()


def ensure_data_directories():
    """Ensure data/ and data/sessions/ exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    with _registry_lock:
        if not REGISTRY_PATH.exists():
            with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
                json.dump([], f, indent=2)

    with _memory_lock:
        if not USER_MEMORY_PATH.exists():
            with open(USER_MEMORY_PATH, "w", encoding="utf-8") as f:
                json.dump({}, f, indent=2)


ensure_data_directories()


def get_session_db_path(session_id: str) -> Path:
    """Return the absolute path to the session's physical SQLite database."""
    safe_id = "".join(c for c in session_id if c.isalnum() or c in ("-", "_"))
    return SESSIONS_DIR / f"{safe_id}.db"


def init_session_db(session_id: str) -> Path:
    """
    Initialize a physical SQLite database for the session with FTS5 and metadata tables.
    Idempotent.
    """
    ensure_data_directories()
    db_path = get_session_db_path(session_id)

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()

        # 1. Virtual FTS5 Full-Text Table for Sub-2ms BM25 Search
        cur.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS document_fts USING fts5(
                chunk_id UNINDEXED,
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
                title TEXT,
                summary TEXT,
                difficulty TEXT,
                key_concepts_json TEXT,
                estimated_study_time TEXT
            );
        """)

        # 4. Persisted Ingested Documents
        cur.execute("""
            CREATE TABLE IF NOT EXISTS session_documents (
                id TEXT PRIMARY KEY,
                filename TEXT,
                file_path TEXT,
                status TEXT,
                page_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        conn.commit()
    finally:
        conn.close()

    # Trigger cloud backup asynchronously
    schedule_s3_db_backup(session_id)
    return db_path


# ─── FTS5 BM25 Full-Text Retrieval ──────────────────────────────────────────

def insert_chunks_to_fts(
    session_id: str,
    doc_id: str,
    chunks: List[Dict[str, Any]]
):
    """
    Batch index semantic chunks into document_fts.
    Each chunk dict should contain: chunk_id, page, source_type, content.
    """
    db_path = init_session_db(session_id)
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        data = [
            (
                str(c.get("chunk_id", i)),
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
                INSERT INTO document_fts(chunk_id, doc_id, page, source_type, content)
                VALUES (?, ?, ?, ?, ?)
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
    source_type: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Execute sub-2ms BM25 full-text search against the session's physical SQLite database.
    Falls back to token-split or LIKE matching if FTS5 MATCH syntax encounters special characters.
    """
    db_path = get_session_db_path(session_id)
    if not db_path.exists():
        return []

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    results = []

    # Clean query for FTS5: strip punctuation, wrap terms in quotes for boolean OR/AND
    clean_words = [
        "".join(c for c in w if c.isalnum() or c in ("-", "_")).strip()
        for w in query.split()
    ]
    clean_words = [w for w in clean_words if len(w) > 1]

    if not clean_words:
        return []

    fts_query = " OR ".join(f'"{w}"' for w in clean_words[:8])

    try:
        cur = conn.cursor()
        if source_type:
            sql = """
                SELECT chunk_id, doc_id, page, source_type, content, bm25(document_fts) as rank
                FROM document_fts
                WHERE document_fts MATCH ? AND source_type = ?
                ORDER BY rank
                LIMIT ?
            """
            cur.execute(sql, (fts_query, source_type, limit))
        else:
            sql = """
                SELECT chunk_id, doc_id, page, source_type, content, bm25(document_fts) as rank
                FROM document_fts
                WHERE document_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """
            cur.execute(sql, (fts_query, limit))

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
                WHERE content LIKE ?
                LIMIT ?
                """,
                (first_term, limit)
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


def get_all_chunks(session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Retrieve sample or all chunks from document_fts."""
    db_path = get_session_db_path(session_id)
    if not db_path.exists():
        return []

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT chunk_id, doc_id, page, source_type, content FROM document_fts LIMIT ?",
            (limit,)
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
    is_explanation: bool = False
):
    """Persist a conversation message to session_messages."""
    init_session_db(session_id)
    db_path = get_session_db_path(session_id)
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO session_messages(
                id, role, text, thought_process, quiz_data_json, topics_json, attachment_json, is_explanation, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
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

    # Update message count in registry
    increment_session_message_count(session_id)
    schedule_s3_db_backup(session_id)


def get_session_messages(session_id: str) -> List[Dict[str, Any]]:
    """Retrieve ordered conversation messages for a session."""
    db_path = get_session_db_path(session_id)
    if not db_path.exists():
        return []

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM session_messages ORDER BY created_at ASC")
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

def save_session_topics(session_id: str, topics: List[Dict[str, Any]]):
    """Batch save extracted topics to session_topics."""
    init_session_db(session_id)
    db_path = get_session_db_path(session_id)
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        for t in topics:
            cur.execute(
                """
                INSERT OR REPLACE INTO session_topics(
                    id, title, summary, difficulty, key_concepts_json, estimated_study_time
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(t.get("id", "")),
                    str(t.get("title", "")),
                    str(t.get("summary", "")),
                    str(t.get("difficulty", "Intermediate")),
                    json.dumps(t.get("key_concepts", [])),
                    str(t.get("estimated_study_time", "15 mins")),
                )
            )
        conn.commit()
    finally:
        conn.close()

    update_session_topic_count(session_id, len(topics))
    schedule_s3_db_backup(session_id)


def get_session_topics(session_id: str) -> List[Dict[str, Any]]:
    """Retrieve saved topics for a session."""
    db_path = get_session_db_path(session_id)
    if not db_path.exists():
        return []

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM session_topics")
        rows = cur.fetchall()
        topics = []
        for r in rows:
            topics.append({
                "id": r["id"],
                "title": r["title"],
                "summary": r["summary"],
                "difficulty": r["difficulty"],
                "key_concepts": json.loads(r["key_concepts_json"]) if r["key_concepts_json"] else [],
                "estimated_study_time": r["estimated_study_time"],
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
    page_count: int = 0
):
    """Record an ingested document state."""
    init_session_db(session_id)
    db_path = get_session_db_path(session_id)
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO session_documents(
                id, filename, file_path, status, page_count, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (doc_id, filename, file_path, status, page_count, datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
    finally:
        conn.close()


def update_document_status(session_id: str, doc_id: str, status: str):
    """Update status (e.g. 'indexing' -> 'text_ready' -> 'fully_processed')."""
    db_path = get_session_db_path(session_id)
    if not db_path.exists():
        return
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE session_documents SET status = ? WHERE id = ?",
            (status, doc_id)
        )
        conn.commit()
    finally:
        conn.close()


def get_session_documents(session_id: str) -> List[Dict[str, Any]]:
    """Retrieve list of documents uploaded to this session."""
    db_path = get_session_db_path(session_id)
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM session_documents ORDER BY created_at DESC")
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


# ─── Global Sessions Registry (sessions_registry.json) ──────────────────────

def list_registry_sessions() -> List[Dict[str, Any]]:
    """List all sessions recorded in sessions_registry.json."""
    ensure_data_directories()
    with _registry_lock:
        try:
            if REGISTRY_PATH.exists():
                with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
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
    document_name: Optional[str] = None
) -> Dict[str, Any]:
    """Add or update session metadata in registry."""
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
            if subject: existing["subject"] = subject
            if title: existing["title"] = title
            if status: existing["status"] = status
            if document_name: existing["document_name"] = document_name
            existing["last_active"] = now_iso
            res = existing
        else:
            res = {
                "id": session_id,
                "subject": subject,
                "title": title,
                "document_name": document_name or "",
                "status": status,
                "topic_count": 0,
                "message_count": 0,
                "created_at": now_iso,
                "last_active": now_iso,
            }
            sessions.insert(0, res)

        with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(sessions, f, indent=2)

    init_session_db(session_id)
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


def delete_registry_session(session_id: str) -> bool:
    """Purge session from registry and delete physical SQLite database."""
    ensure_data_directories()
    with _registry_lock:
        try:
            if REGISTRY_PATH.exists():
                with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
                    sessions = json.load(f)
                sessions = [s for s in sessions if s.get("id") != session_id]
                with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
                    json.dump(sessions, f, indent=2)
        except Exception:
            pass

    # Delete physical db file
    db_path = get_session_db_path(session_id)
    if db_path.exists():
        try:
            db_path.unlink()
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
