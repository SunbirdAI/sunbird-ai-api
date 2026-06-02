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
