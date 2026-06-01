"""Unit tests for the TranscriptionService facade and its schema."""

from app.schemas.stt import TranscriptionPlatform


def test_transcription_platform_values():
    assert TranscriptionPlatform.modal.value == "modal"
    assert TranscriptionPlatform.runpod.value == "runpod"
    assert TranscriptionPlatform("modal") is TranscriptionPlatform.modal
