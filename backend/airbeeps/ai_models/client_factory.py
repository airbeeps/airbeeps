"""
LiteLLM Chat Model Factory
Unified factory function for creating LiteLLM chat clients
"""

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Union

if TYPE_CHECKING:
    from airbeeps.ai_models.models import ModelProvider

logger = logging.getLogger(__name__)


def _is_test_mode() -> bool:
    """Check if test mode is enabled."""
    from airbeeps.config import settings

    return settings.TEST_MODE


# =============================================================================
# Fake LiteLLM Client for Test Mode
# =============================================================================


@dataclass
class FakeMessage:
    """Fake message object mimicking LiteLLM response structure."""

    content: str
    role: str = "assistant"


@dataclass
class FakeChoice:
    """Fake choice object mimicking LiteLLM response structure."""

    message: FakeMessage
    index: int = 0
    finish_reason: str = "stop"


@dataclass
class FakeDelta:
    """Fake delta object for streaming responses."""

    content: str | None = None
    role: str | None = None


@dataclass
class FakeStreamChoice:
    """Fake choice object for streaming responses."""

    delta: FakeDelta
    index: int = 0
    finish_reason: str | None = None


@dataclass
class FakeUsage:
    """Fake usage object mimicking LiteLLM response structure."""

    prompt_tokens: int = 10
    completion_tokens: int = 20
    total_tokens: int = 30


@dataclass
class FakeResponse:
    """Fake response object mimicking LiteLLM response structure."""

    choices: list[FakeChoice] = field(default_factory=list)
    usage: FakeUsage = field(default_factory=FakeUsage)
    model: str = "test-model"
    id: str = "test-response-id"


@dataclass
class FakeStreamChunk:
    """Fake streaming chunk mimicking LiteLLM chunk structure."""

    choices: list[FakeStreamChoice] = field(default_factory=list)
    usage: FakeUsage | None = None
    model: str = "test-model"
    id: str = "test-chunk-id"


class FakeLiteLLMClient:
    """
    Fake LiteLLM client for test mode.

    Returns deterministic responses without making any external API calls.
    The response format is compatible with the parsing logic in chat/service.py.
    """

    # Deterministic response prefix
    RESPONSE_PREFIX = "TEST_MODE_RESPONSE: "

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **additional_params,
    ):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.additional_params = additional_params
        logger.info(f"FakeLiteLLMClient created for model: {model} (TEST_MODE)")

    def _extract_last_user_message(self, messages: list) -> str:
        """Extract the last user message content for deterministic response."""
        for msg in reversed(messages):
            if isinstance(msg, dict) and msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    return content
                # Handle multimodal content (list of parts)
                if isinstance(content, list):
                    text_parts = []
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            text_parts.append(part.get("text", ""))
                        elif isinstance(part, str):
                            text_parts.append(part)
                    return " ".join(text_parts) if text_parts else "empty"
        return "no user message"

    async def ainvoke(self, messages: list) -> FakeResponse:
        """
        Invoke the model asynchronously (non-streaming).

        Returns a deterministic response based on the last user message.
        """
        last_user_msg = self._extract_last_user_message(messages)
        response_content = f"{self.RESPONSE_PREFIX}{last_user_msg}"

        logger.debug(f"FakeLiteLLMClient.ainvoke called with {len(messages)} messages")

        return FakeResponse(
            choices=[
                FakeChoice(
                    message=FakeMessage(content=response_content),
                    index=0,
                    finish_reason="stop",
                )
            ],
            usage=FakeUsage(
                prompt_tokens=len(str(messages)) // 4,
                completion_tokens=len(response_content) // 4,
                total_tokens=(len(str(messages)) + len(response_content)) // 4,
            ),
            model=self.model,
        )

    async def astream(self, messages: list) -> AsyncIterator[FakeStreamChunk]:
        """
        Stream the model response asynchronously.

        Yields deterministic chunks based on the last user message.
        """
        last_user_msg = self._extract_last_user_message(messages)
        response_content = f"{self.RESPONSE_PREFIX}{last_user_msg}"

        logger.debug(f"FakeLiteLLMClient.astream called with {len(messages)} messages")

        # Simulate streaming by yielding chunks of the response
        chunk_size = 10
        for i in range(0, len(response_content), chunk_size):
            chunk_content = response_content[i : i + chunk_size]
            yield FakeStreamChunk(
                choices=[
                    FakeStreamChoice(
                        delta=FakeDelta(content=chunk_content),
                        index=0,
                        finish_reason=None,
                    )
                ],
                usage=None,
                model=self.model,
            )

        # Final chunk with finish_reason and usage
        yield FakeStreamChunk(
            choices=[
                FakeStreamChoice(
                    delta=FakeDelta(content=""),
                    index=0,
                    finish_reason="stop",
                )
            ],
            usage=FakeUsage(
                prompt_tokens=len(str(messages)) // 4,
                completion_tokens=len(response_content) // 4,
                total_tokens=(len(str(messages)) + len(response_content)) // 4,
            ),
            model=self.model,
        )


