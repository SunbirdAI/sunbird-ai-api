"""Integration tests for POST /tasks/audio/speech."""

from datetime import datetime
from typing import Dict
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.api import app
from app.deps import get_speech_service
from app.services.speech_service import SpeechResult


@pytest.fixture(autouse=True)
def stub_feedback(monkeypatch):
    async def noop_save(*args, **kwargs):
        return None

    import app.utils.feedback as feedback_module

    monkeypatch.setattr(feedback_module, "save_api_inference", noop_save, raising=False)
    import app.routers.audio as audio_module

    monkeypatch.setattr(audio_module, "save_api_inference", noop_save, raising=False)
    yield


@pytest.fixture
def fake_speech():
    facade = MagicMock()
    facade.validate_request = MagicMock(return_value=None)
    facade.synthesize = AsyncMock(
        return_value=SpeechResult(
            audio_url="https://x/a.wav",
            model="orpheus-3b-tts",
            platform="modal",
            voice="salt_lug_0001",
            audio_url_expires_at=datetime(2026, 12, 1),
            sample_rate=24000,
            duration_seconds=2.5,
            gcs_object="orpheus_tts/a.wav",
            timings_ms={"total_ms": 16.0},
        )
    )
    app.dependency_overrides[get_speech_service] = lambda: facade
    yield facade
    app.dependency_overrides.pop(get_speech_service, None)


