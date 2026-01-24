"""
Tests for STT Router Module.

This module contains integration tests for the STT router endpoints
defined in app/routers/stt.py. Tests use the shared fixtures from conftest.py
for database, authentication, and HTTP client setup.
"""

import io
from typing import Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.api import app
from app.routers.stt import get_service
from app.services.stt_service import (
    AudioProcessingError,
    AudioValidationError,
    STTService,
    TranscriptionError,
    TranscriptionResult,
    reset_stt_service,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_stt_service() -> MagicMock:
    """Create a mock STT service for testing.

    Returns:
        MagicMock: A mock STT service with common methods configured.
    """
    service = MagicMock(spec=STTService)
    service.validate_audio_file = MagicMock()
    service.transcribe_uploaded_file = AsyncMock()
    service.transcribe_from_gcs = AsyncMock()
    service.transcribe_org_audio = AsyncMock()
    return service


@pytest.fixture
def sample_transcription_result() -> TranscriptionResult:
    """Create a sample transcription result for testing."""
    return TranscriptionResult(
        transcription="Hello world",
        diarization_output={},
        formatted_diarization_output="",
        audio_url="https://storage.example.com/audio.mp3",
        blob_name="audio.mp3",
        was_trimmed=False,
    )


# ---------------------------------------------------------------------------
# STT Endpoint Tests
# ---------------------------------------------------------------------------


class TestSTTEndpoint:
    """Tests for POST /tasks/stt endpoint."""

    @pytest.mark.asyncio
    async def test_successful_transcription(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_stt_service: MagicMock,
        sample_transcription_result: TranscriptionResult,
    ) -> None:
        """Test successful audio transcription."""
        mock_stt_service.transcribe_uploaded_file = AsyncMock(
            return_value=sample_transcription_result
        )

        # Override the service dependency
        app.dependency_overrides[get_service] = lambda: mock_stt_service

        try:
            audio_content = b"fake audio content"
            files = {"audio": ("test.mp3", io.BytesIO(audio_content), "audio/mpeg")}
            data = {"language": "lug", "adapter": "lug"}

            with patch(
                "app.routers.stt.create_audio_transcription", new_callable=AsyncMock
            ):
                with patch("app.routers.stt.log_endpoint", new_callable=AsyncMock):
                    response = await async_client.post(
                        "/tasks/stt",
                        files=files,
                        data=data,
                        headers={"Authorization": f"Bearer {test_user['token']}"},
                    )

            assert response.status_code == 200
            json_response = response.json()
            assert json_response["audio_transcription"] == "Hello world"
            assert json_response["audio_url"] == "https://storage.example.com/audio.mp3"

            # Verify service was called
            mock_stt_service.validate_audio_file.assert_called_once()
            mock_stt_service.transcribe_uploaded_file.assert_called_once()

        finally:
            # Clean up dependency override
            app.dependency_overrides.pop(get_service, None)

    @pytest.mark.asyncio
    async def test_invalid_file_type_returns_415(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_stt_service: MagicMock,
    ) -> None:
        """Test that invalid file type returns 415 Unsupported Media Type."""
        mock_stt_service.validate_audio_file = MagicMock(
            side_effect=AudioValidationError(
                "Unsupported file type. Supported formats: .mp3, .wav, .ogg"
            )
        )

        app.dependency_overrides[get_service] = lambda: mock_stt_service

        try:
            files = {"audio": ("test.txt", io.BytesIO(b"text content"), "text/plain")}
            data = {"language": "lug"}

            response = await async_client.post(
                "/tasks/stt",
                files=files,
                data=data,
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 415
            assert "Unsupported file type" in response.json()["detail"]

        finally:
            app.dependency_overrides.pop(get_service, None)

    @pytest.mark.asyncio
    async def test_audio_processing_error_returns_400(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_stt_service: MagicMock,
    ) -> None:
        """Test that audio processing error returns 400 Bad Request."""
        mock_stt_service.transcribe_uploaded_file = AsyncMock(
            side_effect=AudioProcessingError("Could not decode audio file")
        )

        app.dependency_overrides[get_service] = lambda: mock_stt_service

        try:
            audio_content = b"corrupted audio content"
            files = {"audio": ("test.mp3", io.BytesIO(audio_content), "audio/mpeg")}
            data = {"language": "lug"}

            response = await async_client.post(
                "/tasks/stt",
                files=files,
                data=data,
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 400
            assert "Could not decode audio file" in response.json()["detail"]

        finally:
            app.dependency_overrides.pop(get_service, None)

    @pytest.mark.asyncio
    async def test_transcription_error_returns_503(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_stt_service: MagicMock,
    ) -> None:
        """Test that transcription error returns 503 Service Unavailable."""
        mock_stt_service.transcribe_uploaded_file = AsyncMock(
            side_effect=TranscriptionError("Transcription service timed out")
        )

        app.dependency_overrides[get_service] = lambda: mock_stt_service

        try:
            audio_content = b"valid audio content"
            files = {"audio": ("test.mp3", io.BytesIO(audio_content), "audio/mpeg")}
            data = {"language": "lug"}

            response = await async_client.post(
                "/tasks/stt",
                files=files,
                data=data,
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 503
            assert "timed out" in response.json()["detail"]

        finally:
            app.dependency_overrides.pop(get_service, None)

    @pytest.mark.asyncio
    async def test_unauthenticated_request_returns_401(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test that unauthenticated request returns 401."""
        audio_content = b"fake audio content"
        files = {"audio": ("test.mp3", io.BytesIO(audio_content), "audio/mpeg")}
        data = {"language": "lug"}

        response = await async_client.post(
            "/tasks/stt",
            files=files,
            data=data,
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_transcription_with_trimmed_audio(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_stt_service: MagicMock,
    ) -> None:
        """Test transcription response when audio was trimmed."""
        trimmed_result = TranscriptionResult(
            transcription="Trimmed audio content",
            diarization_output={},
            formatted_diarization_output="",
            audio_url="https://storage.example.com/audio.mp3",
            blob_name="audio.mp3",
            was_trimmed=True,
            original_duration=15.5,
        )
        mock_stt_service.transcribe_uploaded_file = AsyncMock(
            return_value=trimmed_result
        )

        app.dependency_overrides[get_service] = lambda: mock_stt_service

        try:
            audio_content = b"long audio content"
            files = {"audio": ("test.mp3", io.BytesIO(audio_content), "audio/mpeg")}
            data = {"language": "lug"}

            with patch(
                "app.routers.stt.create_audio_transcription", new_callable=AsyncMock
            ):
                with patch("app.routers.stt.log_endpoint", new_callable=AsyncMock):
                    response = await async_client.post(
                        "/tasks/stt",
                        files=files,
                        data=data,
                        headers={"Authorization": f"Bearer {test_user['token']}"},
                    )

            assert response.status_code == 200
            json_response = response.json()
            assert json_response["was_audio_trimmed"] is True
            assert json_response["original_duration_minutes"] == 15.5

        finally:
            app.dependency_overrides.pop(get_service, None)


# ---------------------------------------------------------------------------
# STT From GCS Endpoint Tests
# ---------------------------------------------------------------------------


class TestSTTFromGCSEndpoint:
    """Tests for POST /tasks/stt_from_gcs endpoint."""

    @pytest.mark.asyncio
    async def test_successful_gcs_transcription(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_stt_service: MagicMock,
    ) -> None:
        """Test successful transcription from GCS."""
        gcs_result = TranscriptionResult(
            transcription="Hello from GCS",
            diarization_output={},
            formatted_diarization_output="",
            audio_url="gs://bucket/audio.mp3",
            blob_name="audio.mp3",
            was_trimmed=False,
        )
        mock_stt_service.transcribe_from_gcs = AsyncMock(return_value=gcs_result)

        app.dependency_overrides[get_service] = lambda: mock_stt_service

        try:
            data = {
                "gcs_blob_name": "audio.mp3",
                "language": "lug",
                "adapter": "lug",
            }

            with patch(
                "app.routers.stt.create_audio_transcription", new_callable=AsyncMock
            ):
                with patch("app.routers.stt.log_endpoint", new_callable=AsyncMock):
                    response = await async_client.post(
                        "/tasks/stt_from_gcs",
                        data=data,
                        headers={"Authorization": f"Bearer {test_user['token']}"},
                    )

            assert response.status_code == 200
            json_response = response.json()
            assert json_response["audio_transcription"] == "Hello from GCS"
            assert json_response["audio_url"] == "gs://bucket/audio.mp3"

            mock_stt_service.transcribe_from_gcs.assert_called_once()

        finally:
            app.dependency_overrides.pop(get_service, None)

    @pytest.mark.asyncio
    async def test_gcs_blob_not_found_returns_400(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_stt_service: MagicMock,
    ) -> None:
        """Test that missing GCS blob returns 400."""
        mock_stt_service.transcribe_from_gcs = AsyncMock(
            side_effect=AudioProcessingError("GCS blob missing.mp3 does not exist.")
        )

        app.dependency_overrides[get_service] = lambda: mock_stt_service

        try:
            data = {
                "gcs_blob_name": "missing.mp3",
                "language": "lug",
            }

            response = await async_client.post(
                "/tasks/stt_from_gcs",
                data=data,
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 400
            assert "does not exist" in response.json()["detail"]

        finally:
            app.dependency_overrides.pop(get_service, None)

    @pytest.mark.asyncio
    async def test_gcs_transcription_with_diarization(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_stt_service: MagicMock,
    ) -> None:
        """Test GCS transcription with speaker diarization."""
        diarized_result = TranscriptionResult(
            transcription="Hello world",
            diarization_output={"speakers": ["Speaker_1", "Speaker_2"]},
            formatted_diarization_output="Speaker_1: Hello\nSpeaker_2: World",
            audio_url="gs://bucket/audio.mp3",
            blob_name="audio.mp3",
            was_trimmed=False,
        )
        mock_stt_service.transcribe_from_gcs = AsyncMock(return_value=diarized_result)

        app.dependency_overrides[get_service] = lambda: mock_stt_service

        try:
            data = {
                "gcs_blob_name": "audio.mp3",
                "language": "lug",
                "recognise_speakers": "true",
            }

            with patch(
                "app.routers.stt.create_audio_transcription", new_callable=AsyncMock
            ):
                with patch("app.routers.stt.log_endpoint", new_callable=AsyncMock):
                    response = await async_client.post(
                        "/tasks/stt_from_gcs",
                        data=data,
                        headers={"Authorization": f"Bearer {test_user['token']}"},
                    )

            assert response.status_code == 200
            json_response = response.json()
            assert json_response["diarization_output"]["speakers"] == [
                "Speaker_1",
                "Speaker_2",
            ]
            assert "Speaker_1: Hello" in json_response["formatted_diarization_output"]

        finally:
            app.dependency_overrides.pop(get_service, None)


# ---------------------------------------------------------------------------
# Organization STT Endpoint Tests
# ---------------------------------------------------------------------------


class TestOrgSTTEndpoint:
    """Tests for POST /tasks/org/stt endpoint."""

    @pytest.mark.asyncio
    async def test_successful_org_transcription(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_stt_service: MagicMock,
    ) -> None:
        """Test successful organization transcription."""
        org_result = TranscriptionResult(
            transcription="Organization audio content",
            diarization_output={"speakers": ["A"]},
            formatted_diarization_output="A: Organization audio content",
        )
        mock_stt_service.transcribe_org_audio = AsyncMock(return_value=org_result)

        app.dependency_overrides[get_service] = lambda: mock_stt_service

        try:
            audio_content = b"fake audio content"
            files = {"audio": ("test.mp3", io.BytesIO(audio_content), "audio/mpeg")}
            data = {"recognise_speakers": "true"}

            with patch("app.routers.stt.log_endpoint", new_callable=AsyncMock):
                response = await async_client.post(
                    "/tasks/org/stt",
                    files=files,
                    data=data,
                    headers={"Authorization": f"Bearer {test_user['token']}"},
                )

            assert response.status_code == 200
            json_response = response.json()
            assert json_response["audio_transcription"] == "Organization audio content"
            assert json_response["diarization_output"]["speakers"] == ["A"]

            mock_stt_service.transcribe_org_audio.assert_called_once()

        finally:
            app.dependency_overrides.pop(get_service, None)

    @pytest.mark.asyncio
    async def test_org_transcription_without_diarization(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_stt_service: MagicMock,
    ) -> None:
        """Test organization transcription without speaker diarization."""
        org_result = TranscriptionResult(
            transcription="Simple transcription",
            diarization_output={},
            formatted_diarization_output="",
        )
        mock_stt_service.transcribe_org_audio = AsyncMock(return_value=org_result)

        app.dependency_overrides[get_service] = lambda: mock_stt_service

        try:
            audio_content = b"fake audio content"
            files = {"audio": ("test.mp3", io.BytesIO(audio_content), "audio/mpeg")}
            data = {"recognise_speakers": "false"}

            with patch("app.routers.stt.log_endpoint", new_callable=AsyncMock):
                response = await async_client.post(
                    "/tasks/org/stt",
                    files=files,
                    data=data,
                    headers={"Authorization": f"Bearer {test_user['token']}"},
                )

            assert response.status_code == 200
            json_response = response.json()
            assert json_response["audio_transcription"] == "Simple transcription"

        finally:
            app.dependency_overrides.pop(get_service, None)

    @pytest.mark.asyncio
    async def test_org_transcription_error_returns_503(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_stt_service: MagicMock,
    ) -> None:
        """Test that transcription error in org endpoint returns 503."""
        mock_stt_service.transcribe_org_audio = AsyncMock(
            side_effect=TranscriptionError("Connection error while transcribing")
        )

        app.dependency_overrides[get_service] = lambda: mock_stt_service

        try:
            audio_content = b"valid audio content"
            files = {"audio": ("test.mp3", io.BytesIO(audio_content), "audio/mpeg")}

            response = await async_client.post(
                "/tasks/org/stt",
                files=files,
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 503
            assert "Connection error" in response.json()["detail"]

        finally:
            app.dependency_overrides.pop(get_service, None)


# ---------------------------------------------------------------------------
# Rate Limiting Tests
# ---------------------------------------------------------------------------


class TestRateLimiting:
    """Tests for rate limiting functionality."""

    def test_custom_key_func_extracts_account_type(self) -> None:
        """Test that custom_key_func extracts account type from JWT."""
        from app.routers.stt import custom_key_func

        mock_request = MagicMock()
        mock_request.headers.get.return_value = None

        result = custom_key_func(mock_request)

        assert result == "anonymous"

    def test_custom_key_func_with_valid_token(self) -> None:
        """Test custom_key_func extracts account type from valid JWT."""
        from datetime import timedelta

        from app.routers.stt import custom_key_func
        from app.utils.auth_utils import create_access_token

        # Create a token with account_type
        token = create_access_token(
            data={"sub": "test_user", "account_type": "premium"},
            expires_delta=timedelta(hours=1),
        )

        mock_request = MagicMock()
        mock_request.headers.get.return_value = f"Bearer {token}"

        result = custom_key_func(mock_request)

        assert result == "premium"

    def test_custom_key_func_with_no_auth_header(self) -> None:
        """Test custom_key_func returns 'anonymous' when no auth header."""
        from app.routers.stt import custom_key_func

        mock_request = MagicMock()
        mock_request.headers.get.return_value = None

        result = custom_key_func(mock_request)

        assert result == "anonymous"

    def test_custom_key_func_with_invalid_token(self) -> None:
        """Test custom_key_func handles invalid token gracefully."""
        from app.routers.stt import custom_key_func

        mock_request = MagicMock()
        mock_request.headers.get.return_value = "Bearer invalid_token_here"

        result = custom_key_func(mock_request)

        # Should return empty string on decode failure
        assert result == ""

    def test_get_account_type_limit_admin(self) -> None:
        """Test rate limit for admin account type."""
        from app.routers.stt import get_account_type_limit

        result = get_account_type_limit("admin")

        assert result == "1000/minute"

    def test_get_account_type_limit_premium(self) -> None:
        """Test rate limit for premium account type."""
        from app.routers.stt import get_account_type_limit

        result = get_account_type_limit("premium")

        assert result == "100/minute"

    def test_get_account_type_limit_default(self) -> None:
        """Test rate limit for default/standard account type."""
        from app.routers.stt import get_account_type_limit

        result = get_account_type_limit("standard")

        assert result == "50/minute"

    def test_get_account_type_limit_empty(self) -> None:
        """Test rate limit for empty account type."""
        from app.routers.stt import get_account_type_limit

        result = get_account_type_limit("")

        assert result == "50/minute"

    def test_get_account_type_limit_case_insensitive(self) -> None:
        """Test rate limit is case insensitive."""
        from app.routers.stt import get_account_type_limit

        assert get_account_type_limit("ADMIN") == "1000/minute"
        assert get_account_type_limit("Admin") == "1000/minute"
        assert get_account_type_limit("PREMIUM") == "100/minute"
        assert get_account_type_limit("Premium") == "100/minute"


# ---------------------------------------------------------------------------
# Service Dependency Tests
# ---------------------------------------------------------------------------


class TestGetServiceDependency:
    """Tests for get_service dependency."""

    def test_get_service_returns_stt_service(self) -> None:
        """Test that get_service returns STTService instance."""
        reset_stt_service()

        with patch("app.routers.stt.get_stt_service") as mock_get:
            mock_service = MagicMock(spec=STTService)
            mock_get.return_value = mock_service

            result = get_service()

            assert result is mock_service
            mock_get.assert_called_once()

    def test_get_service_returns_singleton(self) -> None:
        """Test that get_service returns the same instance."""
        reset_stt_service()

        with patch.dict(
            "os.environ",
            {
                "RUNPOD_ENDPOINT_ID": "test",
                "AUDIO_CONTENT_BUCKET_NAME": "test",
            },
        ):
            service1 = get_service()
            service2 = get_service()

            assert service1 is service2

        reset_stt_service()
