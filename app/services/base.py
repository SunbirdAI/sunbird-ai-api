"""
Base Service Module.

This module provides the abstract base class for all service classes
in the Sunbird AI API. Services are responsible for business logic
and orchestrating interactions between routers and external resources.

Design Principles:
    1. Single Responsibility - Each service handles one domain
    2. Dependency Injection - Services receive dependencies via __init__
    3. Error Handling - Services raise domain-specific exceptions
    4. Logging - Services log operations for debugging and monitoring
    5. Async First - Services use async/await for I/O operations

Usage:
    from app.services.base import BaseService

    class MyService(BaseService):
        def __init__(self, db: AsyncSession, external_client: SomeClient):
            super().__init__()
            self.db = db
            self.external_client = external_client

        async def do_something(self, data: dict) -> dict:
            self.log_info("Processing request", extra={"data_keys": list(data.keys())})
            try:
                result = await self._process(data)
                return result
            except ExternalError as e:
                self.log_error("External service failed", exc_info=e)
                raise ExternalServiceError(
                    service_name="SomeService",
                    original_error=str(e)
                )

Example:
    # In a router
    @router.post("/process")
    async def process_data(
        request: ProcessRequest,
        service: Annotated[MyService, Depends(get_my_service)]
    ):
        return await service.do_something(request.model_dump())
"""

import logging
from abc import ABC
from typing import Any, Dict, Optional, Type, TypeVar

from app.core.exceptions import (
    APIException,
    BadRequestError,
    ExternalServiceError,
    NotFoundError,
    ValidationError,
)

# Type variable for generic service creation
T = TypeVar("T", bound="BaseService")


