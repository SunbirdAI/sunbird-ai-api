"""
Tests for Inference Service Module.

This module contains unit tests for the InferenceService class defined in
app/services/inference_service.py. Tests cover initialization, error classification,
retry logic, inference execution, and singleton patterns.
"""

import time
from unittest.mock import MagicMock, patch

import pytest
from openai import APIError, RateLimitError
from requests.exceptions import ConnectionError, HTTPError, Timeout

from app.services.inference_service import (
    InferenceService,
    InferenceTimeoutError,
    ModelLoadingError,
    SunflowerChatMessage,
    SunflowerChatRequest,
    SunflowerChatResponse,
    SunflowerUsageStats,
    classify_error,
    exponential_backoff_retry,
    get_inference_service,
    reset_inference_service,
    run_inference,
)


class TestInferenceServiceInitialization:
    """Tests for InferenceService initialization."""

    def test_default_initialization(self) -> None:
        """Test that service initializes with default settings from env."""
        with patch.dict(
            "os.environ",
            {
                "RUNPOD_API_KEY": "test-api-key",
                "QWEN_ENDPOINT_ID": "test-endpoint-id",
            },
        ):
            service = InferenceService()

            assert service.runpod_api_key == "test-api-key"
            assert service.qwen_endpoint_id == "test-endpoint-id"
            assert "qwen" in service.endpoints

    def test_custom_initialization(self) -> None:
        """Test that service accepts custom configuration."""
        service = InferenceService(
            runpod_api_key="custom-api-key",
            qwen_endpoint_id="custom-endpoint-id",
        )

        assert service.runpod_api_key == "custom-api-key"
        assert service.qwen_endpoint_id == "custom-endpoint-id"

    def test_inherits_from_base_service(self) -> None:
        """Test that InferenceService inherits from BaseService."""
        from app.services.base import BaseService

        service = InferenceService(
            runpod_api_key="test",
            qwen_endpoint_id="test",
        )

        assert isinstance(service, BaseService)
        assert hasattr(service, "log_info")
        assert hasattr(service, "log_error")
        assert hasattr(service, "log_warning")

    def test_logs_warning_when_api_key_missing(self) -> None:
        """Test that warning is logged when RUNPOD_API_KEY is missing."""
        with patch.dict("os.environ", {}, clear=True):
            with patch.object(InferenceService, "log_warning") as mock_log_warning:
                InferenceService()

                # Should warn about missing config
                assert mock_log_warning.call_count >= 1


class TestPydanticModels:
    """Tests for Pydantic request/response models."""

    def test_sunflower_chat_message_creation(self) -> None:
        """Test SunflowerChatMessage model creation."""
        message = SunflowerChatMessage(role="user", content="Hello")

        assert message.role == "user"
        assert message.content == "Hello"

    def test_sunflower_chat_request_defaults(self) -> None:
        """Test SunflowerChatRequest default values."""
        messages = [SunflowerChatMessage(role="user", content="Hi")]
        request = SunflowerChatRequest(messages=messages)

        assert request.model_type == "qwen"
        assert request.temperature == 0.3
        assert request.stream is False
        assert request.system_message is None

    def test_sunflower_usage_stats(self) -> None:
        """Test SunflowerUsageStats model."""
        stats = SunflowerUsageStats(
            completion_tokens=50, prompt_tokens=10, total_tokens=60
        )

        assert stats.completion_tokens == 50
        assert stats.prompt_tokens == 10
        assert stats.total_tokens == 60

    def test_sunflower_chat_response(self) -> None:
        """Test SunflowerChatResponse model."""
        usage = SunflowerUsageStats(total_tokens=100)
        response = SunflowerChatResponse(
            content="Hello!",
            model_type="qwen",
            usage=usage,
            processing_time=1.5,
        )

        assert response.content == "Hello!"
        assert response.model_type == "qwen"
        assert response.processing_time == 1.5


