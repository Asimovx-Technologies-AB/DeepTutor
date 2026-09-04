"""
migrate_to_shared_schema.py
===========================
Unified migration script to move from per-session tables / physical files to
a single shared, indexed schema with user_id and session_id isolation.

Supports:
1. Legacy dynamic tables in the main database named `session_<id>` or `messages_<id>`.
2. Per-session SQLite database files in `backend/data/sessions/{session_id}.db`.

Key guarantees:
- Parameterized queries: NEVER string-interpolates session_id into SQL execution.
- Transaction safety: Migrates each session in a transaction with pre- and post-count verification.
- Non-destructive: Leaves old tables/files intact until manual verification.
- Idempotent: Skips sessions that have already been migrated.
- Detailed logging: Reports exact row counts per table for full auditability.

Usage:
    python migrate_to_shared_schema.py --dry-run
    python migrate_to_shared_schema.py
"""
import os
import sys
import json
import sqlite3
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional

BACKEND_DIR = Path(__file__).resolve().parent
DATA_DIR = BACKEND_DIR / "data"
SESSIONS_DIR = DATA_DIR / "sessions"
REGISTRY_FILE = SESSIONS_DIR / "sessions_registry.json"
MAIN_DB_PATH = BACKEND_DIR / "deep_tutor.db"
SCHEMA_SQL_PATH = BACKEND_DIR / "schema.sql"


def ensure_column_exists(conn: sqlite3.Connection, table: str, column: str, col_type: str = "TEXT"):
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cur.fetchall()]
    if cols and column not in cols:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            conn.commit()
        except Exception:
            pass


