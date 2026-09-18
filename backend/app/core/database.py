import logging
from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.core.config import settings

logger = logging.getLogger(__name__)

# Determine if we are using SQLite or PostgreSQL
is_sqlite = settings.DATABASE_URL.startswith("sqlite")

connect_args = {"check_same_thread": False} if is_sqlite else {}

try:
    if is_sqlite:
        engine = create_engine(
            settings.DATABASE_URL,
            connect_args=connect_args,
            echo=False
        )
    else:
        engine = create_engine(
            settings.DATABASE_URL,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_pre_ping=True,
            echo=False
        )
except Exception as e:
    if is_sqlite:
        engine = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False})
    else:
        logger.error(f"Cannot initialize database engine for {settings.DATABASE_URL}: {e}")
        raise RuntimeError(
            f"Database initialization failed. Set DATABASE_URL correctly in .env. Error: {e}"
        ) from e

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Dependency that yields a database session and closes it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _detect_pgvector_support() -> bool:
    if is_sqlite:
        return False
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT extname FROM pg_extension WHERE extname = 'vector'")).fetchone()
            if result:
                return True
            # Attempt creation
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
            return True
    except Exception:
        return False

has_pgvector = _detect_pgvector_support()


def check_pgvector_support(session: Session) -> bool:
    """Checks if pgvector is enabled in the database."""
    return has_pgvector


def _run_migrations(db: Session):
    """Applies any pending reviewed SQL migrations from the migrations directory."""
    from pathlib import Path
    migrations_dir = Path(__file__).resolve().parent.parent.parent / "migrations"
    if not migrations_dir.is_dir():
        return

    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename TEXT PRIMARY KEY,
                applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """))
        db.commit()

        applied = {
            row[0] for row in db.execute(text("SELECT filename FROM schema_migrations")).fetchall()
        }

        migration_files = sorted(migrations_dir.glob("*.sql"))
        for mig_file in migration_files:
            if mig_file.name not in applied:
                logger.info(f"[DB] Applying migration {mig_file.name}...")
                sql_content = mig_file.read_text(encoding="utf-8")
                db.execute(text(sql_content))
                db.execute(
                    text("INSERT INTO schema_migrations (filename, applied_at) VALUES (:fn, CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING"),
                    {"fn": mig_file.name}
                )
                db.commit()
                logger.info(f"[DB] Migration {mig_file.name} applied successfully.")
    except Exception as e:
        db.rollback()
        logger.warning(f"[DB] Notice during migration run: {e}")


def init_db():
    """Initializes tables and attempts to install the pgvector extension if PostgreSQL."""
    db = SessionLocal()
    try:
        if not is_sqlite:
            try:
                db.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                db.commit()
                logger.info("[DB] pgvector extension verified or created.")
            except Exception as e:
                db.rollback()
                logger.warning(f"[DB] Could not create pgvector extension: {e}. Vector columns will fallback to JSON/Array.")
        
        # Import all models to ensure they are registered with Base metadata
        import app.models # noqa
        Base.metadata.create_all(bind=engine)
        logger.info("[DB] All database tables created/verified successfully.")

        if not is_sqlite:
            _run_migrations(db)
    except Exception as e:
        logger.error(f"[DB] Error initializing database tables: {e}")
        raise
    finally:
        db.close()
