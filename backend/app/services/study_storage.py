"""
PostgreSQL Session Storage & Student Episodic Memory Engine for DeepTutor.
Replaces legacy per-user and per-session local SQLite files with Azure Database for PostgreSQL (Flexible Server).
Integrates with PgFTSStore for hybrid BM25 tsvector + pgvector semantic retrieval.
"""
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import text as sql_text

from app.core.config import get_settings
from app.core.database import engine
from app.rag.pg_fts_store import pg_fts_store

logger = logging.getLogger(__name__)
settings = get_settings()

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BACKEND_DIR / "data"
SESSIONS_DIR = DATA_DIR / "sessions"
USERS_DIR = DATA_DIR / "users"
REGISTRY_PATH = DATA_DIR / "sessions_registry.json"
USER_MEMORY_PATH = DATA_DIR / "user_memory.json"


def ensure_data_directories():
    """Ensure directory structure exists for local artifacts/uploads."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    USERS_DIR.mkdir(parents=True, exist_ok=True)


ensure_data_directories()


def to_uuid(val: Optional[str], namespace_suffix: str = "") -> str:
    """Safely converts any string identifier to a valid UUID string deterministically."""
    if not val:
        return str(uuid.uuid4())
    try:
        return str(uuid.UUID(str(val)))
    except (ValueError, AttributeError):
        seed = f"{val}:{namespace_suffix}" if namespace_suffix else str(val)
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, seed))


def _is_postgres() -> bool:
    return engine.dialect.name.startswith("postgres")


# ─── Stubs for backward compatibility ─────────────────────────────────────────

def get_user_db_path(user_id: Optional[str] = None) -> Path:
    uid = user_id or "default-user"
    safe_uid = "".join(c for c in uid if c.isalnum() or c in ("-", "_"))
    return USERS_DIR / f"user_{safe_uid}.db"


def get_session_db_path(session_id: str, user_id: Optional[str] = None) -> Path:
    return get_user_db_path(user_id)


def init_user_db(user_id: Optional[str] = None) -> Path:
    return get_user_db_path(user_id)


def init_session_db(session_id: str, user_id: Optional[str] = None) -> Path:
    return get_user_db_path(user_id)


# ─── Full-Text & Vector Search Delegation ─────────────────────────────────────

def insert_chunks_to_fts(
    session_id: str,
    doc_id: str,
    chunks: List[Dict[str, Any]],
    user_id: Optional[str] = None,
) -> int:
    """Batch index semantic chunks into document_chunks table with session scoping."""
    return pg_fts_store.index_chunks(
        session_id=session_id,
        doc_id=doc_id,
        chunks=chunks,
        user_id=user_id,
    )


def search_fts_chunks(
    session_id: str,
    query: str,
    limit: int = 5,
    source_type: Optional[str] = None,
    user_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """BM25 full-text search against PostgreSQL tsvector index."""
    return pg_fts_store.search_bm25(
        session_id=session_id,
        query=query,
        limit=limit,
        source_type=source_type,
    )


def get_all_chunks(
    session_id: str,
    limit: int = 100,
    user_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retrieve all indexed chunks for a session."""
    return pg_fts_store.get_all_chunks(session_id=session_id, limit=limit)


