"""
Tests for Modal STT Service Module.

This module contains unit tests for the ModalSTTService class defined in
app/services/modal_stt_service.py. Tests cover transcription, health checks,
response parsing, and error handling scenarios.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.core.exceptions import ExternalServiceError, ValidationError
from app.services.modal_stt_service import (
    LANGUAGE_NAME_TO_CODE,
    VALID_LANGUAGE_CODES,
    ModalSTTService,
    get_modal_stt_service,
    reset_modal_stt_service,
    resolve_language,
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
        mock_response_json = [{"text": "Hello world this is a test."}]

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
                params={},
            )

    @pytest.mark.asyncio
    async def test_transcription_with_multiple_segments(self) -> None:
        """Test transcription with multiple text segments."""
        service = ModalSTTService(api_url="https://test.com/stt", timeout=10)
        mock_response_json = [
            {"text": " First segment."},
            {"text": " Second segment."},
            {"text": " Third segment."},
        ]

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
        mock_response.json.return_value = []

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
        mock_response.json.return_value = [{"text": "hello"}]

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


class TestResolveLanguage:
    """Tests for the resolve_language helper function."""

    def test_resolve_valid_code(self) -> None:
        """Test resolving a valid 3-letter language code."""
        assert resolve_language("eng") == "eng"
        assert resolve_language("lug") == "lug"
        assert resolve_language("nyn") == "nyn"

    def test_resolve_valid_name(self) -> None:
        """Test resolving a full language name."""
        assert resolve_language("english") == "eng"
        assert resolve_language("luganda") == "lug"
        assert resolve_language("swahili") == "swa"

    def test_resolve_case_insensitive(self) -> None:
        """Test that resolution is case-insensitive."""
        assert resolve_language("English") == "eng"
        assert resolve_language("LUGANDA") == "lug"
        assert resolve_language("Acholi") == "ach"
        assert resolve_language("ENG") == "eng"

    def test_resolve_with_whitespace(self) -> None:
        """Test that leading/trailing whitespace is stripped."""
        assert resolve_language("  eng  ") == "eng"
        assert resolve_language(" luganda ") == "lug"

    def test_resolve_invalid_raises_value_error(self) -> None:
        """Test that an invalid language raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported language"):
            resolve_language("xyz")

    def test_resolve_empty_raises_value_error(self) -> None:
        """Test that an empty string raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported language"):
            resolve_language("")

    def test_all_codes_are_valid(self) -> None:
        """Test that every code in VALID_LANGUAGE_CODES resolves to itself."""
        for code in VALID_LANGUAGE_CODES:
            assert resolve_language(code) == code

    def test_all_names_resolve(self) -> None:
        """Test that every name in LANGUAGE_NAME_TO_CODE resolves correctly."""
        for name, code in LANGUAGE_NAME_TO_CODE.items():
            assert resolve_language(name) == code


class TestTranscribeWithLanguage:
    """Tests for transcribe method with language parameter."""

    @pytest.mark.asyncio
    async def test_transcribe_with_language_code(self) -> None:
        """Test that language code is passed as query param."""
        service = ModalSTTService(api_url="https://test.com/stt", timeout=10)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"text": "Hello"}]

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await service.transcribe(b"audio", language="eng")

            assert result == "Hello"
            mock_client.post.assert_called_once_with(
                "https://test.com/stt",
                content=b"audio",
                headers={"Content-Type": "application/octet-stream"},
                params={"language": "eng"},
            )

    @pytest.mark.asyncio
    async def test_transcribe_with_language_name(self) -> None:
        """Test that language name is resolved and passed as query param."""
        service = ModalSTTService(api_url="https://test.com/stt", timeout=10)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"text": "Oli otya"}]

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await service.transcribe(b"audio", language="Luganda")

            assert result == "Oli otya"
            mock_client.post.assert_called_once_with(
                "https://test.com/stt",
                content=b"audio",
                headers={"Content-Type": "application/octet-stream"},
                params={"language": "lug"},
            )

    @pytest.mark.asyncio
    async def test_transcribe_without_language(self) -> None:
        """Test that no language param is sent when not provided."""
        service = ModalSTTService(api_url="https://test.com/stt", timeout=10)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"text": "Auto detected"}]

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await service.transcribe(b"audio")

            assert result == "Auto detected"
            mock_client.post.assert_called_once_with(
                "https://test.com/stt",
                content=b"audio",
                headers={"Content-Type": "application/octet-stream"},
                params={},
            )

    @pytest.mark.asyncio
    async def test_transcribe_with_invalid_language_raises_validation_error(
        self,
    ) -> None:
        """Test that invalid language raises ValidationError."""
        service = ModalSTTService(api_url="https://test.com/stt", timeout=10)

        with pytest.raises(ValidationError) as exc_info:
            await service.transcribe(b"audio", language="klingon")

        assert exc_info.value.status_code == 422
        assert "Unsupported language" in exc_info.value.message
