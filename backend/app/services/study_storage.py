"""
PostgreSQL Session Storage & Student Episodic Memory Engine for DeepTutor.
Replaces legacy per-user and per-session local SQLite files with Azure Database for PostgreSQL (Flexible Server).
Integrates with PgFTSStore for hybrid BM25 tsvector + pgvector semantic retrieval.
"""
import hashlib
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import text as sql_text, bindparam

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
    p = USERS_DIR / f"user_{safe_uid}.db"
    if not p.exists():
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.touch()
        except Exception:
            pass
    return p


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
        SELECT id, session_id, user_id, role, text, thought_process,
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

        # Map database column names to JS frontend ChatMessage model properties
        msg["quiz_data"] = msg.get("quiz_data_json")
        msg["topics"] = msg.get("topics_json")
        msg["attachment"] = msg.get("attachment_json")

        if msg.get("quiz_data") and isinstance(msg["quiz_data"], dict):
            initial_m = msg["quiz_data"].get("initial_mode") or "flashcards"
            msg["format"] = "flashcard" if initial_m == "flashcards" else "quiz"
            msg["response_format"] = msg["format"]

        messages.append(msg)
    return messages


# ─── Curriculum Topics (study_session_topics) ────────────────────────────────

def save_session_topics(
    session_id: str,
    topics: List[Dict[str, Any]],
    user_id: Optional[str] = None,
    append: bool = True,
    document_name: Optional[str] = None,
) -> List[str]:
    """Persist curriculum topics into PostgreSQL with UUID primary keys."""
    if not topics:
        return [t["id"] for t in get_session_topics(session_id)]

    existing = get_session_topics(session_id)
    if not append:
        with engine.begin() as conn:
            conn.execute(sql_text("DELETE FROM study_session_topics WHERE session_id = :sid"), {"sid": str(session_id)})
        existing = []

    existing_titles = {e["title"].strip().lower() for e in existing}

    saved_ids = [e["id"] for e in existing]
    for t in topics:
        title = t.get("title") or t.get("topic_title") or "Untitled Topic"
        if append and title.strip().lower() in existing_titles:
            continue
        existing_titles.add(title.strip().lower())
        raw_id = t.get("id") or t.get("topic_id")
        t_id = to_uuid(raw_id, namespace_suffix=str(session_id))
        summary = t.get("summary") or ""
        diff = t.get("difficulty") or "Intermediate"
        kconcepts = json.dumps(t.get("key_concepts") or t.get("key_concepts_json") or [])
        est_time = str(t.get("estimated_study_time") or t.get("estimated_time") or "15 mins")
        doc_name = str(t.get("document_name") or document_name or "")

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
    return get_session_topics(session_id)


