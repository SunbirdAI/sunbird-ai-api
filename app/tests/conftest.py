"""
Pytest Configuration and Shared Fixtures.

This module contains shared pytest fixtures for testing the Sunbird AI API.
It provides database setup, client fixtures, user authentication fixtures,
and mock service fixtures that can be reused across all test modules.

Usage:
    Fixtures defined here are automatically available to all tests in the
    app/tests directory without needing explicit imports.

Example:
    async def test_example(async_client, test_db, test_user):
        response = await async_client.get("/some-endpoint")
        assert response.status_code == 200
"""

import os
import sys
from datetime import timedelta
from typing import AsyncGenerator, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure the app module is in the path
current_directory = os.path.dirname(os.path.realpath(__file__))
app_base_directory = os.path.abspath(os.path.join(current_directory, "../../"))
if app_base_directory not in sys.path:
    sys.path.insert(0, app_base_directory)

from app.api import app
from app.database.db import Base
from app.deps import get_db
from app.schemas.users import AccountType, User
from app.utils.auth_utils import create_access_token, get_password_hash

# ---------------------------------------------------------------------------
# Database Configuration
# ---------------------------------------------------------------------------

# Use in-memory SQLite for faster tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Create test engine with StaticPool for in-memory database persistence
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    echo=False,
)

# Create test session factory
TestingSessionLocal = sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


