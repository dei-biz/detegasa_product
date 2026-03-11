"""Abstract base class for LLM adapters."""

from abc import ABC, abstractmethod

from pydantic import BaseModel

from src.llm.types import LLMResponse


class LLMAdapter(ABC):
    """Interface for LLM providers (Claude, OpenAI, etc.)."""

    @property
    @abstractmethod
    def provider(self) -> str:
        """Provider name: 'anthropic' or 'openai'."""
        ...

    @property
    @abstractmethod
    def model(self) -> str:
        """Current model identifier."""
        ...

    @abstractmethod
    async def complete(
        self,
        user_prompt: str,
        system_prompt: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Generate a text completion.

        Args:
            user_prompt: The user message.
            system_prompt: Optional system message for context.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature (0 = deterministic).

        Returns:
            LLMResponse with content and usage metadata.
        """
        ...

    @abstractmethod
    async def extract_structured(
        self,
        prompt: str,
        response_model: type[BaseModel],
        system_prompt: str = "",
        max_tokens: int = 4096,
        max_retries: int = 3,
    ) -> tuple[BaseModel, LLMResponse]:
        """Extract structured data using Instructor.

        Uses Instructor to guarantee a valid Pydantic model as output,
        with automatic retries if validation fails.

        Args:
            prompt: The user message with content to extract from.
            response_model: Pydantic model class to validate against.
            system_prompt: Optional system context.
            max_tokens: Maximum tokens to generate.
            max_retries: Number of retries if validation fails.

        Returns:
            Tuple of (validated Pydantic instance, LLMResponse with metadata).
        """
        ...
