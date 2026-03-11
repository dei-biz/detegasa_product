"""Tests for application configuration."""

from src.core.config import Settings


def test_settings_defaults(monkeypatch):
    """Verify Settings loads with sensible defaults (ignoring .env file)."""
    monkeypatch.delenv("DEBUG", raising=False)
    s = Settings(
        _env_file=None,  # Don't read .env for this test
        database_url="postgresql+asyncpg://u:p@localhost/db",
        anthropic_api_key="test",
        openai_api_key="test",
    )
    assert s.default_llm_provider == "anthropic"
    assert s.embedding_provider == "openai"
    assert s.embedding_dimension == 1536
    assert s.enable_llm_cache is True
    assert s.debug is False


def test_settings_sync_url():
    """Verify sync URL generation for Alembic."""
    s = Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",
    )
    assert s.database_url_sync == "postgresql://u:p@localhost/db"


def test_settings_override():
    """Verify settings can be overridden."""
    s = Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        default_llm_provider="openai",
        embedding_provider="local",
        embedding_dimension=384,
        enable_llm_cache=False,
        debug=True,
    )
    assert s.default_llm_provider == "openai"
    assert s.embedding_provider == "local"
    assert s.embedding_dimension == 384
    assert s.enable_llm_cache is False
    assert s.debug is True
