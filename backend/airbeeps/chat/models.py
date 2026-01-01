"""
Chat models and schemas for LiteLLM
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class MessageRole(Enum):
    """Message role enumeration"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class ChatMessage:
    """Unified chat message structure

    content can be either:
    - str: Simple text content
    - list: Multi-modal content with mixed text and images
      Example: [{"type": "text", "text": "..."}, {"type": "image_url", "image_url": {"url": "..."}}]
    """

    role: MessageRole
    content: str | list[dict[str, Any]]
    metadata: dict[str, Any] | None = None

    def to_litellm_message(self) -> dict[str, Any]:
        """Convert to LiteLLM message format"""
        return {"role": self.role.value, "content": self.content}

    @classmethod
    def from_litellm_message(cls, message: dict[str, Any]) -> "ChatMessage":
        """Create from LiteLLM message"""
        role_str = message.get("role", "user")
        try:
            role = MessageRole(role_str)
        except ValueError:
            raise ValueError(f"Unsupported role: {role_str}")

        return cls(role=role, content=message.get("content", ""))


@dataclass
class ChatCompletionRequest:
    """Chat completion request"""

    messages: list[ChatMessage]
    model: str
    temperature: float | None = None
    max_tokens: int | None = None
    stream: bool = False
    additional_params: dict[str, Any] | None = None


@dataclass
class ChatCompletionResponse:
    """Chat completion response"""

    content: str
    model: str
    token_usage: dict[str, int] | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class StreamChunk:
    """Streaming response chunk"""

    content: str
    is_final: bool = False
    metadata: dict[str, Any] | None = None


class ChatProviderError(Exception):
    """Base exception for chat provider errors"""


class ModelNotFoundError(ChatProviderError):
    """Exception raised when model is not found"""


class InvalidRequestError(ChatProviderError):
    """Exception raised for invalid requests"""


class RateLimitError(ChatProviderError):
    """Exception raised when rate limit is exceeded"""


class AuthenticationError(ChatProviderError):
    """Exception raised for authentication failures"""
