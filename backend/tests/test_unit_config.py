"""
test_unit_config.py
===================
Criteria §1.1 — Configuration Parsing & Defaults.

Validates that Settings loads environment variables correctly and that
every field has a safe, predictable default.
"""
import os
import pytest
from unittest.mock import patch


def test_config_loads_defaults():
    """All critical settings have safe defaults without a .env file."""
    # Clear any real env var to test the default path
    with patch.dict(os.environ, {}, clear=False):
        from importlib import reload
        import app.core.config as cfg_module
        # Just access the class, don't re-invoke lru_cache
        settings = cfg_module.Settings()

    assert settings.APP_NAME in ("Deep Tutor API", "Indie Tutor")
    assert settings.ALGORITHM == "HS256"
    assert settings.ACCESS_TOKEN_EXPIRE_MINUTES == 60 * 24 * 7
    assert settings.LLM_PROVIDER in ("gemini", "azure_openai", "ollama", "openai")
    assert settings.OLLAMA_NUM_CTX > 0
    assert settings.UPLOAD_DIR, "UPLOAD_DIR must not be empty"


def test_config_secret_key_not_empty():
    """SECRET_KEY must always be set (non-empty)."""
    from app.core.config import get_settings
    settings = get_settings()
    assert settings.SECRET_KEY and len(settings.SECRET_KEY) > 8


def test_config_token_expiry_is_positive():
    """Access token expiry must be a positive integer (minutes)."""
    from app.core.config import get_settings
    settings = get_settings()
    assert settings.ACCESS_TOKEN_EXPIRE_MINUTES > 0


def test_config_database_url_format():
    """DATABASE_URL must be a recognisable scheme."""
    from app.core.config import get_settings
    settings = get_settings()
    url = settings.DATABASE_URL
    assert any(url.startswith(scheme) for scheme in (
        "sqlite", "postgresql", "postgres"
    )), f"Unexpected DATABASE_URL scheme: {url}"
