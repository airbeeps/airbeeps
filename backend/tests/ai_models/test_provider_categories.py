"""
Tests for provider category system.

Validates:
- Provider creation with new category field
- Connection testing for different categories
- Model discovery for different categories
"""

import pytest

from tests.helpers import (
    create_provider,
    login_and_get_cookies,
    register_user,
)


class TestProviderCategories:
    """Tests for the new provider category system."""

    @pytest.mark.asyncio
    async def test_create_openai_compatible_provider(self, fresh_client):
        """Test creating an OpenAI-compatible provider (e.g., Groq)."""
        client = fresh_client

        # Register and login
        email = "admin@test.com"
        password = "SecurePassword123!"
        await register_user(client, email=email, password=password, name="Test Admin")
        cookies = await login_and_get_cookies(client, email=email, password=password)

        # Create OpenAI-compatible provider
        response = await create_provider(
            client,
            cookies,
            name="test-groq",
            display_name="Test Groq Provider",
            category="OPENAI_COMPATIBLE",
            is_openai_compatible=True,
            litellm_provider="groq",
            api_base_url="https://api.groq.com/openai/v1",
            api_key="gsk-test-key",
        )

        assert response.status_code in (200, 201), (
            f"Create provider failed: {response.text}"
        )
        data = response.json()
        assert data["name"] == "test-groq"
        assert data["category"] == "OPENAI_COMPATIBLE"
        assert data["is_openai_compatible"] is True
        assert data["litellm_provider"] == "groq"

    @pytest.mark.asyncio
    async def test_create_provider_specific_provider(self, fresh_client):
        """Test creating a provider-specific provider (e.g., Gemini)."""
        client = fresh_client

        # Register and login
        email = "admin@test.com"
        password = "SecurePassword123!"
        await register_user(client, email=email, password=password, name="Test Admin")
        cookies = await login_and_get_cookies(client, email=email, password=password)

        # Create provider-specific provider
        response = await create_provider(
            client,
            cookies,
            name="test-gemini",
            display_name="Test Gemini Provider",
            category="PROVIDER_SPECIFIC",
            is_openai_compatible=False,
            litellm_provider="gemini",
            api_base_url="https://generativelanguage.googleapis.com",
            api_key="test-gemini-key",
        )

        assert response.status_code in (200, 201), (
            f"Create provider failed: {response.text}"
        )
        data = response.json()
        assert data["name"] == "test-gemini"
        assert data["category"] == "PROVIDER_SPECIFIC"
        assert data["is_openai_compatible"] is False
        assert data["litellm_provider"] == "gemini"

    @pytest.mark.asyncio
    async def test_create_custom_provider(self, fresh_client):
        """Test creating a custom provider."""
        client = fresh_client

        # Register and login
        email = "admin@test.com"
        password = "SecurePassword123!"
        await register_user(client, email=email, password=password, name="Test Admin")
        cookies = await login_and_get_cookies(client, email=email, password=password)

        # Create custom provider
        response = await create_provider(
            client,
            cookies,
            name="test-custom",
            display_name="Test Custom Provider",
            category="CUSTOM",
            is_openai_compatible=True,
            litellm_provider="openai",
            api_base_url="http://localhost:8000/v1",
            api_key="test-key",
        )

        assert response.status_code in (200, 201), (
            f"Create provider failed: {response.text}"
        )
        data = response.json()
        assert data["name"] == "test-custom"
        assert data["category"] == "CUSTOM"
        assert data["is_openai_compatible"] is True

    @pytest.mark.asyncio
    async def test_provider_test_connection_in_test_mode(self, fresh_client):
        """
        Test that provider test-connection returns mock success in test mode.
        """
        client = fresh_client

        # Register and login
        email = "admin@test.com"
        password = "SecurePassword123!"
        await register_user(client, email=email, password=password, name="Test Admin")
        cookies = await login_and_get_cookies(client, email=email, password=password)

        # Create provider
        provider_response = await create_provider(
            client,
            cookies,
            name="test-provider",
            display_name="Test Provider",
            category="OPENAI_COMPATIBLE",
            is_openai_compatible=True,
            litellm_provider="groq",
            api_base_url="https://api.groq.com/openai/v1",
            api_key="test-key",
        )
        provider_id = provider_response.json()["id"]

        # Test connection (should succeed in test mode without real HTTP call)
        response = await client.post(
            f"/api/v1/admin/providers/{provider_id}/test-connection",
            cookies=cookies,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "TEST_MODE" in data["message"]

    @pytest.mark.asyncio
    async def test_provider_discover_models_in_test_mode(self, fresh_client):
        """
        Test that provider discover-models returns mock models in test mode.
        """
        client = fresh_client

        # Register and login
        email = "admin@test.com"
        password = "SecurePassword123!"
        await register_user(client, email=email, password=password, name="Test Admin")
        cookies = await login_and_get_cookies(client, email=email, password=password)

        # Create provider
        provider_response = await create_provider(
            client,
            cookies,
            name="test-provider",
            display_name="Test Provider",
            category="OPENAI_COMPATIBLE",
            is_openai_compatible=True,
            litellm_provider="groq",
            api_base_url="https://api.groq.com/openai/v1",
            api_key="test-key",
        )
        provider_id = provider_response.json()["id"]

        # Discover models (should return mock models in test mode)
        response = await client.get(
            f"/api/v1/admin/providers/{provider_id}/discover-models",
            cookies=cookies,
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert "test-model" in str(data).lower()

    @pytest.mark.asyncio
    async def test_provider_discover_models_with_method_param(self, fresh_client):
        """
        Test that provider discover-models accepts method parameter.
        """
        client = fresh_client

        # Register and login
        email = "admin@test.com"
        password = "SecurePassword123!"
        await register_user(client, email=email, password=password, name="Test Admin")
        cookies = await login_and_get_cookies(client, email=email, password=password)

        # Create provider
        provider_response = await create_provider(
            client,
            cookies,
            name="test-provider",
            display_name="Test Provider",
            category="PROVIDER_SPECIFIC",
            is_openai_compatible=False,
            litellm_provider="gemini",
            api_base_url="https://generativelanguage.googleapis.com",
            api_key="test-key",
        )
        provider_id = provider_response.json()["id"]

        # Test with different methods
        for method in ["auto", "quick", "comprehensive"]:
            response = await client.get(
                f"/api/v1/admin/providers/{provider_id}/discover-models?method={method}",
                cookies=cookies,
            )

            assert response.status_code == 200, (
                f"Method {method} failed: {response.text}"
            )
            data = response.json()
            assert isinstance(data, list)