async def test_speech_url_mode_returns_200(
    authenticated_client: AsyncClient, fake_speech, test_user: Dict
):
    resp = await authenticated_client.post(
        "/tasks/audio/speech",
        json={"text": "hello", "model": "orpheus-3b-tts", "platform": "modal"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["audio_url"] == "https://x/a.wav"
    assert body["model"] == "orpheus-3b-tts"
    assert body["request_id"]
    fake_speech.validate_request.assert_called_once()
    fake_speech.synthesize.assert_awaited_once()


async def test_speech_requires_auth(async_client: AsyncClient):
    resp = await async_client.post("/tasks/audio/speech", json={"text": "hello"})
    assert resp.status_code == 401


async def test_speech_invalid_combo_returns_400(
    authenticated_client: AsyncClient, test_user: Dict
):
    """Real facade (no override) rejects orpheus on runpod with 400."""
    resp = await authenticated_client.post(
        "/tasks/audio/speech",
        json={"text": "hello", "model": "orpheus-3b-tts", "platform": "runpod"},
    )
    assert resp.status_code == 400


async def test_speech_stream_mode_returns_wav(
    authenticated_client: AsyncClient, test_user: Dict
):
    """spark-tts + modal + response_mode=stream returns streamed audio/wav."""
    from app.deps import get_tts_service

    async def fake_stream(text, speaker_id, chunk_size=8192):
        yield b"RIFF"
        yield b"DATA"

    fake_tts = MagicMock()
    fake_tts.generate_audio_stream = fake_stream
    app.dependency_overrides[get_tts_service] = lambda: fake_tts
    try:
        resp = await authenticated_client.post(
            "/tasks/audio/speech",
            json={
                "text": "hi",
                "model": "spark-tts",
                "platform": "modal",
                "response_mode": "stream",
            },
        )
    finally:
        app.dependency_overrides.pop(get_tts_service, None)

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("audio/wav")
    assert resp.content == b"RIFFDATA"


async def test_openapi_marks_legacy_tts_deprecated(async_client: AsyncClient):
    resp = await async_client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    for path in [
        "/tasks/modal/tts",
        "/tasks/runpod/tts",
        "/tasks/modal/orpheus/tts",
        "/tasks/tts",
    ]:
        assert paths[path]["post"].get("deprecated") is True, path


async def test_legacy_runpod_tts_has_deprecation_headers(
    authenticated_client: AsyncClient, test_user: Dict, monkeypatch
):
    """/tasks/runpod/tts should carry RFC-8594 headers and still return 200."""
    from app.services.runpod_tts_service import RunpodSparkTTSService

    async def fake_synth(self, **kwargs):
        return {
            "audio_url": "https://r/a.mp3",
            "blob": "tts/a.mp3",
            "sample_rate": 16000,
        }

    monkeypatch.setattr(RunpodSparkTTSService, "synthesize", fake_synth)

    async def noop_save(*args, **kwargs):
        return None

    import app.routers.runpod_tts as rp

    monkeypatch.setattr(rp, "save_api_inference", noop_save, raising=False)

    resp = await authenticated_client.post(
        "/tasks/runpod/tts",
        json={"text": "hello", "speaker_id": 248},
    )
    assert resp.status_code == 200
    assert resp.headers.get("Deprecation") == "true"
    assert "Sunset" in resp.headers
    assert 'rel="successor-version"' in resp.headers.get("Link", "")


async def test_legacy_modal_tts_url_mode_has_deprecation_headers(
    authenticated_client: AsyncClient, test_user: Dict, monkeypatch
):
    """/tasks/modal/tts url mode carries RFC-8594 headers (model-return path)."""
    from app.deps import get_legacy_storage_service
    from app.services.tts_service import get_tts_service

    tts = MagicMock()
    tts.generate_audio = AsyncMock(return_value=b"WAVDATA")
    tts.estimate_duration = MagicMock(return_value=1.0)
    storage = MagicMock()
    storage.generate_file_name = MagicMock(return_value="f.wav")
    storage.upload_audio_async = AsyncMock(return_value="blob")
    storage.generate_signed_url = MagicMock(
        return_value=("https://s/f.wav", datetime(2026, 12, 1))
    )

    async def noop_save(*args, **kwargs):
        return None

    import app.routers.tts as tts_module

    monkeypatch.setattr(tts_module, "save_api_inference", noop_save, raising=False)

    app.dependency_overrides[get_tts_service] = lambda: tts
    app.dependency_overrides[get_legacy_storage_service] = lambda: storage
    try:
        resp = await authenticated_client.post("/tasks/modal/tts", json={"text": "hi"})
    finally:
        app.dependency_overrides.pop(get_tts_service, None)
        app.dependency_overrides.pop(get_legacy_storage_service, None)

    assert resp.status_code == 200
    assert resp.headers.get("Deprecation") == "true"
    assert "Sunset" in resp.headers
    assert 'rel="successor-version"' in resp.headers.get("Link", "")


@pytest.mark.real_quota
async def test_speech_quota_exceeded_returns_429(
    authenticated_client: AsyncClient, fake_speech, test_user: Dict, monkeypatch
):
    """When the quota is exhausted, the unified speech endpoint returns 429."""
    from app.services.quota_service import QuotaResult, QuotaService

    async def deny(self, db, user):
        return QuotaResult(allowed=False, scope="day", retry_after_seconds=60)

    monkeypatch.setattr(QuotaService, "check_and_consume", deny)
    resp = await authenticated_client.post(
        "/tasks/audio/speech",
        json={"text": "hi", "model": "orpheus-3b-tts", "platform": "modal"},
    )
    assert resp.status_code == 429


async def test_speech_both_mode_returns_sse(
    authenticated_client: AsyncClient, test_user: Dict, monkeypatch
):
    """spark-tts + modal + response_mode=both returns an SSE (event-stream)."""
    from app.deps import get_legacy_storage_service
    from app.services.tts_service import get_tts_service

    async def fake_stream(text, speaker_id, chunk_size=8192):
        yield b"RIFF"
        yield b"DATA"

    fake_tts = MagicMock()
    fake_tts.generate_audio_stream = fake_stream
    storage = MagicMock()
    storage.generate_file_name = MagicMock(return_value="f.wav")
    storage.upload_audio_async = AsyncMock(return_value="blob")
    storage.generate_signed_url = MagicMock(
        return_value=("https://s/f.wav", datetime(2026, 12, 1))
    )

    app.dependency_overrides[get_tts_service] = lambda: fake_tts
    app.dependency_overrides[get_legacy_storage_service] = lambda: storage
    try:
        resp = await authenticated_client.post(
            "/tasks/audio/speech",
            json={
                "text": "hi",
                "model": "spark-tts",
                "platform": "modal",
                "response_mode": "both",
            },
        )
    finally:
        app.dependency_overrides.pop(get_tts_service, None)
        app.dependency_overrides.pop(get_legacy_storage_service, None)

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")


# ---------------------------------------------------------------------------
# GET /tasks/audio/speech/url (unified signed-URL refresh) + legacy deprecation
# ---------------------------------------------------------------------------


async def test_refresh_speech_url_success(
    authenticated_client: AsyncClient, test_user: Dict
):
    from app.deps import get_legacy_storage_service

    storage = MagicMock()
    storage.get_signed_url_for_file = MagicMock(
        return_value=(
            "https://storage.googleapis.com/signed/abc.wav",
            datetime(2026, 12, 1),
        )
    )
    app.dependency_overrides[get_legacy_storage_service] = lambda: storage
    try:
        resp = await authenticated_client.get(
            "/tasks/audio/speech/url",
            params={"gcs_object": "orpheus_tts/2026-06-03/abc.wav"},
        )
    finally:
        app.dependency_overrides.pop(get_legacy_storage_service, None)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["audio_url"] == "https://storage.googleapis.com/signed/abc.wav"
    assert body["gcs_object"] == "orpheus_tts/2026-06-03/abc.wav"
    assert "audio_url_expires_at" in body
    storage.get_signed_url_for_file.assert_called_once_with(
        "orpheus_tts/2026-06-03/abc.wav"
    )


async def test_refresh_speech_url_not_found_returns_404(
    authenticated_client: AsyncClient, test_user: Dict
):
    from app.deps import get_legacy_storage_service

    storage = MagicMock()
    storage.get_signed_url_for_file = MagicMock(side_effect=Exception("nope"))
    app.dependency_overrides[get_legacy_storage_service] = lambda: storage
    try:
        resp = await authenticated_client.get(
            "/tasks/audio/speech/url", params={"gcs_object": "missing.wav"}
        )
    finally:
        app.dependency_overrides.pop(get_legacy_storage_service, None)

    assert resp.status_code == 404


async def test_refresh_speech_url_requires_gcs_object(
    authenticated_client: AsyncClient, test_user: Dict
):
    resp = await authenticated_client.get("/tasks/audio/speech/url")
    assert resp.status_code == 422


async def test_refresh_speech_url_requires_auth(async_client: AsyncClient):
    resp = await async_client.get(
        "/tasks/audio/speech/url", params={"gcs_object": "abc.wav"}
    )
    assert resp.status_code == 401


async def test_legacy_refresh_url_deprecated_with_headers(
    authenticated_client: AsyncClient, test_user: Dict
):
    """Old /tasks/modal/tts/refresh-url is deprecated + points at the successor."""
    from app.deps import get_legacy_storage_service

    storage = MagicMock()
    storage.get_signed_url_for_file = MagicMock(
        return_value=("https://s/abc.wav", datetime(2026, 12, 1))
    )
    app.dependency_overrides[get_legacy_storage_service] = lambda: storage
    try:
        resp = await authenticated_client.get(
            "/tasks/modal/tts/refresh-url", params={"file_name": "abc.wav"}
        )
    finally:
        app.dependency_overrides.pop(get_legacy_storage_service, None)

    assert resp.status_code == 200, resp.text
    assert resp.headers.get("Deprecation") == "true"
    assert "Sunset" in resp.headers
    assert "/tasks/audio/speech/url" in resp.headers.get("Link", "")


async def test_openapi_refresh_url_tags(async_client: AsyncClient):
    paths = (await async_client.get("/openapi.json")).json()["paths"]
    assert paths["/tasks/audio/speech/url"]["get"]["tags"] == [
        "Text-to-Speech (Unified)"
    ]
    legacy = paths["/tasks/modal/tts/refresh-url"]["get"]
    assert legacy.get("deprecated") is True
    assert legacy["tags"] == ["legacy/deprecated"]
