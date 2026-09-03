"""
Migrates workspace-session data out of the per-session physical SQLite files
(backend/data/sessions/{session_id}.db) and into the shared workspace_sessions /
workspace_messages / workspace_topics tables in the main app database.

WHAT THIS DOES:
  - Reads backend/data/sessions/sessions_registry.json for session metadata.
  - Also scans backend/data/sessions/*.db directly, in case a session's
    physical file exists without a matching registry entry (or vice versa).
  - For each session, reads session_messages / session_topics from the
    physical file and inserts them into the shared tables via the app's
    normal SQLAlchemy engine (same DB used by database.py — SQLite or
    Postgres, whichever DATABASE_URL points to).
  - Verifies row counts (old file vs. new shared tables) before considering
    a session "migrated". Mismatches are rolled back and reported, not
    silently accepted.
  - Idempotent: re-running skips sessions that already exist in
    workspace_sessions.

WHAT THIS DOES NOT DO:
  - Does NOT touch document_fts (the FTS5 search index) — that's owned by
    app/rag/sqlite_fts_store.py, not this migration.
  - Does NOT delete or modify the original .db files or the registry.
    Nothing is destructive. Once you've spot-checked the shared tables,
    archive/delete backend/data/sessions/ yourself.
  - Does NOT assign a user_id — these sessions were never linked to a user
    (confirmed), so they migrate with user_id = NULL. They won't appear
    under any user's get_user_sessions() until claimed some other way.

USAGE:
    cd backend
    python migrate_workspace_sessions.py
    python migrate_workspace_sessions.py --dry-run   # report only, no writes
"""
import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.database import SessionLocal, engine
from app.core.models import Base, WorkspaceSession, WorkspaceMessage, WorkspaceTopic

DATA_DIR = Path(__file__).resolve().parent / "data"
SESSIONS_DIR = DATA_DIR / "sessions"
REGISTRY_FILE = SESSIONS_DIR / "sessions_registry.json"

# Session IDs are generated as f"session_{timestamp_ms}" by SessionManager.
# Validate before building any file path from one, defensively.
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


def load_registry() -> Dict[str, Dict[str, Any]]:
    if not REGISTRY_FILE.exists():
        return {}
    try:
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] Could not read registry file: {e}")
        return {}


def discover_session_ids(registry: Dict[str, Dict[str, Any]]) -> List[str]:
    ids = set(registry.keys())
    if SESSIONS_DIR.exists():
        for db_file in SESSIONS_DIR.glob("*.db"):
            sid = db_file.stem
            if sid not in ids:
                print(f"[WARN] Found {db_file.name} with no registry entry — will migrate with default metadata")
            ids.add(sid)
    return sorted(ids)


