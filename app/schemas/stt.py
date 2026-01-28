"""
Speech-to-Text (STT) Schema Definitions.

This module contains Pydantic models for STT-related request and response
validation. These schemas are used by the STT router and service layers.

Usage:
    from app.schemas.stt import (
        STTTranscript,
        SttbLanguage,
        STTFromGCSRequest,
    )

Note:
    This module was extracted from app/schemas/tasks.py as part of the
    services layer refactoring to improve modularity.
"""

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from app.utils.audio import AUDIO_MIME_TYPES


class SttbLanguage(str, Enum):
    """Supported languages for Speech-to-Text transcription.

    This enum defines the language codes supported by the STT service.
    Each value represents an ISO 639-3 language code.

    Attributes:
        acholi: Acholi language (ach).
        ateso: Ateso language (teo).
        english: English language (eng).
        luganda: Luganda language (lug).
        lugbara: Lugbara language (lgg).
        runyankole: Runyankole language (nyn).
        swahili: Swahili language (swa).
        kinyarwanda: Kinyarwanda language (kin).
        lusoga: Lusoga language (xog).
        lumasaba: Lumasaba language (myx).
    """

    acholi = "ach"
    ateso = "teo"
    english = "eng"
    luganda = "lug"
    lugbara = "lgg"
    runyankole = "nyn"
    swahili = "swa"
    kinyarwanda = "kin"
    lusoga = "xog"
    lumasaba = "myx"


class STTTranscript(BaseModel):
    """Response model for speech-to-text transcription results.

    This model represents the output of an STT transcription request,
    including the transcribed text, diarization data, and metadata.

    Attributes:
        audio_transcription: The transcribed text from the audio.
        diarization_output: Speaker diarization data as a dictionary.
        formatted_diarization_output: Human-readable diarization output.
        audio_transcription_id: Database ID of the saved transcription.
        audio_url: URL or path to the processed audio file.
        language: The language code used for transcription.
        was_audio_trimmed: Whether the audio was trimmed to max duration.
        original_duration_minutes: Original duration if audio was trimmed.
    """

    audio_transcription: Optional[str] = Field(
        None, description="The transcribed text from the audio"
    )
    diarization_output: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Speaker diarization data",
    )
    formatted_diarization_output: Optional[str] = Field(
        None, description="Human-readable diarization output"
    )
    audio_transcription_id: Optional[int] = Field(
        None, description="Database ID of the saved transcription"
    )
    audio_url: Optional[str] = Field(
        None, description="URL or path to the processed audio file"
    )
    language: Optional[str] = Field(
        None, description="The language code used for transcription"
    )
    was_audio_trimmed: Optional[bool] = Field(
        False, description="Whether the audio was trimmed to max duration"
    )
    original_duration_minutes: Optional[float] = Field(
        None, description="Original duration in minutes if audio was trimmed"
    )


class STTFromGCSRequest(BaseModel):
    """Request model for transcribing audio from Google Cloud Storage.

    Attributes:
        gcs_blob_name: The name of the blob in GCS bucket.
        language: Target language for transcription.
        adapter: Language adapter to use.
        recognise_speakers: Whether to enable speaker diarization.
        whisper: Whether to use Whisper model for transcription.
    """

    gcs_blob_name: str = Field(..., description="The name of the blob in GCS bucket")
    language: SttbLanguage = Field(
        SttbLanguage.luganda, description="Target language for transcription"
    )
    adapter: SttbLanguage = Field(
        SttbLanguage.luganda, description="Language adapter to use"
    )
    recognise_speakers: bool = Field(
        False, description="Whether to enable speaker diarization"
    )
    whisper: bool = Field(
        False, description="Whether to use Whisper model for transcription"
    )


class STTUploadRequest(BaseModel):
    """Request parameters for audio file upload transcription.

    Note: Audio file is passed as UploadFile, not in this model.
    This model captures the additional form parameters.

    Attributes:
        language: Target language for transcription.
        adapter: Language adapter to use.
        recognise_speakers: Whether to enable speaker diarization.
        whisper: Whether to use Whisper model for transcription.
    """

    language: SttbLanguage = Field(
        SttbLanguage.luganda, description="Target language for transcription"
    )
    adapter: SttbLanguage = Field(
        SttbLanguage.luganda, description="Language adapter to use"
    )
    recognise_speakers: bool = Field(
        False, description="Whether to enable speaker diarization"
    )
    whisper: bool = Field(
        False, description="Whether to use Whisper model for transcription"
    )


class STTOrgRequest(BaseModel):
    """Request parameters for organization audio transcription.

    Note: Audio file is passed as UploadFile, not in this model.
    This model captures the additional form parameters.

    Attributes:
        recognise_speakers: Whether to enable speaker diarization.
    """

    recognise_speakers: bool = Field(
        False, description="Whether to enable speaker diarization"
    )


# Constants for file validation
MAX_AUDIO_FILE_SIZE_MB = 10  # 10MB limit
MAX_AUDIO_DURATION_MINUTES = 10  # 10 minutes limit
CHUNK_SIZE = 1024 * 1024  # 1MB chunks for streaming

# Use centralized audio MIME types from audio utils
ALLOWED_AUDIO_TYPES = AUDIO_MIME_TYPES