def get_session_topics(
    session_id: str,
    user_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retrieve all curriculum topics for a session."""
    statement = sql_text("""
        SELECT id, session_id, user_id, title, summary, difficulty,
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
    doc_id_or_filename: str = "",
    filename_or_path: str = "",
    file_path: Optional[str] = None,
    status: str = "completed",
    page_count: int = 0,
    user_id: Optional[str] = None,
    doc_id: Optional[str] = None,
    filename: Optional[str] = None,
    **kwargs: Any,
) -> str:
    """Save document metadata to PostgreSQL session_documents with robust positional and keyword handling."""
    # Determine positional ordering vs keyword arguments
    effective_doc_id = doc_id or kwargs.get("doc_id")
    effective_filename = filename or kwargs.get("filename") or kwargs.get("file_name")
    effective_file_path = file_path or kwargs.get("file_path")

    # If positional parameters were provided
    if not effective_filename and not effective_file_path:
        if doc_id_or_filename and filename_or_path and file_path is not None:
            # 4 positional args: (session_id, doc_id, filename, file_path)
            effective_doc_id = doc_id_or_filename
            effective_filename = filename_or_path
            effective_file_path = file_path
        elif doc_id_or_filename and filename_or_path:
            # 3 positional args: (session_id, doc_id_or_name, filename_or_path)
            if doc_id_or_filename.startswith("doc_") or "/" in filename_or_path or "\\" in filename_or_path:
                effective_doc_id = doc_id_or_filename
                effective_filename = Path(filename_or_path).name
                effective_file_path = filename_or_path
            else:
                effective_doc_id = doc_id or str(uuid.uuid4())
                effective_filename = doc_id_or_filename
                effective_file_path = filename_or_path
        elif doc_id_or_filename:
            effective_filename = doc_id_or_filename
            effective_file_path = doc_id_or_filename
    elif not effective_filename:
        if doc_id_or_filename and filename_or_path:
            effective_doc_id = effective_doc_id or doc_id_or_filename
            effective_filename = filename_or_path
        elif doc_id_or_filename:
            effective_filename = doc_id_or_filename

    if not effective_file_path:
        effective_file_path = filename_or_path or effective_filename or "document"

    effective_filename = (effective_filename or "").strip()
    if not effective_filename and effective_file_path:
        effective_filename = Path(effective_file_path).name.strip()
    if not effective_filename:
        effective_filename = f"document_{effective_doc_id or uuid.uuid4().hex[:8]}.pdf"

    effective_status = kwargs.get("status", status)
    effective_page_count = kwargs.get("page_count", page_count)

    d_id = to_uuid(effective_doc_id, namespace_suffix=str(session_id)) if effective_doc_id else str(uuid.uuid4())

    # Cryptographic SHA-256 Content Hash Resolution
    passed_hash = kwargs.get("doc_hash") or kwargs.get("content_hash")
    if passed_hash and len(str(passed_hash).strip()) >= 32:
        doc_hash = str(passed_hash).strip().lower()
    elif effective_file_path and os.path.isfile(effective_file_path):
        try:
            hasher = hashlib.sha256()
            with open(effective_file_path, "rb") as f:
                while block := f.read(65536):
                    hasher.update(block)
            doc_hash = hasher.hexdigest()
        except Exception:
            doc_hash = hashlib.sha256(f"{session_id}:{effective_filename}".encode("utf-8")).hexdigest()
    else:
        doc_hash = hashlib.sha256(f"{session_id}:{effective_filename}".encode("utf-8")).hexdigest()

    # Resolve user_id if omitted
    if not user_id:
        try:
            from app.core.database import get_session
            sess = get_session(session_id)
            if sess and sess.get("user_id"):
                user_id = str(sess["user_id"])
            else:
                user_id = "default_user"
        except Exception:
            user_id = "default_user"

    if _is_postgres():
        with engine.begin() as conn:
            # 1. Check if record already exists for this session
            check_sql = sql_text("""
                SELECT id::text FROM session_documents
                WHERE session_id = :session_id
                  AND (id = CAST(:id AS UUID) OR doc_hash = :doc_hash OR filename = :filename)
                LIMIT 1;
            """)
            existing = conn.execute(check_sql, {
                "session_id": str(session_id),
                "id": d_id,
                "doc_hash": doc_hash,
                "filename": effective_filename,
            }).fetchone()

            if existing:
                existing_id = str(existing[0])
                update_sql = sql_text("""
                    UPDATE session_documents
                    SET filename = :filename,
                        file_path = :file_path,
                        status = :status,
                        page_count = :page_count,
                        doc_hash = :doc_hash
                    WHERE id = CAST(:id AS UUID) OR (session_id = :session_id AND (doc_hash = :doc_hash OR filename = :filename));
                """)
                conn.execute(update_sql, {
                    "id": existing_id,
                    "session_id": str(session_id),
                    "doc_hash": doc_hash,
                    "filename": effective_filename,
                    "file_path": effective_file_path,
                    "status": effective_status,
                    "page_count": effective_page_count,
                })
                return existing_id

            # 2. Insert new record
            insert_sql = sql_text("""
                INSERT INTO session_documents (
                    id, session_id, doc_hash, user_id, filename, file_path, status, page_count, created_at
                )
                VALUES (
                    CAST(:id AS UUID), :session_id, :doc_hash, :user_id, :filename, :file_path,
                    :status, :page_count, now()
                )
                RETURNING id::text;
            """)
            try:
                with conn.begin_nested():
                    res = conn.execute(insert_sql, {
                        "id": d_id,
                        "session_id": str(session_id),
                        "doc_hash": doc_hash,
                        "user_id": user_id,
                        "filename": effective_filename,
                        "file_path": effective_file_path,
                        "status": effective_status,
                        "page_count": effective_page_count,
                    })
                    row = res.fetchone()
                    return str(row[0]) if row else d_id
            except Exception:
                # Concurrent race or existing key fallback - savepoint rolled back cleanly
                conn.execute(sql_text("""
                    UPDATE session_documents
                    SET filename = :filename,
                        file_path = :file_path,
                        status = :status,
                        page_count = :page_count,
                        doc_hash = :doc_hash
                    WHERE session_id = :session_id AND (doc_hash = :doc_hash OR filename = :filename);
                """), {
                    "session_id": str(session_id),
                    "doc_hash": doc_hash,
                    "filename": effective_filename,
                    "file_path": effective_file_path,
                    "status": effective_status,
                    "page_count": effective_page_count,
                })
                return d_id
    else:
        with engine.begin() as conn:
            check_sql = sql_text("""
                SELECT id FROM session_documents
                WHERE session_id = :session_id
                  AND (id = :id OR doc_hash = :doc_hash OR filename = :filename)
                LIMIT 1;
            """)
            existing = conn.execute(check_sql, {
                "session_id": str(session_id),
                "id": d_id,
                "doc_hash": doc_hash,
                "filename": effective_filename,
            }).fetchone()

            if existing:
                existing_id = str(existing[0])
                conn.execute(sql_text("""
                    UPDATE session_documents
                    SET filename = :filename,
                        file_path = :file_path,
                        status = :status,
                        page_count = :page_count,
                        doc_hash = :doc_hash
                    WHERE id = :id OR (session_id = :session_id AND (doc_hash = :doc_hash OR filename = :filename));
                """), {
                    "id": existing_id,
                    "session_id": str(session_id),
                    "doc_hash": doc_hash,
                    "filename": effective_filename,
                    "file_path": effective_file_path,
                    "status": effective_status,
                    "page_count": effective_page_count,
                })
                return existing_id

            conn.execute(sql_text("""
                INSERT INTO session_documents (
                    id, session_id, doc_hash, user_id, filename, file_path, status, page_count, created_at
                )
                VALUES (
                    :id, :session_id, :doc_hash, :user_id, :filename, :file_path,
                    :status, :page_count, CURRENT_TIMESTAMP
                );
            """), {
                "id": d_id,
                "session_id": str(session_id),
                "doc_hash": doc_hash,
                "user_id": user_id,
                "filename": effective_filename,
                "file_path": effective_file_path,
                "status": effective_status,
                "page_count": effective_page_count,
            })
            return d_id


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
          AND (id = :doc_id OR filename = :doc_id)
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
    """Retrieve all document metadata records for a session, filtering out empty or duplicate records."""
    order_clause = "ORDER BY created_at ASC" if _is_postgres() else "ORDER BY created_at ASC, rowid ASC"
    statement = sql_text(f"""
        SELECT id, session_id, doc_hash, filename, file_path, status, page_count, created_at
        FROM session_documents
        WHERE session_id = :session_id
          AND filename IS NOT NULL AND filename != ''
        {order_clause}
    """)
    with engine.connect() as conn:
        rows = conn.execute(statement, {"session_id": str(session_id)}).mappings().fetchall()

    docs = []
    seen_names = set()
    for r in rows:
        d = dict(r)
        fn = (d.get("filename") or "").strip()
        if not fn or fn in seen_names:
            continue
        seen_names.add(fn)
        if isinstance(d.get("created_at"), datetime):
            d["created_at"] = d["created_at"].isoformat()
        d["doc_hash"] = str(d.get("doc_hash") or "")
        docs.append(d)
    return docs