def table_exists(cursor: sqlite3.Cursor, table_name: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return cursor.fetchone() is not None


def read_physical_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Reads session_messages and session_topics from the per-session .db file.
    Returns None if the file doesn't exist. Never string-interpolates session_id
    into SQL — it's only used to build the filesystem path, and only after
    passing SESSION_ID_RE.
    """
    if not SESSION_ID_RE.match(session_id):
        print(f"[SKIP] Session id '{session_id}' has unexpected characters, refusing to build a path from it")
        return None

    db_path = SESSIONS_DIR / f"{session_id}.db"
    if not db_path.exists():
        return None

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    messages: List[sqlite3.Row] = []
    topics: List[sqlite3.Row] = []

    if table_exists(cursor, "session_messages"):
        cursor.execute("SELECT * FROM session_messages ORDER BY rowid ASC")
        messages = cursor.fetchall()

    if table_exists(cursor, "session_topics"):
        cursor.execute("SELECT * FROM session_topics ORDER BY rowid ASC")
        topics = cursor.fetchall()

    conn.close()
    return {"messages": messages, "topics": topics}


def row_get(row: sqlite3.Row, key: str, default=None):
    try:
        return row[key] if key in row.keys() else default
    except Exception:
        return default


def migrate_session(
    db,
    session_id: str,
    meta: Dict[str, Any],
    physical: Dict[str, Any],
    dry_run: bool,
) -> Dict[str, Any]:
    result = {"session_id": session_id, "status": "skipped", "messages": 0, "topics": 0, "error": None}

    existing = db.query(WorkspaceSession).filter(WorkspaceSession.id == session_id).first()
    if existing:
        result["status"] = "already_migrated"
        return result

    old_msg_count = len(physical["messages"])
    old_topic_count = len(physical["topics"])

    if dry_run:
        result["status"] = "would_migrate"
        result["messages"] = old_msg_count
        result["topics"] = old_topic_count
        return result

    try:
        ws = WorkspaceSession(
            id=session_id,
            user_id=None,  # unclaimed — these sessions were never user-linked
            title=meta.get("title") or f"{meta.get('subject', 'General Study')} Study Session",
            subject=meta.get("subject", "General Study"),
            created_at=meta.get("created_at"),
            last_active=meta.get("last_active"),
            topics_count=old_topic_count,
            messages_count=old_msg_count,
        )
        db.add(ws)
        db.flush()

        for m in physical["messages"]:
            wm = WorkspaceMessage(
                id=row_get(m, "id"),
                session_id=session_id,
                role=row_get(m, "role", "assistant"),
                text=row_get(m, "text"),
                thought_process=row_get(m, "thought_process"),
                is_explanation=bool(row_get(m, "is_explanation", 0)),
                created_at=str(row_get(m, "created_at") or ""),
            )
            wm._quiz_data = row_get(m, "quiz_data_json")
            wm._topics = row_get(m, "topics_json")
            wm._attachment = row_get(m, "attachment_json")
            db.add(wm)

        for t in physical["topics"]:
            wt = WorkspaceTopic(
                id=row_get(t, "id"),
                session_id=session_id,
                title=row_get(t, "title"),
                summary=row_get(t, "summary"),
                difficulty=row_get(t, "difficulty", "Beginner"),
                estimated_study_time=row_get(t, "estimated_study_time", "15 mins"),
            )
            wt._key_concepts = row_get(t, "key_concepts_json", "[]")
            db.add(wt)

        db.flush()

        # Verify before committing
        new_msg_count = db.query(WorkspaceMessage).filter(WorkspaceMessage.session_id == session_id).count()
        new_topic_count = db.query(WorkspaceTopic).filter(WorkspaceTopic.session_id == session_id).count()

        if new_msg_count != old_msg_count or new_topic_count != old_topic_count:
            db.rollback()
            result["status"] = "failed_verification"
            result["error"] = (
                f"count mismatch: messages old={old_msg_count} new={new_msg_count}, "
                f"topics old={old_topic_count} new={new_topic_count}"
            )
            return result

        db.commit()
        result["status"] = "migrated"
        result["messages"] = new_msg_count
        result["topics"] = new_topic_count
        return result

    except Exception as e:
        db.rollback()
        result["status"] = "error"
        result["error"] = str(e)
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Report what would migrate, write nothing")
    args = parser.parse_args()

    print(f"[INFO] Sessions dir: {SESSIONS_DIR}")
    print(f"[INFO] Target DB engine: {engine.url}")
    if args.dry_run:
        print("[INFO] DRY RUN — no data will be written")

    # Ensure the new shared tables exist (harmless if they already do)
    Base.metadata.create_all(bind=engine)

    registry = load_registry()
    session_ids = discover_session_ids(registry)
    print(f"[INFO] Found {len(session_ids)} session id(s) to consider\n")

    db = SessionLocal()
    results = []
    try:
        for session_id in session_ids:
            meta = registry.get(session_id, {})
            physical = read_physical_session(session_id)
            if physical is None:
                print(f"[SKIP] {session_id}: no physical .db file found")
                continue

            r = migrate_session(db, session_id, meta, physical, args.dry_run)
            results.append(r)

            if r["status"] in ("migrated", "would_migrate"):
                print(f"[OK] {session_id}: {r['status']} — messages={r['messages']} topics={r['topics']}")
            elif r["status"] == "already_migrated":
                print(f"[SKIP] {session_id}: already migrated")
            else:
                print(f"[FAIL] {session_id}: {r['status']} — {r['error']}")
    finally:
        db.close()

    migrated = [r for r in results if r["status"] in ("migrated", "would_migrate")]
    failed = [r for r in results if r["status"] in ("failed_verification", "error")]
    skipped = [r for r in results if r["status"] == "already_migrated"]

    print("\n" + "=" * 60)
    print(f"Total considered:  {len(results)}")
    print(f"Migrated:          {len(migrated)}")
    print(f"Already migrated:  {len(skipped)}")
    print(f"Failed:            {len(failed)}")
    if failed:
        print("\nFailed sessions:")
        for r in failed:
            print(f"  - {r['session_id']}: {r['error']}")
    print("=" * 60)

    if not args.dry_run:
        print(
            "\nOriginal files under backend/data/sessions/ were NOT modified or deleted. "
            "Spot-check the workspace_sessions / workspace_messages / workspace_topics "
            "tables, then archive or remove the old files yourself when you're confident."
        )

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
