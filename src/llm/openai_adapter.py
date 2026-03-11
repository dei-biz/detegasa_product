"""OpenAI GPT adapter using Instructor for structured extraction."""

import instructor
from openai import AsyncOpenAI
from pydantic import BaseModel

from src.llm.adapter import LLMAdapter
from src.llm.types import DEFAULT_MODELS, LLMResponse, calculate_cost


class OpenAIAdapter(LLMAdapter):
    """OpenAI GPT adapter with Instructor integration."""

    def __init__(
        self,
        api_key: str,
        model: str | None = None,
    ):
        self._model = model or DEFAULT_MODELS["openai"]
        self._raw_client = AsyncOpenAI(api_key=api_key)
        self._instructor_client = instructor.from_openai(self._raw_client)

    @property
    def provider(self) -> str:
        return "openai"

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
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        response = await self._raw_client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        input_tokens = response.usage.prompt_tokens if response.usage else 0
        output_tokens = response.usage.completion_tokens if response.usage else 0

        return LLMResponse(
            content=response.choices[0].message.content or "",
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
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        result, completion = (
            await self._instructor_client.chat.completions.create_with_completion(
                model=self._model,
                messages=messages,
                max_tokens=max_tokens,
                max_retries=max_retries,
                response_model=response_model,
            )
        )

        input_tokens = completion.usage.prompt_tokens if completion.usage else 0
        output_tokens = completion.usage.completion_tokens if completion.usage else 0

        llm_response = LLMResponse(
            content=result.model_dump_json(),
            model=self._model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=calculate_cost(self._model, input_tokens, output_tokens),
        )

        return result, llm_response
