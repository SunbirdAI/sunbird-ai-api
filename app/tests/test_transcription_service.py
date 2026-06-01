"""Unit tests for the TranscriptionService facade and its schema."""

from app.schemas.stt import TranscriptionPlatform
from app.utils.deprecation import (
    STT_SUNSET_DATE,
    SUCCESSOR_TRANSCRIPTIONS,
    deprecation_headers,
)


def test_transcription_platform_values():
    assert TranscriptionPlatform.modal.value == "modal"
    assert TranscriptionPlatform.runpod.value == "runpod"
    assert TranscriptionPlatform("modal") is TranscriptionPlatform.modal


def test_deprecation_headers_contents():
    headers = deprecation_headers(SUCCESSOR_TRANSCRIPTIONS)
    assert headers["Deprecation"] == "true"
    assert headers["Sunset"] == STT_SUNSET_DATE
    assert headers["Link"] == '</tasks/audio/transcriptions>; rel="successor-version"'
