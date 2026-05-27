"""
Tests for the Orpheus TTS Router.

Covers the four /tasks/modal/orpheus/* endpoints by overriding the
``get_orpheus_tts_service`` dependency with a MagicMock. Also exercises
``SpeakersCache`` directly to verify its fail-open + TTL-refresh behavior.
"""

from __future__ import annotations

import datetime as dt
from typing import Dict
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.api import app
from app.core.exceptions import BadRequestError, ExternalServiceError
from app.services.orpheus_tts_service import (
    BatchItemResult,
    BatchResult,
    SpeakerCatalog,
    SpeakersCache,
    SynthesizeResult,
    get_orpheus_tts_service,
)


@pytest.fixture
def sample_catalog() -> SpeakerCatalog:
    return SpeakerCatalog.from_payload(
        {
            "default": "salt_lug_0001",
            "by_language": {
                "lug": ["salt_lug_0001", "salt_lug_0002"],
                "eng": ["salt_eng_0001"],
            },
        }
    )


@pytest.fixture
def sample_synth_result() -> SynthesizeResult:
    return SynthesizeResult(
        audio_url="https://storage.googleapis.com/signed-url",
        audio_url_expires_at=dt.datetime(2026, 5, 27, 12, 30, tzinfo=dt.timezone.utc),
        speaker_id="salt_lug_0001",
        language="lug",
        sample_rate=24000,
        duration_seconds=2.45,
        chunks=3,
        audio_size_bytes=117648,
        gcs_object="orpheus_tts/2026-05-27/abc123.wav",
        inference_ms=1820.5,
        upload_ms=234.1,
        signed_url_ms=12.0,
        total_ms=2095.6,
    )


@pytest.fixture
def mock_orpheus_service(sample_catalog, sample_synth_result) -> MagicMock:
    mock = MagicMock()
    mock.list_speakers = AsyncMock(return_value=sample_catalog)
    mock.speakers_for_language = AsyncMock(
        side_effect=lambda lang: sample_catalog.by_language[lang]
    )
    mock.synthesize = AsyncMock(return_value=sample_synth_result)
    return mock


class TestSpeakersEndpoints:
    """GET /speakers and GET /speakers/{language}."""

    async def test_list_speakers_requires_auth(self, async_client: AsyncClient) -> None:
        response = await async_client.get("/tasks/modal/orpheus/speakers")
        assert response.status_code == 401

    async def test_list_speakers_success(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_orpheus_service: MagicMock,
        sample_catalog: SpeakerCatalog,
    ) -> None:
        app.dependency_overrides[get_orpheus_tts_service] = lambda: mock_orpheus_service
        try:
            response = await async_client.get(
                "/tasks/modal/orpheus/speakers",
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )
        finally:
            app.dependency_overrides.pop(get_orpheus_tts_service, None)

        assert response.status_code == 200
        data = response.json()
        assert data["default"] == sample_catalog.default
        assert data["by_language"] == sample_catalog.by_language
        # Computed fields
        assert data["total"] == 3
        assert sorted(data["languages"]) == ["eng", "lug"]

    async def test_speakers_for_language_success(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_orpheus_service: MagicMock,
    ) -> None:
        app.dependency_overrides[get_orpheus_tts_service] = lambda: mock_orpheus_service
        try:
            response = await async_client.get(
                "/tasks/modal/orpheus/speakers/lug",
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )
        finally:
            app.dependency_overrides.pop(get_orpheus_tts_service, None)

        assert response.status_code == 200
        data = response.json()
        assert data["language"] == "lug"
        assert data["speakers"] == ["salt_lug_0001", "salt_lug_0002"]
        assert data["count"] == 2

    async def test_speakers_for_language_unknown(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_orpheus_service: MagicMock,
    ) -> None:
        mock_orpheus_service.speakers_for_language = AsyncMock(
            side_effect=BadRequestError(
                message="language 'xxx' not supported; supported: ['eng', 'lug']"
            )
        )

        app.dependency_overrides[get_orpheus_tts_service] = lambda: mock_orpheus_service
        try:
            response = await async_client.get(
                "/tasks/modal/orpheus/speakers/xxx",
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )
        finally:
            app.dependency_overrides.pop(get_orpheus_tts_service, None)

        assert response.status_code == 400


