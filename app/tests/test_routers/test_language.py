"""
Tests for Language Router Module.

This module contains tests for the language API endpoints defined in
app/routers/language.py. Tests verify request handling, authentication,
error responses, and integration with the LanguageService.
"""

from typing import Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.api import app
from app.routers.language import get_service
from app.services.language_service import (
    AudioLanguageResult,
    LanguageClassificationResult,
    LanguageConnectionError,
    LanguageDetectionError,
    LanguageError,
    LanguageIdentificationResult,
    LanguageTimeoutError,
)


class TestLanguageIdEndpoint:
    """Tests for POST /tasks/language_id endpoint."""

    @pytest.fixture
    def mock_language_service(self) -> MagicMock:
        """Create a mock LanguageService for testing."""
        mock = MagicMock()
        mock.identify_language = AsyncMock()
        return mock

    @pytest.fixture
    def sample_identification_result(self) -> LanguageIdentificationResult:
        """Create a sample language identification result for testing."""
        return LanguageIdentificationResult(
            language="lug",
            raw_response={"language": "lug"},
        )

    @pytest.mark.asyncio
    async def test_successful_language_identification(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_language_service: MagicMock,
        sample_identification_result: LanguageIdentificationResult,
    ) -> None:
        """Test successful language identification request."""
        mock_language_service.identify_language = AsyncMock(
            return_value=sample_identification_result
        )

        app.dependency_overrides[get_service] = lambda: mock_language_service

        try:
            response = await async_client.post(
                "/tasks/language_id",
                json={"text": "Oli otya?"},
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["language"] == "lug"
            mock_language_service.identify_language.assert_called_once_with(
                text="Oli otya?"
            )
        finally:
            app.dependency_overrides.pop(get_service, None)

    @pytest.mark.asyncio
    async def test_language_identification_without_auth(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test that language identification requires authentication."""
        response = await async_client.post(
            "/tasks/language_id",
            json={"text": "Oli otya?"},
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_language_identification_empty_text(
        self,
        async_client: AsyncClient,
        test_user: Dict,
    ) -> None:
        """Test that empty text returns 422."""
        response = await async_client.post(
            "/tasks/language_id",
            json={"text": ""},
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_language_identification_text_too_short(
        self,
        async_client: AsyncClient,
        test_user: Dict,
    ) -> None:
        """Test that text shorter than 3 characters returns 422."""
        response = await async_client.post(
            "/tasks/language_id",
            json={"text": "ab"},
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_language_identification_text_too_long(
        self,
        async_client: AsyncClient,
        test_user: Dict,
    ) -> None:
        """Test that text longer than 200 characters returns 422."""
        response = await async_client.post(
            "/tasks/language_id",
            json={"text": "a" * 201},
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_language_identification_timeout_error(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_language_service: MagicMock,
    ) -> None:
        """Test that timeout error returns 408."""
        mock_language_service.identify_language = AsyncMock(
            side_effect=LanguageTimeoutError("Timeout")
        )

        app.dependency_overrides[get_service] = lambda: mock_language_service

        try:
            response = await async_client.post(
                "/tasks/language_id",
                json={"text": "Test text"},
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 503
            assert "timed out" in response.json()["message"].lower()
        finally:
            app.dependency_overrides.pop(get_service, None)

    @pytest.mark.asyncio
    async def test_language_identification_generic_error(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_language_service: MagicMock,
    ) -> None:
        """Test that generic error returns 500."""
        mock_language_service.identify_language = AsyncMock(
            side_effect=LanguageError("Unknown error")
        )

        app.dependency_overrides[get_service] = lambda: mock_language_service

        try:
            response = await async_client.post(
                "/tasks/language_id",
                json={"text": "Test text"},
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 502
        finally:
            app.dependency_overrides.pop(get_service, None)


class TestClassifyLanguageEndpoint:
    """Tests for POST /tasks/classify_language endpoint."""

    @pytest.fixture
    def mock_language_service(self) -> MagicMock:
        """Create a mock LanguageService for testing."""
        mock = MagicMock()
        mock.classify_language = AsyncMock()
        return mock

    @pytest.fixture
    def sample_classification_result(self) -> LanguageClassificationResult:
        """Create a sample language classification result for testing."""
        return LanguageClassificationResult(
            language="lug",
            probability=0.95,
            predictions={"lug": 0.95, "eng": 0.03, "ach": 0.02},
            raw_response={"predictions": {"lug": 0.95}},
        )

    @pytest.mark.asyncio
    async def test_successful_language_classification(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_language_service: MagicMock,
        sample_classification_result: LanguageClassificationResult,
    ) -> None:
        """Test successful language classification request."""
        mock_language_service.classify_language = AsyncMock(
            return_value=sample_classification_result
        )

        app.dependency_overrides[get_service] = lambda: mock_language_service

        try:
            response = await async_client.post(
                "/tasks/classify_language",
                json={"text": "Oli otya?"},
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["language"] == "lug"
            mock_language_service.classify_language.assert_called_once_with(
                text="Oli otya?"
            )
        finally:
            app.dependency_overrides.pop(get_service, None)

    @pytest.mark.asyncio
    async def test_language_classification_without_auth(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test that language classification requires authentication."""
        response = await async_client.post(
            "/tasks/classify_language",
            json={"text": "Oli otya?"},
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_language_classification_timeout_error(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_language_service: MagicMock,
    ) -> None:
        """Test that timeout error returns 408."""
        mock_language_service.classify_language = AsyncMock(
            side_effect=LanguageTimeoutError("Timeout")
        )

        app.dependency_overrides[get_service] = lambda: mock_language_service

        try:
            response = await async_client.post(
                "/tasks/classify_language",
                json={"text": "Test text"},
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 503
            assert "timed out" in response.json()["message"].lower()
        finally:
            app.dependency_overrides.pop(get_service, None)

    @pytest.mark.asyncio
    async def test_language_classification_detection_error(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_language_service: MagicMock,
    ) -> None:
        """Test that detection error returns 500."""
        mock_language_service.classify_language = AsyncMock(
            side_effect=LanguageDetectionError("Unexpected format")
        )

        app.dependency_overrides[get_service] = lambda: mock_language_service

        try:
            response = await async_client.post(
                "/tasks/classify_language",
                json={"text": "Test text"},
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 502
            assert "unexpected" in response.json()["message"].lower()
        finally:
            app.dependency_overrides.pop(get_service, None)

    @pytest.mark.asyncio
    async def test_language_classification_generic_error(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_language_service: MagicMock,
    ) -> None:
        """Test that generic error returns 500."""
        mock_language_service.classify_language = AsyncMock(
            side_effect=LanguageError("Unknown error")
        )

        app.dependency_overrides[get_service] = lambda: mock_language_service

        try:
            response = await async_client.post(
                "/tasks/classify_language",
                json={"text": "Test text"},
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 502
        finally:
            app.dependency_overrides.pop(get_service, None)

    @pytest.mark.asyncio
    async def test_language_not_detected_response(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_language_service: MagicMock,
    ) -> None:
        """Test response when language is not detected (below threshold)."""
        mock_language_service.classify_language = AsyncMock(
            return_value=LanguageClassificationResult(
                language="language not detected",
                probability=None,
                predictions={"lug": 0.5, "eng": 0.3},
            )
        )

        app.dependency_overrides[get_service] = lambda: mock_language_service

        try:
            response = await async_client.post(
                "/tasks/classify_language",
                json={"text": "Mixed language text"},
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["language"] == "language not detected"
        finally:
            app.dependency_overrides.pop(get_service, None)


class TestAutoDetectAudioLanguageEndpoint:
    """Tests for POST /tasks/auto_detect_audio_language endpoint."""

    @pytest.fixture
    def mock_language_service(self) -> MagicMock:
        """Create a mock LanguageService for testing."""
        mock = MagicMock()
        mock.detect_audio_language = AsyncMock()
        return mock

    @pytest.fixture
    def sample_audio_result(self) -> AudioLanguageResult:
        """Create a sample audio language result for testing."""
        return AudioLanguageResult(
            detected_language="lug",
            blob_name="audio/test.wav",
            raw_response={"detected_language": "lug"},
        )

    @pytest.mark.asyncio
    async def test_audio_language_detection_without_auth(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test that audio language detection requires authentication."""
        response = await async_client.post(
            "/tasks/auto_detect_audio_language",
            files={"audio": ("test.wav", b"audio content", "audio/wav")},
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_audio_language_detection_without_file(
        self,
        async_client: AsyncClient,
        test_user: Dict,
    ) -> None:
        """Test that audio language detection requires audio file."""
        response = await async_client.post(
            "/tasks/auto_detect_audio_language",
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_audio_language_detection_timeout_error(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_language_service: MagicMock,
    ) -> None:
        """Test that timeout error returns 503."""
        mock_language_service.detect_audio_language = AsyncMock(
            side_effect=LanguageTimeoutError("Timeout")
        )

        app.dependency_overrides[get_service] = lambda: mock_language_service

        try:
            response = await async_client.post(
                "/tasks/auto_detect_audio_language",
                files={"audio": ("test.wav", b"audio content", "audio/wav")},
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 503
            assert "timeout" in response.json()["message"].lower()
        finally:
            app.dependency_overrides.pop(get_service, None)

    @pytest.mark.asyncio
    async def test_audio_language_detection_connection_error(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_language_service: MagicMock,
    ) -> None:
        """Test that connection error returns 503."""
        mock_language_service.detect_audio_language = AsyncMock(
            side_effect=LanguageConnectionError("Connection failed")
        )

        app.dependency_overrides[get_service] = lambda: mock_language_service

        try:
            response = await async_client.post(
                "/tasks/auto_detect_audio_language",
                files={"audio": ("test.wav", b"audio content", "audio/wav")},
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 502
            assert "connection" in response.json()["message"].lower()
        finally:
            app.dependency_overrides.pop(get_service, None)

    @pytest.mark.asyncio
    async def test_audio_language_detection_generic_error(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_language_service: MagicMock,
    ) -> None:
        """Test that generic error returns 500."""
        mock_language_service.detect_audio_language = AsyncMock(
            side_effect=LanguageError("Unknown error")
        )

        app.dependency_overrides[get_service] = lambda: mock_language_service

        try:
            response = await async_client.post(
                "/tasks/auto_detect_audio_language",
                files={"audio": ("test.wav", b"audio content", "audio/wav")},
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 502
        finally:
            app.dependency_overrides.pop(get_service, None)


class TestLanguageSchemaValidation:
    """Tests for request schema validation."""

    @pytest.mark.asyncio
    async def test_missing_text_field(
        self,
        async_client: AsyncClient,
        test_user: Dict,
    ) -> None:
        """Test that missing text field returns 422."""
        response = await async_client.post(
            "/tasks/language_id",
            json={},
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_text_type(
        self,
        async_client: AsyncClient,
        test_user: Dict,
    ) -> None:
        """Test that invalid text type returns 422."""
        response = await async_client.post(
            "/tasks/language_id",
            json={"text": 12345},
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        assert response.status_code == 422
