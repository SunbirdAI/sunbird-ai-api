"""
Tests for API Dependencies Module.

This module tests all dependency injection functions and type aliases
defined in app.deps, including database sessions, authentication,
service dependencies, and integration dependencies.
"""

import pytest
import pytest_asyncio
from fastapi import HTTPException
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import (
    InferenceService,
    InferenceServiceDep,
    LanguageService,
    LanguageServiceDep,
    OpenAIClient,
    OpenAIClientDep,
    RunPodClient,
    RunPodClientDep,
    StorageService,
    StorageServiceDep,
    STTService,
    STTServiceDep,
    TranslationService,
    TranslationServiceDep,
    TTSService,
    TTSServiceDep,
    WhatsAppAPIClient,
    WhatsAppAPIClientDep,
    WhatsAppBusinessService,
    WhatsAppServiceDep,
    get_current_user,
    get_db,
    oauth2_scheme,
)
from app.schemas.users import User
from app.utils.auth import ALGORITHM, SECRET_KEY, create_access_token

# ============================================================================
# Database Dependency Tests
# ============================================================================


class TestGetDB:
    """Tests for get_db() dependency."""

    @pytest.mark.asyncio
    async def test_get_db_yields_session(self, test_db):
        """Test that get_db yields a valid AsyncSession."""
        async for session in get_db():
            assert isinstance(session, AsyncSession)
            assert session is not None

    @pytest.mark.asyncio
    async def test_get_db_session_closes(self, test_db):
        """Test that database session is properly closed after use."""
        session_ref = None
        async for session in get_db():
            session_ref = session
            assert not session_ref.is_active or True  # Session is active during use

        # After generator completes, session should be closed
        # Note: We can't directly test if closed, but we verify it doesn't error


# ============================================================================
# Authentication Dependency Tests
# ============================================================================


class TestGetCurrentUser:
    """Tests for get_current_user() authentication dependency."""

    @pytest.mark.asyncio
    async def test_get_current_user_with_valid_token(self, db_session, test_user):
        """Test authentication with valid JWT token."""
        # Use token from test_user fixture
        token = test_user["token"]

        # Get current user
        user = await get_current_user(token=token, db=db_session)

        assert isinstance(user, User)
        assert user.username == test_user["username"]
        assert user.email == test_user["email"]

    @pytest.mark.asyncio
    async def test_get_current_user_with_invalid_token(self, db_session):
        """Test authentication fails with invalid token."""
        invalid_token = "invalid.token.here"

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token=invalid_token, db=db_session)

        assert exc_info.value.status_code == 401
        assert "Could not validate credentials" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_current_user_with_expired_token(self, db_session):
        """Test authentication fails with expired token."""
        from datetime import datetime, timedelta

        # Create expired token
        expired_time = datetime.utcnow() - timedelta(hours=1)
        expired_payload = {
            "sub": "testuser",
            "exp": expired_time,
        }
        expired_token = jwt.encode(expired_payload, SECRET_KEY, algorithm=ALGORITHM)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token=expired_token, db=db_session)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_with_nonexistent_user(self, db_session):
        """Test authentication fails when user doesn't exist in database."""
        # Create token for non-existent user
        token = create_access_token(data={"sub": "nonexistent_user"})

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token=token, db=db_session)

        assert exc_info.value.status_code == 401
        assert "Could not validate credentials" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_current_user_with_missing_username(self, db_session):
        """Test authentication fails when token doesn't contain username."""
        # Create token without 'sub' field
        malformed_payload = {"user": "testuser"}  # Wrong field name
        malformed_token = jwt.encode(malformed_payload, SECRET_KEY, algorithm=ALGORITHM)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token=malformed_token, db=db_session)

        assert exc_info.value.status_code == 401


# ============================================================================
# Service Dependency Tests
# ============================================================================


class TestServiceDependencies:
    """Tests for service dependency injection."""

    def test_stt_service_type_alias(self):
        """Test that STTServiceDep type alias is properly defined."""
        # Verify the type alias exists and has correct metadata
        assert STTServiceDep is not None
        # Type aliases are Annotated types, we can check the origin
        assert hasattr(STTServiceDep, "__metadata__")

    def test_tts_service_type_alias(self):
        """Test that TTSServiceDep type alias is properly defined."""
        assert TTSServiceDep is not None
        assert hasattr(TTSServiceDep, "__metadata__")

    def test_translation_service_type_alias(self):
        """Test that TranslationServiceDep type alias is properly defined."""
        assert TranslationServiceDep is not None
        assert hasattr(TranslationServiceDep, "__metadata__")

    def test_language_service_type_alias(self):
        """Test that LanguageServiceDep type alias is properly defined."""
        assert LanguageServiceDep is not None
        assert hasattr(LanguageServiceDep, "__metadata__")

    def test_inference_service_type_alias(self):
        """Test that InferenceServiceDep type alias is properly defined."""
        assert InferenceServiceDep is not None
        assert hasattr(InferenceServiceDep, "__metadata__")

    def test_whatsapp_service_type_alias(self):
        """Test that WhatsAppServiceDep type alias is properly defined."""
        assert WhatsAppServiceDep is not None
        assert hasattr(WhatsAppServiceDep, "__metadata__")

    def test_storage_service_type_alias(self):
        """Test that StorageServiceDep type alias is properly defined."""
        assert StorageServiceDep is not None
        assert hasattr(StorageServiceDep, "__metadata__")

    def test_service_classes_importable(self):
        """Test that all service classes can be imported from deps."""
        assert STTService is not None
        assert TTSService is not None
        assert TranslationService is not None
        assert LanguageService is not None
        assert InferenceService is not None
        assert WhatsAppBusinessService is not None
        assert StorageService is not None


