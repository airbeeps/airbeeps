"""
Test data factories for Airbeeps backend tests.

These factories provide convenient methods to generate test data,
reducing boilerplate in tests and ensuring consistent test data structure.
"""

import uuid
from typing import Any, Dict, List, Optional


def make_user_data(
    email: str | None = None,
    password: str = "TestPassword123!",  # noqa: S107
    name: str | None = None,
) -> dict[str, Any]:
    """
    Generate user registration data.

    Args:
        email: User email (auto-generated if not provided)
        password: User password
        name: Optional user name

    Returns:
        Dictionary suitable for user registration endpoint
    """
    data = {
        "email": email or f"test-{uuid.uuid4().hex[:8]}@example.com",
        "password": password,
    }
    if name:
        data["name"] = name
    return data


def make_provider_data(
    name: str | None = None,
    display_name: str | None = None,
    category: str = "PROVIDER_SPECIFIC",
    is_openai_compatible: bool = False,
    litellm_provider: str = "openai",
    api_base_url: str = "https://api.test.com/v1",
    api_key: str = "test-api-key",
    status: str = "ACTIVE",
) -> dict[str, Any]:
    """
    Generate model provider data.

    Args:
        name: Provider unique name (auto-generated if not provided)
        display_name: Human-readable name
        category: Provider category (OPENAI_COMPATIBLE, PROVIDER_SPECIFIC, CUSTOM, LOCAL)
        is_openai_compatible: Whether custom endpoint is OpenAI-compatible
        litellm_provider: LiteLLM provider identifier
        api_base_url: API base URL
        api_key: API key
        status: Provider status

    Returns:
        Dictionary suitable for provider creation endpoint
    """
    unique_id = uuid.uuid4().hex[:8]
    return {
        "name": name or f"test-provider-{unique_id}",
        "display_name": display_name or f"Test Provider {unique_id}",
        "category": category,
        "is_openai_compatible": is_openai_compatible,
        "litellm_provider": litellm_provider,
        "api_base_url": api_base_url,
        "api_key": api_key,
        "status": status,
    }


def make_model_data(
    provider_id: str,
    name: str | None = None,
    display_name: str | None = None,
    capabilities: list[str] | None = None,
    status: str = "ACTIVE",
) -> dict[str, Any]:
    """
    Generate model data.

    Args:
        provider_id: ID of the provider to associate with
        name: Model unique name (auto-generated if not provided)
        display_name: Human-readable name
        capabilities: List of model capabilities
        status: Model status

    Returns:
        Dictionary suitable for model creation endpoint
    """
    unique_id = uuid.uuid4().hex[:8]
    return {
        "name": name or f"test-model-{unique_id}",
        "display_name": display_name or f"Test Model {unique_id}",
        "provider_id": provider_id,
        "capabilities": capabilities or ["chat"],
        "status": status,
    }


def make_assistant_data(
    model_id: str,
    name: str | None = None,
    system_prompt: str = "You are a helpful test assistant.",
    is_public: bool = True,
    status: str = "ACTIVE",
) -> dict[str, Any]:
    """
    Generate assistant data.

    Args:
        model_id: ID of the model to use
        name: Assistant name (auto-generated if not provided)
        system_prompt: System prompt for the assistant
        is_public: Whether assistant is publicly accessible
        status: Assistant status

    Returns:
        Dictionary suitable for assistant creation endpoint
    """
    unique_id = uuid.uuid4().hex[:8]
    return {
        "name": name or f"Test Assistant {unique_id}",
        "model_id": model_id,
        "system_prompt": system_prompt,
        "is_public": is_public,
        "status": status,
    }


def make_conversation_data(
    assistant_id: str,
    title: str | None = None,
) -> dict[str, Any]:
    """
    Generate conversation data.

    Args:
        assistant_id: ID of the assistant for this conversation
        title: Optional conversation title

    Returns:
        Dictionary suitable for conversation creation endpoint
    """
    data = {
        "assistant_id": assistant_id,
    }
    if title:
        data["title"] = title
    return data


def make_chat_message_data(
    conversation_id: str,
    content: str = "Hello, this is a test message!",
    language: str = "en",
) -> dict[str, Any]:
    """
    Generate chat message data.

    Args:
        conversation_id: ID of the conversation
        content: Message content
        language: Language code

    Returns:
        Dictionary suitable for chat endpoint
    """
    return {
        "conversation_id": conversation_id,
        "content": content,
        "language": language,
    }
