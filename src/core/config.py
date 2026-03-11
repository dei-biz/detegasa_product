"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global application settings, loaded from .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Database ──────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://sentinas:sentinas_dev@localhost:5432/sentinas"

    # ── LLM Providers ─────────────────────────────────────────────────────
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    default_llm_provider: str = "anthropic"  # "anthropic" | "openai"

    # ── Embeddings ────────────────────────────────────────────────────────
    embedding_provider: str = "openai"  # "openai" | "local"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 1536

    # ── Langfuse (observability) ──────────────────────────────────────────
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://localhost:3000"

    # ── Cache ─────────────────────────────────────────────────────────────
    enable_llm_cache: bool = True

    # ── Application ───────────────────────────────────────────────────────
    debug: bool = False

    @property
    def database_url_sync(self) -> str:
        """Synchronous database URL for Alembic migrations."""
        return self.database_url.replace("+asyncpg", "")


settings = Settings()
