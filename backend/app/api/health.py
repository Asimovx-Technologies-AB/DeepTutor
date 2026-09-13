from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.database import get_db, check_pgvector_support, is_sqlite
from app.core.config import settings

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Health check endpoint checking DB connectivity and pgvector support."""
    db_status = "healthy"
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    has_pgvector = check_pgvector_support(db)

    return {
        "status": "online",
        "project": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
        "database": {
            "status": db_status,
            "engine": "sqlite" if is_sqlite else "postgresql",
            "pgvector_enabled": has_pgvector,
        },
        "storage": {
            "backend": settings.STORAGE_BACKEND,
            "root_dir": settings.STORAGE_ROOT_DIR,
        },
        "embedding": {
            "provider": settings.EMBEDDING_PROVIDER,
            "dimension": settings.EMBEDDING_DIMENSION,
        }
    }
