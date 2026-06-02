"""Integration tests for GET /tasks/voice/speakers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.api import app
from app.deps import get_speech_service
from app.services.speech_service import SpeechService


@pytest.fixture
def speech_with_mock_orpheus():
    """Real SpeechService with a mocked OrpheusTTSService; spark uses real data."""
    orpheus = MagicMock()
    orpheus.list_speakers = AsyncMock(
        return_value=SimpleNamespace(
            default="salt_lug_0001",
            by_language={"lug": ["salt_lug_0001"], "eng": ["salt_eng_0001"]},
        )
    )
    orpheus.speakers_for_language = AsyncMock(return_value=["salt_lug_0001"])
    facade = SpeechService(
        tts_service=MagicMock(),
        orpheus_service=orpheus,
        runpod_spark_service=MagicMock(),
        storage_service=MagicMock(),
    )
    app.dependency_overrides[get_speech_service] = lambda: facade
    yield facade, orpheus
    app.dependency_overrides.pop(get_speech_service, None)


async def test_voice_speakers_orpheus_default(
    authenticated_client: AsyncClient, speech_with_mock_orpheus, test_user
):
    resp = await authenticated_client.get("/tasks/voice/speakers")
    assert resp.status_code == 200
    body = resp.json()
    assert body["default"] == "salt_lug_0001"
    assert set(body["by_language"].keys()) == {"lug", "eng"}
    assert body["total"] == 2
    assert body["languages"] == ["eng", "lug"]


async def test_voice_speakers_orpheus_by_language(
    authenticated_client: AsyncClient, speech_with_mock_orpheus, test_user
):
    resp = await authenticated_client.get("/tasks/voice/speakers?language=lug")
    assert resp.status_code == 200
    body = resp.json()
    assert body["language"] == "lug"
    assert body["speakers"] == ["salt_lug_0001"]
    assert body["count"] == 1


async def test_voice_speakers_spark(
    authenticated_client: AsyncClient, speech_with_mock_orpheus, test_user
):
    resp = await authenticated_client.get("/tasks/voice/speakers?model=spark-tts")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["speakers"]) == 6
    assert {"id", "name", "display_name", "language", "gender"} <= set(
        body["speakers"][0].keys()
    )


async def test_voice_speakers_spark_with_language_400(
    authenticated_client: AsyncClient, speech_with_mock_orpheus, test_user
):
    resp = await authenticated_client.get(
        "/tasks/voice/speakers?model=spark-tts&language=lug"
    )
    assert resp.status_code == 400


async def test_voice_speakers_unknown_orpheus_language_400(
    authenticated_client: AsyncClient, speech_with_mock_orpheus, test_user
):
    from app.core.exceptions import BadRequestError

    _, orpheus = speech_with_mock_orpheus
    orpheus.speakers_for_language = AsyncMock(
        side_effect=BadRequestError(message="unknown language")
    )
    resp = await authenticated_client.get("/tasks/voice/speakers?language=zzz")
    assert resp.status_code == 400


async def test_voice_speakers_requires_auth(async_client: AsyncClient):
    resp = await async_client.get("/tasks/voice/speakers")
    assert resp.status_code == 401
