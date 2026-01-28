"""
Authentication Router Tests.

This module contains tests for the authentication endpoints including
user registration, login, password management, and token validation.

Tests use fixtures from conftest.py for database and client setup.
"""

import pytest
from httpx import AsyncClient


class TestUserRegistration:
    """Tests for user registration endpoint."""

    @pytest.mark.asyncio
    async def test_register_new_user_success(
        self, async_client: AsyncClient, test_db
    ) -> None:
        """Test successful user registration with valid data.

        Args:
            async_client: The async HTTP client fixture.
            test_db: The test database fixture.
        """
        user_data = {
            "username": "new_user",
            "email": "new_user@example.com",
            "password": "secure_password123",
            "organization": "Test Organization",
            "account_type": "Free",
        }

        response = await async_client.post("/auth/register", json=user_data)

        assert response.status_code == 201
        response_data = response.json()
        assert response_data["username"] == user_data["username"]
        assert response_data["email"] == user_data["email"]
        assert response_data["organization"] == user_data["organization"]
        assert response_data["account_type"] == user_data["account_type"]
        assert "id" in response_data
        assert "password" not in response_data

    @pytest.mark.asyncio
    async def test_register_duplicate_username(
        self, async_client: AsyncClient, test_db
    ) -> None:
        """Test registration fails with duplicate username.

        Args:
            async_client: The async HTTP client fixture.
            test_db: The test database fixture.
        """
        user_data = {
            "username": "duplicate_user",
            "email": "first@example.com",
            "password": "password123",
            "organization": "Org 1",
            "account_type": "Free",
        }

        # First registration should succeed
        response1 = await async_client.post("/auth/register", json=user_data)
        assert response1.status_code == 201

        # Second registration with same username should fail
        user_data["email"] = "second@example.com"
        response2 = await async_client.post("/auth/register", json=user_data)
        assert response2.status_code == 409  # ConflictError returns 409

    @pytest.mark.asyncio
    async def test_register_duplicate_email(
        self, async_client: AsyncClient, test_db
    ) -> None:
        """Test registration fails with duplicate email.

        Args:
            async_client: The async HTTP client fixture.
            test_db: The test database fixture.
        """
        user_data = {
            "username": "user_one",
            "email": "duplicate@example.com",
            "password": "password123",
            "organization": "Org 1",
            "account_type": "Free",
        }

        # First registration should succeed
        response1 = await async_client.post("/auth/register", json=user_data)
        assert response1.status_code == 201

        # Second registration with same email should fail
        user_data["username"] = "user_two"
        response2 = await async_client.post("/auth/register", json=user_data)
        assert response2.status_code == 409  # ConflictError returns 409

    @pytest.mark.asyncio
    async def test_register_invalid_email(
        self, async_client: AsyncClient, test_db
    ) -> None:
        """Test registration fails with invalid email format.

        Args:
            async_client: The async HTTP client fixture.
            test_db: The test database fixture.
        """
        user_data = {
            "username": "test_user",
            "email": "not-a-valid-email",
            "password": "password123",
            "organization": "Test Org",
            "account_type": "Free",
        }

        response = await async_client.post("/auth/register", json=user_data)
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_register_missing_required_fields(
        self, async_client: AsyncClient, test_db
    ) -> None:
        """Test registration fails when required fields are missing.

        Args:
            async_client: The async HTTP client fixture.
            test_db: The test database fixture.
        """
        # Missing password
        user_data = {
            "username": "test_user",
            "email": "test@example.com",
            "organization": "Test Org",
        }

        response = await async_client.post("/auth/register", json=user_data)
        assert response.status_code == 422


class TestUserLogin:
    """Tests for user login endpoint."""

    @pytest.mark.asyncio
    async def test_login_success(
        self, async_client: AsyncClient, test_user: dict
    ) -> None:
        """Test successful login with valid credentials.

        Args:
            async_client: The async HTTP client fixture.
            test_user: The test user fixture with credentials.
        """
        login_data = {
            "username": test_user["username"],
            "password": test_user["password"],
        }

        response = await async_client.post(
            "/auth/token",
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        assert response.status_code == 200
        response_data = response.json()
        assert "access_token" in response_data
        assert response_data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_login_wrong_password(
        self, async_client: AsyncClient, test_user: dict
    ) -> None:
        """Test login fails with incorrect password.

        Args:
            async_client: The async HTTP client fixture.
            test_user: The test user fixture with credentials.
        """
        login_data = {
            "username": test_user["username"],
            "password": "wrong_password",
        }

        response = await async_client.post(
            "/auth/token",
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(
        self, async_client: AsyncClient, test_db
    ) -> None:
        """Test login fails for non-existent user.

        Args:
            async_client: The async HTTP client fixture.
            test_db: The test database fixture.
        """
        login_data = {
            "username": "nonexistent_user",
            "password": "any_password",
        }

        response = await async_client.post(
            "/auth/token",
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        assert response.status_code == 401


class TestCurrentUser:
    """Tests for getting current user endpoint."""

    @pytest.mark.asyncio
    async def test_get_current_user_success(
        self, async_client: AsyncClient, test_user: dict
    ) -> None:
        """Test getting current user with valid token.

        Args:
            async_client: The async HTTP client fixture.
            test_user: The test user fixture with token.
        """
        response = await async_client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        assert response.status_code == 200
        response_data = response.json()
        assert response_data["username"] == test_user["username"]
        assert response_data["email"] == test_user["email"]

    @pytest.mark.asyncio
    async def test_get_current_user_no_token(
        self, async_client: AsyncClient, test_db
    ) -> None:
        """Test getting current user fails without token.

        Args:
            async_client: The async HTTP client fixture.
            test_db: The test database fixture.
        """
        response = await async_client.get("/auth/me")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(
        self, async_client: AsyncClient, test_db
    ) -> None:
        """Test getting current user fails with invalid token.

        Args:
            async_client: The async HTTP client fixture.
            test_db: The test database fixture.
        """
        response = await async_client.get(
            "/auth/me",
            headers={"Authorization": "Bearer invalid_token_here"},
        )

        assert response.status_code == 401


class TestPasswordChange:
    """Tests for password change endpoint."""

    @pytest.mark.asyncio
    async def test_change_password_success(
        self, async_client: AsyncClient, test_user: dict
    ) -> None:
        """Test successful password change.

        Args:
            async_client: The async HTTP client fixture.
            test_user: The test user fixture with credentials.
        """
        password_data = {
            "old_password": test_user["password"],
            "new_password": "new_secure_password123",
        }

        response = await async_client.post(
            "/auth/change-password",
            json=password_data,
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        assert response.status_code == 200

        # Verify can login with new password
        login_data = {
            "username": test_user["username"],
            "password": "new_secure_password123",
        }
        login_response = await async_client.post(
            "/auth/token",
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert login_response.status_code == 200

    @pytest.mark.asyncio
    async def test_change_password_wrong_old_password(
        self, async_client: AsyncClient, test_user: dict
    ) -> None:
        """Test password change fails with wrong old password.

        Args:
            async_client: The async HTTP client fixture.
            test_user: The test user fixture with credentials.
        """
        password_data = {
            "old_password": "wrong_old_password",
            "new_password": "new_password123",
        }

        response = await async_client.post(
            "/auth/change-password",
            json=password_data,
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        assert response.status_code == 401  # AuthenticationError returns 401
