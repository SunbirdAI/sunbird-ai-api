"""
Error Schemas Module.

This module provides Pydantic models for validation error responses.
These models are used by the custom exception handler to format
validation errors in a consistent way.

Note:
    The ErrorDetail and ErrorResponse models in base.py provide a more
    comprehensive error response structure. These models are kept for
    backward compatibility with the existing validation error handler.
"""

from typing import Any, List, Optional, Union

from pydantic import BaseModel, Field


class ValidationErrorDetail(BaseModel):
    """Model for individual validation error details.

    This model represents a single validation error with its location,
    message, and the input value that caused the error.

    Attributes:
        loc: Location of the error as a list of path elements
             (e.g., ["body", "email"] or ["query", "page"]).
        msg: Human-readable error message.
        input: The input value that caused the error. Can be any type
               (str, dict, list, etc.) depending on the validation context.

    Example:
        >>> error = ValidationErrorDetail(
        ...     loc=["body", "email"],
        ...     msg="value is not a valid email address",
        ...     input="not-an-email"
        ... )
    """

    loc: List[Union[str, int]] = Field(
        description="Location of the error in the request"
    )
    msg: str = Field(description="Human-readable error message")
    input: Optional[Any] = Field(
        default=None,
        description="The input value that caused the validation error",
    )


class ValidationErrorResponse(BaseModel):
    """Model for validation error response.

    This model wraps a list of validation errors for the response body.

    Attributes:
        errors: List of validation error details.

    Example:
        >>> response = ValidationErrorResponse(
        ...     errors=[
        ...         ValidationErrorDetail(
        ...             loc=["body", "email"],
        ...             msg="field required"
        ...         )
        ...     ]
        ... )
    """

    errors: List[ValidationErrorDetail] = Field(description="List of validation errors")
