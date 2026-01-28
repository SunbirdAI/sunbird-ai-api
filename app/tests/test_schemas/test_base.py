"""
Tests for Base Schema Module.

This module contains unit tests for the base schemas defined in
app/schemas/base.py, including BaseResponse, DataResponse,
PaginatedResponse, ErrorResponse, and related models.
"""

from datetime import datetime

import pytest
from pydantic import BaseModel, ValidationError

from app.schemas.base import (
    BaseResponse,
    DataResponse,
    ErrorDetail,
    ErrorResponse,
    HealthResponse,
    PaginatedResponse,
)


class TestBaseResponse:
    """Tests for BaseResponse schema."""

    def test_default_values(self) -> None:
        """Test that BaseResponse has correct default values."""
        response = BaseResponse()

        assert response.success is True
        assert response.message == "Request processed successfully"
        assert isinstance(response.timestamp, datetime)

    def test_custom_values(self) -> None:
        """Test BaseResponse with custom values."""
        response = BaseResponse(
            success=False,
            message="Operation failed",
        )

        assert response.success is False
        assert response.message == "Operation failed"

    def test_serialization(self) -> None:
        """Test that BaseResponse serializes correctly."""
        response = BaseResponse(success=True, message="Test message")
        data = response.model_dump()

        assert "success" in data
        assert "message" in data
        assert "timestamp" in data
        assert data["success"] is True
        assert data["message"] == "Test message"

    def test_json_serialization(self) -> None:
        """Test that BaseResponse serializes to JSON correctly."""
        response = BaseResponse()
        json_str = response.model_dump_json()

        assert "success" in json_str
        assert "message" in json_str
        assert "timestamp" in json_str


class TestDataResponse:
    """Tests for DataResponse generic schema."""

    def test_with_dict_data(self) -> None:
        """Test DataResponse with dictionary data."""
        response = DataResponse[dict](
            data={"key": "value"},
            message="Data retrieved",
        )

        assert response.data == {"key": "value"}
        assert response.success is True
        assert response.message == "Data retrieved"

    def test_with_model_data(self) -> None:
        """Test DataResponse with Pydantic model data."""

        class User(BaseModel):
            id: int
            name: str

        user = User(id=1, name="Test User")
        response = DataResponse[User](data=user)

        assert response.data.id == 1
        assert response.data.name == "Test User"
        assert response.success is True

    def test_with_list_data(self) -> None:
        """Test DataResponse with list data."""
        response = DataResponse[list](data=[1, 2, 3])

        assert response.data == [1, 2, 3]
        assert len(response.data) == 3

    def test_serialization_with_nested_model(self) -> None:
        """Test DataResponse serialization with nested model."""

        class Item(BaseModel):
            name: str
            price: float

        item = Item(name="Widget", price=9.99)
        response = DataResponse[Item](data=item)
        data = response.model_dump()

        assert data["data"]["name"] == "Widget"
        assert data["data"]["price"] == 9.99


class TestPaginatedResponse:
    """Tests for PaginatedResponse generic schema."""

    def test_default_values(self) -> None:
        """Test PaginatedResponse default values."""
        response = PaginatedResponse[dict]()

        assert response.items == []
        assert response.total == 0
        assert response.page == 1
        assert response.page_size == 10

    def test_with_items(self) -> None:
        """Test PaginatedResponse with items."""
        items = [{"id": 1}, {"id": 2}, {"id": 3}]
        response = PaginatedResponse[dict](
            items=items,
            total=100,
            page=1,
            page_size=10,
        )

        assert len(response.items) == 3
        assert response.total == 100
        assert response.page == 1
        assert response.page_size == 10

    def test_total_pages_calculation(self) -> None:
        """Test total_pages property calculation."""
        # 100 items, 10 per page = 10 pages
        response = PaginatedResponse[dict](total=100, page_size=10)
        assert response.total_pages == 10

        # 95 items, 10 per page = 10 pages (rounds up)
        response = PaginatedResponse[dict](total=95, page_size=10)
        assert response.total_pages == 10

        # 0 items = 0 pages
        response = PaginatedResponse[dict](total=0, page_size=10)
        assert response.total_pages == 0

        # 1 item = 1 page
        response = PaginatedResponse[dict](total=1, page_size=10)
        assert response.total_pages == 1

    def test_has_next_property(self) -> None:
        """Test has_next property."""
        # Page 1 of 10 - has next
        response = PaginatedResponse[dict](total=100, page=1, page_size=10)
        assert response.has_next is True

        # Page 10 of 10 - no next
        response = PaginatedResponse[dict](total=100, page=10, page_size=10)
        assert response.has_next is False

        # Page 5 of 10 - has next
        response = PaginatedResponse[dict](total=100, page=5, page_size=10)
        assert response.has_next is True

    def test_has_previous_property(self) -> None:
        """Test has_previous property."""
        # Page 1 - no previous
        response = PaginatedResponse[dict](total=100, page=1, page_size=10)
        assert response.has_previous is False

        # Page 2 - has previous
        response = PaginatedResponse[dict](total=100, page=2, page_size=10)
        assert response.has_previous is True

        # Page 10 - has previous
        response = PaginatedResponse[dict](total=100, page=10, page_size=10)
        assert response.has_previous is True

    def test_with_typed_items(self) -> None:
        """Test PaginatedResponse with typed items."""

        class User(BaseModel):
            id: int
            name: str

        users = [User(id=1, name="Alice"), User(id=2, name="Bob")]
        response = PaginatedResponse[User](
            items=users,
            total=2,
            page=1,
            page_size=10,
        )

        assert len(response.items) == 2
        assert response.items[0].name == "Alice"
        assert response.items[1].name == "Bob"

    def test_page_validation(self) -> None:
        """Test that page must be >= 1."""
        with pytest.raises(ValidationError):
            PaginatedResponse[dict](page=0)

    def test_page_size_validation(self) -> None:
        """Test page_size validation constraints."""
        # page_size must be >= 1
        with pytest.raises(ValidationError):
            PaginatedResponse[dict](page_size=0)

        # page_size must be <= 100
        with pytest.raises(ValidationError):
            PaginatedResponse[dict](page_size=101)


