"""
Tests for Translation Router Module (Sunflower-backed).

POST /tasks/translate routes through TranslationService.translate_via_sunflower
(Sunflower model via InferenceService). These tests mock at the service layer
and verify language resolution, response shape backward compatibility, and
error mapping.
"""

from typing import Dict
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.api import app
from app.services.inference_service import InferenceTimeoutError, ModelLoadingError
from app.services.translation_service import TranslationResult, get_translation_service
from app.utils.languages import ResolvedLanguage


def _make_result(
    translated_text="Oli otya?",
    source_language="eng",
    target_language="lug",
):
    return TranslationResult(
        translated_text=translated_text,
        source_language=source_language,
        target_language=target_language,
        status="COMPLETED",
        job_id="trans-abc123",
        raw_response=None,
    )


@pytest.fixture
def mock_translation_service() -> MagicMock:
    mock = MagicMock()
    mock.translate_via_sunflower = AsyncMock(return_value=_make_result())
    return mock


@pytest.fixture
def override_service(mock_translation_service):
    app.dependency_overrides[get_translation_service] = lambda: mock_translation_service
    yield mock_translation_service
    app.dependency_overrides.pop(get_translation_service, None)


def _auth(test_user: Dict) -> Dict[str, str]:
    return {"Authorization": f"Bearer {test_user['token']}"}


