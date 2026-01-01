"""
Authentication endpoint tests.

Tests for user registration, login, logout, and password management.
"""

import pytest
from httpx import AsyncClient

from tests.factories import make_user_data
from tests.helpers.api import _auth_headers, login_and_get_cookies


class TestUserRegistration:
    """Tests for user registration endpoint."""

    @pytest.mark.asyncio
    async def test_register_first_user_becomes_superuser(
        self, fresh_client: AsyncClient
    ):
        """First registered user should automatically become a superuser."""
        user_data = make_user_data(email="first@test.com")
        response = await fresh_client.post("/api/v1/auth/register", json=user_data)

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "first@test.com"
        assert data["is_superuser"] is True

    @pytest.mark.asyncio
    async def test_register_second_user_not_superuser(self, fresh_client: AsyncClient):
        """Second registered user should not be a superuser."""
        # Register first user
        first_user = make_user_data(email="first@test.com")
        await fresh_client.post("/api/v1/auth/register", json=first_user)

        # Register second user
        second_user = make_user_data(email="second@test.com")
        response = await fresh_client.post("/api/v1/auth/register", json=second_user)

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "second@test.com"
        assert data["is_superuser"] is False

    @pytest.mark.asyncio
    async def test_register_duplicate_email_fails(self, fresh_client: AsyncClient):
        """Registering with an existing email should fail."""
        user_data = make_user_data(email="duplicate@test.com")

        # First registration should succeed
        response1 = await fresh_client.post("/api/v1/auth/register", json=user_data)
        assert response1.status_code == 201

        # Second registration with same email should fail
        response2 = await fresh_client.post("/api/v1/auth/register", json=user_data)
        assert response2.status_code == 400

    @pytest.mark.asyncio
    async def test_register_invalid_email_fails(self, fresh_client: AsyncClient):
        """Registration with invalid email format should fail."""
        user_data = {
            "email": "not-an-email",
            "password": "ValidPassword123!",
        }
        response = await fresh_client.post("/api/v1/auth/register", json=user_data)
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_register_weak_password_fails(self, fresh_client: AsyncClient):
        """Registration with a weak password should fail."""
        user_data = {
            "email": "user@test.com",
            "password": "123",  # Too weak
        }
        response = await fresh_client.post("/api/v1/auth/register", json=user_data)
        assert response.status_code == 400


class TestUserLogin:
    """Tests for user login endpoint."""

    @pytest.mark.asyncio
    async def test_login_with_valid_credentials(self, fresh_client: AsyncClient):
        """Login with valid credentials should succeed."""
        # Register user first
        user_data = make_user_data(
            email="login@test.com", password="SecurePassword123!"
        )
        await fresh_client.post("/api/v1/auth/register", json=user_data)

        # Login
        response = await fresh_client.post(
            "/api/v1/auth/login",
            data={"username": "login@test.com", "password": "SecurePassword123!"},
        )

        assert response.status_code == 200
        # Should set auth cookies
        assert len(response.cookies) > 0

    @pytest.mark.asyncio
    async def test_login_with_invalid_password(self, fresh_client: AsyncClient):
        """Login with wrong password should fail."""
        # Register user first
        user_data = make_user_data(
            email="login@test.com", password="CorrectPassword123!"
        )
        await fresh_client.post("/api/v1/auth/register", json=user_data)

        # Login with wrong password
        response = await fresh_client.post(
            "/api/v1/auth/login",
            data={"username": "login@test.com", "password": "WrongPassword123!"},
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_login_with_nonexistent_user(self, fresh_client: AsyncClient):
        """Login with non-existent user should fail."""
        response = await fresh_client.post(
            "/api/v1/auth/login",
            data={"username": "nonexistent@test.com", "password": "SomePassword123!"},
        )

        assert response.status_code == 400


class TestUserLogout:
    """Tests for user logout endpoint."""

    @pytest.mark.asyncio
    async def test_logout_clears_session(self, fresh_client: AsyncClient):
        """Logout should clear the auth session."""
        # Register and login
        user_data = make_user_data(
            email="logout@test.com", password="SecurePassword123!"
        )
        await fresh_client.post("/api/v1/auth/register", json=user_data)
        cookies = await login_and_get_cookies(
            fresh_client, "logout@test.com", "SecurePassword123!"
        )

        # Verify we're authenticated
        me_response = await fresh_client.get(
            "/api/v1/users/me",
            headers=_auth_headers(cookies),
        )
        assert me_response.status_code == 200

        # Logout
        logout_response = await fresh_client.post(
            "/api/v1/auth/logout",
            headers=_auth_headers(cookies),
        )
        assert logout_response.status_code in [200, 204]


class TestCurrentUser:
    """Tests for current user endpoint."""

    @pytest.mark.asyncio
    async def test_get_current_user_authenticated(self, fresh_client: AsyncClient):
        """Authenticated user should be able to get their own info."""
        # Register and login
        user_data = make_user_data(email="me@test.com", password="SecurePassword123!")
        await fresh_client.post("/api/v1/auth/register", json=user_data)
        cookies = await login_and_get_cookies(
            fresh_client, "me@test.com", "SecurePassword123!"
        )

        # Get current user
        response = await fresh_client.get(
            "/api/v1/users/me",
            headers=_auth_headers(cookies),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "me@test.com"

    @pytest.mark.asyncio
    async def test_get_current_user_unauthenticated(self, fresh_client: AsyncClient):
        """Unauthenticated request to /me should fail."""
        response = await fresh_client.get("/api/v1/users/me")
        assert response.status_code == 401
