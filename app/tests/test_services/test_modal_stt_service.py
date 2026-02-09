"""
Tests for Modal STT Service Module.

This module contains unit tests for the ModalSTTService class defined in
app/services/modal_stt_service.py. Tests cover transcription, health checks,
response parsing, and error handling scenarios.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.core.exceptions import ExternalServiceError
from app.services.modal_stt_service import (
    ModalSTTService,
    get_modal_stt_service,
    reset_modal_stt_service,
)


class TestModalSTTServiceInitialization:
    """Tests for ModalSTTService initialization."""

    def test_default_initialization(self) -> None:
        """Test that service initializes with default settings."""
        with patch("app.services.modal_stt_service.settings") as mock_settings:
            mock_settings.modal_stt_api_url = "https://stt.example.com/api"
            mock_settings.request_timeout_seconds = 30

            service = ModalSTTService()

            assert service.api_url == "https://stt.example.com/api"
            assert service.timeout == 30
            assert service.service_name == "ModalSTTService"

    def test_custom_initialization(self) -> None:
        """Test that service accepts custom configuration."""
        service = ModalSTTService(
            api_url="https://custom-stt.example.com/transcribe",
            timeout=60,
        )

        assert service.api_url == "https://custom-stt.example.com/transcribe"
        assert service.timeout == 60

    def test_inherits_from_base_service(self) -> None:
        """Test that ModalSTTService inherits from BaseService."""
        from app.services.base import BaseService

        service = ModalSTTService(api_url="https://test.com", timeout=10)

        assert isinstance(service, BaseService)
        assert hasattr(service, "log_info")
        assert hasattr(service, "log_error")
        assert hasattr(service, "external_service_error")


class TestModalSTTServiceTranscribe:
    """Tests for transcribe method."""

    @pytest.mark.asyncio
    async def test_successful_transcription(self) -> None:
        """Test successful audio transcription returns text."""
        service = ModalSTTService(api_url="https://test.com/stt", timeout=10)
        mock_audio = b"fake audio data"
        mock_response_json = {"text": [{"text": "Hello world this is a test."}]}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_json

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await service.transcribe(mock_audio)

            assert result == "Hello world this is a test."
            mock_client.post.assert_called_once_with(
                "https://test.com/stt",
                content=mock_audio,
                headers={"Content-Type": "application/octet-stream"},
            )

    @pytest.mark.asyncio
    async def test_transcription_with_multiple_segments(self) -> None:
        """Test transcription with multiple text segments."""
        service = ModalSTTService(api_url="https://test.com/stt", timeout=10)
        mock_response_json = {
            "text": [
                {"text": " First segment."},
                {"text": " Second segment."},
                {"text": " Third segment."},
            ]
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_json

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await service.transcribe(b"audio")

            assert result == "First segment. Second segment. Third segment."

    @pytest.mark.asyncio
    async def test_transcription_api_error(self) -> None:
        """Test that API errors raise ExternalServiceError."""
        service = ModalSTTService(api_url="https://test.com/stt", timeout=10)

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            with pytest.raises(ExternalServiceError) as exc_info:
                await service.transcribe(b"audio")

            assert exc_info.value.service_name == "Modal STT API"
            assert "Internal Server Error" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_transcription_timeout(self) -> None:
        """Test that timeout raises ExternalServiceError."""
        service = ModalSTTService(api_url="https://test.com/stt", timeout=10)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(
                side_effect=httpx.TimeoutException("Connection timed out")
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            with pytest.raises(ExternalServiceError) as exc_info:
                await service.transcribe(b"audio")

            assert exc_info.value.service_name == "Modal STT API"
            assert "timeout" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_transcription_connection_error(self) -> None:
        """Test that connection errors raise ExternalServiceError."""
        service = ModalSTTService(api_url="https://test.com/stt", timeout=10)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            with pytest.raises(ExternalServiceError) as exc_info:
                await service.transcribe(b"audio")

            assert exc_info.value.service_name == "Modal STT API"
            assert "connect" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_transcription_malformed_response(self) -> None:
        """Test that malformed response raises ExternalServiceError."""
        service = ModalSTTService(api_url="https://test.com/stt", timeout=10)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"unexpected": "format"}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            with pytest.raises(ExternalServiceError) as exc_info:
                await service.transcribe(b"audio")

            assert "response format" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_transcription_empty_segments(self) -> None:
        """Test transcription with empty segments list."""
        service = ModalSTTService(api_url="https://test.com/stt", timeout=10)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": []}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await service.transcribe(b"audio")

            assert result == ""


class TestModalSTTServiceHealthCheck:
    """Tests for health_check method."""

    @pytest.mark.asyncio
    async def test_health_check_success(self) -> None:
        """Test health check returns True for healthy service."""
        service = ModalSTTService(api_url="https://test.com/stt", timeout=10)

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.head = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await service.health_check()

            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_server_error(self) -> None:
        """Test health check returns False for 5xx errors."""
        service = ModalSTTService(api_url="https://test.com/stt", timeout=10)

        mock_response = MagicMock()
        mock_response.status_code = 503

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.head = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await service.health_check()

            assert result is False

    @pytest.mark.asyncio
    async def test_health_check_connection_error(self) -> None:
        """Test health check returns False on connection error."""
        service = ModalSTTService(api_url="https://test.com/stt", timeout=10)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.head = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await service.health_check()

            assert result is False


class TestModalSTTServiceSingleton:
    """Tests for singleton pattern and dependency injection."""

    def test_get_modal_stt_service_creates_singleton(self) -> None:
        """Test that get_modal_stt_service returns the same instance."""
        reset_modal_stt_service()

        with patch("app.services.modal_stt_service.settings") as mock_settings:
            mock_settings.modal_stt_api_url = "https://test.com"
            mock_settings.request_timeout_seconds = 30

            service1 = get_modal_stt_service()
            service2 = get_modal_stt_service()

            assert service1 is service2

    def test_reset_modal_stt_service_clears_singleton(self) -> None:
        """Test that reset_modal_stt_service clears the singleton."""
        reset_modal_stt_service()

        with patch("app.services.modal_stt_service.settings") as mock_settings:
            mock_settings.modal_stt_api_url = "https://test.com"
            mock_settings.request_timeout_seconds = 30

            service1 = get_modal_stt_service()
            reset_modal_stt_service()
            service2 = get_modal_stt_service()

            assert service1 is not service2


class TestModalSTTServiceLogging:
    """Tests for logging functionality."""

    @pytest.mark.asyncio
    async def test_transcribe_logs_info(self) -> None:
        """Test that transcribe logs info messages."""
        service = ModalSTTService(api_url="https://test.com/stt", timeout=10)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": [{"text": "hello"}]}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            with patch.object(service, "log_info") as mock_log:
                await service.transcribe(b"audio")

                # Should log at least twice (start and success)
                assert mock_log.call_count >= 2

    @pytest.mark.asyncio
    async def test_transcribe_logs_error_on_failure(self) -> None:
        """Test that transcribe logs errors on API failure."""
        service = ModalSTTService(api_url="https://test.com/stt", timeout=10)

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Server Error"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            with patch.object(service, "log_error") as mock_log:
                with pytest.raises(ExternalServiceError):
                    await service.transcribe(b"audio")

                mock_log.assert_called()
