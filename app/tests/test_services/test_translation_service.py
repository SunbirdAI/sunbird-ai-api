"""
Tests for Translation Service Module.

This module contains unit tests for the TranslationService class defined in
app/services/translation_service.py. Tests cover translation API calls,
response validation, and error handling.
"""

import os
from unittest.mock import AsyncMock, patch

import pytest

from app.services.base import BaseService
from app.services.translation_service import (
    TranslationConnectionError,
    TranslationError,
    TranslationResult,
    TranslationService,
    TranslationTimeoutError,
    TranslationValidationError,
    get_translation_service,
    reset_translation_service,
)


class TestTranslationServiceInitialization:
    """Tests for TranslationService initialization."""

    def setup_method(self) -> None:
        """Reset singleton before each test."""
        reset_translation_service()

    def test_default_initialization(self) -> None:
        """Test that service initializes with environment settings."""
        with patch.dict(
            os.environ,
            {
                "RUNPOD_ENDPOINT_ID": "test-endpoint-id",
                "RUNPOD_API_KEY": "test-api-key",
            },
        ):
            service = TranslationService()

            assert service.runpod_endpoint_id == "test-endpoint-id"
            assert service.service_name == "TranslationService"

    def test_custom_initialization(self) -> None:
        """Test that service accepts custom configuration."""
        service = TranslationService(
            runpod_endpoint_id="custom-endpoint",
        )

        assert service.runpod_endpoint_id == "custom-endpoint"

    def test_inherits_from_base_service(self) -> None:
        """Test that TranslationService inherits from BaseService."""
        service = TranslationService(
            runpod_endpoint_id="test",
        )

        assert isinstance(service, BaseService)
        assert hasattr(service, "log_info")
        assert hasattr(service, "log_error")
        assert hasattr(service, "log_warning")

    def test_logs_warning_when_endpoint_missing(self) -> None:
        """Test that warning is logged when RUNPOD_ENDPOINT_ID is missing."""
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(TranslationService, "log_warning") as mock_log_warning:
                TranslationService()

                mock_log_warning.assert_called_with("RUNPOD_ENDPOINT_ID not configured")


class TestTranslationResultDataclass:
    """Tests for TranslationResult dataclass."""

    def test_required_fields(self) -> None:
        """Test TranslationResult with required fields only."""
        result = TranslationResult(
            translated_text="Oli otya?",
            source_language="eng",
            target_language="lug",
        )

        assert result.translated_text == "Oli otya?"
        assert result.source_language == "eng"
        assert result.target_language == "lug"
        assert result.delay_time is None
        assert result.execution_time is None
        assert result.job_id is None
        assert result.worker_id is None
        assert result.status is None
        assert result.raw_response is None

    def test_all_fields(self) -> None:
        """Test TranslationResult with all fields."""
        result = TranslationResult(
            translated_text="Oli otya?",
            source_language="eng",
            target_language="lug",
            delay_time=100,
            execution_time=500,
            job_id="job-123",
            worker_id="worker-456",
            status="COMPLETED",
            raw_response={"output": {"translated_text": "Oli otya?"}},
        )

        assert result.translated_text == "Oli otya?"
        assert result.source_language == "eng"
        assert result.target_language == "lug"
        assert result.delay_time == 100
        assert result.execution_time == 500
        assert result.job_id == "job-123"
        assert result.worker_id == "worker-456"
        assert result.status == "COMPLETED"
        assert result.raw_response == {"output": {"translated_text": "Oli otya?"}}


class TestLanguageValidation:
    """Tests for language validation."""

    def setup_method(self) -> None:
        """Create service instance for tests."""
        self.service = TranslationService(
            runpod_endpoint_id="test",
        )

    def test_validate_valid_languages(self) -> None:
        """Test validation passes for valid language codes."""
        # Should not raise
        self.service.validate_languages("eng", "lug")
        self.service.validate_languages("lug", "eng")
        self.service.validate_languages("ach", "eng")
        self.service.validate_languages("teo", "lug")
        self.service.validate_languages("lgg", "nyn")

    def test_validate_invalid_source_language(self) -> None:
        """Test validation fails for invalid source language."""
        with pytest.raises(TranslationValidationError) as exc_info:
            self.service.validate_languages("xxx", "eng")

        assert "Invalid source language" in str(exc_info.value)
        assert "xxx" in str(exc_info.value)

    def test_validate_invalid_target_language(self) -> None:
        """Test validation fails for invalid target language."""
        with pytest.raises(TranslationValidationError) as exc_info:
            self.service.validate_languages("eng", "yyy")

        assert "Invalid target language" in str(exc_info.value)
        assert "yyy" in str(exc_info.value)

    def test_validate_same_source_and_target(self) -> None:
        """Test validation fails when source equals target."""
        with pytest.raises(TranslationValidationError) as exc_info:
            self.service.validate_languages("eng", "eng")

        assert "must be different" in str(exc_info.value)


