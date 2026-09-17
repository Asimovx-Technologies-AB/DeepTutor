from fastapi import APIRouter
from app.api.documents import router as documents_router
from app.api.chunks import router as chunks_router
from app.api.search import router as search_router
from app.api.health import router as health_router
from app.api.study import router as study_router
from app.api.chat import router as chat_router
from app.api.dashboard import router as dashboard_router
from app.api.auth import router as auth_router
from app.api.study_plan import router as study_plan_router
from app.api.tracking import router as tracking_router
from app.api.question_papers import router as question_papers_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(dashboard_router)
api_router.include_router(documents_router)
api_router.include_router(chunks_router)
api_router.include_router(search_router)
api_router.include_router(study_router)
api_router.include_router(chat_router)
api_router.include_router(study_plan_router)
api_router.include_router(tracking_router)
api_router.include_router(question_papers_router)

__all__ = ["api_router"]

