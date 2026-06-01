"""Integration tests for the unified POST /tasks/audio/transcriptions endpoint."""

import io
from typing import Dict
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.api import app
from app.deps import get_transcription_service
from app.services.stt_service import TranscriptionResult


@pytest.fixture(autouse=True)
def stub_feedback(monkeypatch):
    """Prevent the BackgroundTasks feedback save from making network calls."""

    async def noop_save(*args, **kwargs):
        return None

    import app.utils.feedback as feedback_module

    monkeypatch.setattr(feedback_module, "save_api_inference", noop_save, raising=False)
    import app.routers.stt as stt_module

    monkeypatch.setattr(stt_module, "save_api_inference", noop_save, raising=False)
    yield


@pytest.fixture
def fake_facade():
    """Override the facade dependency with a mock; restore afterward."""
    facade = MagicMock()
    facade.validate_and_normalize = MagicMock(return_value=(True, True))
    facade.transcribe = AsyncMock(
        return_value=TranscriptionResult(
            transcription="hello world",
            diarization_output={},
            formatted_diarization_output="",
            audio_url="gs://bucket/a.wav",
            blob_name="a.wav",
        )
    )
    app.dependency_overrides[get_transcription_service] = lambda: facade
    yield facade
    app.dependency_overrides.pop(get_transcription_service, None)


def audio_part():
    return {"audio": ("sample.wav", io.BytesIO(b"RIFFfake"), "audio/wav")}


async def test_modal_upload_returns_200(
    authenticated_client: AsyncClient, fake_facade, test_user: Dict
):
    resp = await authenticated_client.post(
        "/tasks/audio/transcriptions",
        data={"language": "lug", "platform": "modal"},
        files=audio_part(),
    )
    assert resp.status_code == 200
    assert resp.json()["audio_transcription"] == "hello world"
    assert resp.json()["audio_transcription_id"] is None
    _, kwargs = fake_facade.transcribe.call_args
    assert kwargs["platform"] == "modal"


async def test_runpod_upload_returns_200(
    authenticated_client: AsyncClient, fake_facade, test_user: Dict
):
    resp = await authenticated_client.post(
        "/tasks/audio/transcriptions",
        data={"language": "lug", "platform": "runpod"},
        files=audio_part(),
    )
    assert resp.status_code == 200
    _, kwargs = fake_facade.transcribe.call_args
    assert kwargs["platform"] == "runpod"
    assert kwargs["whisper"] is True
    assert kwargs["recognise_speakers"] is True


async def test_runpod_gcs_returns_200(
    authenticated_client: AsyncClient, fake_facade, test_user: Dict
):
    resp = await authenticated_client.post(
        "/tasks/audio/transcriptions",
        data={
            "language": "lug",
            "platform": "runpod",
            "gcs_blob_name": "audio/file.wav",
        },
    )
    assert resp.status_code == 200
    _, kwargs = fake_facade.transcribe.call_args
    assert kwargs["gcs_blob_name"] == "audio/file.wav"


async def test_invalid_combo_returns_400(
    authenticated_client: AsyncClient, test_user: Dict
):
    """A real facade should reject modal+gcs with 400 (no override here)."""
    resp = await authenticated_client.post(
        "/tasks/audio/transcriptions",
        data={
            "language": "lug",
            "platform": "modal",
            "gcs_blob_name": "audio/file.wav",
        },
    )
    assert resp.status_code == 400


async def test_requires_authentication(async_client: AsyncClient):
    resp = await async_client.post(
        "/tasks/audio/transcriptions",
        data={"language": "lug", "platform": "modal"},
        files=audio_part(),
    )
    assert resp.status_code == 401


async def test_runpod_upload_persists_and_returns_id(
    authenticated_client: AsyncClient, fake_facade, test_user: Dict
):
    """RunPod non-org transcriptions are saved to the DB and return an id."""
    resp = await authenticated_client.post(
        "/tasks/audio/transcriptions",
        data={"language": "lug", "platform": "runpod"},
        files=audio_part(),
    )
    assert resp.status_code == 200
    assert isinstance(resp.json()["audio_transcription_id"], int)


async def test_runpod_org_does_not_persist(
    authenticated_client: AsyncClient, fake_facade, test_user: Dict
):
    """The org workflow must not persist a transcription (parity with /org/stt)."""
    resp = await authenticated_client.post(
        "/tasks/audio/transcriptions",
        data={"language": "lug", "platform": "runpod", "org": "true"},
        files=audio_part(),
    )
    assert resp.status_code == 200
    assert resp.json()["audio_transcription_id"] is None
