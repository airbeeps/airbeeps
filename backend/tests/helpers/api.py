"""
API test helpers for Airbeeps backend tests.

These helper functions simplify common API operations in tests,
reducing boilerplate and making tests more readable.
"""

import json
from typing import Any

from httpx import AsyncClient, Response


async def register_user(
    client: AsyncClient,
    email: str = "test@example.com",
    password: str = "TestPassword123!",  # noqa: S107
    name: str | None = None,
) -> Response:
    """
    Register a new user.

    Note: The first user registered becomes a superuser/admin automatically.

    Args:
        client: Test HTTP client
        email: User email
        password: User password
        name: Optional user name

    Returns:
        Response from the registration endpoint
    """
    payload = {
        "email": email,
        "password": password,
    }
    if name:
        payload["name"] = name

    response = await client.post("/api/v1/auth/register", json=payload)
    return response


async def login_and_get_cookies(
    client: AsyncClient,
    email: str = "test@example.com",
    password: str = "TestPassword123!",  # noqa: S107
) -> dict[str, str]:
    """
    Login and return cookies for authenticated requests.

    Args:
        client: Test HTTP client
        email: User email
        password: User password

    Returns:
        Dictionary of cookies from the login response
    """
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
    )

    if response.status_code != 200:
        raise ValueError(f"Login failed: {response.status_code} - {response.text}")

    # Extract cookies from response
    cookies = {}
    for cookie in response.cookies.jar:
        cookies[cookie.name] = cookie.value

    return cookies


def _auth_headers(cookies: dict[str, str]) -> dict[str, str]:
    """Create headers with auth cookies."""
    if not cookies:
        return {}

    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
    return {"Cookie": cookie_str}


async def create_provider(
    client: AsyncClient,
    cookies: dict[str, str],
    name: str = "test-provider",
    display_name: str = "Test Provider",
    interface_type: str = "OPENAI",
    api_base_url: str = "https://api.test.com/v1",
    api_key: str = "test-api-key",
) -> Response:
    """
    Create a model provider via admin API.

    Args:
        client: Test HTTP client
        cookies: Auth cookies from login
        name: Provider name (unique identifier)
        display_name: Display name for the provider
        interface_type: Provider interface type (OPENAI, ANTHROPIC, etc.)
        api_base_url: API base URL
        api_key: API key for the provider

    Returns:
        Response from the create provider endpoint
    """
    payload = {
        "name": name,
        "display_name": display_name,
        "interface_type": interface_type,
        "api_base_url": api_base_url,
        "api_key": api_key,
        "status": "ACTIVE",
    }

    response = await client.post(
        "/api/v1/admin/providers",
        json=payload,
        headers=_auth_headers(cookies),
    )
    return response


async def create_model(
    client: AsyncClient,
    cookies: dict[str, str],
    provider_id: str,
    name: str = "test-model",
    display_name: str = "Test Model",
    capabilities: list[str] | None = None,
) -> Response:
    """
    Create a model via admin API.

    Args:
        client: Test HTTP client
        cookies: Auth cookies from login
        provider_id: ID of the provider to associate the model with
        name: Model name
        display_name: Display name for the model
        capabilities: List of capabilities (defaults to ["chat"])

    Returns:
        Response from the create model endpoint
    """
    if capabilities is None:
        capabilities = ["chat"]

    payload = {
        "name": name,
        "display_name": display_name,
        "provider_id": provider_id,
        "capabilities": capabilities,
        "status": "ACTIVE",
    }

    response = await client.post(
        "/api/v1/admin/models",
        json=payload,
        headers=_auth_headers(cookies),
    )
    return response


async def create_assistant(
    client: AsyncClient,
    cookies: dict[str, str],
    model_id: str,
    name: str = "Test Assistant",
    system_prompt: str = "You are a helpful test assistant.",
    is_public: bool = True,
) -> Response:
    """
    Create an assistant via admin API.

    Args:
        client: Test HTTP client
        cookies: Auth cookies from login
        model_id: ID of the model to use
        name: Assistant name
        system_prompt: System prompt for the assistant
        is_public: Whether the assistant is publicly accessible

    Returns:
        Response from the create assistant endpoint
    """
    payload = {
        "name": name,
        "model_id": model_id,
        "system_prompt": system_prompt,
        "is_public": is_public,
        "status": "ACTIVE",
    }

    response = await client.post(
        "/api/v1/admin/assistants",
        json=payload,
        headers=_auth_headers(cookies),
    )
    return response


async def create_conversation(
    client: AsyncClient,
    cookies: dict[str, str],
    assistant_id: str,
    title: str | None = None,
) -> Response:
    """
    Create a new conversation with an assistant.

    Args:
        client: Test HTTP client
        cookies: Auth cookies from login
        assistant_id: ID of the assistant to chat with
        title: Optional conversation title

    Returns:
        Response from the create conversation endpoint
    """
    payload = {
        "assistant_id": assistant_id,
    }
    if title:
        payload["title"] = title

    response = await client.post(
        "/api/v1/conversations",
        json=payload,
        headers=_auth_headers(cookies),
    )
    return response


def parse_sse_events(response_text: str) -> list[dict[str, Any]]:
    """
    Parse SSE events from a response text.

    Args:
        response_text: Raw SSE response text

    Returns:
        List of parsed event dictionaries
    """
    events = []

    for line in response_text.strip().split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            data_str = line[6:]  # Remove "data: " prefix
            try:
                event = json.loads(data_str)
                events.append(event)
            except json.JSONDecodeError:
                # Skip malformed events
                pass

    return events


async def post_chat_and_collect_sse_events(
    client: AsyncClient,
    cookies: dict[str, str],
    conversation_id: str,
    content: str,
    language: str = "en",
) -> list[dict[str, Any]]:
    """
    Send a chat message and collect all SSE events from the response.

    Args:
        client: Test HTTP client
        cookies: Auth cookies from login
        conversation_id: ID of the conversation
        content: Message content to send
        language: Language code for the response

    Returns:
        List of parsed SSE event dictionaries
    """
    payload = {
        "conversation_id": conversation_id,
        "content": content,
        "language": language,
    }

    response = await client.post(
        "/api/v1/chat",
        json=payload,
        headers=_auth_headers(cookies),
    )

    if response.status_code != 200:
        raise ValueError(
            f"Chat request failed: {response.status_code} - {response.text}"
        )

    return parse_sse_events(response.text)


def get_final_content_from_events(events: list[dict[str, Any]]) -> str:
    """
    Extract the final assistant message content from SSE events.

    Args:
        events: List of SSE event dictionaries

    Returns:
        Combined content from all content_chunk events
    """
    content_parts = []

    for event in events:
        if event.get("type") == "content_chunk":
            data = event.get("data", {})
            chunk_content = data.get("content", "")
            if chunk_content:
                content_parts.append(chunk_content)

    return "".join(content_parts)


def get_token_usage_from_events(events: list[dict[str, Any]]) -> dict[str, int] | None:
    """
    Extract token usage from SSE events.

    Args:
        events: List of SSE event dictionaries

    Returns:
        Token usage dictionary or None if not found
    """
    for event in events:
        if event.get("type") == "token_usage":
            return event.get("data")

    return None
