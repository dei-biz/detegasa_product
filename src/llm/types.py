"""Shared types for the LLM adapter layer."""

from pydantic import BaseModel, Field


# Cost per million tokens (input, output) by model
MODEL_PRICING: dict[str, tuple[float, float]] = {
    # Anthropic
    "claude-sonnet-4-5-20250514": (3.00, 15.00),
    "claude-haiku-4-5-20250514": (0.80, 4.00),
    # OpenAI
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
}

# Default models per provider
DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-5-20250514",
    "openai": "gpt-4o",
}

# Fast/cheap models per provider (for classification tasks)
FAST_MODELS = {
    "anthropic": "claude-haiku-4-5-20250514",
    "openai": "gpt-4o-mini",
}


class LLMResponse(BaseModel):
    """Response from an LLM call with usage metadata."""

    content: str = Field(..., description="Text content of the response")
    model: str = Field(..., description="Model used for generation")
    input_tokens: int = Field(default=0, description="Input tokens consumed")
    output_tokens: int = Field(default=0, description="Output tokens generated")
    cost_usd: float = Field(default=0.0, description="Estimated cost in USD")


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate the cost of an LLM call based on model pricing."""
    pricing = MODEL_PRICING.get(model)
    if pricing is None:
        return 0.0
    input_price_per_m, output_price_per_m = pricing
    return (input_tokens * input_price_per_m + output_tokens * output_price_per_m) / 1_000_000
