"""Integration tests for POST /tasks/audio/speech/batch."""

import datetime as dt
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.api import app
from app.core.exceptions import BadRequestError, ExternalServiceError
from app.deps import get_speech_service
from app.services.orpheus_tts_service import BatchItemResult, BatchResult
from app.services.speech_service import SpeechService


def _speech_with_orpheus(orpheus):
    return SpeechService(
        tts_service=MagicMock(),
        orpheus_service=orpheus,
        runpod_spark_service=MagicMock(),
        storage_service=MagicMock(),
    )


@pytest.fixture
def mixed_batch() -> BatchResult:
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


async def test_batch_happy_and_partial(
    authenticated_client: AsyncClient, test_user, mixed_batch
):
    orpheus = MagicMock()
    orpheus.synthesize_batch = AsyncMock(return_value=mixed_batch)
    app.dependency_overrides[get_speech_service] = lambda: _speech_with_orpheus(orpheus)
    try:
        resp = await authenticated_client.post(
            "/tasks/audio/speech/batch",
            json={
                "items": [
                    {"text": "hello"},
                    {"text": "world", "voice": "salt_eng_0001"},
                ]
            },
        )
    finally:
        app.dependency_overrides.pop(get_speech_service, None)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["model"] == "orpheus-3b-tts"
    assert data["platform"] == "modal"
    assert len(data["results"]) == 2
    ok, err = data["results"]
    assert ok["status"] == "ok"
    assert ok["voice"] == "salt_lug_0001"
    assert ok["audio_url"] == "https://storage.googleapis.com/u1"
    assert ok["request_id"] is not None
    assert err["status"] == "error"
    assert err["error_code"] == "storage_unavailable"
    assert err["request_id"] is None
    assert data["timings_ms"]["total_ms"] == pytest.approx(1500.0)


async def test_batch_all_failed_returns_502(
    authenticated_client: AsyncClient, test_user
):
    orpheus = MagicMock()
    orpheus.synthesize_batch = AsyncMock(
        side_effect=ExternalServiceError(
            service_name="GCS", message="all 2 batch items failed during upload"
        )
    )
    app.dependency_overrides[get_speech_service] = lambda: _speech_with_orpheus(orpheus)
    try:
        resp = await authenticated_client.post(
            "/tasks/audio/speech/batch",
            json={"items": [{"text": "a"}, {"text": "b"}]},
        )
    finally:
        app.dependency_overrides.pop(get_speech_service, None)

    assert resp.status_code == 502
    assert "failed during upload" in resp.json()["message"]


async def test_batch_bad_item_returns_400(authenticated_client: AsyncClient, test_user):
    orpheus = MagicMock()
    orpheus.synthesize_batch = AsyncMock(
        side_effect=BadRequestError(message="item index 0: speaker_id 'x' not found")
    )
    app.dependency_overrides[get_speech_service] = lambda: _speech_with_orpheus(orpheus)
    try:
        resp = await authenticated_client.post(
            "/tasks/audio/speech/batch",
            json={"items": [{"text": "a", "voice": "x"}]},
        )
    finally:
        app.dependency_overrides.pop(get_speech_service, None)

    assert resp.status_code == 400


async def test_batch_non_orpheus_model_returns_400(
    authenticated_client: AsyncClient, test_user
):
    orpheus = MagicMock()
    orpheus.synthesize_batch = AsyncMock()
    app.dependency_overrides[get_speech_service] = lambda: _speech_with_orpheus(orpheus)
    try:
        resp = await authenticated_client.post(
            "/tasks/audio/speech/batch",
            json={"model": "spark-tts", "items": [{"text": "a"}]},
        )
    finally:
        app.dependency_overrides.pop(get_speech_service, None)

    assert resp.status_code == 400
    orpheus.synthesize_batch.assert_not_called()


async def test_batch_empty_items_returns_422(
    authenticated_client: AsyncClient, test_user
):
    resp = await authenticated_client.post(
        "/tasks/audio/speech/batch", json={"items": []}
    )
    assert resp.status_code == 422


async def test_batch_requires_auth(async_client: AsyncClient):
    resp = await async_client.post(
        "/tasks/audio/speech/batch", json={"items": [{"text": "a"}]}
    )
    assert resp.status_code == 401


async def test_openapi_marks_legacy_endpoints_deprecated(async_client: AsyncClient):
    resp = await async_client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    for path in [
        "/tasks/modal/tts/stream",
        "/tasks/modal/tts/stream-with-url",
        "/tasks/modal/orpheus/tts/batch",
    ]:
        assert paths[path]["post"].get("deprecated") is True, path


async def test_legacy_orpheus_batch_has_deprecation_headers(
    authenticated_client: AsyncClient, test_user, mixed_batch
):
    """/tasks/modal/orpheus/tts/batch carries RFC-8594 headers to the successor."""
    from app.services.orpheus_tts_service import get_orpheus_tts_service

    orpheus = MagicMock()
    orpheus.synthesize_batch = AsyncMock(return_value=mixed_batch)
    app.dependency_overrides[get_orpheus_tts_service] = lambda: orpheus
    try:
        resp = await authenticated_client.post(
            "/tasks/modal/orpheus/tts/batch",
            json={"items": [{"text": "a", "speaker_id": "salt_lug_0001"}]},
        )
    finally:
        app.dependency_overrides.pop(get_orpheus_tts_service, None)

    assert resp.status_code == 200, resp.text
    assert resp.headers.get("Deprecation") == "true"
    assert "Sunset" in resp.headers
    assert "/tasks/audio/speech/batch" in resp.headers.get("Link", "")