def get_chunks_by_page(
    session_id: str,
    page: int,
    source_type: Optional[str] = None,
    user_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retrieve all chunks on a specific page within a session."""
    chunks = pg_fts_store.get_chunks_by_page(session_id=session_id, page=page)
    if source_type:
        chunks = [c for c in chunks if c.get("source_type") == source_type]
    return chunks


# ─── Conversation History (study_session_messages) ───────────────────────────

def save_session_message(
    session_id: str,
    message_id: Optional[str] = None,
    role: str = "user",
    text: Optional[str] = None,
    thought_process: str = "",
    quiz_data: Optional[Dict[str, Any]] = None,
    topics: Optional[List[Dict[str, Any]]] = None,
    attachment: Optional[Dict[str, Any]] = None,
    is_explanation: bool = False,
    user_id: Optional[str] = None,
    text_content: Optional[str] = None,
) -> str:
    """Persist a conversation message into PostgreSQL with DB-assigned UUID."""
    # Handle positional invocation where message_id was omitted: (session_id, role, text)
    if message_id in ("user", "assistant", "system") and role not in ("user", "assistant", "system"):
        actual_text = role if text is None else text
        actual_role = message_id
        actual_msg_id = None
    else:
        actual_role = role
        actual_msg_id = message_id
        actual_text = text if text is not None else (text_content or "")

    m_id = to_uuid(actual_msg_id) if actual_msg_id else str(uuid.uuid4())

    quiz_json = json.dumps(quiz_data) if quiz_data is not None else None
    topics_json = json.dumps(topics) if topics is not None else None
    attachment_json = json.dumps(attachment) if attachment is not None else None

    if _is_postgres():
        sql = sql_text("""
            INSERT INTO study_session_messages (
                id, session_id, user_id, role, text, thought_process,
                quiz_data_json, topics_json, attachment_json, is_explanation, created_at
            )
            VALUES (
                CAST(:id AS UUID), :session_id, :user_id, :role, :text, :thought_process,
                CAST(:quiz_json AS jsonb), CAST(:topics_json AS jsonb), CAST(:attachment_json AS jsonb),
                :is_explanation, now()
            )
            ON CONFLICT (id) DO UPDATE SET
                text = EXCLUDED.text,
                thought_process = EXCLUDED.thought_process,
                quiz_data_json = EXCLUDED.quiz_data_json,
                topics_json = EXCLUDED.topics_json,
                attachment_json = EXCLUDED.attachment_json,
                is_explanation = EXCLUDED.is_explanation
            RETURNING id::text;
        """)
    else:
        sql = sql_text("""
            INSERT INTO study_session_messages (
                id, session_id, user_id, role, text, thought_process,
                quiz_data_json, topics_json, attachment_json, is_explanation, created_at
            )
            VALUES (
                :id, :session_id, :user_id, :role, :text, :thought_process,
                :quiz_json, :topics_json, :attachment_json, :is_explanation, CURRENT_TIMESTAMP
            )
            RETURNING id;
        """)

    with engine.begin() as conn:
        res = conn.execute(sql, {
            "id": m_id,
            "session_id": str(session_id),
            "user_id": user_id,
            "role": actual_role,
            "text": actual_text or "",
            "thought_process": thought_process or "",
            "quiz_json": quiz_json,
            "topics_json": topics_json,
            "attachment_json": attachment_json,
            "is_explanation": is_explanation,
        })
        row = res.fetchone()
        assigned_id = str(row[0]) if row else m_id

    increment_session_message_count(session_id)
    return assigned_id


def get_session_messages(
    session_id: str,
    limit: Optional[int] = None,
    user_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retrieve chronological messages for a study session."""
    lim_clause = f"LIMIT {int(limit)}" if limit else ""

    statement = sql_text(f"""
        SELECT id::text AS id, session_id, user_id, role, text, thought_process,
               quiz_data_json, topics_json, attachment_json, is_explanation,
               created_at
        FROM study_session_messages
        WHERE session_id = :session_id
        ORDER BY created_at ASC
        {lim_clause}
    """)

    with engine.connect() as conn:
        rows = conn.execute(statement, {"session_id": str(session_id)}).mappings().fetchall()

    messages = []
    for r in rows:
        msg = dict(r)
        # Parse JSON fields if stringified
        for f in ("quiz_data_json", "topics_json", "attachment_json"):
            if isinstance(msg.get(f), str):
                try:
                    msg[f] = json.loads(msg[f])
                except Exception:
                    pass
        if isinstance(msg.get("created_at"), datetime):
            msg["created_at"] = msg["created_at"].isoformat()
        messages.append(msg)
    return messages


# ─── Curriculum Topics (study_session_topics) ────────────────────────────────

def save_session_topics(
    session_id: str,
    topics: List[Dict[str, Any]],
    user_id: Optional[str] = None,
) -> List[str]:
    """Persist curriculum topics into PostgreSQL with UUID primary keys."""
    if not topics:
        return []

    saved_ids = []
    for t in topics:
        raw_id = t.get("id") or t.get("topic_id")
        t_id = to_uuid(raw_id, namespace_suffix=str(session_id))
        title = t.get("title") or t.get("topic_title") or "Untitled Topic"
        summary = t.get("summary") or ""
        diff = t.get("difficulty") or "Intermediate"
        kconcepts = json.dumps(t.get("key_concepts") or t.get("key_concepts_json") or [])
        est_time = str(t.get("estimated_study_time") or t.get("estimated_time") or "15 mins")
        doc_name = str(t.get("document_name") or "")

        if _is_postgres():
            sql = sql_text("""
                INSERT INTO study_session_topics (
                    id, session_id, user_id, title, summary, difficulty,
                    key_concepts_json, estimated_study_time, document_name, created_at
                )
                VALUES (
                    CAST(:id AS UUID), :session_id, :user_id, :title, :summary, :difficulty,
                    CAST(:key_concepts AS jsonb), :estimated_time, :document_name, now()
                )
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title,
                    summary = EXCLUDED.summary,
                    difficulty = EXCLUDED.difficulty,
                    key_concepts_json = EXCLUDED.key_concepts_json,
                    estimated_study_time = EXCLUDED.estimated_study_time,
                    document_name = EXCLUDED.document_name
                RETURNING id::text;
            """)
        else:
            sql = sql_text("""
                INSERT INTO study_session_topics (
                    id, session_id, user_id, title, summary, difficulty,
                    key_concepts_json, estimated_study_time, document_name, created_at
                )
                VALUES (
                    :id, :session_id, :user_id, :title, :summary, :difficulty,
                    :key_concepts, :estimated_time, :document_name, CURRENT_TIMESTAMP
                )
                RETURNING id;
            """)

        with engine.begin() as conn:
            res = conn.execute(sql, {
                "id": t_id,
                "session_id": str(session_id),
                "user_id": user_id,
                "title": title,
                "summary": summary,
                "difficulty": diff,
                "key_concepts": kconcepts,
                "estimated_time": est_time,
                "document_name": doc_name,
            })
            row = res.fetchone()
            saved_ids.append(str(row[0]) if row else t_id)

    update_session_topic_count(session_id, len(saved_ids))
    return saved_ids


def get_session_topics(
    session_id: str,
    user_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retrieve all curriculum topics for a session."""
    statement = sql_text("""
        SELECT id::text AS id, session_id, user_id, title, summary, difficulty,
               key_concepts_json, estimated_study_time, document_name, created_at
        FROM study_session_topics
        WHERE session_id = :session_id
        ORDER BY created_at ASC
    """)

    with engine.connect() as conn:
        rows = conn.execute(statement, {"session_id": str(session_id)}).mappings().fetchall()

    topics = []
    for r in rows:
        top = dict(r)
        kc = top.get("key_concepts_json")
        if isinstance(kc, str):
            try:
                top["key_concepts"] = json.loads(kc)
            except Exception:
                top["key_concepts"] = []
        elif isinstance(kc, list):
            top["key_concepts"] = kc
        else:
            top["key_concepts"] = []
        if isinstance(top.get("created_at"), datetime):
            top["created_at"] = top["created_at"].isoformat()
        topics.append(top)
    return topics


# ─── Document Metadata (session_documents) ───────────────────────────────────

def save_session_document(
    session_id: str,
    filename: str,
    file_path: str,
    status: str = "completed",
    page_count: int = 0,
    user_id: Optional[str] = None,
    doc_id: Optional[str] = None,
) -> str:
    """Save document metadata to PostgreSQL session_documents."""
    d_id = to_uuid(doc_id, namespace_suffix=str(session_id)) if doc_id else str(uuid.uuid4())
    doc_hash = "".join(c for c in f"{session_id}_{filename}" if c.isalnum())[:32]

    if _is_postgres():
        sql = sql_text("""
            INSERT INTO session_documents (
                id, session_id, doc_hash, user_id, filename, file_path, status, page_count, created_at
            )
            VALUES (
                CAST(:id AS UUID), :session_id, :doc_hash, :user_id, :filename, :file_path,
                :status, :page_count, now()
            )
            ON CONFLICT (id) DO UPDATE SET
                filename = EXCLUDED.filename,
                file_path = EXCLUDED.file_path,
                status = EXCLUDED.status,
                page_count = EXCLUDED.page_count
            RETURNING id::text;
        """)
    else:
        sql = sql_text("""
            INSERT INTO session_documents (
                id, session_id, doc_hash, user_id, filename, file_path, status, page_count, created_at
            )
            VALUES (
                :id, :session_id, :doc_hash, :user_id, :filename, :file_path,
                :status, :page_count, CURRENT_TIMESTAMP
            )
            RETURNING id;
        """)

    with engine.begin() as conn:
        res = conn.execute(sql, {
            "id": d_id,
            "session_id": str(session_id),
            "doc_hash": doc_hash,
            "user_id": user_id,
            "filename": filename,
            "file_path": file_path,
            "status": status,
            "page_count": page_count,
        })
        row = res.fetchone()
        return str(row[0]) if row else d_id


def update_document_status(
    session_id: str,
    doc_id: str,
    status: str,
    page_count: Optional[int] = None,
) -> bool:
    """Update processing status for a session document."""
    pc_clause = ", page_count = :page_count" if page_count is not None else ""
    statement = sql_text(f"""
        UPDATE session_documents
        SET status = :status {pc_clause}
        WHERE session_id = :session_id
          AND (id::text = :doc_id OR filename = :doc_id)
    """)

    params: Dict[str, Any] = {
        "session_id": str(session_id),
        "doc_id": str(doc_id),
        "status": status,
    }
    if page_count is not None:
        params["page_count"] = int(page_count)

    with engine.begin() as conn:
        res = conn.execute(statement, params)
        return res.rowcount > 0


def get_session_documents(
    session_id: str,
    user_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retrieve all document metadata records for a session."""
    statement = sql_text("""
        SELECT id::text AS id, session_id, filename, file_path, status, page_count, created_at
        FROM session_documents
        WHERE session_id = :session_id
        ORDER BY created_at ASC
    """)
    with engine.connect() as conn:
        rows = conn.execute(statement, {"session_id": str(session_id)}).mappings().fetchall()

    docs = []
    for r in rows:
        d = dict(r)
        if isinstance(d.get("created_at"), datetime):
            d["created_at"] = d["created_at"].isoformat()
        docs.append(d)
    return docs


def delete_session_document(session_id: str, document_name_or_id: str, user_id: Optional[str] = None) -> bool:
    """Delete a document and all its indexed chunks from PostgreSQL."""
    # Delete chunks
    pg_fts_store.delete_session_document(session_id, document_name_or_id)

    # Delete from session_documents
    statement = sql_text("""
        DELETE FROM session_documents
        WHERE session_id = :session_id
          AND (id::text = :doc_id OR filename = :doc_id)
    """)
    with engine.begin() as conn:
        res = conn.execute(statement, {"session_id": str(session_id), "doc_id": str(document_name_or_id)})
        return res.rowcount > 0


# ─── Workspace Sessions Registry (workspace_sessions) ─────────────────────────

def list_registry_sessions(user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """List study sessions from workspace_sessions table."""
    filter_clause = "WHERE user_id = :user_id OR user_id IS NULL" if user_id else ""

    statement = sql_text(f"""
        SELECT id, user_id, title, subject, created_at, last_active,
               topics_count AS topic_count, messages_count AS message_count
        FROM workspace_sessions
        {filter_clause}
        ORDER BY last_active DESC
    """)

    params = {"user_id": str(user_id)} if user_id else {}
    with engine.connect() as conn:
        rows = conn.execute(statement, params).mappings().fetchall()

    sessions = []
    for r in rows:
        s = dict(r)
        s["status"] = "ready"
        s["document_name"] = ""
        s["documents"] = []
        s["document_count"] = 0
        sessions.append(s)
    return sessions


def get_registry_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Fetch session metadata by session_id."""
    statement = sql_text("""
        SELECT id, user_id, title, subject, created_at, last_active,
               topics_count AS topic_count, messages_count AS message_count
        FROM workspace_sessions
        WHERE id = :session_id
    """)
    with engine.connect() as conn:
        row = conn.execute(statement, {"session_id": str(session_id)}).mappings().first()
        if not row:
            return None
        s = dict(row)
        s["status"] = "ready"
        s["document_name"] = ""
        s["documents"] = []
        s["document_count"] = 0
        return s


def register_or_update_session(
    session_id: str,
    subject: str = "General Study",
    title: Optional[str] = None,
    document_name: Optional[str] = None,
    status: str = "ready",
    user_id: Optional[str] = None,
    topic_count: Optional[int] = None,
    message_count: Optional[int] = None,
) -> Dict[str, Any]:
    """Idempotently register or update a workspace session in PostgreSQL."""
    now_str = datetime.now(timezone.utc).isoformat()
    clean_title = title or f"{subject} Study Session"

    # Verify user_id existence to prevent foreign key errors
    valid_uid = None
    if user_id:
        with engine.connect() as conn:
            exists = conn.execute(
                sql_text("SELECT 1 FROM users WHERE id = :uid"),
                {"uid": str(user_id)}
            ).scalar()
            if exists:
                valid_uid = str(user_id)

    statement = sql_text("""
        INSERT INTO workspace_sessions (
            id, user_id, title, subject, created_at, last_active, topics_count, messages_count
        )
        VALUES (
            :id, :user_id, :title, :subject, :now, :now,
            COALESCE(:topic_count, 0), COALESCE(:message_count, 0)
        )
        ON CONFLICT (id) DO UPDATE SET
            user_id = COALESCE(EXCLUDED.user_id, workspace_sessions.user_id),
            title = COALESCE(:title, workspace_sessions.title),
            subject = COALESCE(:subject, workspace_sessions.subject),
            last_active = :now,
            topics_count = COALESCE(:topic_count, workspace_sessions.topics_count),
            messages_count = COALESCE(:message_count, workspace_sessions.messages_count);
    """)

    with engine.begin() as conn:
        conn.execute(statement, {
            "id": str(session_id),
            "user_id": valid_uid,
            "title": clean_title,
            "subject": subject,
            "now": now_str,
            "topic_count": topic_count,
            "message_count": message_count,
        })

    return {
        "id": str(session_id),
        "user_id": valid_uid,
        "title": clean_title,
        "subject": subject,
        "status": status,
        "document_name": document_name or "",
        "created_at": now_str,
        "last_active": now_str,
        "topic_count": topic_count or 0,
        "message_count": message_count or 0,
    }


def increment_session_message_count(session_id: str):
    statement = sql_text("""
        UPDATE workspace_sessions
        SET messages_count = messages_count + 1,
            last_active = :now
        WHERE id = :session_id
    """)
    with engine.begin() as conn:
        conn.execute(statement, {
            "session_id": str(session_id),
            "now": datetime.now(timezone.utc).isoformat()
        })


def update_session_topic_count(session_id: str, count: int):
    statement = sql_text("""
        UPDATE workspace_sessions
        SET topics_count = :count,
            last_active = :now
        WHERE id = :session_id
    """)
    with engine.begin() as conn:
        conn.execute(statement, {
            "session_id": str(session_id),
            "count": int(count),
            "now": datetime.now(timezone.utc).isoformat()
        })


def delete_registry_session(session_id: str, user_id: Optional[str] = None) -> bool:
    """Delete a workspace session and all linked data."""
    pg_fts_store.delete_session_chunks(session_id)

    with engine.begin() as conn:
        conn.execute(sql_text("DELETE FROM study_session_messages WHERE session_id = :sid"), {"sid": str(session_id)})
        conn.execute(sql_text("DELETE FROM study_session_topics WHERE session_id = :sid"), {"sid": str(session_id)})
        conn.execute(sql_text("DELETE FROM session_documents WHERE session_id = :sid"), {"sid": str(session_id)})
        res = conn.execute(sql_text("DELETE FROM workspace_sessions WHERE id = :sid"), {"sid": str(session_id)})
        return res.rowcount > 0


# ─── Long-Term Student Episodic Memory (user_memory) ─────────────────────────

def get_student_memory(user_id: str) -> Dict[str, Any]:
    """Retrieve episodic student memory from PostgreSQL user_memory table."""
    statement = sql_text("SELECT memory_json FROM user_memory WHERE user_id = :user_id")
    with engine.connect() as conn:
        row = conn.execute(statement, {"user_id": str(user_id)}).scalar()
        if not row:
            return {
                "user_id": str(user_id),
                "facts": [],
                "goals": [],
                "weaknesses": [],
                "learning_style": "Visual & Step-by-Step",
                "studied_topics": [],
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        mem = row if isinstance(row, dict) else json.loads(row)
        if "user_id" not in mem:
            mem["user_id"] = str(user_id)
        return mem


def add_student_memory_fact(
    user_id: str,
    fact: Optional[str] = None,
    learning_style: Optional[str] = None,
    goal: Optional[str] = None,
    weakness: Optional[str] = None,
    studied_topic: Optional[str] = None,
) -> Dict[str, Any]:
    """Idempotently add an observation or preference to student memory."""
    mem = get_student_memory(user_id)
    if not isinstance(mem, dict):
        mem = {
            "user_id": str(user_id),
            "facts": [],
            "learning_style": "Visual & Step-by-Step",
            "goals": [],
            "weaknesses": [],
            "studied_topics": [],
        }

    mem["user_id"] = str(user_id)
    mem.setdefault("facts", [])
    mem.setdefault("goals", [])
    mem.setdefault("weaknesses", [])
    mem.setdefault("studied_topics", [])

    if fact and fact not in mem["facts"]:
        mem["facts"].append(fact)
    if learning_style:
        mem["learning_style"] = learning_style
    if goal and goal not in mem["goals"]:
        mem["goals"].append(goal)
    if weakness and weakness not in mem["weaknesses"]:
        mem["weaknesses"].append(weakness)
    if studied_topic and studied_topic not in mem["studied_topics"]:
        mem["studied_topics"].append(studied_topic)

    mem["updated_at"] = datetime.now(timezone.utc).isoformat()
    json_str = json.dumps(mem)

    if _is_postgres():
        sql = sql_text("""
            INSERT INTO user_memory (user_id, memory_json, updated_at)
            VALUES (:user_id, CAST(:mem AS jsonb), now())
            ON CONFLICT (user_id) DO UPDATE SET
                memory_json = EXCLUDED.memory_json,
                updated_at = now();
        """)
    else:
        sql = sql_text("""
            INSERT INTO user_memory (user_id, memory_json, updated_at)
            VALUES (:user_id, :mem, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id) DO UPDATE SET
                memory_json = EXCLUDED.memory_json,
                updated_at = CURRENT_TIMESTAMP;
        """)

    with engine.begin() as conn:
        conn.execute(sql, {"user_id": str(user_id), "mem": json_str})

    return mem


def reset_student_memory(user_id: str) -> bool:
    """Clear memory for a student."""
    empty_mem = {
        "user_id": str(user_id),
        "facts": [],
        "learning_style": "Visual & Step-by-Step",
        "goals": [],
        "weaknesses": [],
        "studied_topics": [],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    empty_json = json.dumps(empty_mem)
    if _is_postgres():
        sql = sql_text("""
            INSERT INTO user_memory (user_id, memory_json, updated_at)
            VALUES (:user_id, CAST(:empty AS jsonb), now())
            ON CONFLICT (user_id) DO UPDATE SET
                memory_json = CAST(:empty AS jsonb),
                updated_at = now();
        """)
    else:
        sql = sql_text("""
            INSERT INTO user_memory (user_id, memory_json, updated_at)
            VALUES (:user_id, :empty, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id) DO UPDATE SET
                memory_json = :empty,
                updated_at = CURRENT_TIMESTAMP;
        """)
    with engine.begin() as conn:
        conn.execute(sql, {"user_id": str(user_id), "empty": empty_json})
    return True


# ─── Teacher Mode Lecture Tracking ───────────────────────────────────────────

def create_lecture_session(
    session_id: str,
    topic_id: str,
    topic_title: str,
    diagnostic_question: Optional[str] = None,
    diagnostic_answer: Optional[str] = None,
    diagnostic_level: str = "standard",
    user_id: Optional[str] = None,
    status: str = "diagnostic",
) -> Dict[str, Any]:
    """Initialize a teacher-mode interactive lecture session in PostgreSQL."""
    lec_id = str(uuid.uuid4())

    if _is_postgres():
        sql = sql_text("""
            INSERT INTO lecture_sessions (
                id, session_id, topic_id, topic_title, status, diagnostic_question,
                diagnostic_answer, diagnostic_level, current_phase, current_segment_index,
                accumulated_notes_markdown, created_at, updated_at
            )
            VALUES (
                CAST(:id AS UUID), :session_id, :topic_id, :topic_title, :status, :diagnostic_q,
                :diagnostic_a, :diagnostic_lvl, 'phase_1', 0, '', now(), now()
            )
            RETURNING id::text;
        """)
    else:
        sql = sql_text("""
            INSERT INTO lecture_sessions (
                id, session_id, topic_id, topic_title, status, diagnostic_question,
                diagnostic_answer, diagnostic_level, current_phase, current_segment_index,
                accumulated_notes_markdown, created_at, updated_at
            )
            VALUES (
                :id, :session_id, :topic_id, :topic_title, :status, :diagnostic_q,
                :diagnostic_a, :diagnostic_lvl, 'phase_1', 0, '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            RETURNING id;
        """)

    with engine.begin() as conn:
        res = conn.execute(sql, {
            "id": lec_id,
            "session_id": str(session_id),
            "topic_id": str(topic_id),
            "topic_title": str(topic_title),
            "status": status,
            "diagnostic_q": diagnostic_question,
            "diagnostic_a": diagnostic_answer,
            "diagnostic_lvl": diagnostic_level,
        })
        row = res.fetchone()
        assigned_id = str(row[0]) if row else lec_id

    return {
        "id": assigned_id,
        "session_id": str(session_id),
        "topic_id": str(topic_id),
        "topic_title": str(topic_title),
        "status": status,
        "diagnostic_question": diagnostic_question,
        "current_phase": "phase_1",
        "accumulated_notes_markdown": "",
    }


def get_lecture_session(
    session_id: str,
    lecture_id: str,
    user_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Retrieve full state of a teacher lecture session."""
    statement = sql_text("""
        SELECT id::text AS id, session_id, topic_id, topic_title, status, diagnostic_question,
               diagnostic_answer, diagnostic_level, current_phase, current_segment_index,
               accumulated_notes_markdown, teach_back_prompt, teach_back_submission,
               teach_back_grade_json, created_at, updated_at
        FROM lecture_sessions
        WHERE session_id = :session_id AND (id::text = :lecture_id OR topic_id = :lecture_id)
    """)
    with engine.connect() as conn:
        row = conn.execute(statement, {
            "session_id": str(session_id),
            "lecture_id": str(lecture_id),
        }).mappings().first()
        if not row:
            return None
        res = dict(row)
        tb_grade = res.get("teach_back_grade_json")
        if isinstance(tb_grade, str):
            try:
                res["teach_back_grade"] = json.loads(tb_grade)
            except Exception:
                res["teach_back_grade"] = None
        else:
            res["teach_back_grade"] = tb_grade
        return res


def update_lecture_session(
    session_id: str,
    lecture_id: str,
    user_id: Optional[str] = None,
    **kwargs,
) -> bool:
    """Update fields on a lecture session dynamically."""
    if not kwargs:
        return False

    set_clauses = []
    params: Dict[str, Any] = {
        "session_id": str(session_id),
        "lecture_id": str(lecture_id),
    }

    for key, val in kwargs.items():
        if key == "teach_back_grade":
            key = "teach_back_grade_json"
            val = json.dumps(val) if val is not None else None
        elif isinstance(val, (dict, list)):
            val = json.dumps(val)

        param_name = f"val_{key}"
        set_clauses.append(f"{key} = :{param_name}")
        params[param_name] = val

    set_clauses.append("updated_at = now()" if _is_postgres() else "updated_at = CURRENT_TIMESTAMP")
    sql = sql_text(f"""
        UPDATE lecture_sessions
        SET {', '.join(set_clauses)}
        WHERE session_id = :session_id AND (id::text = :lecture_id OR topic_id = :lecture_id)
    """)

    with engine.begin() as conn:
        res = conn.execute(sql, params)
        return res.rowcount > 0


def record_lecture_checkpoint(
    session_id: str,
    lecture_id: str,
    phase: str,
    question_prompt: str,
    options: Optional[List[Any]] = None,
    correct_answer: str = "a",
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Store an active-recall checkpoint."""
    cp_id = str(uuid.uuid4())
    opt_json = json.dumps(options or [])

    if _is_postgres():
        sql = sql_text("""
            INSERT INTO lecture_checkpoints (
                id, session_id, lecture_id, phase, question_prompt, options_json, correct_answer, created_at
            )
            VALUES (
                :id, :session_id, :lecture_id, :phase, :question_prompt, :options,
                :correct_answer, now()
            )
            RETURNING id;
        """)
    else:
        sql = sql_text("""
            INSERT INTO lecture_checkpoints (
                id, session_id, lecture_id, phase, question_prompt, options_json, correct_answer, created_at
            )
            VALUES (
                :id, :session_id, :lecture_id, :phase, :question_prompt, :options,
                :correct_answer, CURRENT_TIMESTAMP
            )
            RETURNING id;
        """)

    with engine.begin() as conn:
        res = conn.execute(sql, {
            "id": cp_id,
            "session_id": str(session_id),
            "lecture_id": str(lecture_id),
            "phase": phase,
            "question_prompt": question_prompt,
            "options": opt_json,
            "correct_answer": correct_answer,
        })
        row = res.fetchone()
        assigned_id = str(row[0]) if row else cp_id

    return {
        "id": assigned_id,
        "session_id": str(session_id),
        "lecture_id": str(lecture_id),
        "phase": phase,
        "question_prompt": question_prompt,
        "options": options or [],
        "correct_answer": correct_answer,
    }


def update_lecture_checkpoint(
    checkpoint_id: str,
    student_response: str,
    is_correct: bool,
    remedial_modality: Optional[str] = None,
    remedial_content: Optional[str] = None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> bool:
    """Update checkpoint with student's answer and remediation outcome."""
    cast_where = "id::text = :cp_id" if _is_postgres() else "id = :cp_id"
    statement = sql_text(f"""
        UPDATE lecture_checkpoints
        SET student_response = :response,
            is_correct = :is_correct,
            remedial_modality = :remedial_modality,
            remedial_content = :remedial_content
        WHERE {cast_where}
    """)
    with engine.begin() as conn:
        res = conn.execute(statement, {
            "cp_id": str(checkpoint_id),
            "response": student_response,
            "is_correct": is_correct,
            "remedial_modality": remedial_modality,
            "remedial_content": remedial_content,
        })
        return res.rowcount > 0


def get_lecture_checkpoints(
    session_id: str,
    lecture_id: str,
    user_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retrieve all checkpoints recorded for a lecture."""
    cast_id = "id::text AS id" if _is_postgres() else "id"
    statement = sql_text(f"""
        SELECT {cast_id}, lecture_id, phase, question_prompt, options_json,
               correct_answer, student_response, is_correct, remedial_modality,
               remedial_content, created_at
        FROM lecture_checkpoints
        WHERE lecture_id = :lecture_id
        ORDER BY created_at ASC
    """)
    with engine.connect() as conn:
        rows = conn.execute(statement, {"lecture_id": str(lecture_id)}).mappings().fetchall()

    cps = []
    for r in rows:
        c = dict(r)
        opt = c.get("options_json")
        if isinstance(opt, str):
            try:
                c["options"] = json.loads(opt)
            except Exception:
                c["options"] = []
        elif isinstance(opt, list):
            c["options"] = opt
        else:
            c["options"] = []
        cps.append(c)
    return cps


def record_lecture_pause(
    session_id: str,
    lecture_id: str,
    phase: str,
    student_question: str,
    teacher_response: str,
    token_offset: int = 0,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Log student questions during inline lecture pause."""
    p_id = str(uuid.uuid4())
    if _is_postgres():
        sql = sql_text("""
            INSERT INTO lecture_pause_events (
                id, session_id, lecture_id, phase, token_offset, student_question, teacher_response, created_at
            )
            VALUES (
                :id, :session_id, :lecture_id, :phase, :token_offset, :question, :response, now()
            )
            RETURNING id;
        """)
    else:
        sql = sql_text("""
            INSERT INTO lecture_pause_events (
                id, session_id, lecture_id, phase, token_offset, student_question, teacher_response, created_at
            )
            VALUES (
                :id, :session_id, :lecture_id, :phase, :token_offset, :question, :response, CURRENT_TIMESTAMP
            )
            RETURNING id;
        """)

    with engine.begin() as conn:
        res = conn.execute(sql, {
            "id": p_id,
            "session_id": str(session_id),
            "lecture_id": str(lecture_id),
            "phase": phase,
            "token_offset": token_offset,
            "question": student_question,
            "response": teacher_response,
        })
        row = res.fetchone()
        assigned_id = str(row[0]) if row else p_id

    return {
        "id": assigned_id,
        "lecture_id": str(lecture_id),
        "phase": phase,
        "student_question": student_question,
        "teacher_response": teacher_response,
        "token_offset": token_offset,
    }


def record_mastered_topic(
    session_id: str,
    topic_title: str,
    subject: str,
    mastery_score: float = 100.0,
    lecture_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> bool:
    """Record mastery of a curriculum topic."""
    m_id = str(uuid.uuid4())
    if _is_postgres():
        sql = sql_text("""
            INSERT INTO user_mastered_topics (
                id, session_id, user_id, topic_title, subject, mastery_score, lecture_id, completed_at
            )
            VALUES (
                CAST(:id AS UUID), :session_id, :user_id, :topic_title, :subject,
                :mastery_score, :lecture_id, now()
            )
            RETURNING id::text;
        """)
    else:
        sql = sql_text("""
            INSERT INTO user_mastered_topics (
                id, session_id, user_id, topic_title, subject, mastery_score, lecture_id, completed_at
            )
            VALUES (
                :id, :session_id, :user_id, :topic_title, :subject,
                :mastery_score, :lecture_id, CURRENT_TIMESTAMP
            )
            RETURNING id;
        """)

    with engine.begin() as conn:
        conn.execute(sql, {
            "id": m_id,
            "session_id": str(session_id),
            "user_id": user_id,
            "topic_title": topic_title,
            "subject": subject,
            "mastery_score": float(mastery_score),
            "lecture_id": lecture_id,
        })
        return True


def get_mastered_topics(
    session_id: str,
    user_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retrieve all mastered topics for a user/session."""
    clause = "WHERE session_id = :session_id" if session_id else ""
    if user_id:
        clause = f"{clause} OR user_id = :user_id" if clause else "WHERE user_id = :user_id"

    cast_id = "id::text AS id" if _is_postgres() else "id"
    statement = sql_text(f"""
        SELECT {cast_id}, session_id, user_id, topic_title, subject,
               mastery_score, lecture_id, completed_at
        FROM user_mastered_topics
        {clause}
        ORDER BY completed_at DESC
    """)
    params = {}
    if session_id:
        params["session_id"] = str(session_id)
    if user_id:
        params["user_id"] = str(user_id)

    with engine.connect() as conn:
        rows = conn.execute(statement, params).mappings().fetchall()
    return [dict(r) for r in rows]


# ─── Cloud Storage / S3 Compatibility Stubs ──────────────────────────────────

def schedule_s3_db_backup(session_id: str):
    """No-op: Central PostgreSQL does not require local SQLite disk sync."""
    pass


def schedule_s3_document_backup(session_id: str, file_path: str, filename: str):
    """Optional document binary backup stub."""
    pass


def check_and_restore_s3_backups():
    """Startup verification stub."""
    pass
