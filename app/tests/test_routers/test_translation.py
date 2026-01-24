"""
Tests for Translation Router Module.

This module contains tests for the translation API endpoints defined in
app/routers/translation.py. Tests verify request handling, authentication,
error responses, and integration with the TranslationService.
"""

from typing import Dict
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.api import app
from app.routers.translation import get_service
from app.services.translation_service import (
    TranslationConnectionError,
    TranslationError,
    TranslationResult,
    TranslationTimeoutError,
    TranslationValidationError,
)


class TestNllbTranslateEndpoint:
    """Tests for POST /tasks/nllb_translate endpoint."""

    @pytest.fixture
    def mock_translation_service(self) -> MagicMock:
        """Create a mock TranslationService for testing."""
        mock = MagicMock()
        mock.translate = AsyncMock()
        mock.validate_and_parse_response = MagicMock()
        return mock

    @pytest.fixture
    def sample_translation_result(self) -> TranslationResult:
        """Create a sample translation result for testing."""
        return TranslationResult(
            translated_text="Oli otya?",
            source_language="eng",
            target_language="lug",
            delay_time=100,
            execution_time=500,
            job_id="job-123",
            worker_id="worker-456",
            status="COMPLETED",
            raw_response={
                "id": "job-123",
                "status": "COMPLETED",
                "output": {
                    "translated_text": "Oli otya?",
                    "source_language": "eng",
                    "target_language": "lug",
                },
                "delayTime": 100,
                "executionTime": 500,
                "workerId": "worker-456",
            },
        )

    @pytest.mark.asyncio
    async def test_successful_translation(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_translation_service: MagicMock,
        sample_translation_result: TranslationResult,
    ) -> None:
        """Test successful translation request."""
        mock_translation_service.translate = AsyncMock(
            return_value=sample_translation_result
        )
        mock_translation_service.validate_and_parse_response = MagicMock(
            return_value=MagicMock(
                model_dump=MagicMock(
                    return_value={
                        "id": "job-123",
                        "status": "COMPLETED",
                        "output": {
                            "translated_text": "Oli otya?",
                            "source_language": "eng",
                            "target_language": "lug",
                        },
                        "delayTime": 100,
                        "executionTime": 500,
                        "workerId": "worker-456",
                    }
                )
            )
        )

        app.dependency_overrides[get_service] = lambda: mock_translation_service

        try:
            response = await async_client.post(
                "/tasks/nllb_translate",
                json={
                    "source_language": "eng",
                    "target_language": "lug",
                    "text": "How are you?",
                },
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "COMPLETED"
            assert data["output"]["translated_text"] == "Oli otya?"
            mock_translation_service.translate.assert_called_once_with(
                text="How are you?",
                source_language="eng",
                target_language="lug",
            )
        finally:
            app.dependency_overrides.pop(get_service, None)

    @pytest.mark.asyncio
    async def test_translation_without_auth(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test that translation requires authentication."""
        response = await async_client.post(
            "/tasks/nllb_translate",
            json={
                "source_language": "eng",
                "target_language": "lug",
                "text": "Hello",
            },
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_translation_invalid_source_language(
        self,
        async_client: AsyncClient,
        test_user: Dict,
    ) -> None:
        """Test that invalid source language returns 422."""
        response = await async_client.post(
            "/tasks/nllb_translate",
            json={
                "source_language": "invalid",
                "target_language": "lug",
                "text": "Hello",
            },
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_translation_invalid_target_language(
        self,
        async_client: AsyncClient,
        test_user: Dict,
    ) -> None:
        """Test that invalid target language returns 422."""
        response = await async_client.post(
            "/tasks/nllb_translate",
            json={
                "source_language": "eng",
                "target_language": "invalid",
                "text": "Hello",
            },
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_translation_empty_text(
        self,
        async_client: AsyncClient,
        test_user: Dict,
    ) -> None:
        """Test that empty text returns 422."""
        response = await async_client.post(
            "/tasks/nllb_translate",
            json={
                "source_language": "eng",
                "target_language": "lug",
                "text": "",
            },
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_translation_whitespace_only_text(
        self,
        async_client: AsyncClient,
        test_user: Dict,
    ) -> None:
        """Test that whitespace-only text returns 422."""
        response = await async_client.post(
            "/tasks/nllb_translate",
            json={
                "source_language": "eng",
                "target_language": "lug",
                "text": "   ",
            },
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_translation_timeout_error(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_translation_service: MagicMock,
    ) -> None:
        """Test that timeout error returns 503."""
        mock_translation_service.translate = AsyncMock(
            side_effect=TranslationTimeoutError("Timeout")
        )

        app.dependency_overrides[get_service] = lambda: mock_translation_service

        try:
            response = await async_client.post(
                "/tasks/nllb_translate",
                json={
                    "source_language": "eng",
                    "target_language": "lug",
                    "text": "Hello",
                },
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 503
            assert "timeout" in response.json()["detail"].lower()
        finally:
            app.dependency_overrides.pop(get_service, None)

    @pytest.mark.asyncio
    async def test_translation_connection_error(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_translation_service: MagicMock,
    ) -> None:
        """Test that connection error returns 503."""
        mock_translation_service.translate = AsyncMock(
            side_effect=TranslationConnectionError("Connection failed")
        )

        app.dependency_overrides[get_service] = lambda: mock_translation_service

        try:
            response = await async_client.post(
                "/tasks/nllb_translate",
                json={
                    "source_language": "eng",
                    "target_language": "lug",
                    "text": "Hello",
                },
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 503
            assert "connection" in response.json()["detail"].lower()
        finally:
            app.dependency_overrides.pop(get_service, None)

    @pytest.mark.asyncio
    async def test_translation_validation_error(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_translation_service: MagicMock,
        sample_translation_result: TranslationResult,
    ) -> None:
        """Test that validation error returns 500."""
        mock_translation_service.translate = AsyncMock(
            return_value=sample_translation_result
        )
        mock_translation_service.validate_and_parse_response = MagicMock(
            side_effect=TranslationValidationError("Invalid response")
        )

        app.dependency_overrides[get_service] = lambda: mock_translation_service

        try:
            response = await async_client.post(
                "/tasks/nllb_translate",
                json={
                    "source_language": "eng",
                    "target_language": "lug",
                    "text": "Hello",
                },
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 500
            assert "invalid" in response.json()["detail"].lower()
        finally:
            app.dependency_overrides.pop(get_service, None)

    @pytest.mark.asyncio
    async def test_translation_generic_error(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_translation_service: MagicMock,
    ) -> None:
        """Test that generic error returns 500."""
        mock_translation_service.translate = AsyncMock(
            side_effect=TranslationError("Unknown error")
        )

        app.dependency_overrides[get_service] = lambda: mock_translation_service

        try:
            response = await async_client.post(
                "/tasks/nllb_translate",
                json={
                    "source_language": "eng",
                    "target_language": "lug",
                    "text": "Hello",
                },
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 500
        finally:
            app.dependency_overrides.pop(get_service, None)


class TestSupportedLanguages:
    """Tests for all supported language codes."""

    @pytest.fixture
    def mock_translation_service(self) -> MagicMock:
        """Create a mock TranslationService for testing."""
        mock = MagicMock()
        mock.translate = AsyncMock(
            return_value=TranslationResult(
                translated_text="Translated text",
                source_language="eng",
                target_language="lug",
                status="COMPLETED",
                raw_response={
                    "id": "job-123",
                    "status": "COMPLETED",
                    "output": {"translated_text": "Translated text"},
                },
            )
        )
        mock.validate_and_parse_response = MagicMock(
            return_value=MagicMock(
                model_dump=MagicMock(
                    return_value={
                        "id": "job-123",
                        "status": "COMPLETED",
                        "output": {"translated_text": "Translated text"},
                    }
                )
            )
        )
        return mock

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "source_lang,target_lang",
        [
            ("eng", "lug"),  # English to Luganda
            ("eng", "ach"),  # English to Acholi
            ("eng", "teo"),  # English to Ateso
            ("eng", "lgg"),  # English to Lugbara
            ("eng", "nyn"),  # English to Runyankole
            ("lug", "eng"),  # Luganda to English
            ("ach", "eng"),  # Acholi to English
            ("teo", "eng"),  # Ateso to English
            ("lgg", "eng"),  # Lugbara to English
            ("nyn", "eng"),  # Runyankole to English
        ],
    )
    async def test_supported_language_pairs(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_translation_service: MagicMock,
        source_lang: str,
        target_lang: str,
    ) -> None:
        """Test that all supported language pairs are accepted."""
        app.dependency_overrides[get_service] = lambda: mock_translation_service

        try:
            response = await async_client.post(
                "/tasks/nllb_translate",
                json={
                    "source_language": source_lang,
                    "target_language": target_lang,
                    "text": "Hello world",
                },
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 200
        finally:
            app.dependency_overrides.pop(get_service, None)


class TestFallbackResponse:
    """Tests for fallback response when raw_response is missing."""

    @pytest.fixture
    def mock_translation_service(self) -> MagicMock:
        """Create a mock TranslationService for testing."""
        mock = MagicMock()
        return mock

    @pytest.mark.asyncio
    async def test_fallback_response_without_raw_response(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_translation_service: MagicMock,
    ) -> None:
        """Test that fallback response is returned when raw_response is None."""
        # Create result without raw_response
        result = TranslationResult(
            translated_text="Oli otya?",
            source_language="eng",
            target_language="lug",
            status="COMPLETED",
            job_id="job-123",
            raw_response=None,  # No raw response
        )

        mock_translation_service.translate = AsyncMock(return_value=result)

        app.dependency_overrides[get_service] = lambda: mock_translation_service

        try:
            response = await async_client.post(
                "/tasks/nllb_translate",
                json={
                    "source_language": "eng",
                    "target_language": "lug",
                    "text": "How are you?",
                },
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "COMPLETED"
            assert data["output"]["translated_text"] == "Oli otya?"
            assert data["output"]["source_language"] == "eng"
            assert data["output"]["target_language"] == "lug"
        finally:
            app.dependency_overrides.pop(get_service, None)