class TestClassifyError:
    """Tests for error classification function."""

    def test_classify_model_loading_error_from_response(self) -> None:
        """Test that model loading errors are correctly classified."""
        error = Exception("Some error")
        response_text = "Error: model is loading, please wait"

        result = classify_error(error, response_text)

        assert isinstance(result, ModelLoadingError)

    def test_classify_worker_not_ready_error(self) -> None:
        """Test classification of worker not ready errors."""
        error = Exception("Error: worker is not ready")

        result = classify_error(error)

        assert isinstance(result, ModelLoadingError)

    def test_classify_timeout_error(self) -> None:
        """Test classification of timeout errors."""
        error = Exception("Request timed out after 30 seconds")

        result = classify_error(error)

        assert isinstance(result, InferenceTimeoutError)

    def test_classify_connection_timeout(self) -> None:
        """Test classification of connection timeout."""
        error = Timeout("Connection timeout")

        result = classify_error(error)

        assert isinstance(result, InferenceTimeoutError)

    def test_classify_connection_error(self) -> None:
        """Test classification of connection errors."""
        error = ConnectionError("Connection refused")

        result = classify_error(error)

        assert isinstance(result, InferenceTimeoutError)

    def test_classify_http_5xx_error(self) -> None:
        """Test classification of HTTP 5xx errors."""
        mock_response = MagicMock()
        mock_response.status_code = 503

        error = HTTPError()
        error.response = mock_response

        result = classify_error(error)

        assert isinstance(result, ModelLoadingError)

    def test_classify_rate_limit_error(self) -> None:
        """Test classification of rate limit errors."""
        error = RateLimitError(
            "Rate limit exceeded",
            response=MagicMock(),
            body=None,
        )

        result = classify_error(error)

        assert isinstance(result, InferenceTimeoutError)

    def test_classify_non_retryable_error(self) -> None:
        """Test that non-retryable errors pass through."""
        error = ValueError("Invalid input")

        result = classify_error(error)

        assert isinstance(result, ValueError)
        assert result is error


class TestExponentialBackoffRetry:
    """Tests for the exponential backoff retry decorator."""

    def test_successful_execution_no_retry(self) -> None:
        """Test that successful execution doesn't trigger retries."""
        call_count = 0

        @exponential_backoff_retry(max_retries=3, base_delay=0.01)
        def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = successful_func()

        assert result == "success"
        assert call_count == 1

    def test_retry_on_retryable_error(self) -> None:
        """Test that retryable errors trigger retries."""
        call_count = 0

        @exponential_backoff_retry(
            max_retries=2,
            base_delay=0.01,
            retryable_exceptions=(ModelLoadingError,),
        )
        def failing_then_success():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ModelLoadingError("Model loading")
            return "success"

        result = failing_then_success()

        assert result == "success"
        assert call_count == 2

    def test_non_retryable_error_raises_immediately(self) -> None:
        """Test that non-retryable errors are raised immediately."""
        call_count = 0

        @exponential_backoff_retry(
            max_retries=3,
            base_delay=0.01,
            retryable_exceptions=(ModelLoadingError,),
        )
        def non_retryable_failure():
            nonlocal call_count
            call_count += 1
            raise ValueError("Invalid input")

        with pytest.raises(ValueError):
            non_retryable_failure()

        assert call_count == 1

    def test_max_retries_exceeded(self) -> None:
        """Test that max retries raises the error."""
        call_count = 0

        @exponential_backoff_retry(
            max_retries=2,
            base_delay=0.01,
            retryable_exceptions=(ModelLoadingError,),
        )
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise ModelLoadingError("Always fails")

        with pytest.raises(ModelLoadingError):
            always_fails()

        # Initial + 2 retries = 3 attempts
        assert call_count == 3


class TestInferenceServiceBuildMessages:
    """Tests for message building logic."""

    def test_build_messages_with_messages_array(self) -> None:
        """Test building messages from provided array."""
        service = InferenceService(
            runpod_api_key="test",
            qwen_endpoint_id="test",
        )

        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
        ]

        result = service._build_messages(messages=messages)

        assert len(result) == 2
        assert result[0]["role"] == "system"
        assert result[1]["content"] == "Hello"

    def test_build_messages_with_custom_system_override(self) -> None:
        """Test that custom system message overrides existing."""
        service = InferenceService(
            runpod_api_key="test",
            qwen_endpoint_id="test",
        )

        messages = [
            {"role": "system", "content": "Original system"},
            {"role": "user", "content": "Hello"},
        ]

        result = service._build_messages(
            messages=messages, custom_system_message="Custom system"
        )

        assert result[0]["content"] == "Custom system"

    def test_build_messages_legacy_instruction(self) -> None:
        """Test building messages from legacy instruction format."""
        service = InferenceService(
            runpod_api_key="test",
            qwen_endpoint_id="test",
        )

        result = service._build_messages(instruction="Translate hello")

        assert len(result) == 2
        assert result[0]["role"] == "system"
        assert result[1]["role"] == "user"
        assert result[1]["content"] == "Translate hello"


