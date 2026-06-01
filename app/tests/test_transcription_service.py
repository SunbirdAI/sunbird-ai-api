"""Unit tests for the TranscriptionService facade and its schema."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import BadRequestError
from app.schemas.stt import TranscriptionPlatform
from app.services.stt_service import TranscriptionResult
from app.services.transcription_service import TranscriptionService
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


def make_facade():
    stt = MagicMock()
    stt.validate_audio_file = MagicMock(return_value=None)
    stt.transcribe_from_gcs = AsyncMock(
        return_value=TranscriptionResult(
            transcription="gcs text",
            diarization_output={},
            formatted_diarization_output="",
            audio_url="gs://bucket/a.wav",
            blob_name="a.wav",
        )
    )
    stt.transcribe_uploaded_file = AsyncMock(
        return_value=TranscriptionResult(
            transcription="upload text",
            diarization_output={},
            formatted_diarization_output="",
            audio_url="gs://bucket/u.wav",
            blob_name="u.wav",
        )
    )
    stt.transcribe_org_audio = AsyncMock(
        return_value=TranscriptionResult(
            transcription="org text",
            diarization_output={},
            formatted_diarization_output="",
        )
    )
    modal = MagicMock()
    modal.transcribe = AsyncMock(return_value="modal text")
    return TranscriptionService(stt_service=stt, modal_stt_service=modal), stt, modal


# --- validate_and_normalize ---


def test_validate_runpod_passes_flags_through():
    facade, _, _ = make_facade()
    whisper, speakers = facade.validate_and_normalize(
        platform="runpod",
        has_audio=True,
        gcs_blob_name=None,
        org=False,
        whisper=True,
        recognise_speakers=True,
    )
    assert whisper is True
    assert speakers is True


def test_validate_runpod_defaults_false():
    facade, _, _ = make_facade()
    whisper, speakers = facade.validate_and_normalize(
        platform="runpod",
        has_audio=True,
        gcs_blob_name=None,
        org=False,
        whisper=False,
        recognise_speakers=False,
    )
    assert whisper is False
    assert speakers is False


def test_validate_modal_allows_false_flags():
    facade, _, _ = make_facade()
    whisper, speakers = facade.validate_and_normalize(
        platform="modal",
        has_audio=True,
        gcs_blob_name=None,
        org=False,
        whisper=False,
        recognise_speakers=False,
    )
    assert whisper is False
    assert speakers is False


def test_validate_rejects_no_input():
    facade, _, _ = make_facade()
    with pytest.raises(BadRequestError):
        facade.validate_and_normalize(
            platform="runpod",
            has_audio=False,
            gcs_blob_name=None,
            org=False,
            whisper=False,
            recognise_speakers=False,
        )


def test_validate_rejects_both_inputs():
    facade, _, _ = make_facade()
    with pytest.raises(BadRequestError):
        facade.validate_and_normalize(
            platform="runpod",
            has_audio=True,
            gcs_blob_name="a.wav",
            org=False,
            whisper=False,
            recognise_speakers=False,
        )


def test_validate_rejects_modal_with_gcs():
    facade, _, _ = make_facade()
    with pytest.raises(BadRequestError):
        facade.validate_and_normalize(
            platform="modal",
            has_audio=False,
            gcs_blob_name="a.wav",
            org=False,
            whisper=False,
            recognise_speakers=False,
        )


def test_validate_rejects_modal_with_org():
    facade, _, _ = make_facade()
    with pytest.raises(BadRequestError):
        facade.validate_and_normalize(
            platform="modal",
            has_audio=True,
            gcs_blob_name=None,
            org=True,
            whisper=False,
            recognise_speakers=False,
        )


def test_validate_rejects_modal_with_runpod_only_flags():
    facade, _, _ = make_facade()
    with pytest.raises(BadRequestError):
        facade.validate_and_normalize(
            platform="modal",
            has_audio=True,
            gcs_blob_name=None,
            org=False,
            whisper=True,
            recognise_speakers=False,
        )


def test_validate_rejects_unknown_platform():
    facade, _, _ = make_facade()
    with pytest.raises(BadRequestError):
        facade.validate_and_normalize(
            platform="gcp",
            has_audio=True,
            gcs_blob_name=None,
            org=False,
            whisper=False,
            recognise_speakers=False,
        )


# --- transcribe dispatch ---


async def test_transcribe_dispatches_modal():
    facade, stt, modal = make_facade()
    result = await facade.transcribe(
        platform="modal",
        language="lug",
        adapter="lug",
        audio_bytes=b"xx",
    )
    modal.transcribe.assert_awaited_once_with(b"xx", language="lug")
    assert result.transcription == "modal text"
    stt.transcribe_uploaded_file.assert_not_called()


async def test_transcribe_dispatches_gcs():
    facade, stt, _ = make_facade()
    result = await facade.transcribe(
        platform="runpod",
        language="lug",
        adapter="lug",
        gcs_blob_name="a.wav",
        whisper=True,
        recognise_speakers=True,
    )
    stt.transcribe_from_gcs.assert_awaited_once()
    assert result.transcription == "gcs text"


async def test_transcribe_dispatches_uploaded():
    facade, stt, _ = make_facade()
    result = await facade.transcribe(
        platform="runpod",
        language="lug",
        adapter="lug",
        org=False,
        whisper=True,
        recognise_speakers=True,
        file_path="/tmp/u.wav",
        file_extension=".wav",
        content_type="audio/wav",
    )
    stt.validate_audio_file.assert_called_once_with("audio/wav", ".wav")
    stt.transcribe_uploaded_file.assert_awaited_once()
    assert result.transcription == "upload text"


async def test_transcribe_dispatches_org():
    facade, stt, _ = make_facade()
    result = await facade.transcribe(
        platform="runpod",
        language="lug",
        adapter="lug",
        org=True,
        recognise_speakers=True,
        file_path="/tmp/o.wav",
        file_extension=".wav",
        content_type="audio/wav",
    )
    stt.validate_audio_file.assert_called_once_with("audio/wav", ".wav")
    stt.transcribe_org_audio.assert_awaited_once_with(
        file_path="/tmp/o.wav", recognise_speakers=True
    )
    assert result.transcription == "org text"


def test_transcription_service_dep_is_exported():
    import app.deps as deps

    assert hasattr(deps, "TranscriptionServiceDep")
    assert "TranscriptionServiceDep" in deps.__all__