class BaseService(ABC):
    """Abstract base class for all service classes.

    This class provides common functionality for all services including
    logging, error handling helpers, and a consistent interface pattern.

    All services should inherit from this class and implement their
    domain-specific methods.

    Attributes:
        _logger: Logger instance for the service.
        service_name: Name of the service for logging and error messages.

    Example:
        >>> class UserService(BaseService):
        ...     def __init__(self, db: AsyncSession):
        ...         super().__init__()
        ...         self.db = db
        ...
        ...     async def get_user(self, user_id: int) -> User:
        ...         user = await self.db.get(User, user_id)
        ...         if not user:
        ...             raise self.not_found_error("User", user_id)
        ...         return user
    """

    def __init__(self) -> None:
        """Initialize the base service.

        Sets up the logger with the service class name for easy
        identification in log output.
        """
        self._logger = logging.getLogger(self.__class__.__name__)
        self.service_name = self.__class__.__name__

    # -------------------------------------------------------------------------
    # Logging Methods
    # -------------------------------------------------------------------------

    def log_debug(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Log a debug message.

        Args:
            message: The log message.
            extra: Additional context to include in the log.

        Example:
            >>> self.log_debug("Processing item", extra={"item_id": 123})
        """
        self._logger.debug(message, extra=extra or {})

    def log_info(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Log an info message.

        Args:
            message: The log message.
            extra: Additional context to include in the log.

        Example:
            >>> self.log_info("Request completed successfully")
        """
        self._logger.info(message, extra=extra or {})

    def log_warning(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Log a warning message.

        Args:
            message: The log message.
            extra: Additional context to include in the log.

        Example:
            >>> self.log_warning("Rate limit approaching", extra={"usage": 90})
        """
        self._logger.warning(message, extra=extra or {})

    def log_error(
        self,
        message: str,
        extra: Optional[Dict[str, Any]] = None,
        exc_info: Optional[Exception] = None,
    ) -> None:
        """Log an error message.

        Args:
            message: The log message.
            extra: Additional context to include in the log.
            exc_info: Exception to include in the log for traceback.

        Example:
            >>> try:
            ...     await some_operation()
            ... except Exception as e:
            ...     self.log_error("Operation failed", exc_info=e)
        """
        self._logger.error(message, extra=extra or {}, exc_info=exc_info)

    # -------------------------------------------------------------------------
    # Error Factory Methods
    # -------------------------------------------------------------------------

    def not_found_error(
        self,
        resource: str,
        resource_id: Optional[Any] = None,
        message: Optional[str] = None,
    ) -> NotFoundError:
        """Create a NotFoundError for a missing resource.

        Args:
            resource: Type of resource that was not found.
            resource_id: Identifier of the missing resource.
            message: Custom error message (optional).

        Returns:
            NotFoundError instance ready to be raised.

        Example:
            >>> raise self.not_found_error("User", user_id=123)
        """
        self.log_warning(
            f"{resource} not found",
            extra={"resource": resource, "resource_id": resource_id},
        )
        return NotFoundError(
            resource=resource, resource_id=resource_id, message=message
        )

    def validation_error(
        self,
        message: str,
        errors: Optional[list] = None,
    ) -> ValidationError:
        """Create a ValidationError for invalid input.

        Args:
            message: Human-readable error message.
            errors: List of validation error details.

        Returns:
            ValidationError instance ready to be raised.

        Example:
            >>> raise self.validation_error(
            ...     "Invalid date range",
            ...     errors=[{"field": "end_date", "message": "must be after start_date"}]
            ... )
        """
        self.log_warning(f"Validation error: {message}", extra={"errors": errors})
        return ValidationError(message=message, errors=errors)

    def bad_request_error(
        self,
        message: str,
        details: Optional[list] = None,
    ) -> BadRequestError:
        """Create a BadRequestError for malformed requests.

        Args:
            message: Human-readable error message.
            details: Additional error details.

        Returns:
            BadRequestError instance ready to be raised.

        Example:
            >>> raise self.bad_request_error("Invalid audio format")
        """
        self.log_warning(f"Bad request: {message}", extra={"details": details})
        return BadRequestError(message=message, details=details)

    def external_service_error(
        self,
        service_name: str,
        message: Optional[str] = None,
        original_error: Optional[str] = None,
    ) -> ExternalServiceError:
        """Create an ExternalServiceError for external API failures.

        Args:
            service_name: Name of the external service that failed.
            message: Human-readable error message.
            original_error: The original error from the external service.

        Returns:
            ExternalServiceError instance ready to be raised.

        Example:
            >>> raise self.external_service_error(
            ...     "RunPod",
            ...     message="Transcription failed",
            ...     original_error=str(e)
            ... )
        """
        self.log_error(
            f"External service error: {service_name}",
            extra={"service": service_name, "original_error": original_error},
        )
        return ExternalServiceError(
            service_name=service_name,
            message=message,
            original_error=original_error,
        )

    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------

    async def handle_external_call(
        self,
        service_name: str,
        operation: str,
        coro: Any,
    ) -> Any:
        """Execute an external service call with error handling.

        This method wraps an async operation with logging and error
        handling for external service calls.

        Args:
            service_name: Name of the external service being called.
            operation: Description of the operation being performed.
            coro: The coroutine to execute.

        Returns:
            The result of the coroutine.

        Raises:
            ExternalServiceError: If the external call fails.

        Example:
            >>> result = await self.handle_external_call(
            ...     "RunPod",
            ...     "transcription",
            ...     self.client.transcribe(audio_data)
            ... )
        """
        self.log_info(
            f"Calling external service",
            extra={"service": service_name, "operation": operation},
        )
        try:
            result = await coro
            self.log_info(
                f"External service call completed",
                extra={"service": service_name, "operation": operation},
            )
            return result
        except APIException:
            # Re-raise API exceptions as-is
            raise
        except Exception as e:
            self.log_error(
                f"External service call failed",
                extra={
                    "service": service_name,
                    "operation": operation,
                    "error": str(e),
                },
                exc_info=e,
            )
            raise self.external_service_error(
                service_name=service_name,
                message=f"{operation} failed",
                original_error=str(e),
            )

    def __repr__(self) -> str:
        """Return string representation of the service."""
        return f"<{self.service_name}>"


class ServiceMixin:
    """Mixin class providing additional service utilities.

    This mixin can be combined with BaseService or other classes
    to add common utility methods.

    Example:
        >>> class MyService(BaseService, ServiceMixin):
        ...     pass
    """

    def validate_required_fields(
        self,
        data: Dict[str, Any],
        required_fields: list,
    ) -> None:
        """Validate that required fields are present in data.

        Args:
            data: Dictionary to validate.
            required_fields: List of required field names.

        Raises:
            ValidationError: If any required fields are missing.

        Example:
            >>> self.validate_required_fields(
            ...     {"name": "John"},
            ...     ["name", "email"]
            ... )  # Raises ValidationError: missing 'email'
        """
        missing = [field for field in required_fields if field not in data]
        if missing:
            raise ValidationError(
                message=f"Missing required fields: {', '.join(missing)}",
                errors=[
                    {"field": field, "message": "field required"} for field in missing
                ],
            )

    def sanitize_string(self, value: str, max_length: int = 1000) -> str:
        """Sanitize a string value by stripping whitespace and truncating.

        Args:
            value: String to sanitize.
            max_length: Maximum length of the result.

        Returns:
            Sanitized string.

        Example:
            >>> self.sanitize_string("  hello world  ", max_length=5)
            'hello'
        """
        return value.strip()[:max_length]
