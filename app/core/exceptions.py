"""
Custom Exceptions Module.

This module provides custom exception classes for the Sunbird AI API.
All custom exceptions inherit from APIException base class and are designed
to be caught by FastAPI exception handlers to return consistent error responses.

Usage:
    from app.core.exceptions import NotFoundError, ValidationError

    # In a route handler
    if not user:
        raise NotFoundError(resource="User", resource_id=user_id)

Exception Hierarchy:
    APIException (base)
    ├── NotFoundError - Resource not found (404)
    ├── ValidationError - Invalid input data (422)
    ├── AuthenticationError - Authentication failed (401)
    ├── AuthorizationError - Permission denied (403)
    ├── ExternalServiceError - External API failure (502)
    ├── RateLimitError - Rate limit exceeded (429)
    └── ConflictError - Resource conflict (409)
"""

from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status


class APIException(HTTPException):
    """Base exception class for all API exceptions.

    This class extends FastAPI's HTTPException to provide additional
    context and consistent error formatting across the application.

    Attributes:
        status_code: HTTP status code for the error.
        error_code: Machine-readable error code string.
        message: Human-readable error message.
        details: Additional error details (e.g., field-level errors).
        headers: Optional HTTP headers to include in the response.

    Example:
        >>> raise APIException(
        ...     status_code=400,
        ...     error_code="INVALID_REQUEST",
        ...     message="The request could not be processed"
        ... )
    """

    def __init__(
        self,
        status_code: int,
        error_code: str,
        message: str,
        details: Optional[List[Dict[str, Any]]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        """Initialize the API exception.

        Args:
            status_code: HTTP status code for the error.
            error_code: Machine-readable error code string.
            message: Human-readable error message.
            details: Additional error details.
            headers: Optional HTTP headers to include in the response.
        """
        self.error_code = error_code
        self.message = message
        self.details = details

        # Build the detail dict for HTTPException
        detail = {
            "error_code": error_code,
            "message": message,
        }
        if details:
            detail["details"] = details

        super().__init__(status_code=status_code, detail=detail, headers=headers)

    def __repr__(self) -> str:
        """Return string representation of the exception."""
        return (
            f"{self.__class__.__name__}("
            f"status_code={self.status_code}, "
            f"error_code='{self.error_code}', "
            f"message='{self.message}')"
        )


class NotFoundError(APIException):
    """Exception raised when a requested resource is not found.

    This exception should be raised when a database lookup or external
    resource fetch returns no results.

    Attributes:
        resource: Type of resource that was not found.
        resource_id: Identifier of the resource that was not found.

    Example:
        >>> raise NotFoundError(resource="User", resource_id=123)
        # Returns 404 with message "User with id '123' not found"
    """

    def __init__(
        self,
        resource: str,
        resource_id: Optional[Any] = None,
        message: Optional[str] = None,
    ) -> None:
        """Initialize NotFoundError.

        Args:
            resource: Type of resource that was not found.
            resource_id: Identifier of the resource.
            message: Custom error message (optional).
        """
        self.resource = resource
        self.resource_id = resource_id

        if message is None:
            if resource_id is not None:
                message = f"{resource} with id '{resource_id}' not found"
            else:
                message = f"{resource} not found"

        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="NOT_FOUND",
            message=message,
        )


class ValidationError(APIException):
    """Exception raised when request validation fails.

    This exception should be raised when custom validation logic fails
    beyond Pydantic's automatic validation.

    Attributes:
        errors: List of validation error details.

    Example:
        >>> raise ValidationError(
        ...     message="Invalid date range",
        ...     errors=[{"field": "end_date", "message": "must be after start_date"}]
        ... )
    """

    def __init__(
        self,
        message: str = "Validation error",
        errors: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Initialize ValidationError.

        Args:
            message: Human-readable error message.
            errors: List of field-level validation errors.
        """
        self.errors = errors or []

        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="VALIDATION_ERROR",
            message=message,
            details=errors,
        )


class AuthenticationError(APIException):
    """Exception raised when authentication fails.

    This exception should be raised when user credentials are invalid,
    tokens are expired, or authentication is required but not provided.

    Example:
        >>> raise AuthenticationError(message="Invalid or expired token")
    """

    def __init__(
        self,
        message: str = "Authentication failed",
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        """Initialize AuthenticationError.

        Args:
            message: Human-readable error message.
            headers: Optional headers (e.g., WWW-Authenticate).
        """
        if headers is None:
            headers = {"WWW-Authenticate": "Bearer"}

        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="AUTHENTICATION_ERROR",
            message=message,
            headers=headers,
        )


class AuthorizationError(APIException):
    """Exception raised when user lacks required permissions.

    This exception should be raised when an authenticated user attempts
    to access a resource they don't have permission to access.

    Example:
        >>> raise AuthorizationError(
        ...     message="You don't have permission to delete this resource"
        ... )
    """

    def __init__(
        self,
        message: str = "Permission denied",
        required_permission: Optional[str] = None,
    ) -> None:
        """Initialize AuthorizationError.

        Args:
            message: Human-readable error message.
            required_permission: The permission that was required.
        """
        self.required_permission = required_permission

        details = None
        if required_permission:
            details = [{"required_permission": required_permission}]

        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="AUTHORIZATION_ERROR",
            message=message,
            details=details,
        )


class ExternalServiceError(APIException):
    """Exception raised when an external service call fails.

    This exception should be raised when calls to external APIs
    (RunPod, OpenAI, WhatsApp, etc.) fail or return errors.

    Attributes:
        service_name: Name of the external service that failed.
        original_error: The original error from the service (if available).

    Example:
        >>> raise ExternalServiceError(
        ...     service_name="RunPod",
        ...     message="Transcription service unavailable"
        ... )
    """

    def __init__(
        self,
        service_name: str,
        message: Optional[str] = None,
        original_error: Optional[str] = None,
    ) -> None:
        """Initialize ExternalServiceError.

        Args:
            service_name: Name of the external service.
            message: Human-readable error message.
            original_error: The original error message from the service.
        """
        self.service_name = service_name
        self.original_error = original_error

        if message is None:
            message = f"External service '{service_name}' is unavailable"

        details = [{"service": service_name}]
        if original_error:
            details[0]["original_error"] = original_error

        super().__init__(
            status_code=status.HTTP_502_BAD_GATEWAY,
            error_code="EXTERNAL_SERVICE_ERROR",
            message=message,
            details=details,
        )


class RateLimitError(APIException):
    """Exception raised when rate limit is exceeded.

    This exception should be raised when a user exceeds their
    allowed request rate.

    Attributes:
        retry_after: Seconds until the rate limit resets.

    Example:
        >>> raise RateLimitError(retry_after=60)
    """

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: Optional[int] = None,
    ) -> None:
        """Initialize RateLimitError.

        Args:
            message: Human-readable error message.
            retry_after: Seconds until the rate limit resets.
        """
        self.retry_after = retry_after

        headers = None
        if retry_after:
            headers = {"Retry-After": str(retry_after)}

        details = None
        if retry_after:
            details = [{"retry_after_seconds": retry_after}]

        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            error_code="RATE_LIMIT_ERROR",
            message=message,
            details=details,
            headers=headers,
        )


class ConflictError(APIException):
    """Exception raised when a resource conflict occurs.

    This exception should be raised when an operation cannot be completed
    due to a conflict with the current state (e.g., duplicate username).

    Example:
        >>> raise ConflictError(
        ...     resource="User",
        ...     message="Username already exists"
        ... )
    """

    def __init__(
        self,
        message: str = "Resource conflict",
        resource: Optional[str] = None,
        conflict_field: Optional[str] = None,
    ) -> None:
        """Initialize ConflictError.

        Args:
            message: Human-readable error message.
            resource: Type of resource with the conflict.
            conflict_field: The field causing the conflict.
        """
        self.resource = resource
        self.conflict_field = conflict_field

        details = []
        if resource:
            details.append({"resource": resource})
        if conflict_field:
            details.append({"conflict_field": conflict_field})

        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            error_code="CONFLICT_ERROR",
            message=message,
            details=details if details else None,
        )


class ServiceUnavailableError(APIException):
    """Exception raised when the service is temporarily unavailable.

    This exception should be raised during maintenance or when
    critical dependencies are down.

    Example:
        >>> raise ServiceUnavailableError(
        ...     message="Service is under maintenance"
        ... )
    """

    def __init__(
        self,
        message: str = "Service temporarily unavailable",
        retry_after: Optional[int] = None,
    ) -> None:
        """Initialize ServiceUnavailableError.

        Args:
            message: Human-readable error message.
            retry_after: Seconds until service might be available.
        """
        headers = None
        if retry_after:
            headers = {"Retry-After": str(retry_after)}

        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error_code="SERVICE_UNAVAILABLE",
            message=message,
            headers=headers,
        )


class BadRequestError(APIException):
    """Exception raised for malformed or invalid requests.

    This exception should be raised when the request cannot be
    processed due to client error that isn't validation-related.

    Example:
        >>> raise BadRequestError(message="Invalid audio format")
    """

    def __init__(
        self,
        message: str = "Bad request",
        details: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Initialize BadRequestError.

        Args:
            message: Human-readable error message.
            details: Additional error details.
        """
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="BAD_REQUEST",
            message=message,
            details=details,
        )