class TestTranslationAPI:
    """Tests for translation API calls."""

    def setup_method(self) -> None:
        """Create service instance for tests."""
        self.service = TranslationService(
            runpod_endpoint_id="test-endpoint",
        )

    @pytest.mark.asyncio
    async def test_successful_translation(self) -> None:
        """Test successful translation API call."""
        mock_raw_response = {
            "translated_text": "Oli otya?",
        }
        mock_job_details = {
            "id": "job-123",
            "status": "COMPLETED",
            "output": {"translated_text": "Oli otya?"},
            "delayTime": 100,
            "executionTime": 500,
            "workerId": "worker-456",
        }

        with patch(
            "app.services.translation_service.run_job_and_get_output",
            new_callable=AsyncMock,
            return_value=(mock_raw_response, mock_job_details),
        ):
            result = await self.service.translate(
                text="How are you?",
                source_language="eng",
                target_language="lug",
            )

            assert result.translated_text == "Oli otya?"
            assert result.source_language == "eng"
            assert result.target_language == "lug"
            assert result.status == "COMPLETED"
            assert result.job_id == "job-123"

    @pytest.mark.asyncio
    async def test_translation_with_text_field(self) -> None:
        """Test translation response with 'text' field instead of 'translated_text'."""
        mock_raw_response = {
            "text": "Oli otya?",
        }
        mock_job_details = {
            "id": "job-123",
            "status": "COMPLETED",
            "output": {"text": "Oli otya?"},
        }

        with patch(
            "app.services.translation_service.run_job_and_get_output",
            new_callable=AsyncMock,
            return_value=(mock_raw_response, mock_job_details),
        ):
            result = await self.service.translate(
                text="How are you?",
                source_language="eng",
                target_language="lug",
            )

            assert result.translated_text == "Oli otya?"

    @pytest.mark.asyncio
    async def test_translation_timeout_raises_error(self) -> None:
        """Test that timeout raises TranslationTimeoutError."""
        with patch(
            "app.services.translation_service.run_job_and_get_output",
            new_callable=AsyncMock,
            side_effect=TimeoutError("Request timed out"),
        ):
            with pytest.raises(TranslationTimeoutError) as exc_info:
                await self.service.translate(
                    text="Hello",
                    source_language="eng",
                    target_language="lug",
                )

            assert "timed out" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_translation_connection_error_raises_error(self) -> None:
        """Test that connection error raises TranslationConnectionError."""
        with patch(
            "app.services.translation_service.run_job_and_get_output",
            new_callable=AsyncMock,
            side_effect=ConnectionError("Connection refused"),
        ):
            with pytest.raises(TranslationConnectionError) as exc_info:
                await self.service.translate(
                    text="Hello",
                    source_language="eng",
                    target_language="lug",
                )

            assert "Connection error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_translation_generic_error_raises_translation_error(self) -> None:
        """Test that generic error raises TranslationError."""
        with patch(
            "app.services.translation_service.run_job_and_get_output",
            new_callable=AsyncMock,
            side_effect=Exception("Unknown error"),
        ):
            with pytest.raises(TranslationError) as exc_info:
                await self.service.translate(
                    text="Hello",
                    source_language="eng",
                    target_language="lug",
                )

            assert "unexpected error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_translation_strips_whitespace(self) -> None:
        """Test that text whitespace is stripped before sending."""
        mock_job_details = {
            "id": "job-123",
            "status": "COMPLETED",
            "output": {"translated_text": "Oli otya?"},
        }

        with patch(
            "app.services.translation_service.run_job_and_get_output",
            new_callable=AsyncMock,
            return_value=({}, mock_job_details),
        ) as mock_run:
            await self.service.translate(
                text="  How are you?  ",
                source_language="eng",
                target_language="lug",
            )

            # Verify text was stripped in payload
            call_args = mock_run.call_args[0][0]
            assert call_args["text"] == "How are you?"