class TestInferenceServiceCleanResponse:
    """Tests for response cleaning logic."""

    def test_clean_response_removes_think_tags(self) -> None:
        """Test that think tags are removed from response."""
        service = InferenceService(
            runpod_api_key="test",
            qwen_endpoint_id="test",
        )

        content = "<think>I'm thinking</think>Hello there!"

        result = service._clean_response(content)

        assert result == "Hello there!"
        assert "<think>" not in result
        assert "</think>" not in result

    def test_clean_response_handles_empty(self) -> None:
        """Test handling of empty response."""
        service = InferenceService(
            runpod_api_key="test",
            qwen_endpoint_id="test",
        )

        assert service._clean_response(None) == ""
        assert service._clean_response("") == ""


class TestInferenceServiceRunInference:
    """Tests for run_inference method."""

    def test_run_inference_success(self) -> None:
        """Test successful inference execution."""
        service = InferenceService(
            runpod_api_key="test-key",
            qwen_endpoint_id="test-endpoint",
        )

        # Create mock response
        mock_choice = MagicMock()
        mock_choice.message.content = "Hello! I am Sunflower."

        mock_usage = MagicMock()
        mock_usage.completion_tokens = 10
        mock_usage.prompt_tokens = 5
        mock_usage.total_tokens = 15

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        with patch.object(service, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = service.run_inference(
                messages=[{"role": "user", "content": "Hello"}]
            )

            assert result["content"] == "Hello! I am Sunflower."
            assert result["model_type"] == "qwen"
            assert result["usage"]["total_tokens"] == 15
            assert "processing_time" in result

    def test_run_inference_unsupported_model(self) -> None:
        """Test that unsupported model type raises error."""
        service = InferenceService(
            runpod_api_key="test",
            qwen_endpoint_id="test",
        )

        with pytest.raises(ValueError) as exc_info:
            service.run_inference(
                instruction="Hello",
                model_type="unsupported_model",
            )

        assert "Unsupported model type" in str(exc_info.value)


class TestInferenceServiceSingleton:
    """Tests for singleton pattern and dependency injection."""

    def test_get_inference_service_creates_singleton(self) -> None:
        """Test that get_inference_service returns the same instance."""
        reset_inference_service()

        with patch.dict(
            "os.environ",
            {
                "RUNPOD_API_KEY": "test-key",
                "QWEN_ENDPOINT_ID": "test-endpoint",
            },
        ):
            service1 = get_inference_service()
            service2 = get_inference_service()

            assert service1 is service2

    def test_reset_inference_service_clears_singleton(self) -> None:
        """Test that reset_inference_service clears the singleton."""
        reset_inference_service()

        with patch.dict(
            "os.environ",
            {
                "RUNPOD_API_KEY": "test-key",
                "QWEN_ENDPOINT_ID": "test-endpoint",
            },
        ):
            service1 = get_inference_service()
            reset_inference_service()
            service2 = get_inference_service()

            assert service1 is not service2


class TestStandaloneRunInference:
    """Tests for the standalone run_inference function."""

    def test_standalone_run_inference_calls_service(self) -> None:
        """Test that standalone function delegates to service."""
        reset_inference_service()

        mock_result = {
            "content": "Test response",
            "usage": {},
            "model_type": "qwen",
            "processing_time": 1.0,
        }

        with patch(
            "app.services.inference_service.get_inference_service"
        ) as mock_get_service:
            mock_service = MagicMock()
            mock_service.run_inference.return_value = mock_result
            mock_get_service.return_value = mock_service

            result = run_inference(instruction="Test")

            assert result == mock_result
            mock_service.run_inference.assert_called_once()

    def test_standalone_function_passes_all_params(self) -> None:
        """Test that standalone function passes all parameters."""
        reset_inference_service()

        with patch(
            "app.services.inference_service.get_inference_service"
        ) as mock_get_service:
            mock_service = MagicMock()
            mock_service.run_inference.return_value = {"content": ""}
            mock_get_service.return_value = mock_service

            messages = [{"role": "user", "content": "Hello"}]
            run_inference(
                instruction="Test instruction",
                model_type="qwen",
                stream=True,
                custom_system_message="Custom system",
                messages=messages,
            )

            mock_service.run_inference.assert_called_once_with(
                instruction="Test instruction",
                model_type="qwen",
                stream=True,
                custom_system_message="Custom system",
                messages=messages,
            )


class TestInferenceServiceLogging:
    """Tests for logging functionality."""

    def test_run_inference_logs_start(self) -> None:
        """Test that run_inference logs start message."""
        service = InferenceService(
            runpod_api_key="test",
            qwen_endpoint_id="test",
        )

        mock_choice = MagicMock()
        mock_choice.message.content = "Response"

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = None

        with patch.object(service, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_get_client.return_value = mock_client

            with patch.object(service, "log_info") as mock_log:
                service.run_inference(instruction="Test")

                # Should log at start
                mock_log.assert_any_call("Starting run_inference")
