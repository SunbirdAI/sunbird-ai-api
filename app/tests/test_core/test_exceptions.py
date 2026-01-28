"""
Tests for Custom Exceptions Module.

This module contains unit tests for the custom exception classes defined
in app/core/exceptions.py.
"""

import pytest
from fastapi import status

from app.core.exceptions import (
    APIException,
    AuthenticationError,
    AuthorizationError,
    BadRequestError,
    ConflictError,
    ExternalServiceError,
    NotFoundError,
    RateLimitError,
    ServiceUnavailableError,
    ValidationError,
)


class TestAPIException:
    """Tests for APIException base class."""

    def test_basic_creation(self) -> None:
        """Test basic APIException creation."""
        exc = APIException(
            status_code=400,
            error_code="TEST_ERROR",
            message="Test error message",
        )

        assert exc.status_code == 400
        assert exc.error_code == "TEST_ERROR"
        assert exc.message == "Test error message"
        assert exc.details is None

    def test_with_details(self) -> None:
        """Test APIException with details."""
        details = [{"field": "email", "error": "invalid"}]
        exc = APIException(
            status_code=422,
            error_code="VALIDATION_ERROR",
            message="Validation failed",
            details=details,
        )

        assert exc.details == details
        assert exc.detail["details"] == details

    def test_with_headers(self) -> None:
        """Test APIException with custom headers."""
        headers = {"X-Custom-Header": "value"}
        exc = APIException(
            status_code=400,
            error_code="TEST",
            message="Test",
            headers=headers,
        )

        assert exc.headers == headers

    def test_detail_structure(self) -> None:
        """Test that detail is properly structured."""
        exc = APIException(
            status_code=400,
            error_code="TEST_ERROR",
            message="Test message",
        )

        assert exc.detail["error_code"] == "TEST_ERROR"
        assert exc.detail["message"] == "Test message"

    def test_repr(self) -> None:
        """Test string representation."""
        exc = APIException(
            status_code=400,
            error_code="TEST",
            message="Test message",
        )

        repr_str = repr(exc)
        assert "APIException" in repr_str
        assert "400" in repr_str
        assert "TEST" in repr_str


class TestNotFoundError:
    """Tests for NotFoundError exception."""

    def test_basic_not_found(self) -> None:
        """Test basic NotFoundError creation."""
        exc = NotFoundError(resource="User")

        assert exc.status_code == status.HTTP_404_NOT_FOUND
        assert exc.error_code == "NOT_FOUND"
        assert exc.resource == "User"
        assert "User not found" in exc.message

    def test_with_resource_id(self) -> None:
        """Test NotFoundError with resource ID."""
        exc = NotFoundError(resource="User", resource_id=123)

        assert exc.resource_id == 123
        assert "User with id '123' not found" in exc.message

    def test_with_custom_message(self) -> None:
        """Test NotFoundError with custom message."""
        exc = NotFoundError(
            resource="Item",
            message="The requested item does not exist",
        )

        assert exc.message == "The requested item does not exist"

    def test_with_string_id(self) -> None:
        """Test NotFoundError with string resource ID."""
        exc = NotFoundError(resource="Document", resource_id="doc-abc-123")

        assert "Document with id 'doc-abc-123' not found" in exc.message


class TestValidationError:
    """Tests for ValidationError exception."""

    def test_basic_validation_error(self) -> None:
        """Test basic ValidationError creation."""
        exc = ValidationError()

        assert exc.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert exc.error_code == "VALIDATION_ERROR"
        assert exc.message == "Validation error"
        assert exc.errors == []

    def test_with_custom_message(self) -> None:
        """Test ValidationError with custom message."""
        exc = ValidationError(message="Invalid date range")

        assert exc.message == "Invalid date range"

    def test_with_errors(self) -> None:
        """Test ValidationError with error details."""
        errors = [
            {"field": "email", "message": "Invalid email format"},
            {"field": "password", "message": "Too short"},
        ]
        exc = ValidationError(message="Multiple errors", errors=errors)

        assert exc.errors == errors
        assert exc.details == errors


class TestAuthenticationError:
    """Tests for AuthenticationError exception."""

    def test_basic_auth_error(self) -> None:
        """Test basic AuthenticationError creation."""
        exc = AuthenticationError()

        assert exc.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc.error_code == "AUTHENTICATION_ERROR"
        assert exc.message == "Authentication failed"
        assert exc.headers == {"WWW-Authenticate": "Bearer"}

    def test_with_custom_message(self) -> None:
        """Test AuthenticationError with custom message."""
        exc = AuthenticationError(message="Token expired")

        assert exc.message == "Token expired"

    def test_with_custom_headers(self) -> None:
        """Test AuthenticationError with custom headers."""
        headers = {"WWW-Authenticate": "Basic"}
        exc = AuthenticationError(headers=headers)

        assert exc.headers == headers


class TestAuthorizationError:
    """Tests for AuthorizationError exception."""

    def test_basic_authorization_error(self) -> None:
        """Test basic AuthorizationError creation."""
        exc = AuthorizationError()

        assert exc.status_code == status.HTTP_403_FORBIDDEN
        assert exc.error_code == "AUTHORIZATION_ERROR"
        assert exc.message == "Permission denied"

    def test_with_custom_message(self) -> None:
        """Test AuthorizationError with custom message."""
        exc = AuthorizationError(
            message="You don't have permission to delete this resource"
        )

        assert exc.message == "You don't have permission to delete this resource"

    def test_with_required_permission(self) -> None:
        """Test AuthorizationError with required permission."""
        exc = AuthorizationError(
            message="Admin access required",
            required_permission="admin:write",
        )

        assert exc.required_permission == "admin:write"
        assert exc.details is not None
        assert exc.details[0]["required_permission"] == "admin:write"