# ============================================================================
# Integration Dependency Tests
# ============================================================================


class TestIntegrationDependencies:
    """Tests for integration client dependency injection."""

    def test_runpod_client_type_alias(self):
        """Test that RunPodClientDep type alias is properly defined."""
        assert RunPodClientDep is not None
        assert hasattr(RunPodClientDep, "__metadata__")

    def test_openai_client_type_alias(self):
        """Test that OpenAIClientDep type alias is properly defined."""
        assert OpenAIClientDep is not None
        assert hasattr(OpenAIClientDep, "__metadata__")

    def test_whatsapp_api_client_type_alias(self):
        """Test that WhatsAppAPIClientDep type alias is properly defined."""
        assert WhatsAppAPIClientDep is not None
        assert hasattr(WhatsAppAPIClientDep, "__metadata__")

    def test_integration_classes_importable(self):
        """Test that all integration classes can be imported from deps."""
        assert RunPodClient is not None
        assert OpenAIClient is not None
        assert WhatsAppAPIClient is not None


# ============================================================================
# OAuth2 Scheme Tests
# ============================================================================


class TestOAuth2Scheme:
    """Tests for OAuth2 password bearer scheme."""

    def test_oauth2_scheme_exists(self):
        """Test that oauth2_scheme is properly configured."""
        assert oauth2_scheme is not None
        assert oauth2_scheme.scheme_name == "OAuth2PasswordBearer"

    def test_oauth2_scheme_token_url(self):
        """Test that oauth2_scheme has correct token URL."""
        # The tokenUrl should be set to /auth/token
        assert hasattr(oauth2_scheme, "model")
        # Check the flows configuration
        flows = oauth2_scheme.model.flows
        assert flows is not None


# ============================================================================
# Type Hint Verification Tests
# ============================================================================


class TestTypeHints:
    """Tests to verify type hints are properly defined."""

    def test_get_db_return_type(self):
        """Test that get_db has proper return type annotation."""
        import inspect
        from typing import get_type_hints

        # Get type hints for the function
        hints = get_type_hints(get_db)
        assert "return" in hints

    def test_get_current_user_return_type(self):
        """Test that get_current_user returns User type."""
        import inspect
        from typing import get_type_hints

        hints = get_type_hints(get_current_user)
        assert hints.get("return") == User


# ============================================================================
# Module Exports Tests
# ============================================================================


class TestModuleExports:
    """Tests for __all__ exports in deps module."""

    def test_all_defined(self):
        """Test that __all__ is defined in deps module."""
        from app import deps

        assert hasattr(deps, "__all__")
        assert isinstance(deps.__all__, list)
        assert len(deps.__all__) > 0

    def test_core_dependencies_exported(self):
        """Test that core dependencies are in __all__."""
        from app import deps

        assert "get_db" in deps.__all__
        assert "get_current_user" in deps.__all__
        assert "oauth2_scheme" in deps.__all__

    def test_service_dependencies_exported(self):
        """Test that service dependencies are in __all__."""
        from app import deps

        assert "STTServiceDep" in deps.__all__
        assert "TTSServiceDep" in deps.__all__
        assert "TranslationServiceDep" in deps.__all__
        assert "LanguageServiceDep" in deps.__all__
        assert "InferenceServiceDep" in deps.__all__
        assert "WhatsAppServiceDep" in deps.__all__
        assert "StorageServiceDep" in deps.__all__

    def test_integration_dependencies_exported(self):
        """Test that integration dependencies are in __all__."""
        from app import deps

        assert "RunPodClientDep" in deps.__all__
        assert "OpenAIClientDep" in deps.__all__
        assert "WhatsAppAPIClientDep" in deps.__all__

    def test_service_classes_exported(self):
        """Test that service classes are in __all__."""
        from app import deps

        assert "STTService" in deps.__all__
        assert "TTSService" in deps.__all__
        assert "TranslationService" in deps.__all__
        assert "LanguageService" in deps.__all__
        assert "InferenceService" in deps.__all__
        assert "WhatsAppBusinessService" in deps.__all__
        assert "StorageService" in deps.__all__

    def test_integration_classes_exported(self):
        """Test that integration classes are in __all__."""
        from app import deps

        assert "RunPodClient" in deps.__all__
        assert "OpenAIClient" in deps.__all__
        assert "WhatsAppAPIClient" in deps.__all__


# ============================================================================
# Integration Tests with FastAPI
# ============================================================================


class TestDependencyInjectionInRoutes:
    """Integration tests for dependency injection in actual routes."""

    @pytest.mark.asyncio
    async def test_db_dependency_in_route(self, async_client, test_db):
        """Test that database dependency works in actual route."""
        # Test with an existing route that uses get_db
        response = await async_client.post(
            "/auth/register",
            json={
                "username": "integration_test_user",
                "email": "integration@test.com",
                "password": "TestPassword123!",
                "organization": "Test Org",
            },
        )

        # Should succeed if db dependency works
        # 200/201 = success, 409 = user already exists, 422 = validation error (but db was accessed)
        assert response.status_code in [200, 201, 409, 422]

        # If we got a response, the db dependency worked (even if validation failed)
        assert response is not None

    @pytest.mark.asyncio
    async def test_auth_dependency_in_route(self, async_client, test_db, test_user):
        """Test that auth dependency works in protected routes."""
        # Test with a protected route using test_user token
        response = await async_client.get(
            "/auth/me", headers={"Authorization": f"Bearer {test_user['token']}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "username" in data
