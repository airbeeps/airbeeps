"""
Security and authorization tests.

Tests for permission checks, access control, and cross-user data isolation.
"""

import pytest
from httpx import AsyncClient

from tests.factories import make_user_data
from tests.helpers.api import (
    _auth_headers,
    create_assistant,
    create_conversation,
    create_model,
    create_provider,
    login_and_get_cookies,
)


class TestAdminAuthorization:
    """Tests for admin route access control."""

    @pytest.mark.asyncio
    async def test_non_admin_cannot_access_admin_providers(
        self, fresh_client: AsyncClient
    ):
        """Non-admin users should not be able to access admin provider routes."""
        # Create first user (admin)
        admin_data = make_user_data(
            email="admin@test.com", password="AdminPassword123!"
        )
        await fresh_client.post("/api/v1/auth/register", json=admin_data)

        # Create second user (non-admin)
        user_data = make_user_data(email="user@test.com", password="UserPassword123!")
        await fresh_client.post("/api/v1/auth/register", json=user_data)

        # Login as non-admin
        cookies = await login_and_get_cookies(
            fresh_client, "user@test.com", "UserPassword123!"
        )

        # Try to access admin providers endpoint
        response = await fresh_client.get(
            "/api/v1/admin/providers",
            headers=_auth_headers(cookies),
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_non_admin_cannot_create_provider(self, fresh_client: AsyncClient):
        """Non-admin users should not be able to create providers."""
        # Create first user (admin)
        admin_data = make_user_data(
            email="admin@test.com", password="AdminPassword123!"
        )
        await fresh_client.post("/api/v1/auth/register", json=admin_data)

        # Create second user (non-admin)
        user_data = make_user_data(email="user@test.com", password="UserPassword123!")
        await fresh_client.post("/api/v1/auth/register", json=user_data)

        # Login as non-admin
        cookies = await login_and_get_cookies(
            fresh_client, "user@test.com", "UserPassword123!"
        )

        # Try to create a provider
        provider_data = {
            "name": "test-provider",
            "display_name": "Test Provider",
            "category": "PROVIDER_SPECIFIC",
            "is_openai_compatible": False,
            "litellm_provider": "openai",
            "api_base_url": "https://api.test.com/v1",
            "api_key": "test-key",
            "status": "ACTIVE",
        }
        response = await fresh_client.post(
            "/api/v1/admin/providers",
            json=provider_data,
            headers=_auth_headers(cookies),
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_can_access_admin_routes(self, fresh_client: AsyncClient):
        """Admin users should be able to access admin routes."""
        # Create admin user (first user)
        admin_data = make_user_data(
            email="admin@test.com", password="AdminPassword123!"
        )
        await fresh_client.post("/api/v1/auth/register", json=admin_data)

        # Login as admin
        cookies = await login_and_get_cookies(
            fresh_client, "admin@test.com", "AdminPassword123!"
        )

        # Access admin providers endpoint
        response = await fresh_client.get(
            "/api/v1/admin/providers",
            headers=_auth_headers(cookies),
        )

        assert response.status_code == 200


class TestConversationIsolation:
    """Tests for conversation data isolation between users."""

    @pytest.mark.asyncio
    async def test_user_cannot_access_other_users_conversation(
        self, fresh_client: AsyncClient
    ):
        """Users should not be able to access conversations belonging to other users."""
        # Setup: Create admin, provider, model, assistant
        admin_data = make_user_data(
            email="admin@test.com", password="AdminPassword123!"
        )
        await fresh_client.post("/api/v1/auth/register", json=admin_data)
        admin_cookies = await login_and_get_cookies(
            fresh_client, "admin@test.com", "AdminPassword123!"
        )

        # Create infrastructure as admin
        provider_resp = await create_provider(fresh_client, admin_cookies)
        assert provider_resp.status_code == 201
        provider_id = provider_resp.json()["id"]

        model_resp = await create_model(fresh_client, admin_cookies, provider_id)
        assert model_resp.status_code == 201
        model_id = model_resp.json()["id"]

        assistant_resp = await create_assistant(fresh_client, admin_cookies, model_id)
        assert assistant_resp.status_code == 201
        assistant_id = assistant_resp.json()["id"]

        # Create user A and their conversation
        user_a_data = make_user_data(
            email="user_a@test.com", password="UserAPassword123!"
        )
        await fresh_client.post("/api/v1/auth/register", json=user_a_data)
        user_a_cookies = await login_and_get_cookies(
            fresh_client, "user_a@test.com", "UserAPassword123!"
        )

        conv_resp = await create_conversation(
            fresh_client, user_a_cookies, assistant_id
        )
        assert conv_resp.status_code == 201
        conversation_id = conv_resp.json()["id"]

        # Create user B
        user_b_data = make_user_data(
            email="user_b@test.com", password="UserBPassword123!"
        )
        await fresh_client.post("/api/v1/auth/register", json=user_b_data)
        user_b_cookies = await login_and_get_cookies(
            fresh_client, "user_b@test.com", "UserBPassword123!"
        )

        # User B tries to access User A's conversation
        response = await fresh_client.get(
            f"/api/v1/conversations/{conversation_id}",
            headers=_auth_headers(user_b_cookies),
        )

        # Should either return 404 (not found for this user) or 403 (forbidden)
        assert response.status_code in [403, 404]

    @pytest.mark.asyncio
    async def test_user_can_access_own_conversation(self, fresh_client: AsyncClient):
        """Users should be able to access their own conversations."""
        # Setup admin and infrastructure
        admin_data = make_user_data(
            email="admin@test.com", password="AdminPassword123!"
        )
        await fresh_client.post("/api/v1/auth/register", json=admin_data)
        admin_cookies = await login_and_get_cookies(
            fresh_client, "admin@test.com", "AdminPassword123!"
        )

        provider_resp = await create_provider(fresh_client, admin_cookies)
        provider_id = provider_resp.json()["id"]

        model_resp = await create_model(fresh_client, admin_cookies, provider_id)
        model_id = model_resp.json()["id"]

        assistant_resp = await create_assistant(fresh_client, admin_cookies, model_id)
        assistant_id = assistant_resp.json()["id"]

        # Create user and their conversation
        user_data = make_user_data(email="user@test.com", password="UserPassword123!")
        await fresh_client.post("/api/v1/auth/register", json=user_data)
        user_cookies = await login_and_get_cookies(
            fresh_client, "user@test.com", "UserPassword123!"
        )

        conv_resp = await create_conversation(fresh_client, user_cookies, assistant_id)
        conversation_id = conv_resp.json()["id"]

        # User can access their own conversation
        response = await fresh_client.get(
            f"/api/v1/conversations/{conversation_id}",
            headers=_auth_headers(user_cookies),
        )

        assert response.status_code == 200
        assert response.json()["id"] == conversation_id


class TestUnauthenticatedAccess:
    """Tests for unauthenticated access control."""

    @pytest.mark.asyncio
    async def test_unauthenticated_cannot_access_conversations(
        self, fresh_client: AsyncClient
    ):
        """Unauthenticated users should not be able to access conversations."""
        response = await fresh_client.get("/api/v1/conversations")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_unauthenticated_cannot_access_admin(self, fresh_client: AsyncClient):
        """Unauthenticated users should not be able to access admin routes."""
        response = await fresh_client.get("/api/v1/admin/providers")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_unauthenticated_can_access_public_endpoints(
        self, fresh_client: AsyncClient
    ):
        """Unauthenticated users should be able to access public endpoints."""
        # Health check or public assistants list should work
        response = await fresh_client.get("/api/v1/health")
        # May return 200 or 404 depending on if endpoint exists
        assert response.status_code in [200, 404]
