"""Unit tests for the TTS unified speech facade and helpers."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import (
    BadRequestError,
    ExternalServiceError,
    ServiceUnavailableError,
)
from app.models.enums import SpeakerID
from app.schemas.orpheus_tts import (
    OrpheusLanguageSpeakersResponse,
    OrpheusSpeakersResponse,
)
from app.schemas.speech import SpeechRequest, SpeechResponse, TTSModel, TTSPlatform
from app.schemas.tts import SpeakersListResponse
from app.services.orpheus_tts_service import SynthesizeResult
from app.services.speech_service import SpeechService
from app.utils.deprecation import (
    STT_SUNSET_DATE,
    SUCCESSOR_SPEECH,
    SUNSET_DATE,
    deprecation_headers,
)


def test_speech_successor_and_sunset_constants():
    assert SUCCESSOR_SPEECH == "/tasks/audio/speech"
    # STT alias preserved for Phase 1.
    assert STT_SUNSET_DATE == SUNSET_DATE


def test_deprecation_headers_for_speech():
    headers = deprecation_headers(SUCCESSOR_SPEECH)
    assert headers["Deprecation"] == "true"
    assert headers["Sunset"] == SUNSET_DATE
    assert headers["Link"] == '</tasks/audio/speech>; rel="successor-version"'


def test_speech_request_defaults():
    req = SpeechRequest(text="hello")
    assert req.model is TTSModel.orpheus_3b_tts
    assert req.platform is TTSPlatform.modal
    assert req.response_mode.value == "url"
    assert req.voice is None
    assert req.temperature is None


def test_tts_enum_values():
    assert TTSModel.orpheus_3b_tts.value == "orpheus-3b-tts"
    assert TTSModel.spark_tts.value == "spark-tts"
    assert TTSPlatform.modal.value == "modal"
    assert TTSPlatform.runpod.value == "runpod"


def test_speech_response_minimal():
    resp = SpeechResponse(
        audio_url="https://x/y.wav",
        model="spark-tts",
        platform="runpod",
        voice="luganda_female",
    )
    assert resp.audio_url == "https://x/y.wav"
    assert resp.sample_rate is None


async def test_runpod_spark_service_builds_payload_and_returns_output(monkeypatch):
    from app.services import runpod_tts_service as mod

    captured = {}

    def fake_run_sync(data, timeout):
        captured["data"] = data
        captured["timeout"] = timeout
        return {
            "audio_url": "https://x/y.mp3",
            "blob": "tts/y.mp3",
            "sample_rate": 16000,
        }

    fake_endpoint = MagicMock()
    fake_endpoint.run_sync = fake_run_sync
    monkeypatch.setattr(mod.runpod, "Endpoint", lambda _id: fake_endpoint)

    svc = mod.RunpodSparkTTSService(endpoint_id="ep123")
    out = await svc.synthesize(
        text="  hello  ", speaker_id=248, temperature=0.7, max_new_audio_tokens=2000
    )
    assert out["audio_url"] == "https://x/y.mp3"
    assert captured["data"]["input"] == {
        "task": "tts",
        "text": "hello",
        "speaker_id": 248,
        "temperature": 0.7,
        "max_new_audio_tokens": 2000,
    }
    assert captured["timeout"] == 600


async def test_runpod_spark_service_maps_timeout(monkeypatch):
    from app.services import runpod_tts_service as mod

    def boom(data, timeout):
        raise TimeoutError("slow")

    fake_endpoint = MagicMock()
    fake_endpoint.run_sync = boom
    monkeypatch.setattr(mod.runpod, "Endpoint", lambda _id: fake_endpoint)

    svc = mod.RunpodSparkTTSService(endpoint_id="ep123")
    with pytest.raises(ServiceUnavailableError):
        await svc.synthesize(
            text="hi", speaker_id=248, temperature=0.7, max_new_audio_tokens=2000
        )


async def test_runpod_spark_service_maps_connection_error(monkeypatch):
    from app.services import runpod_tts_service as mod

    def boom(data, timeout):
        raise ConnectionError("lost")

    fake_endpoint = MagicMock()
    fake_endpoint.run_sync = boom
    monkeypatch.setattr(mod.runpod, "Endpoint", lambda _id: fake_endpoint)

    svc = mod.RunpodSparkTTSService(endpoint_id="ep123")
    with pytest.raises(ExternalServiceError):
        await svc.synthesize(
            text="hi", speaker_id=248, temperature=0.7, max_new_audio_tokens=2000
        )


async def test_runpod_spark_service_maps_value_error(monkeypatch):
    from app.services import runpod_tts_service as mod

    def boom(data, timeout):
        raise ValueError("bad input")

    fake_endpoint = MagicMock()
    fake_endpoint.run_sync = boom
    monkeypatch.setattr(mod.runpod, "Endpoint", lambda _id: fake_endpoint)

    svc = mod.RunpodSparkTTSService(endpoint_id="ep123")
    with pytest.raises(BadRequestError):
        await svc.synthesize(
            text="hi", speaker_id=248, temperature=0.7, max_new_audio_tokens=2000
        )


# ---------------------------------------------------------------------------
# Task 4 — SpeechService facade
# ---------------------------------------------------------------------------


def make_speech_facade():
    spark = MagicMock()
    spark.generate_audio = AsyncMock(return_value=b"WAVDATA")
    spark.estimate_duration = MagicMock(return_value=3.0)
    orpheus = MagicMock()
    orpheus.synthesize = AsyncMock(
        return_value=SynthesizeResult(
            audio_url="https://o/a.wav",
            audio_url_expires_at=datetime(2026, 12, 1),
            speaker_id="salt_lug_0001",
            language="lug",
            sample_rate=24000,
            duration_seconds=2.5,
            chunks=1,
            audio_size_bytes=1000,
            gcs_object="orpheus_tts/a.wav",
            inference_ms=10.0,
            upload_ms=5.0,
            signed_url_ms=1.0,
            total_ms=16.0,
        )
    )
    runpod_spark = MagicMock()
    runpod_spark.synthesize = AsyncMock(
        return_value={
            "audio_url": "https://r/a.mp3",
            "blob": "tts/a.mp3",
            "sample_rate": 16000,
        }
    )
    storage = MagicMock()
    storage.generate_file_name = MagicMock(return_value="tts_audio/x.wav")
    storage.upload_audio_async = AsyncMock(return_value="blob-obj")
    storage.generate_signed_url = MagicMock(
        return_value=("https://s/x.wav", datetime(2026, 12, 1))
    )
    facade = SpeechService(
        tts_service=spark,
        orpheus_service=orpheus,
        runpod_spark_service=runpod_spark,
        storage_service=storage,
    )
    return facade, spark, orpheus, runpod_spark, storage


def test_resolve_spark_speaker_default():
    assert SpeechService.resolve_spark_speaker(None) is SpeakerID.LUGANDA_FEMALE


def test_resolve_spark_speaker_by_name_and_int():
    assert (
        SpeechService.resolve_spark_speaker("luganda_female")
        is SpeakerID.LUGANDA_FEMALE
    )
    assert SpeechService.resolve_spark_speaker("248") is SpeakerID.LUGANDA_FEMALE
    assert (
        SpeechService.resolve_spark_speaker("ACHOLI_FEMALE") is SpeakerID.ACHOLI_FEMALE
    )


def test_resolve_spark_speaker_invalid():
    with pytest.raises(BadRequestError):
        SpeechService.resolve_spark_speaker("no_such_voice")


def test_validate_rejects_orpheus_on_runpod():
    facade, *_ = make_speech_facade()
    req = SpeechRequest(text="hi", model="orpheus-3b-tts", platform="runpod")
    with pytest.raises(BadRequestError):
        facade.validate_request(req)


def test_validate_rejects_stream_on_non_modal_spark():
    facade, *_ = make_speech_facade()
    req = SpeechRequest(
        text="hi", model="spark-tts", platform="runpod", response_mode="stream"
    )
    with pytest.raises(BadRequestError):
        facade.validate_request(req)


def test_validate_rejects_orpheus_param_on_spark():
    facade, *_ = make_speech_facade()
    req = SpeechRequest(text="hi", model="spark-tts", platform="runpod", top_p=0.9)
    with pytest.raises(BadRequestError):
        facade.validate_request(req)


def test_validate_rejects_max_new_audio_tokens_off_target():
    facade, *_ = make_speech_facade()
    req = SpeechRequest(
        text="hi", model="spark-tts", platform="modal", max_new_audio_tokens=100
    )
    with pytest.raises(BadRequestError):
        facade.validate_request(req)


def test_validate_rejects_temperature_on_modal_spark():
    facade, *_ = make_speech_facade()
    req = SpeechRequest(text="hi", model="spark-tts", platform="modal", temperature=0.5)
    with pytest.raises(BadRequestError):
        facade.validate_request(req)


def test_validate_rejects_overlong_orpheus_text():
    facade, *_ = make_speech_facade()
    req = SpeechRequest(text="x" * 2001, model="orpheus-3b-tts", platform="modal")
    with pytest.raises(BadRequestError):
        facade.validate_request(req)


def test_validate_accepts_valid_runpod_spark():
    facade, *_ = make_speech_facade()
    req = SpeechRequest(
        text="hi", model="spark-tts", platform="runpod", temperature=0.7
    )
    facade.validate_request(req)  # no raise


async def test_synthesize_orpheus():
    facade, _, orpheus, _, _ = make_speech_facade()
    req = SpeechRequest(
        text="hi", model="orpheus-3b-tts", platform="modal", voice="salt_lug_0001"
    )
    result = await facade.synthesize(req)
    orpheus.synthesize.assert_awaited_once()
    assert result.audio_url == "https://o/a.wav"
    assert result.model == "orpheus-3b-tts"
    assert result.timings_ms["total_ms"] == 16.0


async def test_synthesize_spark_modal_uploads_and_signs():
    facade, spark, _, _, storage = make_speech_facade()
    req = SpeechRequest(
        text="hi", model="spark-tts", platform="modal", voice="luganda_female"
    )
    result = await facade.synthesize(req)
    spark.generate_audio.assert_awaited_once()
    storage.upload_audio_async.assert_awaited_once()
    assert result.audio_url == "https://s/x.wav"
    assert result.voice == "luganda_female"


async def test_synthesize_spark_runpod_maps_output():
    facade, _, _, runpod_spark, _ = make_speech_facade()
    req = SpeechRequest(text="hi", model="spark-tts", platform="runpod", voice="248")
    result = await facade.synthesize(req)
    runpod_spark.synthesize.assert_awaited_once()
    assert result.audio_url == "https://r/a.mp3"
    assert result.sample_rate == 16000
    assert result.gcs_object == "tts/a.mp3"


async def test_synthesize_spark_runpod_missing_audio_url_raises():
    facade, _, _, runpod_spark, _ = make_speech_facade()
    runpod_spark.synthesize = AsyncMock(return_value={"blob": "tts/a.mp3"})
    req = SpeechRequest(text="hi", model="spark-tts", platform="runpod", voice="248")
    with pytest.raises(ExternalServiceError):
        await facade.synthesize(req)


def test_speech_deps_exported():
    import app.deps as deps

    assert hasattr(deps, "SpeechServiceDep")
    assert hasattr(deps, "RunpodSparkTTSServiceDep")
    assert "SpeechServiceDep" in deps.__all__
    assert "RunpodSparkTTSServiceDep" in deps.__all__


def test_validate_rejects_overlong_spark_text():
    facade, *_ = make_speech_facade()
    req = SpeechRequest(text="x" * 10001, model="spark-tts", platform="runpod")
    with pytest.raises(BadRequestError):
        facade.validate_request(req)


async def test_list_voices_spark_returns_all_speakers():
    facade, *_ = make_speech_facade()
    result = await facade.list_voices("spark-tts", None)
    assert isinstance(result, SpeakersListResponse)
    assert len(result.speakers) == 6


async def test_list_voices_spark_with_language_rejected():
    facade, *_ = make_speech_facade()
    with pytest.raises(BadRequestError):
        await facade.list_voices("spark-tts", "lug")


async def test_list_voices_orpheus_grouped():
    facade, _, orpheus, _, _ = make_speech_facade()
    orpheus.list_speakers = AsyncMock(
        return_value=SimpleNamespace(
            default="salt_lug_0001",
            by_language={"lug": ["salt_lug_0001"], "eng": ["salt_eng_0001"]},
        )
    )
    result = await facade.list_voices("orpheus-3b-tts", None)
    assert isinstance(result, OrpheusSpeakersResponse)
    assert result.default == "salt_lug_0001"
    assert result.total == 2


async def test_list_voices_orpheus_by_language():
    facade, _, orpheus, _, _ = make_speech_facade()
    orpheus.speakers_for_language = AsyncMock(return_value=["salt_lug_0001"])
    result = await facade.list_voices("orpheus-3b-tts", "lug")
    assert isinstance(result, OrpheusLanguageSpeakersResponse)
    assert result.language == "lug"
    assert result.speakers == ["salt_lug_0001"]
    orpheus.speakers_for_language.assert_awaited_once_with("lug")
