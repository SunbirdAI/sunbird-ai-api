"""
Tests for TTS Service Module.

This module contains unit tests for the TTSService class defined in
app/services/tts_service.py. Tests cover audio generation, streaming,
health checks, and error handling scenarios.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.core.exceptions import ExternalServiceError
from app.models.enums import SpeakerID
from app.services.tts_service import (
    TTSService,
    get_tts_service,
    reset_tts_service,
)


class TestTTSServiceInitialization:
    """Tests for TTSService initialization."""

    def test_default_initialization(self) -> None:
        """Test that service initializes with default settings."""
        with patch("app.services.tts_service.settings") as mock_settings:
            mock_settings.tts_api_url = "https://tts.example.com/api"
            mock_settings.request_timeout_seconds = 30

            service = TTSService()

            assert service.api_url == "https://tts.example.com/api"
            assert service.timeout == 30
            assert service.service_name == "TTSService"

    def test_custom_initialization(self) -> None:
        """Test that service accepts custom configuration."""
        service = TTSService(
            api_url="https://custom-tts.example.com/synthesize",
            timeout=60,
        )

        assert service.api_url == "https://custom-tts.example.com/synthesize"
        assert service.timeout == 60

    def test_inherits_from_base_service(self) -> None:
        """Test that TTSService inherits from BaseService."""
        from app.services.base import BaseService

        service = TTSService(api_url="https://test.com", timeout=10)

        assert isinstance(service, BaseService)
        assert hasattr(service, "log_info")
        assert hasattr(service, "log_error")
        assert hasattr(service, "external_service_error")


class TestTTSServiceSpeakerId:
    """Tests for speaker ID handling."""

    def test_get_speaker_id_from_enum(self) -> None:
        """Test extracting speaker ID from SpeakerID enum."""
        service = TTSService(api_url="https://test.com", timeout=10)

        result = service._get_speaker_id_value(SpeakerID.LUGANDA_FEMALE)

        assert isinstance(result, int)
        assert result == SpeakerID.LUGANDA_FEMALE.value

    def test_get_speaker_id_from_int(self) -> None:
        """Test that integer speaker IDs pass through unchanged."""
        service = TTSService(api_url="https://test.com", timeout=10)

        result = service._get_speaker_id_value(42)

        assert result == 42


class TestTTSServiceGenerateAudio:
    """Tests for generate_audio method."""

    @pytest.mark.asyncio
    async def test_successful_audio_generation(self) -> None:
        """Test successful audio generation returns bytes."""
        service = TTSService(api_url="https://test.com/tts", timeout=10)
        mock_audio_data = b"fake audio data"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = mock_audio_data

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await service.generate_audio(
                text="Hello world",
                speaker_id=1,
            )

            assert result == mock_audio_data
            mock_client.post.assert_called_once_with(
                "https://test.com/tts",
                params={"text": "Hello world", "speaker_id": "1"},
            )

    @pytest.mark.asyncio
    async def test_audio_generation_with_enum_speaker_id(self) -> None:
        """Test audio generation works with SpeakerID enum."""
        service = TTSService(api_url="https://test.com/tts", timeout=10)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"audio"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await service.generate_audio(
                text="Test",
                speaker_id=SpeakerID.LUGANDA_FEMALE,
            )

            assert result == b"audio"
            # Verify the enum value was used
            call_args = mock_client.post.call_args
            assert call_args.kwargs["params"]["speaker_id"] == str(
                SpeakerID.LUGANDA_FEMALE.value
            )

    @pytest.mark.asyncio
    async def test_audio_generation_api_error(self) -> None:
        """Test that API errors raise ExternalServiceError."""
        service = TTSService(api_url="https://test.com/tts", timeout=10)

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
                await service.generate_audio(text="Test", speaker_id=1)

            assert exc_info.value.service_name == "TTS API"
            assert "Internal Server Error" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_audio_generation_timeout(self) -> None:
        """Test that timeout raises ExternalServiceError."""
        service = TTSService(api_url="https://test.com/tts", timeout=10)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(
                side_effect=httpx.TimeoutException("Connection timed out")
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            with pytest.raises(ExternalServiceError) as exc_info:
                await service.generate_audio(text="Test", speaker_id=1)

            assert exc_info.value.service_name == "TTS API"
            assert "timeout" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_audio_generation_connection_error(self) -> None:
        """Test that connection errors raise ExternalServiceError."""
        service = TTSService(api_url="https://test.com/tts", timeout=10)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            with pytest.raises(ExternalServiceError) as exc_info:
                await service.generate_audio(text="Test", speaker_id=1)

            assert exc_info.value.service_name == "TTS API"
            assert "connect" in exc_info.value.message.lower()


class TestTTSServiceGenerateAudioStream:
    """Tests for generate_audio_stream method."""

    @pytest.mark.asyncio
    async def test_successful_audio_streaming(self) -> None:
        """Test successful audio streaming yields chunks."""
        service = TTSService(api_url="https://test.com/tts", timeout=10)
        chunks = [b"chunk1", b"chunk2", b"chunk3"]

        mock_response = AsyncMock()
        mock_response.status_code = 200

        async def mock_aiter_bytes(chunk_size=8192):
            for chunk in chunks:
                yield chunk

        mock_response.aiter_bytes = mock_aiter_bytes

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_stream_context = AsyncMock()
            mock_stream_context.__aenter__ = AsyncMock(return_value=mock_response)
            mock_stream_context.__aexit__ = AsyncMock(return_value=None)
            mock_client.stream = MagicMock(return_value=mock_stream_context)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            received_chunks = []
            async for chunk in service.generate_audio_stream(
                text="Test", speaker_id=1
            ):
                received_chunks.append(chunk)

            assert received_chunks == chunks

    @pytest.mark.asyncio
    async def test_streaming_api_error(self) -> None:
        """Test that streaming API errors raise ExternalServiceError."""
        service = TTSService(api_url="https://test.com/tts", timeout=10)

        mock_response = AsyncMock()
        mock_response.status_code = 500
        mock_response.aread = AsyncMock(return_value=b"Server Error")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_stream_context = AsyncMock()
            mock_stream_context.__aenter__ = AsyncMock(return_value=mock_response)
            mock_stream_context.__aexit__ = AsyncMock(return_value=None)
            mock_client.stream = MagicMock(return_value=mock_stream_context)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            with pytest.raises(ExternalServiceError) as exc_info:
                async for _ in service.generate_audio_stream(text="Test", speaker_id=1):
                    pass

            assert exc_info.value.service_name == "TTS API"


class TestTTSServiceHealthCheck:
    """Tests for health_check method."""

    @pytest.mark.asyncio
    async def test_health_check_success(self) -> None:
        """Test health check returns True for healthy service."""
        service = TTSService(api_url="https://test.com/tts", timeout=10)

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
        service = TTSService(api_url="https://test.com/tts", timeout=10)

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
    async def test_health_check_returns_true_for_4xx(self) -> None:
        """Test health check returns True for 4xx errors (service is up)."""
        service = TTSService(api_url="https://test.com/tts", timeout=10)

        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.head = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await service.health_check()

            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_exception(self) -> None:
        """Test health check returns False on connection error."""
        service = TTSService(api_url="https://test.com/tts", timeout=10)

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


class TestTTSServiceEstimateDuration:
    """Tests for estimate_duration static method."""

    def test_estimate_duration_default_rate(self) -> None:
        """Test duration estimation with default WPM."""
        # "Hello world" = 2 words, 150 WPM default
        # (2 / 150) * 60 = 0.8 seconds
        result = TTSService.estimate_duration("Hello world")

        assert result == pytest.approx(0.8, rel=0.01)

    def test_estimate_duration_custom_rate(self) -> None:
        """Test duration estimation with custom WPM."""
        # 10 words at 100 WPM = (10/100) * 60 = 6 seconds
        text = "one two three four five six seven eight nine ten"
        result = TTSService.estimate_duration(text, words_per_minute=100)

        assert result == pytest.approx(6.0, rel=0.01)

    def test_estimate_duration_empty_text(self) -> None:
        """Test duration estimation with empty text."""
        result = TTSService.estimate_duration("")

        assert result == 0.0

    def test_estimate_duration_single_word(self) -> None:
        """Test duration estimation with single word."""
        # 1 word at 150 WPM = (1/150) * 60 = 0.4 seconds
        result = TTSService.estimate_duration("Hello")

        assert result == pytest.approx(0.4, rel=0.01)


class TestTTSServiceSingleton:
    """Tests for singleton pattern and dependency injection."""

    def test_get_tts_service_creates_singleton(self) -> None:
        """Test that get_tts_service returns the same instance."""
        reset_tts_service()

        with patch("app.services.tts_service.settings") as mock_settings:
            mock_settings.tts_api_url = "https://test.com"
            mock_settings.request_timeout_seconds = 30

            service1 = get_tts_service()
            service2 = get_tts_service()

            assert service1 is service2

    def test_reset_tts_service_clears_singleton(self) -> None:
        """Test that reset_tts_service clears the singleton."""
        reset_tts_service()

        with patch("app.services.tts_service.settings") as mock_settings:
            mock_settings.tts_api_url = "https://test.com"
            mock_settings.request_timeout_seconds = 30

            service1 = get_tts_service()
            reset_tts_service()
            service2 = get_tts_service()

            assert service1 is not service2


class TestTTSServiceLogging:
    """Tests for logging functionality."""

    @pytest.mark.asyncio
    async def test_generate_audio_logs_info(self) -> None:
        """Test that generate_audio logs info messages."""
        service = TTSService(api_url="https://test.com/tts", timeout=10)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"audio"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            with patch.object(service, "log_info") as mock_log:
                await service.generate_audio(text="Test", speaker_id=1)

                # Should log at least twice (start and success)
                assert mock_log.call_count >= 2

    @pytest.mark.asyncio
    async def test_generate_audio_logs_error_on_failure(self) -> None:
        """Test that generate_audio logs errors on API failure."""
        service = TTSService(api_url="https://test.com/tts", timeout=10)

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
                    await service.generate_audio(text="Test", speaker_id=1)

                mock_log.assert_called()
