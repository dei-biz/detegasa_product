"""LLM result cache using PostgreSQL to avoid reprocessing."""

import hashlib
import json
import logging

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import LLMCache as LLMCacheModel

logger = logging.getLogger(__name__)


class LLMResultCache:
    """Cache for LLM extraction results, keyed by SHA-256 of input+schema+model."""

    def __init__(self, session: AsyncSession, enabled: bool = True):
        self._session = session
        self._enabled = enabled

    @staticmethod
    def _make_key(input_text: str, schema_name: str, model: str) -> str:
        """Generate a deterministic cache key."""
        payload = f"{input_text}:{schema_name}:{model}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _hash_input(input_text: str) -> str:
        """Hash just the input text for auditing."""
        return hashlib.sha256(input_text.encode("utf-8")).hexdigest()

    async def get(
        self,
        input_text: str,
        schema: type[BaseModel],
        model: str,
    ) -> BaseModel | None:
        """Look up a cached result. Returns None if not found or cache disabled."""
        if not self._enabled:
            return None

        cache_key = self._make_key(input_text, schema.__name__, model)

        stmt = select(LLMCacheModel).where(LLMCacheModel.cache_key == cache_key)
        result = await self._session.execute(stmt)
        cached = result.scalar_one_or_none()

        if cached is None:
            return None

        logger.debug("Cache HIT for %s (model=%s, schema=%s)", cache_key[:12], model, schema.__name__)
        return schema.model_validate(cached.result)

    async def put(
        self,
        input_text: str,
        schema: type[BaseModel],
        model: str,
        result: BaseModel,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        """Store a result in the cache."""
        if not self._enabled:
            return

        cache_key = self._make_key(input_text, schema.__name__, model)

        cache_entry = LLMCacheModel(
            cache_key=cache_key,
            input_hash=self._hash_input(input_text),
            model=model,
            schema_name=schema.__name__,
            result=json.loads(result.model_dump_json()),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )

        self._session.add(cache_entry)
        await self._session.flush()
        logger.debug("Cache STORE for %s (model=%s, schema=%s)", cache_key[:12], model, schema.__name__)