# ---------------------------------------------------------------------------
# Database Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="function")
async def test_db() -> AsyncGenerator[None, None]:
    """Create and tear down test database tables.

    This fixture creates all database tables before each test and drops
    them after the test completes. Uses in-memory SQLite for speed.

    Yields:
        None: Tables are available during test execution.

    Example:
        async def test_something(test_db):
            # Tables exist here
            pass
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def db_session(test_db) -> AsyncGenerator[AsyncSession, None]:
    """Provide a database session for direct database operations in tests.

    This fixture depends on test_db to ensure tables exist. Use this when
    you need to perform direct database operations in tests.

    Args:
        test_db: The test database fixture (automatically injected).

    Yields:
        AsyncSession: An async database session.

    Example:
        async def test_create_user(db_session):
            user = User(username="test", email="test@example.com")
            db_session.add(user)
            await db_session.commit()
    """
    async with TestingSessionLocal() as session:
        yield session


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    """Override the get_db dependency for testing.

    This function is used to override the production database dependency
    with the test database session.

    Yields:
        AsyncSession: A test database session.
    """
    async with TestingSessionLocal() as session:
        yield session


# Apply the database override to the app
app.dependency_overrides[get_db] = override_get_db


# ---------------------------------------------------------------------------
# HTTP Client Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="function")
async def async_client(test_db) -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP client for making API requests.

    This fixture creates an AsyncClient configured to make requests to
    the test application. It depends on test_db to ensure the database
    is set up before making requests.

    Args:
        test_db: The test database fixture (automatically injected).

    Yields:
        AsyncClient: An async HTTP client for API testing.

    Example:
        async def test_get_endpoint(async_client):
            response = await async_client.get("/some-endpoint")
            assert response.status_code == 200
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture(scope="function")
async def authenticated_client(
    async_client: AsyncClient, test_user: Dict
) -> AsyncGenerator[AsyncClient, None]:
    """Provide an authenticated HTTP client with valid auth headers.

    This fixture wraps the async_client and adds authentication headers
    using a valid JWT token for the test user.

    Args:
        async_client: The base async HTTP client.
        test_user: The test user fixture containing user data and token.

    Yields:
        AsyncClient: An authenticated async HTTP client.

    Example:
        async def test_protected_endpoint(authenticated_client):
            response = await authenticated_client.get("/protected")
            assert response.status_code == 200
    """
    async_client.headers["Authorization"] = f"Bearer {test_user['token']}"
    yield async_client


# ---------------------------------------------------------------------------
# User Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="function")
async def test_user(db_session: AsyncSession) -> Dict:
    """Create a test user and return user data with authentication token.

    This fixture creates a standard test user in the database and returns
    a dictionary containing the user data and a valid JWT token.

    Args:
        db_session: The database session fixture.

    Returns:
        Dict containing:
            - id: User ID
            - username: Username
            - email: Email address
            - organization: Organization name
            - account_type: Account type (Free)
            - password: Plain text password (for testing)
            - token: Valid JWT access token

    Example:
        async def test_user_login(test_user):
            assert test_user["username"] == "test_user"
            assert "token" in test_user
    """
    from app.models.users import User as UserModel

    user_data = {
        "username": "test_user",
        "email": "test_user@example.com",
        "password": "test_password123",
        "organization": "Test Organization",
        "account_type": AccountType.free.value,
    }

    # Create user in database
    db_user = UserModel(
        username=user_data["username"],
        email=user_data["email"],
        hashed_password=get_password_hash(user_data["password"]),
        organization=user_data["organization"],
        account_type=user_data["account_type"],
    )
    db_session.add(db_user)
    await db_session.commit()
    await db_session.refresh(db_user)

    # Generate access token
    access_token = create_access_token(
        data={"sub": user_data["username"]},
        expires_delta=timedelta(hours=1),
    )

    return {
        "id": db_user.id,
        "username": user_data["username"],
        "email": user_data["email"],
        "organization": user_data["organization"],
        "account_type": user_data["account_type"],
        "password": user_data["password"],
        "token": access_token,
    }


@pytest_asyncio.fixture(scope="function")
async def admin_user(db_session: AsyncSession) -> Dict:
    """Create an admin test user and return user data with authentication token.

    This fixture creates an admin user in the database and returns
    a dictionary containing the user data and a valid JWT token.

    Args:
        db_session: The database session fixture.

    Returns:
        Dict containing user data and token for an admin user.

    Example:
        async def test_admin_endpoint(admin_user, async_client):
            headers = {"Authorization": f"Bearer {admin_user['token']}"}
            response = await async_client.get("/admin/users", headers=headers)
    """
    from app.models.users import User as UserModel

    user_data = {
        "username": "admin_user",
        "email": "admin@example.com",
        "password": "admin_password123",
        "organization": "Admin Organization",
        "account_type": AccountType.admin.value,
    }

    # Create admin user in database
    db_user = UserModel(
        username=user_data["username"],
        email=user_data["email"],
        hashed_password=get_password_hash(user_data["password"]),
        organization=user_data["organization"],
        account_type=user_data["account_type"],
    )
    db_session.add(db_user)
    await db_session.commit()
    await db_session.refresh(db_user)

    # Generate access token
    access_token = create_access_token(
        data={"sub": user_data["username"]},
        expires_delta=timedelta(hours=1),
    )

    return {
        "id": db_user.id,
        "username": user_data["username"],
        "email": user_data["email"],
        "organization": user_data["organization"],
        "account_type": user_data["account_type"],
        "password": user_data["password"],
        "token": access_token,
    }


@pytest_asyncio.fixture(scope="function")
async def premium_user(db_session: AsyncSession) -> Dict:
    """Create a premium test user and return user data with authentication token.

    Args:
        db_session: The database session fixture.

    Returns:
        Dict containing user data and token for a premium user.
    """
    from app.models.users import User as UserModel

    user_data = {
        "username": "premium_user",
        "email": "premium@example.com",
        "password": "premium_password123",
        "organization": "Premium Organization",
        "account_type": AccountType.premium.value,
    }

    # Create premium user in database
    db_user = UserModel(
        username=user_data["username"],
        email=user_data["email"],
        hashed_password=get_password_hash(user_data["password"]),
        organization=user_data["organization"],
        account_type=user_data["account_type"],
    )
    db_session.add(db_user)
    await db_session.commit()
    await db_session.refresh(db_user)

    # Generate access token
    access_token = create_access_token(
        data={"sub": user_data["username"]},
        expires_delta=timedelta(hours=1),
    )

    return {
        "id": db_user.id,
        "username": user_data["username"],
        "email": user_data["email"],
        "organization": user_data["organization"],
        "account_type": user_data["account_type"],
        "password": user_data["password"],
        "token": access_token,
    }


# ---------------------------------------------------------------------------
# Mock Service Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_storage_service() -> MagicMock:
    """Provide a mock GCP storage service for testing.

    This fixture creates a mock storage service that can be used to
    test endpoints that interact with GCP storage without making
    actual API calls.

    Returns:
        MagicMock: A mock storage service with common methods configured.

    Example:
        def test_upload(mock_storage_service, monkeypatch):
            monkeypatch.setattr("app.deps.get_storage_service", lambda: mock_storage_service)
            mock_storage_service.upload_file.return_value = "https://storage.example.com/file"
    """
    mock = MagicMock()
    mock.upload_file = AsyncMock(
        return_value="https://storage.example.com/uploaded-file"
    )
    mock.generate_signed_url = AsyncMock(
        return_value="https://storage.example.com/signed-url"
    )
    mock.delete_file = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def mock_tts_service() -> MagicMock:
    """Provide a mock TTS service for testing.

    This fixture creates a mock TTS service that can be used to
    test endpoints that interact with text-to-speech functionality.

    Returns:
        MagicMock: A mock TTS service with common methods configured.
    """
    mock = MagicMock()
    mock.generate_speech = AsyncMock(return_value=b"audio_bytes")
    mock.get_speakers = AsyncMock(
        return_value=[
            {"id": "241", "name": "Speaker 1"},
            {"id": "242", "name": "Speaker 2"},
        ]
    )
    return mock


@pytest.fixture
def mock_runpod_client() -> MagicMock:
    """Provide a mock RunPod client for testing.

    This fixture creates a mock RunPod client that can be used to
    test endpoints that interact with RunPod inference services.

    Returns:
        MagicMock: A mock RunPod client with common methods configured.
    """
    mock = MagicMock()
    mock.run_sync = MagicMock(
        return_value={
            "output": {"text": "transcribed text"},
            "status": "COMPLETED",
        }
    )
    mock.run_async = AsyncMock(
        return_value={
            "output": {"text": "transcribed text"},
            "status": "COMPLETED",
        }
    )
    return mock


# ---------------------------------------------------------------------------
# Utility Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_audio_file() -> bytes:
    """Provide sample audio file bytes for testing.

    Returns:
        bytes: Minimal valid audio file bytes for testing uploads.
    """
    # Minimal WAV file header (44 bytes) + some audio data
    # This is a valid but silent WAV file
    wav_header = bytes(
        [
            0x52,
            0x49,
            0x46,
            0x46,  # "RIFF"
            0x24,
            0x00,
            0x00,
            0x00,  # File size - 8
            0x57,
            0x41,
            0x56,
            0x45,  # "WAVE"
            0x66,
            0x6D,
            0x74,
            0x20,  # "fmt "
            0x10,
            0x00,
            0x00,
            0x00,  # Subchunk1 size (16 for PCM)
            0x01,
            0x00,  # Audio format (1 = PCM)
            0x01,
            0x00,  # Number of channels (1)
            0x44,
            0xAC,
            0x00,
            0x00,  # Sample rate (44100)
            0x88,
            0x58,
            0x01,
            0x00,  # Byte rate
            0x02,
            0x00,  # Block align
            0x10,
            0x00,  # Bits per sample (16)
            0x64,
            0x61,
            0x74,
            0x61,  # "data"
            0x00,
            0x00,
            0x00,
            0x00,  # Data size
        ]
    )
    return wav_header


@pytest.fixture
def auth_headers(test_user: Dict) -> Dict[str, str]:
    """Provide authentication headers for a test user.

    Args:
        test_user: The test user fixture.

    Returns:
        Dict[str, str]: Headers dictionary with Authorization header.
    """
    return {"Authorization": f"Bearer {test_user['token']}"}


# ---------------------------------------------------------------------------
# Pytest Configuration
# ---------------------------------------------------------------------------


def pytest_configure(config):
    """Configure pytest with custom markers.

    This function registers custom markers that can be used to categorize
    and selectively run tests.
    """
    config.addinivalue_line("markers", "slow: marks tests as slow running")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "unit: marks tests as unit tests")


# Configure pytest-asyncio mode
pytest_plugins = ["pytest_asyncio"]