class TestExternalServiceError:
    """Tests for ExternalServiceError exception."""

    def test_basic_external_error(self) -> None:
        """Test basic ExternalServiceError creation."""
        exc = ExternalServiceError(service_name="RunPod")

        assert exc.status_code == status.HTTP_502_BAD_GATEWAY
        assert exc.error_code == "EXTERNAL_SERVICE_ERROR"
        assert exc.service_name == "RunPod"
        assert "RunPod" in exc.message
        assert exc.details[0]["service"] == "RunPod"

    def test_with_custom_message(self) -> None:
        """Test ExternalServiceError with custom message."""
        exc = ExternalServiceError(
            service_name="OpenAI",
            message="AI service rate limited",
        )

        assert exc.message == "AI service rate limited"

    def test_with_original_error(self) -> None:
        """Test ExternalServiceError with original error."""
        exc = ExternalServiceError(
            service_name="WhatsApp",
            original_error="Connection timeout",
        )

        assert exc.original_error == "Connection timeout"
        assert exc.details[0]["original_error"] == "Connection timeout"


class TestRateLimitError:
    """Tests for RateLimitError exception."""

    def test_basic_rate_limit_error(self) -> None:
        """Test basic RateLimitError creation."""
        exc = RateLimitError()

        assert exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert exc.error_code == "RATE_LIMIT_ERROR"
        assert exc.message == "Rate limit exceeded"

    def test_with_retry_after(self) -> None:
        """Test RateLimitError with retry_after."""
        exc = RateLimitError(retry_after=60)

        assert exc.retry_after == 60
        assert exc.headers["Retry-After"] == "60"
        assert exc.details[0]["retry_after_seconds"] == 60

    def test_with_custom_message(self) -> None:
        """Test RateLimitError with custom message."""
        exc = RateLimitError(message="Too many requests, please slow down")

        assert exc.message == "Too many requests, please slow down"


class TestConflictError:
    """Tests for ConflictError exception."""

    def test_basic_conflict_error(self) -> None:
        """Test basic ConflictError creation."""
        exc = ConflictError()

        assert exc.status_code == status.HTTP_409_CONFLICT
        assert exc.error_code == "CONFLICT_ERROR"
        assert exc.message == "Resource conflict"

    def test_with_resource(self) -> None:
        """Test ConflictError with resource."""
        exc = ConflictError(
            message="Username already exists",
            resource="User",
        )

        assert exc.resource == "User"
        assert exc.details is not None

    def test_with_conflict_field(self) -> None:
        """Test ConflictError with conflict field."""
        exc = ConflictError(
            message="Email already registered",
            resource="User",
            conflict_field="email",
        )

        assert exc.conflict_field == "email"


class TestServiceUnavailableError:
    """Tests for ServiceUnavailableError exception."""

    def test_basic_unavailable_error(self) -> None:
        """Test basic ServiceUnavailableError creation."""
        exc = ServiceUnavailableError()

        assert exc.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert exc.error_code == "SERVICE_UNAVAILABLE"
        assert exc.message == "Service temporarily unavailable"

    def test_with_retry_after(self) -> None:
        """Test ServiceUnavailableError with retry_after."""
        exc = ServiceUnavailableError(
            message="Maintenance in progress",
            retry_after=300,
        )

        assert exc.headers["Retry-After"] == "300"

    def test_with_custom_message(self) -> None:
        """Test ServiceUnavailableError with custom message."""
        exc = ServiceUnavailableError(message="Database maintenance")

        assert exc.message == "Database maintenance"


class TestBadRequestError:
    """Tests for BadRequestError exception."""

    def test_basic_bad_request(self) -> None:
        """Test basic BadRequestError creation."""
        exc = BadRequestError()

        assert exc.status_code == status.HTTP_400_BAD_REQUEST
        assert exc.error_code == "BAD_REQUEST"
        assert exc.message == "Bad request"

    def test_with_custom_message(self) -> None:
        """Test BadRequestError with custom message."""
        exc = BadRequestError(message="Invalid audio format")

        assert exc.message == "Invalid audio format"

    def test_with_details(self) -> None:
        """Test BadRequestError with details."""
        details = [{"supported_formats": ["mp3", "wav", "ogg"]}]
        exc = BadRequestError(
            message="Unsupported file format",
            details=details,
        )

        assert exc.details == details


class TestExceptionInheritance:
    """Tests for exception inheritance hierarchy."""

    def test_all_exceptions_inherit_from_api_exception(self) -> None:
        """Test that all custom exceptions inherit from APIException."""
        exceptions = [
            NotFoundError(resource="Test"),
            ValidationError(),
            AuthenticationError(),
            AuthorizationError(),
            ExternalServiceError(service_name="Test"),
            RateLimitError(),
            ConflictError(),
            ServiceUnavailableError(),
            BadRequestError(),
        ]

        for exc in exceptions:
            assert isinstance(exc, APIException)

    def test_all_exceptions_are_http_exceptions(self) -> None:
        """Test that all exceptions can be caught as HTTPException."""
        from fastapi import HTTPException

        exceptions = [
            NotFoundError(resource="Test"),
            ValidationError(),
            AuthenticationError(),
        ]

        for exc in exceptions:
            assert isinstance(exc, HTTPException)