# Type alias for client that can be either real or fake
LiteLLMClientType = Union["LiteLLMClient", FakeLiteLLMClient]


class LiteLLMClient:
    """Wrapper for LiteLLM client with unified interface"""

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **additional_params,
    ):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.additional_params = additional_params

    def _prepare_request_params(
        self, messages: list, stream: bool = False
    ) -> dict[str, Any]:
        """Prepare request parameters for LiteLLM"""
        params = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "stream": stream,
            **self.additional_params,
        }

        if self.max_tokens:
            params["max_tokens"] = self.max_tokens

        if self.api_key:
            params["api_key"] = self.api_key

        if self.base_url:
            params["api_base"] = self.base_url

        # Enable stream_options to get usage info in final chunk (includes reasoning tokens)
        if stream:
            params["stream_options"] = {"include_usage": True}

        return params

    async def ainvoke(self, messages: list) -> Any:
        """Invoke the model asynchronously (non-streaming)"""
        # Import here to avoid import at module level when using FakeLiteLLMClient
        from litellm import acompletion

        params = self._prepare_request_params(messages, stream=False)
        response = await acompletion(**params)
        return response

    async def astream(self, messages: list):
        """Stream the model response asynchronously"""
        # Import here to avoid import at module level when using FakeLiteLLMClient
        from litellm import acompletion

        params = self._prepare_request_params(messages, stream=True)
        response = await acompletion(**params)

        async for chunk in response:
            yield chunk


def create_chat_model(
    provider: "ModelProvider",
    model_name: str,
    temperature: float = 0.7,
    max_tokens: int | None = None,
    **additional_params,
) -> LiteLLMClientType:
    """
    Unified factory using LiteLLM's provider system.

    All provider-specific logic is handled by LiteLLM internally.
    We just need to construct the right model identifier.

    In test mode (AIRBEEPS_TEST_MODE=1), returns a FakeLiteLLMClient that
    produces deterministic responses without making any external API calls.

    Args:
        provider: ModelProvider instance with category, litellm_provider, api_key, api_base_url
        model_name: Model name
        temperature: Temperature parameter
        max_tokens: Max output tokens
        **additional_params: Other additional parameters

    Returns:
        LiteLLMClient or FakeLiteLLMClient: Chat client instance

    Raises:
        ValueError: Raised when creation fails
    """
    # Check for test mode first - return fake client without any external setup
    if _is_test_mode():
        logger.info(f"TEST_MODE: Creating FakeLiteLLMClient for model: {model_name}")
        return FakeLiteLLMClient(
            model=f"fake/{model_name}",
            api_key=None,
            base_url=None,
            temperature=temperature,
            max_tokens=max_tokens,
            **additional_params,
        )

    # Build LiteLLM model identifier
    # Format: provider/model-name (e.g., "groq/llama-3.3-70b", "gemini/gemini-1.5-pro")
    full_model_name = f"{provider.litellm_provider}/{model_name}"

    logger.info(f"Creating LiteLLM client for: {full_model_name}")

    # Prepare client parameters
    client_params = {
        "model": full_model_name,
        "api_key": provider.api_key,
        "temperature": temperature,
        "max_tokens": max_tokens,
        **additional_params,
    }

    # Add base_url for custom endpoints
    if provider.api_base_url:
        client_params["base_url"] = provider.api_base_url

    # For OpenAI-compatible providers, specify custom_llm_provider
    # This helps LiteLLM route correctly
    from airbeeps.ai_models.models import ProviderCategoryEnum

    if provider.category == ProviderCategoryEnum.OPENAI_COMPATIBLE or (
        provider.category == ProviderCategoryEnum.CUSTOM
        and provider.is_openai_compatible
    ):
        client_params["custom_llm_provider"] = provider.litellm_provider
        logger.info(f"Using custom LiteLLM provider: {provider.litellm_provider}")

    try:
        return LiteLLMClient(**client_params)
    except Exception as e:
        error_msg = f"Failed to create chat model {full_model_name}: {e!s}"
        logger.error(error_msg)
        raise ValueError(error_msg)
