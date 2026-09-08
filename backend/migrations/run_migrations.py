"""
DeepTutor Schema Migration Runner for PostgreSQL + pgvector.

Features:
- Connects via DATABASE_URL using psycopg2.
- Maintains idempotent schema_migrations tracking table.
- Executes each migration in its own atomic transaction.
- Verifies pgvector extension version and HNSW support before applying vector schema.
"""
import os
import sys
from pathlib import Path
import psycopg2

# Arbitrary but fixed key for pg_advisory_lock, so concurrent workers cannot
# apply the same migration twice.
MIGRATION_LOCK_ID = 8734512901

# Bounds for every database call made on the startup path.
CONNECT_TIMEOUT_SECONDS = 10
LOCK_TIMEOUT_SECONDS = 30
STATEMENT_TIMEOUT_SECONDS = 300

MIGRATIONS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = MIGRATIONS_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings


def check_azure_and_pgvector(conn):
    """Inspects target PostgreSQL instance for Azure extensions and pgvector version."""
    with conn.cursor() as cur:
        # 1. Check azure.extensions if on Azure Flexible Server
        try:
            cur.execute("SHOW azure.extensions;")
            row = cur.fetchone()
            print(f"[PREFLIGHT] azure.extensions: {row[0] if row else 'none'}")
        except Exception:
            conn.rollback()
            print("[PREFLIGHT] Note: Target DB is not Azure Flexible Server or azure.extensions is not exposed.")

        # 2. Ensure vector extension is installed and query its version
        try:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"[PREFLIGHT] Warning: Failed to create extension vector: {e}")

        try:
            cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector';")
            row = cur.fetchone()
            if row and row[0]:
                version = row[0]
                print(f"[PREFLIGHT] pgvector version installed: {version}")
                # Parse version tuple
                parts = version.split(".")
                major = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 0
                minor = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
                if (major, minor) < (0, 5):
                    print(
                        f"[PREFLIGHT] WARNING: pgvector version {version} < 0.5.0! "
                        "HNSW indexes require pgvector >= 0.5.0. Will fall back to IVFFlat if needed."
                    )
            else:
                print("[PREFLIGHT] Warning: pgvector extension not found in pg_extension.")
        except Exception as e:
            conn.rollback()
            print(f"[PREFLIGHT] Could not query pgvector extension version: {e}")


def init_tracking_table(conn):
    """Initializes the schema_migrations tracking table."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ DEFAULT now()
            );
        """)
    conn.commit()


def get_applied_migrations(conn):
    """Returns set of already applied migration filenames."""
    with conn.cursor() as cur:
        cur.execute("SELECT filename FROM schema_migrations;")
        return {row[0] for row in cur.fetchall()}


def run_migrations():
    settings = get_settings()
    db_url = settings.DATABASE_URL
    if db_url.startswith("sqlite"):
        print("[MIGRATION] SQLite in use; PostgreSQL migrations skipped.")
        return

    # Clean connection URL for psycopg2
    if db_url.startswith("postgresql+asyncpg://"):
        db_url = db_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    elif db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    print(f"[MIGRATION] Connecting to database: {db_url.split('@')[-1] if '@' in db_url else db_url}")
    # Every call here is bounded. An unreachable database or a lock held by
    # another replica must surface as a logged failure, never as a hang: this
    # runs inside a container whose readiness probe is counting.
    conn = psycopg2.connect(db_url, connect_timeout=CONNECT_TIMEOUT_SECONDS)

    try:
        with conn.cursor() as cur:
            cur.execute("SET lock_timeout = %s;", (f"{LOCK_TIMEOUT_SECONDS}s",))
            cur.execute("SET statement_timeout = %s;", (f"{STATEMENT_TIMEOUT_SECONDS}s",))
        conn.commit()

        # The API runs two Gunicorn workers and Container Apps may hold several
        # replicas, all of which call this on startup. A session-level advisory
        # lock serialises them: the first worker migrates, the rest find every
        # file already applied.
        #
        # pg_try_advisory_lock, not pg_advisory_lock: the blocking form waits
        # forever, and "forever" here means a replica that never reports ready.
        # Losing the race is a normal outcome — another worker is migrating —
        # so bail out quietly rather than queue behind it.
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s);", (MIGRATION_LOCK_ID,))
            got_lock = bool(cur.fetchone()[0])
        conn.commit()

        if not got_lock:
            print("[MIGRATION] Another worker holds the migration lock; skipping.")
            return

        check_azure_and_pgvector(conn)
        init_tracking_table(conn)
        applied = get_applied_migrations(conn)

        # Collect all .sql files in migrations directory
        sql_files = sorted([f for f in MIGRATIONS_DIR.glob("*.sql") if f.is_file()])

        for sql_file in sql_files:
            filename = sql_file.name
            if filename in applied:
                print(f"[MIGRATION] Skipping {filename} (already applied)")
                continue

            print(f"[MIGRATION] Applying {filename}...")
            content = sql_file.read_text(encoding="utf-8")

            # Execute within an atomic transaction per file
            try:
                with conn.cursor() as cur:
                    cur.execute(content)
                    cur.execute(
                        "INSERT INTO schema_migrations (filename) VALUES (%s);",
                        (filename,)
                    )
                conn.commit()
                print(f"[MIGRATION] Successfully applied {filename}")
            except Exception as e:
                conn.rollback()
                print(f"[MIGRATION] ERROR applying {filename}: {e}")
                raise

        print("[MIGRATION] All migrations are up to date.")
    finally:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s);", (MIGRATION_LOCK_ID,))
            conn.commit()
        except Exception:
            pass
        conn.close()


def safe_run_migrations() -> bool:
    """
    run_migrations() wrapped for application startup.

    Schema work must never be the reason a container fails to come up: an
    unreachable database at boot is usually transient (Container Apps scaling
    from zero against a burstable Postgres), and crashing the replica turns a
    slow start into a crash loop. Failures are logged loudly and the API starts
    anyway — the endpoints that need the new tables will surface the error.
    """
    try:
        run_migrations()
        return True
    except Exception as e:
        print(f"[MIGRATION] ERROR: schema migration failed: {e}")
        print("[MIGRATION] The API will start, but endpoints needing the new tables will fail.")
        return False


if __name__ == "__main__":
    run_migrations()
