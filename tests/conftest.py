"""Shared test fixtures."""

import pytest

from src.core.config import Settings


@pytest.fixture
def test_settings() -> Settings:
    """Settings with test defaults (no real API keys needed)."""
    return Settings(
        database_url="postgresql+asyncpg://test:test@localhost:5432/test_sentinas",
        anthropic_api_key="sk-ant-test-key",
        openai_api_key="sk-test-key",
        default_llm_provider="anthropic",
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        embedding_dimension=1536,
        enable_llm_cache=True,
        debug=True,
    )