class TestTTSEndpoint:
    """POST /tasks/modal/orpheus/tts."""

    async def test_tts_requires_auth(self, async_client: AsyncClient) -> None:
        response = await async_client.post(
            "/tasks/modal/orpheus/tts",
            json={"text": "Mwattu, oli otya?", "speaker_id": "salt_lug_0001"},
        )
        assert response.status_code == 401

    async def test_tts_success(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_orpheus_service: MagicMock,
        sample_synth_result: SynthesizeResult,
    ) -> None:
        app.dependency_overrides[get_orpheus_tts_service] = lambda: mock_orpheus_service
        try:
            response = await async_client.post(
                "/tasks/modal/orpheus/tts",
                headers={"Authorization": f"Bearer {test_user['token']}"},
                json={
                    "text": "Mwattu, oli otya?",
                    "speaker_id": "salt_lug_0001",
                    "language": "lug",
                },
            )
        finally:
            app.dependency_overrides.pop(get_orpheus_tts_service, None)

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["audio_url"] == sample_synth_result.audio_url
        assert data["speaker_id"] == "salt_lug_0001"
        assert data["language"] == "lug"
        assert data["sample_rate"] == 24000
        assert data["gcs_object"] == sample_synth_result.gcs_object
        assert "request_id" in data and len(data["request_id"]) > 0
        timings = data["timings_ms"]
        assert timings["inference_ms"] == pytest.approx(1820.5)
        assert timings["total_ms"] == pytest.approx(2095.6)

        # Service was called with the request parameters
        mock_orpheus_service.synthesize.assert_awaited_once()
        kwargs = mock_orpheus_service.synthesize.await_args.kwargs
        assert kwargs["text"] == "Mwattu, oli otya?"
        assert kwargs["speaker_id"] == "salt_lug_0001"
        assert kwargs["language"] == "lug"

    async def test_tts_invalid_speaker(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_orpheus_service: MagicMock,
    ) -> None:
        mock_orpheus_service.synthesize = AsyncMock(
            side_effect=BadRequestError(
                message="speaker_id 'bogus' not found; see /speakers"
            )
        )

        app.dependency_overrides[get_orpheus_tts_service] = lambda: mock_orpheus_service
        try:
            response = await async_client.post(
                "/tasks/modal/orpheus/tts",
                headers={"Authorization": f"Bearer {test_user['token']}"},
                json={"text": "hi", "speaker_id": "bogus"},
            )
        finally:
            app.dependency_overrides.pop(get_orpheus_tts_service, None)

        assert response.status_code == 400
        body = response.json()
        assert "speaker_id" in body["message"]

    async def test_tts_validation_error_on_empty_text(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_orpheus_service: MagicMock,
    ) -> None:
        app.dependency_overrides[get_orpheus_tts_service] = lambda: mock_orpheus_service
        try:
            response = await async_client.post(
                "/tasks/modal/orpheus/tts",
                headers={"Authorization": f"Bearer {test_user['token']}"},
                json={"text": "", "speaker_id": "salt_lug_0001"},
            )
        finally:
            app.dependency_overrides.pop(get_orpheus_tts_service, None)

        assert response.status_code == 422


class TestTTSBatchEndpoint:
    """POST /tasks/modal/orpheus/tts/batch."""

    @pytest.fixture
    def sample_batch_ok(self) -> BatchResult:
        expires_at = dt.datetime(2026, 5, 27, 12, 30, tzinfo=dt.timezone.utc)
        return BatchResult(
            results=[
                BatchItemResult(
                    index=0,
                    status="ok",
                    speaker_id="salt_lug_0001",
                    audio_url="https://storage.googleapis.com/u1",
                    audio_url_expires_at=expires_at,
                    language="lug",
                    sample_rate=24000,
                    duration_seconds=2.0,
                    audio_size_bytes=1000,
                    gcs_object="orpheus_tts/2026-05-27/u1.wav",
                ),
                BatchItemResult(
                    index=1,
                    status="error",
                    speaker_id="salt_eng_0001",
                    error_code="storage_unavailable",
                    error_detail="GCS upload failed",
                ),
            ],
            inference_ms=1200.0,
            upload_ms=300.0,
            total_ms=1500.0,
        )

    async def test_batch_mixed_results(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_orpheus_service: MagicMock,
        sample_batch_ok: BatchResult,
    ) -> None:
        mock_orpheus_service.synthesize_batch = AsyncMock(return_value=sample_batch_ok)

        app.dependency_overrides[get_orpheus_tts_service] = lambda: mock_orpheus_service
        try:
            response = await async_client.post(
                "/tasks/modal/orpheus/tts/batch",
                headers={"Authorization": f"Bearer {test_user['token']}"},
                json={
                    "items": [
                        {"text": "hello", "speaker_id": "salt_lug_0001"},
                        {"text": "world", "speaker_id": "salt_eng_0001"},
                    ]
                },
            )
        finally:
            app.dependency_overrides.pop(get_orpheus_tts_service, None)

        assert response.status_code == 200, response.text
        data = response.json()
        assert len(data["results"]) == 2
        ok, err = data["results"]
        assert ok["status"] == "ok"
        assert ok["audio_url"] == "https://storage.googleapis.com/u1"
        assert err["status"] == "error"
        assert err["error_code"] == "storage_unavailable"
        assert data["timings_ms"]["total_ms"] == pytest.approx(1500.0)

    async def test_batch_all_failed_returns_502(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        mock_orpheus_service: MagicMock,
    ) -> None:
        mock_orpheus_service.synthesize_batch = AsyncMock(
            side_effect=ExternalServiceError(
                service_name="GCS",
                message="all 2 batch items failed during upload",
            )
        )

        app.dependency_overrides[get_orpheus_tts_service] = lambda: mock_orpheus_service
        try:
            response = await async_client.post(
                "/tasks/modal/orpheus/tts/batch",
                headers={"Authorization": f"Bearer {test_user['token']}"},
                json={
                    "items": [
                        {"text": "a", "speaker_id": "salt_lug_0001"},
                        {"text": "b", "speaker_id": "salt_eng_0001"},
                    ]
                },
            )
        finally:
            app.dependency_overrides.pop(get_orpheus_tts_service, None)

        assert response.status_code == 502
        body = response.json()
        assert "failed during upload" in body["message"]

    async def test_batch_requires_auth(self, async_client: AsyncClient) -> None:
        response = await async_client.post(
            "/tasks/modal/orpheus/tts/batch",
            json={"items": [{"text": "hello", "speaker_id": "salt_lug_0001"}]},
        )
        assert response.status_code == 401


