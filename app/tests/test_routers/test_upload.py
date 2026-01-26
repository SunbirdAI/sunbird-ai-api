"""
Tests for Upload Router Module.

This module contains tests for the upload API endpoints defined in
app/routers/upload.py. Tests verify request handling, error responses,
and integration with the StorageService.
"""

from datetime import datetime, timezone
from typing import Dict
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient

from app.api import app
from app.routers.upload import get_service
from app.services.storage_service import StorageError, StorageService


class TestGenerateUploadUrlEndpoint:
    """Tests for POST /tasks/generate-upload-url endpoint."""

    @pytest.fixture
    def mock_storage_service(self) -> MagicMock:
        """Create a mock StorageService for testing."""
        mock = MagicMock(spec=StorageService)
        return mock

    @pytest.fixture
    def sample_upload_response(self) -> tuple:
        """Create a sample upload response for testing."""
        return (
            "https://storage.googleapis.com/bucket/uploads/file-id/test.wav?signed=...",
            "550e8400-e29b-41d4-a716-446655440000",
            datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        )

    @pytest.mark.asyncio
    async def test_successful_upload_url_generation(
        self,
        async_client: AsyncClient,
        mock_storage_service: MagicMock,
        sample_upload_response: tuple,
    ) -> None:
        """Test successful upload URL generation."""
        mock_storage_service.generate_upload_url = MagicMock(
            return_value=sample_upload_response
        )

        app.dependency_overrides[get_service] = lambda: mock_storage_service

        try:
            response = await async_client.post(
                "/tasks/generate-upload-url",
                json={
                    "file_name": "recording.wav",
                    "content_type": "audio/wav",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert "upload_url" in data
            assert "file_id" in data
            assert "expires_at" in data
            # Check that file_id is a valid UUID string
            assert len(data["file_id"]) == 36  # UUID format
            assert data["upload_url"].startswith("https://")
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_upload_url_with_different_content_types(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test upload URL generation with different content types."""
        # Test with image content type
        response = await async_client.post(
            "/tasks/generate-upload-url",
            json={
                "file_name": "photo.png",
                "content_type": "image/png",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "upload_url" in data
        assert "file_id" in data

    @pytest.mark.asyncio
    async def test_upload_url_missing_file_name(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test that missing file_name returns 422."""
        response = await async_client.post(
            "/tasks/generate-upload-url",
            json={
                "content_type": "audio/wav",
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_upload_url_missing_content_type(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test that missing content_type returns 422."""
        response = await async_client.post(
            "/tasks/generate-upload-url",
            json={
                "file_name": "test.wav",
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_upload_url_empty_file_name(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test that empty file_name returns 422."""
        response = await async_client.post(
            "/tasks/generate-upload-url",
            json={
                "file_name": "",
                "content_type": "audio/wav",
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_upload_url_path_traversal_blocked(
        self,
        async_client: AsyncClient,
        mock_storage_service: MagicMock,
    ) -> None:
        """Test that path traversal attempts are blocked."""
        app.dependency_overrides[get_service] = lambda: mock_storage_service

        try:
            # Test with .. in file name
            response = await async_client.post(
                "/tasks/generate-upload-url",
                json={
                    "file_name": "../../../etc/passwd",
                    "content_type": "text/plain",
                },
            )

            assert response.status_code == 400
            assert "path traversal" in response.json()["detail"].lower()

            # Test with leading /
            response = await async_client.post(
                "/tasks/generate-upload-url",
                json={
                    "file_name": "/etc/passwd",
                    "content_type": "text/plain",
                },
            )

            assert response.status_code == 400
            assert "path traversal" in response.json()["detail"].lower()
        finally:
            app.dependency_overrides.pop(get_service, None)

    @pytest.mark.asyncio
    async def test_upload_url_storage_error(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test that storage error returns 500."""
        # Mock the service at the function level using patch
        with patch("app.routers.upload.get_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.generate_upload_url = MagicMock(
                side_effect=StorageError("Connection failed")
            )
            mock_get_service.return_value = mock_service

            response = await async_client.post(
                "/tasks/generate-upload-url",
                json={
                    "file_name": "test.wav",
                    "content_type": "audio/wav",
                },
            )

            assert response.status_code == 500
            assert "error" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_upload_url_generic_error(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test that generic error returns 500."""
        # Mock the service at the function level using patch
        with patch("app.routers.upload.get_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.generate_upload_url = MagicMock(
                side_effect=Exception("Unexpected error")
            )
            mock_get_service.return_value = mock_service

            response = await async_client.post(
                "/tasks/generate-upload-url",
                json={
                    "file_name": "test.wav",
                    "content_type": "audio/wav",
                },
            )

            assert response.status_code == 500


class TestUploadSchemaValidation:
    """Tests for upload request schema validation."""

    @pytest.mark.asyncio
    async def test_empty_request_body(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test that empty request body returns 422."""
        response = await async_client.post(
            "/tasks/generate-upload-url",
            json={},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_json(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test that invalid JSON returns 422."""
        response = await async_client.post(
            "/tasks/generate-upload-url",
            content="not valid json",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_file_name_too_long(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test that file name longer than 255 chars returns 422."""
        response = await async_client.post(
            "/tasks/generate-upload-url",
            json={
                "file_name": "a" * 256,
                "content_type": "audio/wav",
            },
        )

        assert response.status_code == 422


class TestStorageServiceIntegration:
    """Tests for StorageService integration."""

    @pytest.mark.asyncio
    async def test_service_is_called_with_correct_params(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test that StorageService is called with correct parameters."""
        with patch("app.routers.upload.get_service") as mock_get_service:
            mock_service = MagicMock(spec=StorageService)
            mock_service.generate_upload_url = MagicMock(
                return_value=(
                    "https://storage.googleapis.com/...",
                    "test-id",
                    datetime.now(timezone.utc),
                )
            )
            mock_get_service.return_value = mock_service

            await async_client.post(
                "/tasks/generate-upload-url",
                json={
                    "file_name": "test.wav",
                    "content_type": "audio/wav",
                },
            )

            mock_service.generate_upload_url.assert_called_once_with(
                file_name="test.wav",
                content_type="audio/wav",
            )
