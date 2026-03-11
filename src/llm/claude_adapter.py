"""Claude (Anthropic) LLM adapter using Instructor for structured extraction."""

import instructor
from anthropic import AsyncAnthropic
from pydantic import BaseModel

from src.llm.adapter import LLMAdapter
from src.llm.types import DEFAULT_MODELS, LLMResponse, calculate_cost


class ClaudeAdapter(LLMAdapter):
    """Anthropic Claude adapter with Instructor integration."""

    def __init__(
        self,
        api_key: str,
        model: str | None = None,
    ):
        self._model = model or DEFAULT_MODELS["anthropic"]
        self._raw_client = AsyncAnthropic(api_key=api_key)
        self._instructor_client = instructor.from_anthropic(self._raw_client)

    @property
    def provider(self) -> str:
        return "anthropic"

    @property
    def model(self) -> str:
        return self._model

    async def complete(
        self,
        user_prompt: str,
        system_prompt: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> LLMResponse:
        kwargs: dict = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        response = await self._raw_client.messages.create(**kwargs)

        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens

        return LLMResponse(
            content=response.content[0].text,
            model=self._model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=calculate_cost(self._model, input_tokens, output_tokens),
        )

    async def extract_structured(
        self,
        prompt: str,
        response_model: type[BaseModel],
        system_prompt: str = "",
        max_tokens: int = 4096,
        max_retries: int = 3,
    ) -> tuple[BaseModel, LLMResponse]:
        kwargs: dict = {
            "model": self._model,
            "max_tokens": max_tokens,
            "max_retries": max_retries,
            "messages": [{"role": "user", "content": prompt}],
            "response_model": response_model,
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        result, completion = (
            await self._instructor_client.messages.create_with_completion(**kwargs)
        )

        input_tokens = completion.usage.input_tokens
        output_tokens = completion.usage.output_tokens

        llm_response = LLMResponse(
            content=result.model_dump_json(),
            model=self._model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=calculate_cost(self._model, input_tokens, output_tokens),
        )

        return result, llm_response
