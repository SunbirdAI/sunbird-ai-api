"""Unit tests for the TTS unified speech facade and helpers."""

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


from app.schemas.speech import SpeechRequest, SpeechResponse, TTSModel, TTSPlatform


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
