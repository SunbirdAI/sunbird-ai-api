"""
Tests for Base Service Module.

This module contains unit tests for the BaseService abstract class
and ServiceMixin defined in app/services/base.py.
"""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import (
    BadRequestError,
    ExternalServiceError,
    NotFoundError,
    ValidationError,
)
from app.services.base import BaseService, ServiceMixin


class ConcreteService(BaseService):
    """Concrete implementation of BaseService for testing."""

    def __init__(self):
        super().__init__()
        self.custom_attribute = "test_value"

    async def do_work(self, data: dict) -> dict:
        """Example method that does some work."""
        self.log_info("Doing work", extra={"data": data})
        return {"result": "success", "input": data}


class ConcreteServiceWithMixin(BaseService, ServiceMixin):
    """Concrete implementation with ServiceMixin for testing."""

    pass


class TestBaseServiceInitialization:
    """Tests for BaseService initialization."""

    def test_service_initializes_correctly(self) -> None:
        """Test that service initializes with proper attributes."""
        service = ConcreteService()

        assert service.service_name == "ConcreteService"
        assert service._logger is not None
        assert service._logger.name == "ConcreteService"

    def test_service_preserves_custom_attributes(self) -> None:
        """Test that subclass attributes are preserved."""
        service = ConcreteService()

        assert service.custom_attribute == "test_value"

    def test_service_repr(self) -> None:
        """Test string representation of service."""
        service = ConcreteService()

        assert repr(service) == "<ConcreteService>"


class TestBaseServiceLogging:
    """Tests for BaseService logging methods."""

    def test_log_debug(self) -> None:
        """Test debug logging."""
        service = ConcreteService()

        with patch.object(service._logger, "debug") as mock_debug:
            service.log_debug("Test debug message", extra={"key": "value"})

            mock_debug.assert_called_once_with(
                "Test debug message", extra={"key": "value"}
            )

    def test_log_info(self) -> None:
        """Test info logging."""
        service = ConcreteService()

        with patch.object(service._logger, "info") as mock_info:
            service.log_info("Test info message")

            mock_info.assert_called_once_with("Test info message", extra={})

    def test_log_warning(self) -> None:
        """Test warning logging."""
        service = ConcreteService()

        with patch.object(service._logger, "warning") as mock_warning:
            service.log_warning("Test warning", extra={"alert": True})

            mock_warning.assert_called_once_with("Test warning", extra={"alert": True})

    def test_log_error(self) -> None:
        """Test error logging."""
        service = ConcreteService()
        test_exception = ValueError("Test error")

        with patch.object(service._logger, "error") as mock_error:
            service.log_error(
                "Test error message",
                extra={"context": "test"},
                exc_info=test_exception,
            )

            mock_error.assert_called_once_with(
                "Test error message",
                extra={"context": "test"},
                exc_info=test_exception,
            )

    def test_log_with_none_extra(self) -> None:
        """Test logging with None extra converts to empty dict."""
        service = ConcreteService()

        with patch.object(service._logger, "info") as mock_info:
            service.log_info("Message")

            mock_info.assert_called_once_with("Message", extra={})


class TestBaseServiceErrorFactories:
    """Tests for BaseService error factory methods."""

    def test_not_found_error_with_id(self) -> None:
        """Test not_found_error creates proper exception."""
        service = ConcreteService()

        error = service.not_found_error("User", resource_id=123)

        assert isinstance(error, NotFoundError)
        assert error.resource == "User"
        assert error.resource_id == 123
        assert "User with id '123' not found" in error.message

    def test_not_found_error_without_id(self) -> None:
        """Test not_found_error without resource ID."""
        service = ConcreteService()

        error = service.not_found_error("Configuration")

        assert isinstance(error, NotFoundError)
        assert "Configuration not found" in error.message

    def test_not_found_error_with_custom_message(self) -> None:
        """Test not_found_error with custom message."""
        service = ConcreteService()

        error = service.not_found_error(
            "Document", message="The requested document does not exist"
        )

        assert error.message == "The requested document does not exist"

    def test_validation_error_basic(self) -> None:
        """Test validation_error creates proper exception."""
        service = ConcreteService()

        error = service.validation_error("Invalid input")

        assert isinstance(error, ValidationError)
        assert error.message == "Invalid input"
        assert error.errors == []

    def test_validation_error_with_details(self) -> None:
        """Test validation_error with error details."""
        service = ConcreteService()
        errors = [
            {"field": "email", "message": "Invalid format"},
            {"field": "age", "message": "Must be positive"},
        ]

        error = service.validation_error("Multiple errors", errors=errors)

        assert error.errors == errors
        assert error.details == errors

    def test_bad_request_error_basic(self) -> None:
        """Test bad_request_error creates proper exception."""
        service = ConcreteService()

        error = service.bad_request_error("Invalid audio format")

        assert isinstance(error, BadRequestError)
        assert error.message == "Invalid audio format"

    def test_bad_request_error_with_details(self) -> None:
        """Test bad_request_error with details."""
        service = ConcreteService()
        details = [{"supported_formats": ["mp3", "wav"]}]

        error = service.bad_request_error("Unsupported format", details=details)

        assert error.details == details

    def test_external_service_error_basic(self) -> None:
        """Test external_service_error creates proper exception."""
        service = ConcreteService()

        error = service.external_service_error("RunPod")

        assert isinstance(error, ExternalServiceError)
        assert error.service_name == "RunPod"
        assert "RunPod" in error.message

    def test_external_service_error_with_details(self) -> None:
        """Test external_service_error with full details."""
        service = ConcreteService()

        error = service.external_service_error(
            service_name="OpenAI",
            message="API rate limited",
            original_error="429 Too Many Requests",
        )

        assert error.service_name == "OpenAI"
        assert error.message == "API rate limited"
        assert error.original_error == "429 Too Many Requests"


