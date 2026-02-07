"""
Cost Estimation for Agent Execution.

Provides model-aware cost estimation for LLM calls and tool execution.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Model pricing per 1M tokens (input, output)
# Updated pricing as of 2026 - adjust as needed
MODEL_PRICING: dict[str, tuple[float, float]] = {
    # OpenAI
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-4": (30.00, 60.00),
    "gpt-3.5-turbo": (0.50, 1.50),
    "o1": (15.00, 60.00),
    "o1-mini": (3.00, 12.00),
    "o3-mini": (1.10, 4.40),
    # Anthropic
    "claude-3-5-sonnet": (3.00, 15.00),
    "claude-3-5-haiku": (0.25, 1.25),
    "claude-3-opus": (15.00, 75.00),
    "claude-3-sonnet": (3.00, 15.00),
    "claude-3-haiku": (0.25, 1.25),
    # Google
    "gemini-2.0-flash": (0.075, 0.30),
    "gemini-1.5-pro": (1.25, 5.00),
    "gemini-1.5-flash": (0.075, 0.30),
    # DeepSeek
    "deepseek-chat": (0.14, 0.28),
    "deepseek-reasoner": (0.55, 2.19),
    # Default fallback
    "default": (1.00, 3.00),
}


def get_model_pricing(model_name: str) -> tuple[float, float]:
    """
    Get pricing for a model (per 1M tokens).

    Returns (input_price, output_price) tuple.
    """
    model_lower = model_name.lower() if model_name else "default"

    # Try exact match first
    if model_lower in MODEL_PRICING:
        return MODEL_PRICING[model_lower]

    # Try partial match
    for key, pricing in MODEL_PRICING.items():
        if key in model_lower or model_lower in key:
            return pricing

    # Default pricing
    return MODEL_PRICING["default"]


def estimate_cost(
    input_tokens: int,
    output_tokens: int,
    model_name: str = "default",
) -> float:
    """
    Estimate cost for a single LLM call.

    Args:
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        model_name: Model name for pricing lookup

    Returns:
        Estimated cost in USD
    """
    input_price, output_price = get_model_pricing(model_name)

    # Price is per 1M tokens
    input_cost = (input_tokens / 1_000_000) * input_price
    output_cost = (output_tokens / 1_000_000) * output_price

    return input_cost + output_cost


def estimate_tokens(text: str) -> int:
    """
    Estimate token count for text.

    Simple estimation: ~4 chars per token for English text.
    For production, consider using tiktoken or model-specific tokenizers.
    """
    if not text:
        return 0
    return len(text) // 4


def estimate_message_tokens(messages: list[dict]) -> int:
    """
    Estimate token count for a list of messages.
    """
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += estimate_tokens(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and "text" in part:
                    total += estimate_tokens(part["text"])
    return total


def estimate_remaining_budget(
    state: dict[str, Any],
    model_name: str = "default",
) -> dict[str, Any]:
    """
    Estimate remaining budget based on current state.

    Returns dict with:
    - remaining_usd: Estimated remaining USD budget
    - estimated_tokens_remaining: Based on average cost per token
    - should_abort: True if budget is critically low
    """
    cost_spent = state.get("cost_spent_usd", 0.0)
    cost_limit = state.get("cost_limit_usd", 0.50)
    remaining = cost_limit - cost_spent

    # Estimate how many tokens we can still use
    input_price, output_price = get_model_pricing(model_name)
    avg_price_per_token = (input_price + output_price) / 2 / 1_000_000

    estimated_tokens = (
        int(remaining / avg_price_per_token) if avg_price_per_token > 0 else 0
    )

    # Should abort if less than 5% budget remains
    should_abort = remaining < (cost_limit * 0.05)

    return {
        "remaining_usd": remaining,
        "estimated_tokens_remaining": estimated_tokens,
        "should_abort": should_abort,
        "percentage_used": (cost_spent / cost_limit * 100) if cost_limit > 0 else 100,
    }


def estimate_tool_cost(tool_name: str, tool_input: dict) -> float:
    """
    Estimate cost for a tool call.

    Some tools have associated API costs (e.g., web search).
    Most internal tools have zero marginal cost.
    """
    # Tools with potential API costs
    api_cost_tools = {
        "web_search": 0.001,  # ~$0.001 per search
        "execute_python": 0.0001,  # Minimal compute cost
    }

    return api_cost_tools.get(tool_name, 0.0)


class CostTracker:
    """
    Track costs across an agent execution session.
    """

    def __init__(self, model_name: str = "default", cost_limit: float = 0.50):
        self.model_name = model_name
        self.cost_limit = cost_limit
        self.total_cost = 0.0
        self.llm_calls = 0
        self.tool_calls = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def record_llm_call(
        self,
        input_tokens: int,
        output_tokens: int,
        model_name: str | None = None,
    ) -> float:
        """Record an LLM call and return its cost."""
        model = model_name or self.model_name
        cost = estimate_cost(input_tokens, output_tokens, model)

        self.total_cost += cost
        self.llm_calls += 1
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens

        return cost

    def record_tool_call(self, tool_name: str, tool_input: dict) -> float:
        """Record a tool call and return its cost."""
        cost = estimate_tool_cost(tool_name, tool_input)

        self.total_cost += cost
        self.tool_calls += 1

        return cost

    def is_over_budget(self) -> bool:
        """Check if cost limit has been exceeded."""
        return self.total_cost >= self.cost_limit

    def get_remaining(self) -> float:
        """Get remaining budget."""
        return max(0, self.cost_limit - self.total_cost)

    def get_summary(self) -> dict[str, Any]:
        """Get cost tracking summary."""
        return {
            "total_cost_usd": self.total_cost,
            "cost_limit_usd": self.cost_limit,
            "remaining_usd": self.get_remaining(),
            "llm_calls": self.llm_calls,
            "tool_calls": self.tool_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "is_over_budget": self.is_over_budget(),
        }
