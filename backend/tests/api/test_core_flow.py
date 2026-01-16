"""
Core flow integration test.

This test validates the complete user journey:
1. Register a new user (becomes admin)
2. Login
3. Create a model provider
4. Create a model
5. Create an assistant
6. Create a conversation
7. Send a chat message and receive a deterministic response

Uses the fresh_client fixture for complete database isolation.
"""

import pytest

from tests.helpers import (
    create_assistant,
    create_conversation,
    create_model,
    create_provider,
    login_and_get_cookies,
    post_chat_and_collect_sse_events,
    register_user,
)
from tests.helpers.api import get_final_content_from_events, get_token_usage_from_events


class TestCoreFlow:
    """Integration tests for the core application flow."""

    @pytest.mark.asyncio
    async def test_complete_user_journey(self, fresh_client):
        """
        Test the complete user journey from registration to chat.

        This test exercises the primary product flow and validates that:
        - User registration and login work
        - Admin can create providers, models, and assistants
        - Chat works with the fake LLM client in test mode
        - Response includes deterministic content and token usage
        """
        client = fresh_client

        # Step 1: Register a new user (first user becomes admin)
        email = "admin@test.com"
        password = "SecurePassword123!"

        register_response = await register_user(
            client,
            email=email,
            password=password,
            name="Test Admin",
        )
        assert register_response.status_code == 201, (
            f"Registration failed: {register_response.text}"
        )

        user_data = register_response.json()
        assert user_data["email"] == email
        assert user_data["is_superuser"] is True, "First user should be superuser"

        # Step 2: Login
        cookies = await login_and_get_cookies(client, email=email, password=password)
        assert cookies, "Login should return auth cookies"

        # Step 3: Create a model provider
        provider_response = await create_provider(
            client,
            cookies,
            name="test-openai",
            display_name="Test OpenAI Provider",
            category="PROVIDER_SPECIFIC",
            litellm_provider="openai",
            api_base_url="https://api.openai.com/v1",
            api_key="sk-test-key",
        )
        assert provider_response.status_code in (200, 201), (
            f"Create provider failed: {provider_response.text}"
        )

        provider_data = provider_response.json()
        provider_id = provider_data["id"]
        assert provider_data["name"] == "test-openai"

        # Step 4: Create a model
        model_response = await create_model(
            client,
            cookies,
            provider_id=provider_id,
            name="gpt-4-test",
            display_name="GPT-4 Test Model",
            capabilities=["chat"],
        )
        assert model_response.status_code in (200, 201), (
            f"Create model failed: {model_response.text}"
        )

        model_data = model_response.json()
        model_id = model_data["id"]
        assert model_data["name"] == "gpt-4-test"

        # Step 5: Create an assistant
        assistant_response = await create_assistant(
            client,
            cookies,
            model_id=model_id,
            name="Test Chat Assistant",
            system_prompt="You are a helpful test assistant.",
            is_public=True,
        )
        assert assistant_response.status_code in (200, 201), (
            f"Create assistant failed: {assistant_response.text}"
        )

        assistant_data = assistant_response.json()
        assistant_id = assistant_data["id"]
        assert assistant_data["name"] == "Test Chat Assistant"

        # Step 6: Create a conversation
        conversation_response = await create_conversation(
            client,
            cookies,
            assistant_id=assistant_id,
            title="Test Conversation",
        )
        assert conversation_response.status_code == 200, (
            f"Create conversation failed: {conversation_response.text}"
        )

        conversation_data = conversation_response.json()
        conversation_id = conversation_data["id"]

        # Step 7: Send a chat message
        test_message = "Hello, this is a test message!"

        events = await post_chat_and_collect_sse_events(
            client,
            cookies,
            conversation_id=conversation_id,
            content=test_message,
        )

        # Validate SSE events
        assert len(events) > 0, "Should receive SSE events"

        # Check for content chunks
        content_chunks = [e for e in events if e.get("type") == "content_chunk"]
        assert len(content_chunks) > 0, "Should receive content chunks"

        # Validate deterministic fake response
        final_content = get_final_content_from_events(events)
        assert final_content, "Should have final content"
        assert "TEST_MODE_RESPONSE:" in final_content, (
            f"Response should contain test mode prefix. Got: {final_content}"
        )
        assert test_message in final_content, (
            f"Response should echo the user message. Got: {final_content}"
        )

        # Validate token usage
        token_usage = get_token_usage_from_events(events)
        assert token_usage is not None, "Should receive token usage"
        assert "total_tokens" in token_usage, "Token usage should have total_tokens"
        assert token_usage["total_tokens"] > 0, "Total tokens should be positive"

    @pytest.mark.asyncio
    async def test_second_user_is_not_admin(self, fresh_client):
        """
        Test that only the first user becomes admin.

        Subsequent users should have is_superuser=False.
        """
        client = fresh_client

        # Register first user (becomes admin)
        first_response = await register_user(
            client,
            email="first@test.com",
            password="Password123!",
        )
        assert first_response.status_code == 201
        first_user = first_response.json()
        assert first_user["is_superuser"] is True

        # Register second user (should NOT be admin)
        second_response = await register_user(
            client,
            email="second@test.com",
            password="Password123!",
        )
        assert second_response.status_code == 201
        second_user = second_response.json()
        assert second_user["is_superuser"] is False, (
            "Second user should not be superuser"
        )

    @pytest.mark.asyncio
    async def test_provider_test_connection_in_test_mode(self, fresh_client):
        """
        Test that provider test-connection returns mock success in test mode.
        """
        client = fresh_client

        # Register and login
        await register_user(client, email="test@test.com", password="Password123!")
        cookies = await login_and_get_cookies(
            client, email="test@test.com", password="Password123!"
        )

        # Create a provider
        provider_response = await create_provider(client, cookies)
        assert provider_response.status_code == 201
        provider_id = provider_response.json()["id"]

        # Test connection (should succeed in test mode without real HTTP call)
        headers = {"Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items())}
        test_response = await client.post(
            f"/api/v1/admin/providers/{provider_id}/test-connection",
            headers=headers,
        )

        assert test_response.status_code == 200
        test_data = test_response.json()
        assert test_data["ok"] is True
        assert "TEST_MODE" in test_data.get("message", "")