class TestResponseValidation:
    """Tests for response validation."""

    def setup_method(self) -> None:
        """Create service instance for tests."""
        self.service = TranslationService(
            runpod_endpoint_id="test",
        )

    def test_validate_valid_response(self) -> None:
        """Test validation passes for valid response."""
        response = {
            "id": "job-123",
            "status": "COMPLETED",
            "output": {"translated_text": "Oli otya?"},
        }

        result = self.service.validate_and_parse_response(response)

        assert result.id == "job-123"
        assert result.status == "COMPLETED"

    def test_validate_response_with_extra_fields(self) -> None:
        """Test validation allows extra fields."""
        response = {
            "id": "job-123",
            "status": "COMPLETED",
            "output": {"translated_text": "Oli otya?"},
            "extra_field": "should be allowed",
        }

        # Should not raise due to extra="allow" in model config
        result = self.service.validate_and_parse_response(response)
        assert result.id == "job-123"

    def test_validate_invalid_response_raises_error(self) -> None:
        """Test validation fails for completely invalid response."""
        # Pass a response that would fail Pydantic validation
        # Since the model is very permissive (all Optional), we'd need
        # to pass something that can't be validated at all
        with patch(
            "app.services.translation_service.WorkerTranslationResponse.model_validate",
            side_effect=ValueError("Validation failed"),
        ):
            with pytest.raises(TranslationValidationError) as exc_info:
                self.service.validate_and_parse_response({"bad": "data"})

            assert "Invalid response" in str(exc_info.value)


class TestTranslationServiceSingleton:
    """Tests for singleton pattern and dependency injection."""

    def setup_method(self) -> None:
        """Reset singleton before each test."""
        reset_translation_service()

    def test_get_translation_service_creates_singleton(self) -> None:
        """Test that get_translation_service returns the same instance."""
        with patch.dict(
            os.environ,
            {
                "RUNPOD_ENDPOINT_ID": "test",
                "RUNPOD_API_KEY": "test",
            },
        ):
            service1 = get_translation_service()
            service2 = get_translation_service()

            assert service1 is service2

    def test_reset_translation_service_clears_singleton(self) -> None:
        """Test that reset_translation_service clears the singleton."""
        with patch.dict(
            os.environ,
            {
                "RUNPOD_ENDPOINT_ID": "test",
                "RUNPOD_API_KEY": "test",
            },
        ):
            service1 = get_translation_service()
            reset_translation_service()
            service2 = get_translation_service()

            assert service1 is not service2


class TestTranslationServiceLogging:
    """Tests for logging functionality."""

    def setup_method(self) -> None:
        """Create service instance for tests."""
        self.service = TranslationService(
            runpod_endpoint_id="test-endpoint",
        )

    @pytest.mark.asyncio
    async def test_translation_logs_info(self) -> None:
        """Test that translation logs info messages."""
        mock_job_details = {
            "id": "job-123",
            "status": "COMPLETED",
            "output": {"translated_text": "Oli otya?"},
        }

        with patch(
            "app.services.translation_service.run_job_and_get_output",
            new_callable=AsyncMock,
            return_value=({}, mock_job_details),
        ):
            with patch.object(self.service, "log_info") as mock_log:
                await self.service.translate(
                    text="Hello",
                    source_language="eng",
                    target_language="lug",
                )

                # Should log at least once
                assert mock_log.call_count >= 1

    @pytest.mark.asyncio
    async def test_translation_logs_error_on_failure(self) -> None:
        """Test that translation logs errors on API failure."""
        with patch(
            "app.services.translation_service.run_job_and_get_output",
            new_callable=AsyncMock,
            side_effect=Exception("API Error"),
        ):
            with patch.object(self.service, "log_error") as mock_log:
                with pytest.raises(TranslationError):
                    await self.service.translate(
                        text="Hello",
                        source_language="eng",
                        target_language="lug",
                    )

                mock_log.assert_called()


class TestExceptionClasses:
    """Tests for custom exception classes."""

    def test_translation_error(self) -> None:
        """Test TranslationError exception."""
        error = TranslationError("Translation failed")
        assert str(error) == "Translation failed"

    def test_translation_timeout_error(self) -> None:
        """Test TranslationTimeoutError exception."""
        error = TranslationTimeoutError("Request timed out")
        assert str(error) == "Request timed out"
        assert isinstance(error, TranslationError)

    def test_translation_connection_error(self) -> None:
        """Test TranslationConnectionError exception."""
        error = TranslationConnectionError("Connection failed")
        assert str(error) == "Connection failed"
        assert isinstance(error, TranslationError)

    def test_translation_validation_error(self) -> None:
        """Test TranslationValidationError exception."""
        error = TranslationValidationError("Invalid response")
        assert str(error) == "Invalid response"
        assert isinstance(error, TranslationError)
