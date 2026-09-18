import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.core.database import init_db
from app.api import api_router
from app.api import topic_analysis

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize database schema & vector extensions
    logger.info("Initializing DeepTutor Document Processing & Storage Engine...")
    try:
        init_db()
    except Exception as e:
        logger.error(f"Failed to initialize database on startup: {e}")
    yield
    logger.info("Shutting down DeepTutor Processing Engine...")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Advanced PDF Document Processing, Knowledge Chunking, and Multi-Model Data Storage Architecture",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Exception Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error handling {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error occurred.", "error": str(exc)},
    )

# Mount API routers under API_V1_STR
app.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(topic_analysis.router, prefix=settings.API_V1_STR)


@app.get("/")
def root():
    return {
        "message": "DeepTutor Document Processing & Storage Engine is running.",
        "version": "2.0.0",
        "docs": "/docs",
        "health": f"{settings.API_V1_STR}/health"
    }
