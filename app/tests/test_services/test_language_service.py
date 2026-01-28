"""
Tests for Language Service Module.

This module contains unit tests for the LanguageService class defined in
app/services/language_service.py. Tests cover language identification,
classification, audio language detection, and error handling.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.base import BaseService
from app.services.language_service import (
    AudioLanguageResult,
    LanguageClassificationResult,
    LanguageConnectionError,
    LanguageDetectionError,
    LanguageError,
    LanguageIdentificationResult,
    LanguageService,
    LanguageTimeoutError,
    get_language_service,
    reset_language_service,
)


class TestLanguageServiceInitialization:
    """Tests for LanguageService initialization."""

    def setup_method(self) -> None:
        """Reset singleton before each test."""
        reset_language_service()

    def test_default_initialization(self) -> None:
        """Test that service initializes with environment settings."""
        with patch.dict(
            os.environ,
            {
                "RUNPOD_ENDPOINT_ID": "test-endpoint-id",
                "RUNPOD_API_KEY": "test-api-key",
            },
        ):
            service = LanguageService()

            assert service.runpod_endpoint_id == "test-endpoint-id"
            assert service.service_name == "LanguageService"
            assert service.classification_threshold == 0.9

    def test_custom_initialization(self) -> None:
        """Test that service accepts custom configuration."""
        service = LanguageService(
            runpod_endpoint_id="custom-endpoint",
            classification_threshold=0.8,
        )

        assert service.runpod_endpoint_id == "custom-endpoint"
        assert service.classification_threshold == 0.8

    def test_inherits_from_base_service(self) -> None:
        """Test that LanguageService inherits from BaseService."""
        service = LanguageService(
            runpod_endpoint_id="test",
        )

        assert isinstance(service, BaseService)
        assert hasattr(service, "log_info")
        assert hasattr(service, "log_error")
        assert hasattr(service, "log_warning")

    def test_logs_warning_when_endpoint_missing(self) -> None:
        """Test that warning is logged when RUNPOD_ENDPOINT_ID is missing."""
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(LanguageService, "log_warning") as mock_log_warning:
                LanguageService()

                mock_log_warning.assert_called_with("RUNPOD_ENDPOINT_ID not configured")


class TestLanguageIdentificationResultDataclass:
    """Tests for LanguageIdentificationResult dataclass."""

    def test_required_fields(self) -> None:
        """Test LanguageIdentificationResult with required fields only."""
        result = LanguageIdentificationResult(
            language="lug",
        )

        assert result.language == "lug"
        assert result.raw_response is None

    def test_all_fields(self) -> None:
        """Test LanguageIdentificationResult with all fields."""
        result = LanguageIdentificationResult(
            language="lug",
            raw_response={"language": "lug"},
        )

        assert result.language == "lug"
        assert result.raw_response == {"language": "lug"}


class TestLanguageClassificationResultDataclass:
    """Tests for LanguageClassificationResult dataclass."""

    def test_required_fields(self) -> None:
        """Test LanguageClassificationResult with required fields only."""
        result = LanguageClassificationResult(
            language="lug",
        )

        assert result.language == "lug"
        assert result.probability is None
        assert result.predictions is None
        assert result.raw_response is None

    def test_all_fields(self) -> None:
        """Test LanguageClassificationResult with all fields."""
        result = LanguageClassificationResult(
            language="lug",
            probability=0.95,
            predictions={"lug": 0.95, "eng": 0.03, "ach": 0.02},
            raw_response={"predictions": {"lug": 0.95}},
        )

        assert result.language == "lug"
        assert result.probability == 0.95
        assert result.predictions == {"lug": 0.95, "eng": 0.03, "ach": 0.02}
        assert result.raw_response == {"predictions": {"lug": 0.95}}


class TestAudioLanguageResultDataclass:
    """Tests for AudioLanguageResult dataclass."""

    def test_required_fields(self) -> None:
        """Test AudioLanguageResult with required fields only."""
        result = AudioLanguageResult(
            detected_language="lug",
        )

        assert result.detected_language == "lug"
        assert result.blob_name is None
        assert result.raw_response is None

    def test_all_fields(self) -> None:
        """Test AudioLanguageResult with all fields."""
        result = AudioLanguageResult(
            detected_language="lug",
            blob_name="audio/test.wav",
            raw_response={"detected_language": "lug"},
        )

        assert result.detected_language == "lug"
        assert result.blob_name == "audio/test.wav"
        assert result.raw_response == {"detected_language": "lug"}


class TestLanguageIdentificationAPI:
    """Tests for language identification API calls."""

    def setup_method(self) -> None:
        """Create service instance for tests."""
        self.service = LanguageService(
            runpod_endpoint_id="test-endpoint",
        )

    @pytest.mark.asyncio
    async def test_successful_language_identification(self) -> None:
        """Test successful language identification API call."""
        mock_endpoint = MagicMock()
        mock_endpoint.run_sync = MagicMock(return_value={"language": "lug"})

        with patch(
            "app.services.language_service.runpod.Endpoint", return_value=mock_endpoint
        ):
            result = await self.service.identify_language(text="Oli otya?")

            assert result.language == "lug"
            assert result.raw_response == {"language": "lug"}
            mock_endpoint.run_sync.assert_called_once()

    @pytest.mark.asyncio
    async def test_language_identification_timeout_raises_error(self) -> None:
        """Test that timeout raises LanguageTimeoutError."""
        mock_endpoint = MagicMock()
        mock_endpoint.run_sync = MagicMock(
            side_effect=TimeoutError("Request timed out")
        )

        with patch(
            "app.services.language_service.runpod.Endpoint", return_value=mock_endpoint
        ):
            with pytest.raises(LanguageTimeoutError) as exc_info:
                await self.service.identify_language(text="Hello")

            assert "timed out" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_language_identification_generic_error_raises_language_error(
        self,
    ) -> None:
        """Test that generic error raises LanguageError."""
        mock_endpoint = MagicMock()
        mock_endpoint.run_sync = MagicMock(side_effect=Exception("Unknown error"))

        with patch(
            "app.services.language_service.runpod.Endpoint", return_value=mock_endpoint
        ):
            with pytest.raises(LanguageError) as exc_info:
                await self.service.identify_language(text="Hello")

            assert "unexpected error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_language_identification_returns_unknown_for_none_response(
        self,
    ) -> None:
        """Test that None response returns 'unknown' language."""
        mock_endpoint = MagicMock()
        mock_endpoint.run_sync = MagicMock(return_value=None)

        with patch(
            "app.services.language_service.runpod.Endpoint", return_value=mock_endpoint
        ):
            result = await self.service.identify_language(text="Test")

            assert result.language == "unknown"


class TestLanguageClassificationAPI:
    """Tests for language classification API calls."""

    def setup_method(self) -> None:
        """Create service instance for tests."""
        self.service = LanguageService(
            runpod_endpoint_id="test-endpoint",
            classification_threshold=0.9,
        )

    @pytest.mark.asyncio
    async def test_successful_language_classification(self) -> None:
        """Test successful language classification API call."""
        mock_endpoint = MagicMock()
        mock_endpoint.run_sync = MagicMock(
            return_value={"predictions": {"lug": 0.95, "eng": 0.03, "ach": 0.02}}
        )

        with patch(
            "app.services.language_service.runpod.Endpoint", return_value=mock_endpoint
        ):
            result = await self.service.classify_language(text="Oli otya?")

            assert result.language == "lug"
            assert result.probability == 0.95
            assert result.predictions == {"lug": 0.95, "eng": 0.03, "ach": 0.02}

    @pytest.mark.asyncio
    async def test_language_classification_below_threshold(self) -> None:
        """Test classification returns 'language not detected' when below threshold."""
        mock_endpoint = MagicMock()
        mock_endpoint.run_sync = MagicMock(
            return_value={"predictions": {"lug": 0.5, "eng": 0.3, "ach": 0.2}}
        )

        with patch(
            "app.services.language_service.runpod.Endpoint", return_value=mock_endpoint
        ):
            result = await self.service.classify_language(text="Test text")

            assert result.language == "language not detected"
            assert result.probability is None

    @pytest.mark.asyncio
    async def test_language_classification_normalizes_text_to_lowercase(self) -> None:
        """Test that text is normalized to lowercase before classification."""
        mock_endpoint = MagicMock()
        mock_endpoint.run_sync = MagicMock(return_value={"predictions": {"eng": 0.95}})

        with patch(
            "app.services.language_service.runpod.Endpoint", return_value=mock_endpoint
        ):
            await self.service.classify_language(text="HELLO WORLD")

            call_args = mock_endpoint.run_sync.call_args[0][0]
            assert call_args["input"]["text"] == "hello world"

    @pytest.mark.asyncio
    async def test_language_classification_timeout_raises_error(self) -> None:
        """Test that timeout raises LanguageTimeoutError."""
        mock_endpoint = MagicMock()
        mock_endpoint.run_sync = MagicMock(
            side_effect=TimeoutError("Request timed out")
        )

        with patch(
            "app.services.language_service.runpod.Endpoint", return_value=mock_endpoint
        ):
            with pytest.raises(LanguageTimeoutError) as exc_info:
                await self.service.classify_language(text="Hello")

            assert "timed out" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_language_classification_invalid_response_raises_error(self) -> None:
        """Test that invalid response raises LanguageDetectionError."""
        mock_endpoint = MagicMock()
        mock_endpoint.run_sync = MagicMock(return_value={"invalid": "response"})

        with patch(
            "app.services.language_service.runpod.Endpoint", return_value=mock_endpoint
        ):
            with pytest.raises(LanguageDetectionError) as exc_info:
                await self.service.classify_language(text="Hello")

            assert "Unexpected response format" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_language_classification_generic_error_raises_language_error(
        self,
    ) -> None:
        """Test that generic error raises LanguageError."""
        mock_endpoint = MagicMock()
        mock_endpoint.run_sync = MagicMock(side_effect=Exception("Unknown error"))

        with patch(
            "app.services.language_service.runpod.Endpoint", return_value=mock_endpoint
        ):
            with pytest.raises(LanguageError) as exc_info:
                await self.service.classify_language(text="Hello")

            assert "unexpected error" in str(exc_info.value)


class TestAudioLanguageDetectionAPI:
    """Tests for audio language detection API calls."""

    def setup_method(self) -> None:
        """Create service instance for tests."""
        self.service = LanguageService(
            runpod_endpoint_id="test-endpoint",
        )

    @pytest.mark.asyncio
    async def test_successful_audio_language_detection(self) -> None:
        """Test successful audio language detection API call."""
        mock_endpoint = MagicMock()
        mock_endpoint.run_sync = MagicMock(return_value={"detected_language": "lug"})

        with patch(
            "app.services.language_service.runpod.Endpoint", return_value=mock_endpoint
        ):
            with patch(
                "app.services.language_service.upload_audio_file",
                return_value=(
                    "audio/test.wav",
                    "https://storage.example.com/audio/test.wav",
                ),
            ):
                result = await self.service.detect_audio_language(
                    file_path="/tmp/test.wav"
                )

                assert result.detected_language == "lug"
                assert result.blob_name == "audio/test.wav"
                assert result.raw_response == {"detected_language": "lug"}

    @pytest.mark.asyncio
    async def test_audio_language_detection_upload_failure_raises_error(self) -> None:
        """Test that upload failure raises LanguageError."""
        with patch(
            "app.services.language_service.upload_audio_file",
            return_value=(None, None),
        ):
            with pytest.raises(LanguageError) as exc_info:
                await self.service.detect_audio_language(file_path="/tmp/test.wav")

            assert "Failed to upload" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_audio_language_detection_timeout_raises_error(self) -> None:
        """Test that timeout raises LanguageTimeoutError."""
        mock_endpoint = MagicMock()
        mock_endpoint.run_sync = MagicMock(
            side_effect=TimeoutError("Request timed out")
        )

        with patch(
            "app.services.language_service.runpod.Endpoint", return_value=mock_endpoint
        ):
            with patch(
                "app.services.language_service.upload_audio_file",
                return_value=(
                    "audio/test.wav",
                    "https://storage.example.com/audio/test.wav",
                ),
            ):
                with pytest.raises(LanguageTimeoutError) as exc_info:
                    await self.service.detect_audio_language(file_path="/tmp/test.wav")

                assert "timed out" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_audio_language_detection_connection_error_raises_error(self) -> None:
        """Test that connection error raises LanguageConnectionError."""
        mock_endpoint = MagicMock()
        mock_endpoint.run_sync = MagicMock(
            side_effect=ConnectionError("Connection refused")
        )

        with patch(
            "app.services.language_service.runpod.Endpoint", return_value=mock_endpoint
        ):
            with patch(
                "app.services.language_service.upload_audio_file",
                return_value=(
                    "audio/test.wav",
                    "https://storage.example.com/audio/test.wav",
                ),
            ):
                with pytest.raises(LanguageConnectionError) as exc_info:
                    await self.service.detect_audio_language(file_path="/tmp/test.wav")

                assert "Connection error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_audio_language_detection_generic_error_raises_language_error(
        self,
    ) -> None:
        """Test that generic error raises LanguageError."""
        mock_endpoint = MagicMock()
        mock_endpoint.run_sync = MagicMock(side_effect=Exception("Unknown error"))

        with patch(
            "app.services.language_service.runpod.Endpoint", return_value=mock_endpoint
        ):
            with patch(
                "app.services.language_service.upload_audio_file",
                return_value=(
                    "audio/test.wav",
                    "https://storage.example.com/audio/test.wav",
                ),
            ):
                with pytest.raises(LanguageError) as exc_info:
                    await self.service.detect_audio_language(file_path="/tmp/test.wav")

                assert "unexpected error" in str(exc_info.value)


class TestLanguageServiceSingleton:
    """Tests for singleton pattern and dependency injection."""

    def setup_method(self) -> None:
        """Reset singleton before each test."""
        reset_language_service()

    def test_get_language_service_creates_singleton(self) -> None:
        """Test that get_language_service returns the same instance."""
        with patch.dict(
            os.environ,
            {
                "RUNPOD_ENDPOINT_ID": "test",
                "RUNPOD_API_KEY": "test",
            },
        ):
            service1 = get_language_service()
            service2 = get_language_service()

            assert service1 is service2

    def test_reset_language_service_clears_singleton(self) -> None:
        """Test that reset_language_service clears the singleton."""
        with patch.dict(
            os.environ,
            {
                "RUNPOD_ENDPOINT_ID": "test",
                "RUNPOD_API_KEY": "test",
            },
        ):
            service1 = get_language_service()
            reset_language_service()
            service2 = get_language_service()

            assert service1 is not service2


class TestLanguageServiceLogging:
    """Tests for logging functionality."""

    def setup_method(self) -> None:
        """Create service instance for tests."""
        self.service = LanguageService(
            runpod_endpoint_id="test-endpoint",
        )

    @pytest.mark.asyncio
    async def test_language_identification_logs_info(self) -> None:
        """Test that language identification logs info messages."""
        mock_endpoint = MagicMock()
        mock_endpoint.run_sync = MagicMock(return_value={"language": "lug"})

        with patch(
            "app.services.language_service.runpod.Endpoint", return_value=mock_endpoint
        ):
            with patch.object(self.service, "log_info") as mock_log:
                await self.service.identify_language(text="Hello")

                # Should log at least once
                assert mock_log.call_count >= 1

    @pytest.mark.asyncio
    async def test_language_identification_logs_error_on_failure(self) -> None:
        """Test that language identification logs errors on API failure."""
        mock_endpoint = MagicMock()
        mock_endpoint.run_sync = MagicMock(side_effect=Exception("API Error"))

        with patch(
            "app.services.language_service.runpod.Endpoint", return_value=mock_endpoint
        ):
            with patch.object(self.service, "log_error") as mock_log:
                with pytest.raises(LanguageError):
                    await self.service.identify_language(text="Hello")

                mock_log.assert_called()


class TestExceptionClasses:
    """Tests for custom exception classes."""

    def test_language_error(self) -> None:
        """Test LanguageError exception."""
        error = LanguageError("Language operation failed")
        assert str(error) == "Language operation failed"

    def test_language_timeout_error(self) -> None:
        """Test LanguageTimeoutError exception."""
        error = LanguageTimeoutError("Request timed out")
        assert str(error) == "Request timed out"
        assert isinstance(error, LanguageError)

    def test_language_connection_error(self) -> None:
        """Test LanguageConnectionError exception."""
        error = LanguageConnectionError("Connection failed")
        assert str(error) == "Connection failed"
        assert isinstance(error, LanguageError)

    def test_language_detection_error(self) -> None:
        """Test LanguageDetectionError exception."""
        error = LanguageDetectionError("Detection failed")
        assert str(error) == "Detection failed"
        assert isinstance(error, LanguageError)
