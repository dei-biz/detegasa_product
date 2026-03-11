"""Factory for creating LLM adapters based on configuration."""

from src.core.config import Settings
from src.llm.adapter import LLMAdapter
from src.llm.claude_adapter import ClaudeAdapter
from src.llm.openai_adapter import OpenAIAdapter


def create_llm_adapter(
    settings: Settings | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> LLMAdapter:
    """Create an LLM adapter based on settings or explicit parameters.

    Args:
        settings: Application settings. If None, imports the global singleton.
        provider: Override the default provider ('anthropic' or 'openai').
        model: Override the default model for the provider.

    Returns:
        Configured LLMAdapter instance.

    Raises:
        ValueError: If the provider is not supported or API key is missing.
    """
    if settings is None:
        from src.core.config import settings as global_settings
        settings = global_settings

    chosen_provider = provider or settings.default_llm_provider

    if chosen_provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is required when using the Anthropic provider. "
                "Set it in your .env file."
            )
        return ClaudeAdapter(
            api_key=settings.anthropic_api_key,
            model=model,
        )

    elif chosen_provider == "openai":
        if not settings.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY is required when using the OpenAI provider. "
                "Set it in your .env file."
            )
        return OpenAIAdapter(
            api_key=settings.openai_api_key,
            model=model,
        )

    else:
        raise ValueError(
            f"Unsupported LLM provider: '{chosen_provider}'. "
            f"Use 'anthropic' or 'openai'."
        )