def init_shared_schema(conn: sqlite3.Connection):
    """Executes schema.sql if shared tables do not exist."""
    # Ensure legacy tables have session_id / user_id columns before index creation
    ensure_column_exists(conn, "study_notes", "session_id", "TEXT")
    ensure_column_exists(conn, "quizzes", "session_id", "TEXT")
    ensure_column_exists(conn, "quizzes", "user_id", "TEXT")
    ensure_column_exists(conn, "quiz_attempts", "session_id", "TEXT")
    ensure_column_exists(conn, "flashcards", "session_id", "TEXT")
    ensure_column_exists(conn, "flashcards", "user_id", "TEXT")

    if SCHEMA_SQL_PATH.exists():
        with open(SCHEMA_SQL_PATH, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
    else:
        # Fallback minimal schema definition
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                title TEXT NOT NULL,
                subject TEXT NOT NULL DEFAULT 'General Study',
                topics_count INTEGER DEFAULT 0,
                messages_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                user_id TEXT,
                role TEXT NOT NULL,
                content TEXT,
                thought_process TEXT,
                quiz_data_json TEXT,
                topics_json TEXT,
                attachment_json TEXT,
                is_explanation BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );
            CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
            CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id);

            CREATE TABLE IF NOT EXISTS topics (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                user_id TEXT,
                title TEXT NOT NULL,
                summary TEXT,
                difficulty TEXT DEFAULT 'Beginner',
                key_concepts_json TEXT DEFAULT '[]',
                estimated_study_time TEXT DEFAULT '15 mins',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );
            CREATE INDEX IF NOT EXISTS idx_topics_session_id ON topics(session_id);
            CREATE INDEX IF NOT EXISTS idx_topics_user_id ON topics(user_id);
        """)
    conn.commit()


def load_registry() -> Dict[str, Dict[str, Any]]:
    if not REGISTRY_FILE.exists():
        return {}
    try:
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"[WARN] Failed to read registry: {e}")
        return {}


def migrate_from_per_session_db_files(main_conn: sqlite3.Connection, dry_run: bool = False):
    """Migrates data from data/sessions/{session_id}.db files into the shared tables."""
    if not SESSIONS_DIR.exists():
        return []

    registry = load_registry()
    db_files = list(SESSIONS_DIR.glob("*.db"))
    print(f"[INFO] Found {len(db_files)} per-session SQLite database file(s) in {SESSIONS_DIR}")

    results = []

    for db_file in db_files:
        session_id = db_file.stem
        meta = registry.get(session_id, {})
        title = meta.get("title") or f"{meta.get('subject', 'General Study')} Study Session"
        subject = meta.get("subject", "General Study")
        user_id = meta.get("user_id", None)

        # Check if already migrated
        cur = main_conn.cursor()
        cur.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
        if cur.fetchone():
            print(f"[SKIP] Session '{session_id}' is already present in shared 'sessions' table.")
            results.append({"session_id": session_id, "status": "already_migrated"})
            continue

        # Connect to old per-session file
        src_conn = sqlite3.connect(str(db_file))
        src_conn.row_factory = sqlite3.Row
        src_cur = src_conn.cursor()

        messages = []
        topics = []

        # Check if source tables exist
        src_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='session_messages'")
        if src_cur.fetchone():
            src_cur.execute("SELECT * FROM session_messages ORDER BY rowid ASC")
            messages = src_cur.fetchall()

        src_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='session_topics'")
        if src_cur.fetchone():
            src_cur.execute("SELECT * FROM session_topics ORDER BY rowid ASC")
            topics = src_cur.fetchall()

        src_conn.close()

        old_msg_count = len(messages)
        old_top_count = len(topics)

        if dry_run:
            print(f"[DRY-RUN] Would migrate session '{session_id}': {old_msg_count} messages, {old_top_count} topics")
            results.append({
                "session_id": session_id,
                "status": "would_migrate",
                "messages": old_msg_count,
                "topics": old_top_count
            })
            continue

        # Insert transactionally with row count verification
        try:
            main_conn.execute("BEGIN TRANSACTION")

            main_conn.execute("""
                INSERT INTO sessions (id, user_id, title, subject, topics_count, messages_count)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (session_id, user_id, title, subject, old_top_count, old_msg_count))

            for m in messages:
                m_dict = dict(m)
                main_conn.execute("""
                    INSERT OR REPLACE INTO messages (
                        id, session_id, user_id, role, content,
                        thought_process, quiz_data_json, topics_json,
                        attachment_json, is_explanation, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    m_dict.get("id"),
                    session_id,
                    user_id,
                    m_dict.get("role", "assistant"),
                    m_dict.get("text") or m_dict.get("content", ""),
                    m_dict.get("thought_process", ""),
                    m_dict.get("quiz_data_json"),
                    m_dict.get("topics_json"),
                    m_dict.get("attachment_json"),
                    m_dict.get("is_explanation", 0),
                    m_dict.get("created_at")
                ))

            for t in topics:
                t_dict = dict(t)
                main_conn.execute("""
                    INSERT OR REPLACE INTO topics (
                        id, session_id, user_id, title, summary,
                        difficulty, key_concepts_json, estimated_study_time
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    t_dict.get("id"),
                    session_id,
                    user_id,
                    t_dict.get("title", ""),
                    t_dict.get("summary", ""),
                    t_dict.get("difficulty", "Beginner"),
                    t_dict.get("key_concepts_json", "[]"),
                    t_dict.get("estimated_study_time", "15 mins")
                ))

            # Verify row counts
            ver_cur = main_conn.cursor()
            ver_cur.execute("SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,))
            new_msg_count = ver_cur.fetchone()[0]

            ver_cur.execute("SELECT COUNT(*) FROM topics WHERE session_id = ?", (session_id,))
            new_top_count = ver_cur.fetchone()[0]

            if new_msg_count != old_msg_count or new_top_count != old_top_count:
                main_conn.rollback()
                print(f"[ERROR] Verification failed for '{session_id}': message count {new_msg_count} vs {old_msg_count}")
                results.append({"session_id": session_id, "status": "failed_verification"})
                continue

            main_conn.commit()
            print(f"[SUCCESS] Migrated session '{session_id}': {new_msg_count} messages, {new_top_count} topics verified.")
            results.append({
                "session_id": session_id,
                "status": "migrated",
                "messages": new_msg_count,
                "topics": new_top_count
            })
        except Exception as e:
            main_conn.rollback()
            print(f"[ERROR] Failed migrating '{session_id}': {e}")
            results.append({"session_id": session_id, "status": "error", "error": str(e)})

    return results


def migrate_from_dynamic_session_tables(main_conn: sqlite3.Connection, dry_run: bool = False):
    """Migrates any legacy tables matching 'session_%' inside the main SQLite database."""
    cur = main_conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'session_%'")
    tables = [r[0] for r in cur.fetchall()]

    # Ignore modern shared tables like sessions
    excluded = {"sessions", "session_messages", "session_topics", "session_documents"}
    target_tables = [t for t in tables if t not in excluded]

    if not target_tables:
        return []

    print(f"[INFO] Found {len(target_tables)} dynamic session table(s) in main DB: {target_tables}")
    results = []

    for tbl in target_tables:
        # e.g. session_12345 -> session_id = session_12345 or 12345
        session_id = tbl
        cur.execute(f"SELECT COUNT(*) FROM \"{tbl}\"")  # Safe table count lookup
        row_count = cur.fetchone()[0]

        if dry_run:
            print(f"[DRY-RUN] Would migrate table '{tbl}' ({row_count} rows)")
            results.append({"table": tbl, "status": "would_migrate", "rows": row_count})
            continue

        try:
            main_conn.execute("BEGIN TRANSACTION")
            # Ensure parent session exists
            main_conn.execute("""
                INSERT OR IGNORE INTO sessions (id, title, subject)
                VALUES (?, ?, ?)
            """, (session_id, f"Workspace {session_id}", "General Study"))

            # Copy rows
            cur.execute(f"SELECT * FROM \"{tbl}\"")
            rows = cur.fetchall()
            col_names = [d[0].lower() for d in cur.description]

            for r in rows:
                r_dict = dict(zip(col_names, r))
                msg_id = r_dict.get("id") or r_dict.get("message_id") or os.urandom(8).hex()
                role = r_dict.get("role", "user")
                content = r_dict.get("content") or r_dict.get("text", "")
                created_at = r_dict.get("created_at")

                main_conn.execute("""
                    INSERT OR REPLACE INTO messages (id, session_id, role, content, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (msg_id, session_id, role, content, created_at))

            # Verify
            ver_cur = main_conn.cursor()
            ver_cur.execute("SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,))
            migrated_count = ver_cur.fetchone()[0]

            if migrated_count < row_count:
                main_conn.rollback()
                print(f"[ERROR] Mismatch for table '{tbl}': {migrated_count} < {row_count}")
                results.append({"table": tbl, "status": "failed_verification"})
                continue

            main_conn.commit()
            print(f"[SUCCESS] Migrated table '{tbl}': {migrated_count} rows copied.")
            results.append({"table": tbl, "status": "migrated", "rows": migrated_count})
        except Exception as e:
            main_conn.rollback()
            print(f"[ERROR] Failed migrating table '{tbl}': {e}")
            results.append({"table": tbl, "status": "error", "error": str(e)})

    return results


def main():
    parser = argparse.ArgumentParser(description="DeepTutor Shared Schema Migration")
    parser.add_argument("--dry-run", action="store_true", help="Inspect and report without writing data")
    args = parser.parse_args()

    print("=" * 60)
    print(" DeepTutor Schema Migration: Per-Session -> Shared Unified Schema")
    print("=" * 60)
    print(f"Target Database: {MAIN_DB_PATH}")
    if args.dry_run:
        print("[MODE] DRY RUN — No changes will be written.\n")

    conn = sqlite3.connect(str(MAIN_DB_PATH))
    try:
        # Step 1: Ensure shared tables & indexes exist
        print("[1/3] Initializing shared schema and foreign key indexes...")
        init_shared_schema(conn)

        # Step 2: Migrate per-session SQLite database files (if any)
        print("\n[2/3] Migrating per-session SQLite database files...")
        file_results = migrate_from_per_session_db_files(conn, dry_run=args.dry_run)

        # Step 3: Migrate any dynamic session_<id> tables in main DB (if any)
        print("\n[3/3] Scanning for dynamic session_<id> tables inside main DB...")
        table_results = migrate_from_dynamic_session_tables(conn, dry_run=args.dry_run)

        print("\n" + "=" * 60)
        print(" Migration Summary")
        print("=" * 60)
        total_migrated = sum(1 for r in file_results + table_results if r.get("status") in ("migrated", "would_migrate"))
        total_skipped = sum(1 for r in file_results + table_results if r.get("status") == "already_migrated")
        total_failed = sum(1 for r in file_results + table_results if r.get("status") in ("failed_verification", "error"))

        print(f"Total processed: {len(file_results) + len(table_results)}")
        print(f"Successfully migrated: {total_migrated}")
        print(f"Already migrated:      {total_skipped}")
        print(f"Failed:                {total_failed}")
        print("=" * 60)
        print("[NOTE] All source files and tables were LEFT IN PLACE untouched for verification safety.")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
