"""
Tests for Modal STT Router Endpoint.

This module contains integration tests for the Modal STT endpoint
(POST /tasks/modal/stt) defined in app/routers/stt.py. Tests use
the shared fixtures from conftest.py for database, authentication,
and HTTP client setup.
"""

import io
from typing import Dict
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.api import app
from app.core.exceptions import ExternalServiceError, ServiceUnavailableError
from app.services.modal_stt_service import ModalSTTService, get_modal_stt_service

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_modal_stt_service() -> MagicMock:
    """Create a mock Modal STT service for testing.

    Returns:
        MagicMock: A mock service with transcribe method configured.
    """
    service = MagicMock(spec=ModalSTTService)
    service.transcribe = AsyncMock()
    service.health_check = AsyncMock(return_value=True)
    return service


# ---------------------------------------------------------------------------
# Modal STT Endpoint Tests
# ---------------------------------------------------------------------------


class TestModalSTTEndpoint:
    """Tests for POST /tasks/modal/stt endpoint."""

    @pytest.mark.asyncio
    async def test_successful_transcription(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_modal_stt_service: MagicMock,
    ) -> None:
        """Test successful audio transcription via Modal."""
        mock_modal_stt_service.transcribe = AsyncMock(
            return_value="Hello world this is a test."
        )

        app.dependency_overrides[get_modal_stt_service] = lambda: mock_modal_stt_service

        try:
            audio_content = b"fake audio content"
            files = {"audio": ("test.wav", io.BytesIO(audio_content), "audio/wav")}

            response = await async_client.post(
                "/tasks/modal/stt",
                files=files,
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 200
            json_response = response.json()
            assert json_response["audio_transcription"] == "Hello world this is a test."

            mock_modal_stt_service.transcribe.assert_called_once_with(audio_content)

        finally:
            app.dependency_overrides.pop(get_modal_stt_service, None)

    @pytest.mark.asyncio
    async def test_transcription_returns_empty_optional_fields(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_modal_stt_service: MagicMock,
    ) -> None:
        """Test that response has None for unused fields."""
        mock_modal_stt_service.transcribe = AsyncMock(return_value="Transcribed text")

        app.dependency_overrides[get_modal_stt_service] = lambda: mock_modal_stt_service

        try:
            files = {"audio": ("test.mp3", io.BytesIO(b"audio"), "audio/mpeg")}

            response = await async_client.post(
                "/tasks/modal/stt",
                files=files,
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 200
            json_response = response.json()
            assert json_response["audio_transcription"] == "Transcribed text"
            assert json_response["diarization_output"] == {}
            assert json_response["formatted_diarization_output"] is None
            assert json_response["audio_url"] is None
            assert json_response["was_audio_trimmed"] is False

        finally:
            app.dependency_overrides.pop(get_modal_stt_service, None)

    @pytest.mark.asyncio
    async def test_unauthenticated_request_returns_401(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test that unauthenticated request returns 401."""
        files = {"audio": ("test.wav", io.BytesIO(b"audio"), "audio/wav")}

        response = await async_client.post(
            "/tasks/modal/stt",
            files=files,
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_external_service_error_returns_502(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_modal_stt_service: MagicMock,
    ) -> None:
        """Test that ExternalServiceError returns 502."""
        mock_modal_stt_service.transcribe = AsyncMock(
            side_effect=ExternalServiceError(
                service_name="Modal STT API",
                message="STT API error: Internal Server Error",
            )
        )

        app.dependency_overrides[get_modal_stt_service] = lambda: mock_modal_stt_service

        try:
            files = {"audio": ("test.wav", io.BytesIO(b"audio"), "audio/wav")}

            response = await async_client.post(
                "/tasks/modal/stt",
                files=files,
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 502
            assert "STT API error" in response.json()["message"]

        finally:
            app.dependency_overrides.pop(get_modal_stt_service, None)

    @pytest.mark.asyncio
    async def test_service_unavailable_error_returns_503(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_modal_stt_service: MagicMock,
    ) -> None:
        """Test that ServiceUnavailableError returns 503."""
        mock_modal_stt_service.transcribe = AsyncMock(
            side_effect=ServiceUnavailableError(message="STT service timeout")
        )

        app.dependency_overrides[get_modal_stt_service] = lambda: mock_modal_stt_service

        try:
            files = {"audio": ("test.wav", io.BytesIO(b"audio"), "audio/wav")}

            response = await async_client.post(
                "/tasks/modal/stt",
                files=files,
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 503
            assert "timeout" in response.json()["message"].lower()

        finally:
            app.dependency_overrides.pop(get_modal_stt_service, None)

    @pytest.mark.asyncio
    async def test_unexpected_error_returns_502(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_modal_stt_service: MagicMock,
    ) -> None:
        """Test that unexpected errors are wrapped in ExternalServiceError (502)."""
        mock_modal_stt_service.transcribe = AsyncMock(
            side_effect=RuntimeError("Something went wrong")
        )

        app.dependency_overrides[get_modal_stt_service] = lambda: mock_modal_stt_service

        try:
            files = {"audio": ("test.wav", io.BytesIO(b"audio"), "audio/wav")}

            response = await async_client.post(
                "/tasks/modal/stt",
                files=files,
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 502
            json_response = response.json()
            assert "unexpected error" in json_response["message"].lower()

        finally:
            app.dependency_overrides.pop(get_modal_stt_service, None)

    @pytest.mark.asyncio
    async def test_missing_audio_file_returns_422(
        self,
        async_client: AsyncClient,
        test_user: Dict,
    ) -> None:
        """Test that missing audio file returns 422 validation error."""
        response = await async_client.post(
            "/tasks/modal/stt",
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        assert response.status_code == 422
