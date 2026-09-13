import os
from pathlib import Path
from typing import Literal, Optional, ClassVar
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

    # Database Configuration
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/deeptutor"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # Object Storage
    STORAGE_BACKEND: Literal["local", "s3"] = "local"
    STORAGE_ROOT_DIR: str = str(Path(__file__).resolve().parent.parent.parent / "storage_vault")

    # LLM (Language Model) Settings
    LLM_PROVIDER: Literal["gemini", "openai", "groq", "azure_openai", "anthropic", "mock"] = "mock"
    LLM_MODEL: str = "gemini-3.5-flash"
    LLM_TEMPERATURE: float = 0.8

    # Embedding Settings
    EMBEDDING_PROVIDER: Literal["local", "gemini", "azure_openai", "openai"] = "local"
    EMBEDDING_MODEL: str = "gemini-embedding-001"
    EMBEDDING_DIMENSION: int = 768  # 768 for gemini text-embedding-004, 1536 for openai

    # Vision-Language Model (VLM)
    VLM_PROVIDER: Literal["mock", "gemini", "azure_openai", "openai"] = "mock"
    VLM_MODEL: str = "gemini-3.6-flash"

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

    def auto_detect_providers(self):
        """Automatically selects active provider when corresponding API key is populated."""
        if self.GEMINI_API_KEY:
            self.LLM_PROVIDER = "gemini"
            self.EMBEDDING_PROVIDER = "gemini"
            self.VLM_PROVIDER = "gemini"
        elif self.OPENAI_API_KEY:
            self.LLM_PROVIDER = "openai"
            self.EMBEDDING_PROVIDER = "openai"
            self.EMBEDDING_MODEL = "text-embedding-3-small"
            self.EMBEDDING_DIMENSION = 1536
            self.VLM_PROVIDER = "openai"
        elif self.GROQ_API_KEY:
            self.LLM_PROVIDER = "groq"
            self.LLM_MODEL = "llama-3.3-70b-versatile"
        else:
            self.LLM_PROVIDER = "mock"
            self.EMBEDDING_PROVIDER = "local"
            self.VLM_PROVIDER = "mock"


settings = Settings()
settings.auto_detect_providers()
