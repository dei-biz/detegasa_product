"""Tests for LLM adapters — factory, types, and cache (no real API calls)."""

import pytest

from src.core.config import Settings
from src.llm.claude_adapter import ClaudeAdapter
from src.llm.factory import create_llm_adapter
from src.llm.openai_adapter import OpenAIAdapter
from src.llm.types import DEFAULT_MODELS, FAST_MODELS, LLMResponse, calculate_cost


# ── LLMResponse ──────────────────────────────────────────────────────────────


class TestLLMResponse:
    def test_creation(self):
        r = LLMResponse(
            content="test",
            model="gpt-4o",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.0075,
        )
        assert r.content == "test"
        assert r.input_tokens == 100

    def test_defaults(self):
        r = LLMResponse(content="x", model="m")
        assert r.input_tokens == 0
        assert r.cost_usd == 0.0


# ── Cost calculation ─────────────────────────────────────────────────────────


class TestCalculateCost:
    def test_claude_sonnet(self):
        cost = calculate_cost("claude-sonnet-4-5-20250929", 1000, 500)
        # (1000 * 3.00 + 500 * 15.00) / 1_000_000 = 0.0105
        assert abs(cost - 0.0105) < 0.0001

    def test_gpt4o_mini(self):
        cost = calculate_cost("gpt-4o-mini", 10000, 1000)
        # (10000 * 0.15 + 1000 * 0.60) / 1_000_000 = 0.0021
        assert abs(cost - 0.0021) < 0.0001

    def test_unknown_model(self):
        cost = calculate_cost("unknown-model", 1000, 500)
        assert cost == 0.0


class TestModelConstants:
    def test_default_models(self):
        assert "anthropic" in DEFAULT_MODELS
        assert "openai" in DEFAULT_MODELS

    def test_fast_models(self):
        assert "anthropic" in FAST_MODELS
        assert "openai" in FAST_MODELS


# ── Factory ──────────────────────────────────────────────────────────────────


class TestFactory:
    def test_create_anthropic(self):
        settings = Settings(
            database_url="postgresql+asyncpg://x:x@localhost/x",
            anthropic_api_key="sk-ant-test",
            default_llm_provider="anthropic",
        )
        adapter = create_llm_adapter(settings=settings)
        assert isinstance(adapter, ClaudeAdapter)
        assert adapter.provider == "anthropic"

    def test_create_openai(self):
        settings = Settings(
            database_url="postgresql+asyncpg://x:x@localhost/x",
            openai_api_key="sk-test",
            default_llm_provider="openai",
        )
        adapter = create_llm_adapter(settings=settings)
        assert isinstance(adapter, OpenAIAdapter)
        assert adapter.provider == "openai"

    def test_override_provider(self):
        settings = Settings(
            database_url="postgresql+asyncpg://x:x@localhost/x",
            anthropic_api_key="sk-ant-test",
            openai_api_key="sk-test",
            default_llm_provider="anthropic",
        )
        adapter = create_llm_adapter(settings=settings, provider="openai")
        assert isinstance(adapter, OpenAIAdapter)

    def test_missing_api_key_raises(self):
        settings = Settings(
            database_url="postgresql+asyncpg://x:x@localhost/x",
            anthropic_api_key="",
            default_llm_provider="anthropic",
        )
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            create_llm_adapter(settings=settings)

    def test_unsupported_provider(self):
        settings = Settings(
            database_url="postgresql+asyncpg://x:x@localhost/x",
            default_llm_provider="google",
        )
        with pytest.raises(ValueError, match="Unsupported"):
            create_llm_adapter(settings=settings)

    def test_custom_model(self):
        settings = Settings(
            database_url="postgresql+asyncpg://x:x@localhost/x",
            anthropic_api_key="sk-ant-test",
            default_llm_provider="anthropic",
        )
        adapter = create_llm_adapter(settings=settings, model="claude-haiku-4-5-20251001")
        assert adapter.model == "claude-haiku-4-5-20251001"
