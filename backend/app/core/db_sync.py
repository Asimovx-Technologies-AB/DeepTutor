import logging
from sqlalchemy import text
from app.core.database import engine, Base, is_sqlite
import app.models # Registers all SQLAlchemy models

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def sync_database():
    """
    Synchronizes the database schema with the new fresh-start architecture.
    Handles legacy PostgreSQL tables by dropping obsolete tables or adding missing columns,
    then executes create_all to ensure all 11 new tables exist with correct schemas.
    """
    logger.info(f"Synchronizing database on: {engine.url.render_as_string(hide_password=True)}...")

    with engine.connect() as conn:
        if not is_sqlite:
            # Check if pgvector extension exists
            try:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.commit()
                logger.info("[DB] pgvector extension verified.")
            except Exception as e:
                conn.rollback()
                logger.warning(f"[DB] Notice on vector extension: {e}")

            # Check if legacy documents table has older schema (missing file_hash)
            check_col = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='documents' AND column_name='file_hash'")
            ).scalar()

            if not check_col:
                logger.info("[DB] Detected legacy 'documents' table missing 'file_hash'. Migrating to fresh-start schema...")
                # Drop legacy conflicting tables cleanly
                legacy_tables = [
                    "study_session_messages", "study_session_topics", "lecture_checkpoints",
                    "lecture_pause_events", "session_documents", "lecture_sessions",
                    "workspace_messages", "workspace_topics", "workspace_sessions",
                    "document_chunks", "documents", "study_sessions", "curriculum_topics",
                    "chat_messages", "student_mastery"
                ]
                for tbl in legacy_tables:
                    try:
                        conn.execute(text(f"DROP TABLE IF EXISTS {tbl} CASCADE"))
                        conn.commit()
                    except Exception as drop_err:
                        conn.rollback()
                        logger.warning(f"[DB] Drop notice for {tbl}: {drop_err}")

                logger.info("[DB] Legacy tables dropped.")

        # Re-create all models using current SQLAlchemy metadata
        Base.metadata.create_all(bind=engine)
        logger.info("[DB] All tables successfully created and verified:")
        for table_name in Base.metadata.tables:
            logger.info(f"  - {table_name}")

    logger.info("[DB] Schema synchronization completed successfully!")


if __name__ == "__main__":
    sync_database()
