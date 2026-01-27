"""
API Dependencies Module.

This module provides FastAPI dependency injection functions and type aliases
for all services, integrations, and common dependencies used across the API.

Dependencies are organized into three categories:
1. Core dependencies (database, authentication)
2. Service dependencies (business logic layer)
3. Integration dependencies (external API clients)

Usage:
    Services and integrations use singleton pattern for efficient resource management.
    Type aliases are provided for convenient dependency injection in routers.

    Example:
        @router.post("/endpoint")
        async def endpoint(
            stt_service: STTServiceDep,
            db: AsyncSession = Depends(get_db),
            current_user: User = Depends(get_current_user)
        ):
            result = await stt_service.transcribe(...)
            return result
"""

from typing import Annotated, AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.users import get_user_by_username
from app.database.db import async_session_maker
# Integration imports
from app.integrations.openai_client import OpenAIClient, get_openai_client
from app.integrations.runpod import RunPodClient, get_runpod_client
from app.integrations.whatsapp_api import WhatsAppAPIClient, get_whatsapp_api_client
from app.schemas.users import TokenData, User
# Service imports
from app.services.inference_service import InferenceService, get_inference_service
from app.services.language_service import LanguageService, get_language_service
from app.services.storage_service import StorageService
from app.services.storage_service import get_storage_service as get_new_storage_service
from app.services.stt_service import STTService, get_stt_service
from app.services.translation_service import TranslationService, get_translation_service
from app.services.tts_service import TTSService, get_tts_service
from app.services.whatsapp_service import WhatsAppBusinessService, get_whatsapp_service
# Legacy imports (maintained for backward compatibility)
from app.utils.auth import get_username_from_token
from app.utils.storage import GCPStorageService
from app.utils.storage import get_storage_service as get_legacy_storage_service

# ============================================================================
# Type Aliases for Dependency Injection
# ============================================================================

# Service dependencies
STTServiceDep = Annotated[STTService, Depends(get_stt_service)]
TTSServiceDep = Annotated[TTSService, Depends(get_tts_service)]
TranslationServiceDep = Annotated[TranslationService, Depends(get_translation_service)]
LanguageServiceDep = Annotated[LanguageService, Depends(get_language_service)]
InferenceServiceDep = Annotated[InferenceService, Depends(get_inference_service)]
WhatsAppServiceDep = Annotated[WhatsAppBusinessService, Depends(get_whatsapp_service)]
StorageServiceDep = Annotated[StorageService, Depends(get_new_storage_service)]

# Integration dependencies
RunPodClientDep = Annotated[RunPodClient, Depends(get_runpod_client)]
OpenAIClientDep = Annotated[OpenAIClient, Depends(get_openai_client)]
WhatsAppAPIClientDep = Annotated[WhatsAppAPIClient, Depends(get_whatsapp_api_client)]

# Legacy dependencies (maintained for backward compatibility)
LegacyStorageServiceDep = Annotated[
    GCPStorageService, Depends(get_legacy_storage_service)
]


# ============================================================================
# Core Dependencies
# ============================================================================

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Get database session dependency.

    Provides an async database session for use in route handlers.
    The session is automatically closed after the request completes.

    Yields:
        AsyncSession: SQLAlchemy async database session.

    Example:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            items = await db.execute(select(Item))
            return items.scalars().all()
    """
    async with async_session_maker() as db_session:
        yield db_session


async def get_current_user(
    token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)
) -> User:
    """
    Get authenticated user from JWT token.

    Validates the JWT token from the Authorization header and returns
    the corresponding user from the database.

    Args:
        token: JWT token from OAuth2 bearer authentication.
        db: Database session dependency.

    Returns:
        User: Authenticated user schema.

    Raises:
        HTTPException: 401 Unauthorized if:
            - Token is invalid or expired
            - Username not found in token
            - User does not exist in database

    Example:
        @router.get("/me")
        async def get_me(current_user: User = Depends(get_current_user)):
            return {"username": current_user.username}
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        username = get_username_from_token(token)
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception

    user = await get_user_by_username(db, token_data.username)
    if user is None:
        raise credentials_exception
    return User.model_validate(user)


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    # Core dependencies
    "get_db",
    "get_current_user",
    "oauth2_scheme",
    # Service dependencies
    "STTServiceDep",
    "TTSServiceDep",
    "TranslationServiceDep",
    "LanguageServiceDep",
    "InferenceServiceDep",
    "WhatsAppServiceDep",
    "StorageServiceDep",
    # Integration dependencies
    "RunPodClientDep",
    "OpenAIClientDep",
    "WhatsAppAPIClientDep",
    # Legacy dependencies
    "LegacyStorageServiceDep",
    # Service classes (for type hints)
    "STTService",
    "TTSService",
    "TranslationService",
    "LanguageService",
    "InferenceService",
    "WhatsAppBusinessService",
    "StorageService",
    # Integration classes (for type hints)
    "RunPodClient",
    "OpenAIClient",
    "WhatsAppAPIClient",
    "GCPStorageService",
    # Other types
    "User",
    "AsyncSession",
]
