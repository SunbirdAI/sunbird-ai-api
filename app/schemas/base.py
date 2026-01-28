"""
Base Schemas Module.

This module provides common base schemas used across the application for
consistent API response formatting. All response models should inherit from
or use these base classes to ensure uniform API responses.

Usage:
    from app.schemas.base import BaseResponse, PaginatedResponse, ErrorResponse

Example:
    class UserResponse(BaseResponse):
        data: User

    class UsersListResponse(PaginatedResponse[User]):
        pass
"""

from datetime import datetime
from typing import Any, Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

# Type variable for generic models
DataT = TypeVar("DataT")


class BaseResponse(BaseModel):
    """Base response model for all API responses.

    This model provides a consistent structure for API responses with
    success status, message, and optional timestamp.

    Attributes:
        success: Indicates whether the request was successful.
        message: Human-readable message describing the result.
        timestamp: UTC timestamp when the response was generated.

    Example:
        >>> response = BaseResponse(success=True, message="Operation completed")
        >>> response.model_dump()
        {'success': True, 'message': 'Operation completed', 'timestamp': ...}
    """

    success: bool = Field(
        default=True,
        description="Indicates whether the request was successful",
    )
    message: str = Field(
        default="Request processed successfully",
        description="Human-readable message describing the result",
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC timestamp when the response was generated",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Request processed successfully",
                "timestamp": "2024-01-23T12:00:00Z",
            }
        }
    )


class DataResponse(BaseResponse, Generic[DataT]):
    """Generic response model that includes data payload.

    This model extends BaseResponse to include a typed data field,
    allowing for type-safe response handling.

    Attributes:
        data: The response payload of type DataT.

    Example:
        >>> from pydantic import BaseModel
        >>> class User(BaseModel):
        ...     id: int
        ...     name: str
        >>> response = DataResponse[User](data=User(id=1, name="John"))
        >>> response.data.name
        'John'
    """

    data: DataT = Field(description="Response data payload")


class PaginatedResponse(BaseResponse, Generic[DataT]):
    """Generic paginated response model for list endpoints.

    This model extends BaseResponse to include pagination metadata
    along with a list of items. Use this for any endpoint that returns
    a paginated list of resources.

    Attributes:
        items: List of items of type DataT.
        total: Total number of items across all pages.
        page: Current page number (1-indexed).
        page_size: Number of items per page.
        total_pages: Total number of pages available.
        has_next: Whether there is a next page.
        has_previous: Whether there is a previous page.

    Example:
        >>> class User(BaseModel):
        ...     id: int
        ...     name: str
        >>> users = [User(id=1, name="John"), User(id=2, name="Jane")]
        >>> response = PaginatedResponse[User](
        ...     items=users,
        ...     total=100,
        ...     page=1,
        ...     page_size=10
        ... )
        >>> response.total_pages
        10
    """

    items: List[DataT] = Field(
        default_factory=list,
        description="List of items for the current page",
    )
    total: int = Field(
        default=0,
        ge=0,
        description="Total number of items across all pages",
    )
    page: int = Field(
        default=1,
        ge=1,
        description="Current page number (1-indexed)",
    )
    page_size: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Number of items per page",
    )

    @property
    def total_pages(self) -> int:
        """Calculate total number of pages.

        Returns:
            Total number of pages based on total items and page size.
        """
        if self.page_size <= 0:
            return 0
        return (self.total + self.page_size - 1) // self.page_size

    @property
    def has_next(self) -> bool:
        """Check if there is a next page.

        Returns:
            True if current page is less than total pages.
        """
        return self.page < self.total_pages

    @property
    def has_previous(self) -> bool:
        """Check if there is a previous page.

        Returns:
            True if current page is greater than 1.
        """
        return self.page > 1

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Items retrieved successfully",
                "timestamp": "2024-01-23T12:00:00Z",
                "items": [],
                "total": 100,
                "page": 1,
                "page_size": 10,
            }
        }
    )


class ErrorDetail(BaseModel):
    """Model for individual error details.

    Attributes:
        loc: Location of the error (e.g., field path).
        msg: Error message.
        type: Error type identifier.
        input: The input value that caused the error (can be any type).
    """

    loc: Optional[List[str]] = Field(
        default=None,
        description="Location of the error in the request",
    )
    msg: str = Field(description="Error message")
    type: Optional[str] = Field(
        default=None,
        description="Error type identifier",
    )
    input: Optional[Any] = Field(
        default=None,
        description="The input value that caused the error",
    )


class ErrorResponse(BaseModel):
    """Standard error response model for API errors.

    This model provides a consistent structure for error responses
    across all API endpoints.

    Attributes:
        success: Always False for error responses.
        error_code: Machine-readable error code.
        message: Human-readable error message.
        details: List of detailed error information.
        timestamp: UTC timestamp when the error occurred.

    Example:
        >>> error = ErrorResponse(
        ...     error_code="VALIDATION_ERROR",
        ...     message="Invalid input data",
        ...     details=[ErrorDetail(msg="Field required", loc=["body", "email"])]
        ... )
    """

    success: bool = Field(
        default=False,
        description="Always False for error responses",
    )
    error_code: str = Field(
        description="Machine-readable error code",
    )
    message: str = Field(
        description="Human-readable error message",
    )
    details: Optional[List[ErrorDetail]] = Field(
        default=None,
        description="List of detailed error information",
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC timestamp when the error occurred",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": False,
                "error_code": "VALIDATION_ERROR",
                "message": "Invalid input data",
                "details": [
                    {
                        "loc": ["body", "email"],
                        "msg": "field required",
                        "type": "missing",
                    }
                ],
                "timestamp": "2024-01-23T12:00:00Z",
            }
        }
    )


class HealthResponse(BaseModel):
    """Health check response model.

    Attributes:
        status: Service status (healthy, unhealthy, degraded).
        version: Application version.
        timestamp: UTC timestamp of the health check.
    """

    status: str = Field(
        default="healthy",
        description="Service status",
    )
    version: Optional[str] = Field(
        default=None,
        description="Application version",
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC timestamp of the health check",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "healthy",
                "version": "1.0.0",
                "timestamp": "2024-01-23T12:00:00Z",
            }
        }
    )