def delete_session_document(session_id: str, document_name_or_id: str, user_id: Optional[str] = None) -> bool:
    """Delete a document and all its indexed chunks from PostgreSQL and clean up stale hashes."""
    sid_str = str(session_id)
    doc_id_str = str(document_name_or_id)

    # Check if doc_id_str is a valid UUID string to prevent PostgreSQL UUID type mismatch errors
    is_uuid = False
    try:
        import uuid
        uuid.UUID(doc_id_str)
        is_uuid = True
    except ValueError:
        is_uuid = False

    id_clause = "(id = :doc_id OR filename = :doc_id OR doc_hash = :doc_id)" if is_uuid else "(filename = :doc_id OR doc_hash = :doc_id)"

    with engine.begin() as conn:
        # 1. Mandatory ownership verification when user_id is supplied
        if user_id:
            uid_str = str(user_id)
            owner_check = conn.execute(
                sql_text(f"""
                    SELECT 1 FROM workspace_sessions WHERE id = :sid AND user_id = :uid
                    UNION
                    SELECT 1 FROM session_documents WHERE session_id = :sid AND {id_clause} AND user_id = :uid
                    UNION
                    SELECT 1 FROM chat_sessions WHERE id = :sid AND user_id = :uid
                """),
                {"sid": sid_str, "doc_id": doc_id_str, "uid": uid_str}
            ).fetchone()
            if not owner_check:
                return False

            statement = sql_text(f"""
                DELETE FROM session_documents
                WHERE session_id = :session_id
                  AND {id_clause}
                  AND user_id = :user_id
            """)
            res = conn.execute(statement, {
                "session_id": sid_str,
                "doc_id": doc_id_str,
                "user_id": uid_str,
            })
        else:
            statement = sql_text(f"""
                DELETE FROM session_documents
                WHERE session_id = :session_id
                  AND {id_clause}
            """)
            res = conn.execute(statement, {
                "session_id": sid_str,
                "doc_id": doc_id_str,
            })

        deleted = (res.rowcount or 0) > 0

    # 2. ONLY delete vector/FTS chunks after session document ownership & metadata deletion is verified!
    if deleted:
        pg_fts_store.delete_session_document(sid_str, doc_id_str)

    return deleted