class TestSpeakersCache:
    """Unit tests for the TTL cache + fail-open validation."""

    @pytest.fixture
    def modal_client(self) -> MagicMock:
        mock = MagicMock()
        mock.speakers = AsyncMock(
            return_value={
                "default": "salt_lug_0001",
                "by_language": {
                    "lug": ["salt_lug_0001"],
                    "eng": ["salt_eng_0001"],
                },
            }
        )
        return mock

    async def test_try_warm_populates_cache(self, modal_client: MagicMock) -> None:
        cache = SpeakersCache(modal=modal_client, ttl_seconds=60)
        assert not cache.is_warm
        await cache.try_warm()
        assert cache.is_warm
        modal_client.speakers.assert_awaited_once()

    async def test_try_warm_swallows_errors(self) -> None:
        modal = MagicMock()
        modal.speakers = AsyncMock(side_effect=RuntimeError("modal down"))
        cache = SpeakersCache(modal=modal, ttl_seconds=60)
        # Must not raise
        await cache.try_warm()
        assert not cache.is_warm

    async def test_validate_speaker_fails_open_when_cold(
        self, modal_client: MagicMock
    ) -> None:
        cache = SpeakersCache(modal=modal_client, ttl_seconds=60)
        # Cache is cold; should not raise even for an unknown speaker.
        await cache.validate_speaker("unknown_speaker", language=None)
        modal_client.speakers.assert_not_awaited()

    async def test_validate_speaker_rejects_unknown_speaker(
        self, modal_client: MagicMock
    ) -> None:
        cache = SpeakersCache(modal=modal_client, ttl_seconds=60)
        await cache.try_warm()
        with pytest.raises(BadRequestError) as exc:
            await cache.validate_speaker("bogus", language=None)
        assert "bogus" in exc.value.message

    async def test_validate_speaker_rejects_wrong_language(
        self, modal_client: MagicMock
    ) -> None:
        cache = SpeakersCache(modal=modal_client, ttl_seconds=60)
        await cache.try_warm()
        with pytest.raises(BadRequestError) as exc:
            await cache.validate_speaker("salt_lug_0001", language="eng")
        assert "lug" in exc.value.message and "eng" in exc.value.message

    async def test_validate_speaker_rejects_unknown_language(
        self, modal_client: MagicMock
    ) -> None:
        cache = SpeakersCache(modal=modal_client, ttl_seconds=60)
        await cache.try_warm()
        with pytest.raises(BadRequestError) as exc:
            await cache.validate_speaker("salt_lug_0001", language="xxx")
        assert "xxx" in exc.value.message

    async def test_language_for_returns_none_when_cold(
        self, modal_client: MagicMock
    ) -> None:
        cache = SpeakersCache(modal=modal_client, ttl_seconds=60)
        assert await cache.language_for("salt_lug_0001") is None

    async def test_language_for_resolves_after_warm(
        self, modal_client: MagicMock
    ) -> None:
        cache = SpeakersCache(modal=modal_client, ttl_seconds=60)
        await cache.try_warm()
        assert await cache.language_for("salt_lug_0001") == "lug"
        assert await cache.language_for("salt_eng_0001") == "eng"
        assert await cache.language_for("nonexistent") is None