class TestErrorDetail:
    """Tests for ErrorDetail schema."""

    def test_basic_error(self) -> None:
        """Test basic ErrorDetail creation."""
        error = ErrorDetail(msg="Field is required")

        assert error.msg == "Field is required"
        assert error.loc is None
        assert error.type is None
        assert error.input is None

    def test_full_error(self) -> None:
        """Test ErrorDetail with all fields."""
        error = ErrorDetail(
            loc=["body", "email"],
            msg="Invalid email format",
            type="value_error",
            input="not-an-email",
        )

        assert error.loc == ["body", "email"]
        assert error.msg == "Invalid email format"
        assert error.type == "value_error"
        assert error.input == "not-an-email"

    def test_input_can_be_any_type(self) -> None:
        """Test that input field accepts any type."""
        # String input
        error1 = ErrorDetail(msg="Error", input="string value")
        assert error1.input == "string value"

        # Dict input
        error2 = ErrorDetail(msg="Error", input={"key": "value"})
        assert error2.input == {"key": "value"}

        # List input
        error3 = ErrorDetail(msg="Error", input=[1, 2, 3])
        assert error3.input == [1, 2, 3]

        # None input
        error4 = ErrorDetail(msg="Error", input=None)
        assert error4.input is None


class TestErrorResponse:
    """Tests for ErrorResponse schema."""

    def test_basic_error_response(self) -> None:
        """Test basic ErrorResponse creation."""
        response = ErrorResponse(
            error_code="VALIDATION_ERROR",
            message="Invalid input",
        )

        assert response.success is False
        assert response.error_code == "VALIDATION_ERROR"
        assert response.message == "Invalid input"
        assert response.details is None
        assert isinstance(response.timestamp, datetime)

    def test_error_response_with_details(self) -> None:
        """Test ErrorResponse with error details."""
        details = [
            ErrorDetail(loc=["body", "email"], msg="Invalid email"),
            ErrorDetail(loc=["body", "password"], msg="Too short"),
        ]
        response = ErrorResponse(
            error_code="VALIDATION_ERROR",
            message="Multiple validation errors",
            details=details,
        )

        assert response.success is False
        assert len(response.details) == 2
        assert response.details[0].msg == "Invalid email"
        assert response.details[1].msg == "Too short"

    def test_serialization(self) -> None:
        """Test ErrorResponse serialization."""
        response = ErrorResponse(
            error_code="NOT_FOUND",
            message="Resource not found",
        )
        data = response.model_dump()

        assert data["success"] is False
        assert data["error_code"] == "NOT_FOUND"
        assert data["message"] == "Resource not found"


class TestHealthResponse:
    """Tests for HealthResponse schema."""

    def test_default_values(self) -> None:
        """Test HealthResponse default values."""
        response = HealthResponse()

        assert response.status == "healthy"
        assert response.version is None
        assert isinstance(response.timestamp, datetime)

    def test_custom_values(self) -> None:
        """Test HealthResponse with custom values."""
        response = HealthResponse(
            status="unhealthy",
            version="1.0.0",
        )

        assert response.status == "unhealthy"
        assert response.version == "1.0.0"

    def test_serialization(self) -> None:
        """Test HealthResponse serialization."""
        response = HealthResponse(status="healthy", version="2.0.0")
        data = response.model_dump()

        assert data["status"] == "healthy"
        assert data["version"] == "2.0.0"
        assert "timestamp" in data
