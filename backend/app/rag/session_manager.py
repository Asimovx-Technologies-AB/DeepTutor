"""
Multi-Session Workspace Manager — shared-schema version.

Session messages/topics now live in the shared workspace_sessions /
workspace_messages / workspace_topics tables (see app/core/models.py),
filtered by session_id and, where available, user_id. This replaces the
old one-physical-SQLite-file-per-session design.

NOTE: The physical file at backend/data/sessions/{session_id}.db still
exists and is still created — but now it holds ONLY the document_fts
search index, which is owned by app/rag/sqlite_fts_store.py. This module
no longer reads or writes session_messages/session_topics there.

Existing sessions from before the migration have user_id = NULL (they were
never linked to a user). get_session_data() will not return a session it
can't verify a user_id match for, so old unclaimed sessions won't surface
through user-scoped lookups until they're explicitly claimed.
"""
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.rag.sqlite_fts_store import close_session_store
from app.core.database import SessionLocal
from app.core.models import WorkspaceSession, WorkspaceMessage, WorkspaceTopic

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

SESSIONS_DIR = DATA_DIR / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


class SessionManager:
    """Manages the lifecycle and metadata for study sessions via the shared DB."""

    # ── physical file: FTS index only ───────────────────────────────────
    def get_session_db_path(self, session_id: str) -> Path:
        """Physical SQLite file path — now used only for the FTS5 index."""
        return SESSIONS_DIR / f"{session_id}.db"

    def init_session_database(self, session_id: str):
        """Initializes the physical SQLite file's FTS5 table only.
        session_messages/session_topics no longer live here — see
        workspace_messages/workspace_topics in the shared DB instead.
        """
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
        conn.commit()
        conn.close()

    # ── session lifecycle ────────────────────────────────────────────────
    def create_session(
        self,
        subject: Optional[str] = None,
        title: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Creates a new session in the shared DB and initializes its FTS file.

        user_id defaults to None for backward compatibility with existing
        call sites. Update callers (e.g. api/chat.py) to pass the logged-in
        user's id so new sessions are actually owned by someone.
        """
        session_id = f"session_{int(datetime.now().timestamp() * 1000)}"
        self.init_session_database(session_id)

        clean_sub = (subject or "General Study").strip()
        clean_title = (title or f"{clean_sub} Study Session").strip()
        now = datetime.now().isoformat()

        db = SessionLocal()
        try:
            ws = WorkspaceSession(
                id=session_id,
                user_id=user_id,
                title=clean_title,
                subject=clean_sub,
                created_at=now,
                last_active=now,
                topics_count=0,
                messages_count=0,
            )
            db.add(ws)
            db.commit()
        finally:
            db.close()

        return {
            "session_id": session_id,
            "user_id": user_id,
            "title": clean_title,
            "subject": clean_sub,
            "created_at": now,
            "last_active": now,
            "topics_count": 0,
            "messages_count": 0,
        }

    def _session_to_meta(self, ws: WorkspaceSession) -> Dict[str, Any]:
        return {
            "session_id": ws.id,
            "user_id": ws.user_id,
            "title": ws.title,
            "subject": ws.subject,
            "created_at": ws.created_at,
            "last_active": ws.last_active,
            "topics_count": ws.topics_count,
            "messages_count": ws.messages_count,
        }

    def list_sessions(self) -> List[Dict[str, Any]]:
        """Returns all sessions ordered by last active descending.
        Kept for backward compatibility — prefer get_user_sessions() for
        anything user-facing.
        """
        db = SessionLocal()
        try:
            rows = db.query(WorkspaceSession).order_by(WorkspaceSession.last_active.desc()).all()
            return [self._session_to_meta(w) for w in rows]
        finally:
            db.close()

    def get_user_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        """Returns all sessions belonging to a specific user, most recent first."""
        db = SessionLocal()
        try:
            rows = (
                db.query(WorkspaceSession)
                .filter(WorkspaceSession.user_id == user_id)
                .order_by(WorkspaceSession.last_active.desc())
                .all()
            )
            return [self._session_to_meta(w) for w in rows]
        finally:
            db.close()

    def get_session_meta(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Gets metadata for a specific session (no ownership check)."""
        db = SessionLocal()
        try:
            ws = db.query(WorkspaceSession).filter(WorkspaceSession.id == session_id).first()
            return self._session_to_meta(ws) if ws else None
        finally:
            db.close()

    def get_session_data(self, user_id: str, session_id: str) -> Optional[Dict[str, Any]]:
        """Returns full session data (meta + messages + topics) ONLY if it
        belongs to user_id. Returns None for sessions owned by someone else,
        and for unclaimed legacy sessions (user_id is NULL) — those can't be
        verified as belonging to this user, so they're excluded rather than
        guessed at.
        """
        db = SessionLocal()
        try:
            ws = (
                db.query(WorkspaceSession)
                .filter(WorkspaceSession.id == session_id, WorkspaceSession.user_id == user_id)
                .first()
            )
            if not ws:
                return None
            return self._load_state_for(db, ws)
        finally:
            db.close()

    def update_session_meta(self, session_id: str, updates: Dict[str, Any]):
        """Updates metadata such as title, subject, or counts, creating entry if not present."""
        db = SessionLocal()
        try:
            ws = db.query(WorkspaceSession).filter(WorkspaceSession.id == session_id).first()
            now = datetime.now().isoformat()
            if not ws:
                clean_sub = updates.get("subject") or "General Study"
                clean_title = updates.get("title") or f"{clean_sub} Study Session"
                ws = WorkspaceSession(
                    id=session_id,
                    user_id=updates.get("user_id"),
                    title=clean_title,
                    subject=clean_sub,
                    created_at=now,
                    last_active=now,
                    topics_count=0,
                    messages_count=0,
                )
                db.add(ws)

            for key in ("title", "subject", "topics_count", "messages_count", "user_id"):
                if key in updates:
                    setattr(ws, key, updates[key])
            ws.last_active = now
            db.commit()
        finally:
            db.close()

    def delete_session(self, session_id: str) -> bool:
        """Permanently deletes a session and its shared-DB rows, plus the
        physical FTS file.
        """
        db = SessionLocal()
        try:
            ws = db.query(WorkspaceSession).filter(WorkspaceSession.id == session_id).first()
            if ws:
                db.delete(ws)  # cascades to workspace_messages / workspace_topics
                db.commit()
        finally:
            db.close()

        close_session_store(session_id)

        db_path = self.get_session_db_path(session_id)
        if db_path.exists():
            try:
                db_path.unlink()
            except Exception as e:
                print(f"[SessionManager] Error deleting FTS file {db_path}: {e}")
        return True

    # ── state save/load ─────────────────────────────────────────────────
    def save_session_state(
        self,
        session_id: str,
        messages: Optional[List[Dict[str, Any]]] = None,
        topics: Optional[List[Dict[str, Any]]] = None,
        subject: Optional[str] = None,
        title: Optional[str] = None,
    ):
        """Persists chat messages and extracted topics into the shared DB,
        replacing whatever was previously stored for this session_id
        (same replace-all semantics as the old per-file version).

        NOTE: the previous S3 whole-database-file backup is gone — there's
        no longer a single file holding this session's app data to upload.
        If you still want cloud backup of workspace conversations, that
        needs a proper DB-level export/backup strategy, which is out of
        scope for this migration.
        """
        if not self.get_session_meta(session_id):
            self.init_session_database(session_id)

        db = SessionLocal()
        try:
            if messages is not None:
                db.query(WorkspaceMessage).filter(WorkspaceMessage.session_id == session_id).delete(
                    synchronize_session=False
                )
                for m in messages:
                    wm = WorkspaceMessage(
                        id=m.get("id", ""),
                        session_id=session_id,
                        role=m.get("role", "assistant"),
                        text=m.get("text", ""),
                        thought_process=m.get("thoughtProcess", ""),
                        is_explanation=bool(m.get("isExplanation")),
                        created_at=datetime.now().isoformat(),
                    )
                    wm.quiz_data = m.get("quizData")
                    wm.topics = m.get("topics")
                    wm.attachment = m.get("attachment")
                    db.add(wm)

            if topics is not None:
                db.query(WorkspaceTopic).filter(WorkspaceTopic.session_id == session_id).delete(
                    synchronize_session=False
                )
                for t in topics:
                    wt = WorkspaceTopic(
                        id=t.get("id", ""),
                        session_id=session_id,
                        title=t.get("title", ""),
                        summary=t.get("summary", ""),
                        difficulty=t.get("difficulty", "Beginner"),
                        estimated_study_time=t.get("estimated_study_time", "15 mins"),
                    )
                    wt.key_concepts = t.get("key_concepts", [])
                    db.add(wt)

            db.commit()
        finally:
            db.close()

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

    def _load_state_for(self, db, ws: WorkspaceSession) -> Dict[str, Any]:
        msg_rows = (
            db.query(WorkspaceMessage)
            .filter(WorkspaceMessage.session_id == ws.id)
            .order_by(WorkspaceMessage.created_at.asc())
            .all()
        )
        messages = [
            {
                "id": m.id,
                "role": m.role,
                "text": m.text,
                "thoughtProcess": m.thought_process,
                "quizData": m.quiz_data,
                "topics": m.topics,
                "attachment": m.attachment,
                "isExplanation": bool(m.is_explanation),
            }
            for m in msg_rows
        ]

        topic_rows = db.query(WorkspaceTopic).filter(WorkspaceTopic.session_id == ws.id).all()
        topics = [
            {
                "id": t.id,
                "title": t.title,
                "summary": t.summary,
                "difficulty": t.difficulty,
                "key_concepts": t.key_concepts,
                "estimated_study_time": t.estimated_study_time,
            }
            for t in topic_rows
        ]

        return {
            "meta": self._session_to_meta(ws),
            "messages": messages,
            "topics": topics,
        }

    def load_session_state(self, session_id: str) -> Dict[str, Any]:
        """Loads all saved messages, topics, and metadata (no ownership check —
        kept for backward compatibility with existing internal callers).
        """
        db = SessionLocal()
        try:
            ws = db.query(WorkspaceSession).filter(WorkspaceSession.id == session_id).first()
            if not ws:
                # Preserve old behavior: return an empty-but-valid shape
                # rather than raising, since callers didn't handle None before.
                return {
                    "meta": {
                        "session_id": session_id,
                        "title": "Study Session",
                        "subject": "General",
                    },
                    "messages": [],
                    "topics": [],
                }
            return self._load_state_for(db, ws)
        finally:
            db.close()

    def get_session_state(self, session_id: str) -> Dict[str, Any]:
        """Alias for load_session_state."""
        return self.load_session_state(session_id)


# Singleton instance
session_manager = SessionManager()