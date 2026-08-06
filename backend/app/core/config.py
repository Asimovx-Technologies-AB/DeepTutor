from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_NAME: str = "Deep Tutor API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # Security
    SECRET_KEY: str = "deep-tutor-super-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./deep_tutor.db"

    # Ollama
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_CHAT_MODEL: str = "llama3.2"      # or mistral, gemma2
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"
    OLLAMA_TIMEOUT: int = 120

    # ChromaDB
    CHROMA_PERSIST_DIR: str = "./chroma_data"

    # Graph Store
    GRAPH_DATA_DIR: str = "./graph_data"

    # File uploads
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 50

    # RAG settings
    CHUNK_SIZE: int = 384
    CHUNK_OVERLAP: int = 80
    TOP_K_CHUNKS: int = 4
    GRAPH_HOP_DEPTH: int = 2


@lru_cache
def get_settings() -> Settings:
    return Settings()