class TestBaseServiceHandleExternalCall:
    """Tests for handle_external_call method."""

    @pytest.mark.asyncio
    async def test_successful_external_call(self) -> None:
        """Test successful external service call."""
        service = ConcreteService()

        async def mock_operation():
            return {"status": "success"}

        result = await service.handle_external_call(
            "TestService",
            "test_operation",
            mock_operation(),
        )

        assert result == {"status": "success"}

    @pytest.mark.asyncio
    async def test_failed_external_call(self) -> None:
        """Test failed external service call raises ExternalServiceError."""
        service = ConcreteService()

        async def failing_operation():
            raise ConnectionError("Connection refused")

        with pytest.raises(ExternalServiceError) as exc_info:
            await service.handle_external_call(
                "TestService",
                "test_operation",
                failing_operation(),
            )

        assert exc_info.value.service_name == "TestService"
        assert "test_operation failed" in exc_info.value.message
        assert "Connection refused" in exc_info.value.original_error

    @pytest.mark.asyncio
    async def test_external_call_preserves_api_exceptions(self) -> None:
        """Test that APIException subclasses are re-raised as-is."""
        service = ConcreteService()

        async def operation_with_not_found():
            raise NotFoundError(resource="Item", resource_id=123)

        with pytest.raises(NotFoundError) as exc_info:
            await service.handle_external_call(
                "TestService",
                "find_item",
                operation_with_not_found(),
            )

        assert exc_info.value.resource == "Item"
        assert exc_info.value.resource_id == 123

    @pytest.mark.asyncio
    async def test_external_call_logs_operations(self) -> None:
        """Test that external calls are logged."""
        service = ConcreteService()

        async def mock_operation():
            return "result"

        with patch.object(service, "log_info") as mock_log:
            await service.handle_external_call(
                "TestService",
                "operation",
                mock_operation(),
            )

            # Should log both start and completion
            assert mock_log.call_count == 2


class TestServiceMixin:
    """Tests for ServiceMixin utility methods."""

    def test_validate_required_fields_passes(self) -> None:
        """Test validation passes when all required fields present."""
        service = ConcreteServiceWithMixin()

        # Should not raise
        service.validate_required_fields(
            {"name": "John", "email": "john@example.com"},
            ["name", "email"],
        )

    def test_validate_required_fields_fails(self) -> None:
        """Test validation fails when required fields missing."""
        service = ConcreteServiceWithMixin()

        with pytest.raises(ValidationError) as exc_info:
            service.validate_required_fields(
                {"name": "John"},
                ["name", "email", "age"],
            )

        assert "email" in exc_info.value.message
        assert "age" in exc_info.value.message

    def test_validate_required_fields_error_details(self) -> None:
        """Test validation error contains proper details."""
        service = ConcreteServiceWithMixin()

        with pytest.raises(ValidationError) as exc_info:
            service.validate_required_fields(
                {},
                ["field1", "field2"],
            )

        assert len(exc_info.value.errors) == 2
        assert exc_info.value.errors[0]["field"] == "field1"
        assert exc_info.value.errors[1]["field"] == "field2"

    def test_sanitize_string_strips_whitespace(self) -> None:
        """Test string sanitization strips whitespace."""
        service = ConcreteServiceWithMixin()

        result = service.sanitize_string("  hello world  ")

        assert result == "hello world"

    def test_sanitize_string_truncates(self) -> None:
        """Test string sanitization truncates to max length."""
        service = ConcreteServiceWithMixin()

        result = service.sanitize_string("hello world", max_length=5)

        assert result == "hello"

    def test_sanitize_string_combined(self) -> None:
        """Test sanitization with both strip and truncate."""
        service = ConcreteServiceWithMixin()

        result = service.sanitize_string("  hello world  ", max_length=5)

        assert result == "hello"


class TestBaseServiceInheritance:
    """Tests for service inheritance patterns."""

    def test_can_create_concrete_subclass(self) -> None:
        """Test that concrete subclasses can be created."""
        service = ConcreteService()

        assert isinstance(service, BaseService)
        assert hasattr(service, "log_info")
        assert hasattr(service, "not_found_error")

    def test_subclass_can_add_methods(self) -> None:
        """Test that subclasses can add custom methods."""
        service = ConcreteService()

        assert hasattr(service, "do_work")

    @pytest.mark.asyncio
    async def test_subclass_methods_work(self) -> None:
        """Test that subclass methods function correctly."""
        service = ConcreteService()

        result = await service.do_work({"input": "data"})

        assert result["result"] == "success"
        assert result["input"] == {"input": "data"}

    def test_mixin_combines_correctly(self) -> None:
        """Test that mixin combines correctly with base class."""
        service = ConcreteServiceWithMixin()

        assert isinstance(service, BaseService)
        assert hasattr(service, "log_info")
        assert hasattr(service, "validate_required_fields")
        assert hasattr(service, "sanitize_string")