# ─── Workspace Sessions Registry (workspace_sessions) ─────────────────────────

def list_registry_sessions(user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """List study sessions from workspace_sessions table with document counts and document metadata."""
    filter_clause = "WHERE s.user_id = :user_id OR s.user_id IS NULL" if user_id else ""

    statement = sql_text(f"""
        SELECT s.id, s.user_id, s.title, s.subject, s.created_at, s.last_active,
               s.topics_count AS topic_count, s.messages_count AS message_count
        FROM workspace_sessions s
        {filter_clause}
        ORDER BY s.last_active DESC
    """)

    params = {"user_id": str(user_id)} if user_id else {}
    with engine.connect() as conn:
        rows = conn.execute(statement, params).mappings().fetchall()

    if not rows:
        return []

    session_ids = [str(r["id"]) for r in rows if r.get("id")]
    docs_by_session: Dict[str, List[str]] = {sid: [] for sid in session_ids}
    if session_ids:
        try:
            with engine.connect() as conn:
                doc_stmt = sql_text("""
                    SELECT session_id, filename
                    FROM session_documents
                    WHERE session_id IN :sids
                    ORDER BY created_at ASC
                """).bindparams(bindparam("sids", expanding=True))
                doc_rows = conn.execute(doc_stmt, {"sids": session_ids}).fetchall()

                for d_sid, d_fn in doc_rows:
                    if d_fn and str(d_sid) in docs_by_session:
                        docs_by_session[str(d_sid)].append(d_fn)
        except Exception as e:
            logger.warning(f"[list_registry_sessions] Batch document fetch notice: {e}")

    sessions = []
    for r in rows:
        s = dict(r)
        sid = str(s["id"])
        doc_names = docs_by_session.get(sid, [])
        s["status"] = "ready"
        s["document_name"] = doc_names[0] if doc_names else ""
        s["documents"] = doc_names
        s["document_count"] = len(doc_names)
        sessions.append(s)
    return sessions


def get_registry_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Fetch session metadata by session_id with accurate document metadata."""
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
        docs = get_session_documents(session_id)
        doc_names = [d["filename"] for d in docs if d.get("filename")]
        s["status"] = "ready"
        s["document_name"] = doc_names[0] if doc_names else ""
        s["documents"] = doc_names
        s["document_count"] = len(doc_names)
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
    """Idempotently register or update a workspace session in PostgreSQL in a single atomic UPSERT."""
    now_str = datetime.now(timezone.utc).isoformat()
    clean_title = title or f"{subject} Study Session"

    # Single-query atomic insert or update preserving non-generic titles
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
            title = CASE
                WHEN workspace_sessions.title IS NOT NULL
                     AND workspace_sessions.title NOT IN ('New Study Workspace', 'General Study Study Session', 'General Study (High School)', 'General Study', 'New Course Workspace')
                THEN workspace_sessions.title
                ELSE COALESCE(:title, workspace_sessions.title)
            END,
            subject = COALESCE(:subject, workspace_sessions.subject),
            last_active = :now,
            topics_count = COALESCE(:topic_count, workspace_sessions.topics_count),
            messages_count = COALESCE(:message_count, workspace_sessions.messages_count)
        RETURNING title, user_id, topics_count, messages_count;
    """)

    with engine.begin() as conn:
        res = conn.execute(statement, {
            "id": str(session_id),
            "user_id": str(user_id) if user_id else None,
            "title": clean_title,
            "subject": subject,
            "now": now_str,
            "topic_count": topic_count,
            "message_count": message_count,
        }).mappings().first()

    final_title = res["title"] if res else clean_title
    final_uid = res["user_id"] if res else user_id

    docs = get_session_documents(session_id)
    doc_count = len(docs)
    doc_names = [d.get("filename") for d in docs if d.get("filename")]

    return {
        "id": str(session_id),
        "user_id": final_uid,
        "title": final_title,
        "subject": subject,
        "status": status,
        "document_name": document_name or (docs[0]["filename"] if docs else ""),
        "document_count": doc_count,
        "documents": doc_names,
        "document_records": docs,
        "created_at": now_str,
        "last_active": now_str,
        "topic_count": (res["topics_count"] if res else topic_count) or 0,
        "message_count": (res["messages_count"] if res else message_count) or 0,
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
    """Delete a workspace session and all linked data in a single batch round-trip."""
    # Sanitize session_id to prevent path traversal
    if not session_id or not re.match(r"^[a-zA-Z0-9_\-\.]+$", str(session_id)) or ".." in str(session_id):
        return False

    sid_str = str(session_id)

    delete_targets = [
        ("document_chunks", "session_id"),
        ("workspace_messages", "session_id"),
        ("workspace_topics", "session_id"),
        ("study_session_messages", "session_id"),
        ("study_session_topics", "session_id"),
        ("session_documents", "session_id"),
        ("workspace_sessions", "id"),
        ("chat_messages", "session_id"),
        ("chat_sessions", "id"),
        ("documents", "topic_id"),
    ]

    with engine.begin() as conn:
        # Mandatory fail-closed ownership verification inside transaction
        if user_id:
            uid_str = str(user_id)
            ws_owner = conn.execute(
                sql_text("SELECT user_id FROM workspace_sessions WHERE id = :sid"),
                {"sid": sid_str}
            ).fetchone()

            cs_owner = conn.execute(
                sql_text("SELECT user_id FROM chat_sessions WHERE id = :sid"),
                {"sid": sid_str}
            ).fetchone()

            is_valid_owner = False
            if ws_owner is not None and ws_owner[0] is not None and str(ws_owner[0]) == uid_str:
                is_valid_owner = True
            elif cs_owner is not None and cs_owner[0] is not None and str(cs_owner[0]) == uid_str:
                is_valid_owner = True

            # Fail-closed: reject if no record exists, owner is null, or owner does not match user_id
            if not is_valid_owner:
                return False

        deleted = False
        for tbl, col in delete_targets:
            try:
                with conn.begin_nested():
                    res = conn.execute(sql_text(f"DELETE FROM {tbl} WHERE {col} = :sid"), {"sid": sid_str})
                    if (res.rowcount or 0) > 0:
                        deleted = True
            except Exception:
                pass

    try:
        import shutil
        safe_sid = os.path.basename(sid_str)
        for base_dir in [DATA_DIR / "uploads", SESSIONS_DIR]:
            target_path = (base_dir / safe_sid).resolve()
            if str(target_path).startswith(str(base_dir.resolve())) and target_path.exists():
                shutil.rmtree(target_path, ignore_errors=True)
    except Exception:
        pass

    return deleted


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
        SELECT id, session_id, topic_id, topic_title, status, diagnostic_question,
               diagnostic_answer, diagnostic_level, current_phase, current_segment_index,
               accumulated_notes_markdown, teach_back_prompt, teach_back_submission,
               teach_back_grade_json, created_at, updated_at
        FROM lecture_sessions
        WHERE session_id = :session_id AND (id = :lecture_id OR topic_id = :lecture_id)
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
        WHERE session_id = :session_id AND (id = :lecture_id OR topic_id = :lecture_id)
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
