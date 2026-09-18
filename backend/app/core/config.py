import os
from pathlib import Path
from typing import List, Literal, Optional, ClassVar, Any, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, PydanticBaseSettingsSource


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=[
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), ".env"),
            ".env"
        ],
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Application
    PROJECT_NAME: str = "DeepTutor Processing & Storage Engine"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_STR: str = "/api"

    # Security Configuration
    SECRET_KEY: str = "deeptutor-dev-insecure-secret-key-change-in-production-min32bytes"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7
    MAX_UPLOAD_SIZE_MB: int = 50
    RATE_LIMIT_PER_MINUTE: int = 60
    LLM_RATE_LIMIT_PER_MINUTE: int = 20

    # CORS Configuration
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, (list, tuple)):
            return [str(i).strip() for i in v]
        return [
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
        ]

    # Database Configuration
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/deeptutor"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # Object Storage
    STORAGE_BACKEND: Literal["local", "s3"] = "local"
    STORAGE_ROOT_DIR: str = str(Path(__file__).resolve().parent.parent.parent / "storage_vault")

    # LLM (Language Model) Settings
    LLM_PROVIDER: Literal["gemini", "openai", "groq", "azure_openai", "anthropic", "mock"] = "mock"
    LLM_MODEL: str = "gemini-3.1-flash-lite"
    LLM_TEMPERATURE: float = 0.8

    # Embedding Settings
    EMBEDDING_PROVIDER: Literal["local", "gemini", "azure_openai", "openai"] = "local"
    EMBEDDING_MODEL: str = "gemini-embedding-001"
    EMBEDDING_DIMENSION: int = 768  # 768 for gemini text-embedding-004, 1536 for openai

    # Vision-Language Model (VLM)
    VLM_PROVIDER: Literal["mock", "gemini", "azure_openai", "openai"] = "mock"
    VLM_MODEL: str = "gemini-3.5-flash-lite"

    # API Keys
    GEMINI_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    AZURE_OPENAI_ENDPOINT: Optional[str] = None
    AZURE_OPENAI_API_KEY: Optional[str] = None
    AZURE_OPENAI_DEPLOYMENT_NAME: Optional[str] = None

    @field_validator(
        "GEMINI_API_KEY",
        "OPENAI_API_KEY",
        "GROQ_API_KEY",
        "ANTHROPIC_API_KEY",
        "AZURE_OPENAI_API_KEY",
        mode="before"
    )
    @classmethod
    def clean_api_keys(cls, v):
        if isinstance(v, str):
            v = v.strip()
            if not v or v.lower() in ("your_api_key", "your_gemini_api_key", "your_openai_api_key", "none"):
                return None
            return v
        return v

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Prioritize .env file so user-configured keys in backend/.env take precedence
        return (init_settings, dotenv_settings, file_secret_settings)

    # Chunking & Document Processing Parameters
    MIN_TEXT_DENSITY_CHARS_PER_PAGE: int = 100
    MAX_CHUNK_TOKENS: int = 512
    MIN_CHUNK_TOKENS: int = 64
    CHUNK_OVERLAP_TOKENS: int = 64
    TEXT_QUALITY_OCR_THRESHOLD: float = 0.65

    def model_post_init(self, __context: Any) -> None:
        """Auto-detect providers after all fields are resolved from env."""
        if self.GEMINI_API_KEY:
            object.__setattr__(self, "LLM_PROVIDER", "gemini")
            object.__setattr__(self, "EMBEDDING_PROVIDER", "gemini")
            object.__setattr__(self, "VLM_PROVIDER", "gemini")
        elif self.OPENAI_API_KEY:
            object.__setattr__(self, "LLM_PROVIDER", "openai")
            object.__setattr__(self, "EMBEDDING_PROVIDER", "openai")
            object.__setattr__(self, "EMBEDDING_MODEL", "text-embedding-3-small")
            object.__setattr__(self, "EMBEDDING_DIMENSION", 1536)
            object.__setattr__(self, "VLM_PROVIDER", "openai")
        elif self.GROQ_API_KEY:
            object.__setattr__(self, "LLM_PROVIDER", "groq")
            object.__setattr__(self, "LLM_MODEL", "llama-3.3-70b-versatile")
        else:
            object.__setattr__(self, "LLM_PROVIDER", "mock")
            object.__setattr__(self, "EMBEDDING_PROVIDER", "local")
            object.__setattr__(self, "VLM_PROVIDER", "mock")

    def auto_detect_providers(self):
        """Backwards-compatible alias for manual trigger in tests."""
        self.model_post_init(None)


settings = Settings()