class TestTranslateEndpoint:
    """Happy-path and language-resolution tests for POST /tasks/translate."""

    async def test_legacy_payload_with_codes(
        self, async_client: AsyncClient, test_user: Dict, override_service
    ):
        response = await async_client.post(
            "/tasks/translate",
            json={
                "source_language": "eng",
                "target_language": "lug",
                "text": "How are you?",
            },
            headers=_auth(test_user),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "COMPLETED"
        assert data["id"] == "trans-abc123"
        assert data["output"]["translated_text"] == "Oli otya?"
        assert data["output"]["source_language"] == "eng"
        assert data["output"]["target_language"] == "lug"
        override_service.translate_via_sunflower.assert_awaited_once_with(
            text="How are you?",
            target_language=ResolvedLanguage(code="lug", name="Luganda"),
            source_language=ResolvedLanguage(code="eng", name="English"),
        )

    async def test_full_name_payload(
        self, async_client: AsyncClient, test_user: Dict, override_service
    ):
        response = await async_client.post(
            "/tasks/translate",
            json={
                "source_language": "English",
                "target_language": "Luganda",
                "text": "How are you?",
            },
            headers=_auth(test_user),
        )

        assert response.status_code == 200
        override_service.translate_via_sunflower.assert_awaited_once_with(
            text="How are you?",
            target_language=ResolvedLanguage(code="lug", name="Luganda"),
            source_language=ResolvedLanguage(code="eng", name="English"),
        )

    async def test_alias_name_resolves(
        self, async_client: AsyncClient, test_user: Dict, override_service
    ):
        response = await async_client.post(
            "/tasks/translate",
            json={
                "source_language": "eng",
                "target_language": "Runyankore",
                "text": "Hello",
            },
            headers=_auth(test_user),
        )

        assert response.status_code == 200
        call_kwargs = override_service.translate_via_sunflower.await_args.kwargs
        assert call_kwargs["target_language"] == ResolvedLanguage(
            code="nyn", name="Runyankole"
        )

    async def test_omitted_source_language(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        override_service,
        mock_translation_service,
    ):
        mock_translation_service.translate_via_sunflower = AsyncMock(
            return_value=_make_result(source_language=None)
        )

        response = await async_client.post(
            "/tasks/translate",
            json={"target_language": "lug", "text": "How are you?"},
            headers=_auth(test_user),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["output"]["source_language"] is None
        call_kwargs = mock_translation_service.translate_via_sunflower.await_args.kwargs
        assert call_kwargs["source_language"] is None

    @pytest.mark.parametrize(
        "source_lang,target_lang",
        [
            ("eng", "lug"),
            ("eng", "ach"),
            ("eng", "teo"),
            ("eng", "lgg"),
            ("eng", "nyn"),
            ("lug", "eng"),
            ("ach", "eng"),
            ("teo", "eng"),
            ("lgg", "eng"),
            ("nyn", "eng"),
        ],
    )
    async def test_legacy_language_pairs_still_accepted(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        override_service,
        source_lang: str,
        target_lang: str,
    ):
        response = await async_client.post(
            "/tasks/translate",
            json={
                "source_language": source_lang,
                "target_language": target_lang,
                "text": "Hello world",
            },
            headers=_auth(test_user),
        )

        assert response.status_code == 200

    async def test_new_sunflower_pair_accepted(
        self, async_client: AsyncClient, test_user: Dict, override_service
    ):
        # Any-to-any: Swahili -> Kinyarwanda was impossible with NLLB.
        response = await async_client.post(
            "/tasks/translate",
            json={
                "source_language": "swa",
                "target_language": "kin",
                "text": "Habari",
            },
            headers=_auth(test_user),
        )

        assert response.status_code == 200

    async def test_feedback_logged_with_sunflower_model(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        override_service,
        monkeypatch,
    ):
        calls = []

        async def record_feedback(*args, **kwargs):
            calls.append(kwargs)

        monkeypatch.setattr(
            "app.routers.translation.save_api_inference", record_feedback
        )

        response = await async_client.post(
            "/tasks/translate",
            json={
                "source_language": "eng",
                "target_language": "lug",
                "text": "Hello",
            },
            headers=_auth(test_user),
        )

        assert response.status_code == 200
        assert len(calls) == 1
        assert calls[0]["model_type"] == "Sunbird/Sunflower-14B"
        assert calls[0]["inference_type"] == "translation"


class TestTranslateValidation:
    """400/422 validation tests."""

    async def test_unsupported_target_code(
        self, async_client: AsyncClient, test_user: Dict, override_service
    ):
        response = await async_client.post(
            "/tasks/translate",
            json={"target_language": "fra", "text": "Hello"},
            headers=_auth(test_user),
        )

        assert response.status_code == 400
        message = response.json()["message"]
        assert "fra" in message
        assert "Supported languages" in message
        override_service.translate_via_sunflower.assert_not_awaited()

    async def test_unsupported_source_name(
        self, async_client: AsyncClient, test_user: Dict, override_service
    ):
        response = await async_client.post(
            "/tasks/translate",
            json={
                "source_language": "French",
                "target_language": "lug",
                "text": "Bonjour",
            },
            headers=_auth(test_user),
        )

        assert response.status_code == 400
        override_service.translate_via_sunflower.assert_not_awaited()

    async def test_source_equals_target_code_vs_name(
        self, async_client: AsyncClient, test_user: Dict, override_service
    ):
        response = await async_client.post(
            "/tasks/translate",
            json={
                "source_language": "lug",
                "target_language": "Luganda",
                "text": "Hello",
            },
            headers=_auth(test_user),
        )

        assert response.status_code == 400
        assert "different" in response.json()["message"].lower()
        override_service.translate_via_sunflower.assert_not_awaited()

    async def test_without_auth(self, async_client: AsyncClient):
        response = await async_client.post(
            "/tasks/translate",
            json={"target_language": "lug", "text": "Hello"},
        )
        assert response.status_code == 401

    async def test_missing_target_language(
        self, async_client: AsyncClient, test_user: Dict
    ):
        response = await async_client.post(
            "/tasks/translate",
            json={"text": "Hello"},
            headers=_auth(test_user),
        )
        assert response.status_code == 422

    async def test_empty_text(self, async_client: AsyncClient, test_user: Dict):
        response = await async_client.post(
            "/tasks/translate",
            json={"target_language": "lug", "text": ""},
            headers=_auth(test_user),
        )
        assert response.status_code == 422

    async def test_whitespace_only_text(
        self, async_client: AsyncClient, test_user: Dict
    ):
        response = await async_client.post(
            "/tasks/translate",
            json={"target_language": "lug", "text": "   "},
            headers=_auth(test_user),
        )
        assert response.status_code == 422


class TestTranslateErrorMapping:
    """Inference error -> HTTP status mapping."""

    async def _post(self, async_client, test_user):
        return await async_client.post(
            "/tasks/translate",
            json={
                "source_language": "eng",
                "target_language": "lug",
                "text": "Hello",
            },
            headers=_auth(test_user),
        )

    async def test_model_loading_maps_to_503(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        override_service,
        mock_translation_service,
    ):
        mock_translation_service.translate_via_sunflower = AsyncMock(
            side_effect=ModelLoadingError("loading")
        )
        response = await self._post(async_client, test_user)
        assert response.status_code == 503
        assert "loading" in response.json()["message"].lower()

    async def test_timeout_maps_to_503(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        override_service,
        mock_translation_service,
    ):
        mock_translation_service.translate_via_sunflower = AsyncMock(
            side_effect=InferenceTimeoutError("timeout")
        )
        response = await self._post(async_client, test_user)
        assert response.status_code == 503
        assert "timed out" in response.json()["message"].lower()

    async def test_generic_error_maps_to_502(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        override_service,
        mock_translation_service,
    ):
        mock_translation_service.translate_via_sunflower = AsyncMock(
            side_effect=RuntimeError("boom")
        )
        response = await self._post(async_client, test_user)
        assert response.status_code == 502

    async def test_empty_translation_maps_to_502(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        override_service,
        mock_translation_service,
    ):
        mock_translation_service.translate_via_sunflower = AsyncMock(
            return_value=_make_result(translated_text=None)
        )
        response = await self._post(async_client, test_user)
        assert response.status_code == 502
        assert "empty" in response.json()["message"].lower()
