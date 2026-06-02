"""Schemas for the unified Text-to-Speech endpoint (/tasks/audio/speech)."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.models.enums import TTSResponseMode  # reused: url | stream | both


class TTSModel(str, Enum):
    """Supported TTS models for the unified endpoint."""

    orpheus_3b_tts = "orpheus-3b-tts"
    spark_tts = "spark-tts"


class TTSPlatform(str, Enum):
    """Supported TTS platforms for the unified endpoint."""

    modal = "modal"
    runpod = "runpod"


class SpeechRequest(BaseModel):
    """Unified text-to-speech request.

    Some fields apply only to specific model/platform combinations; the
    SpeechService validates combinations and returns 400 on a mismatch.
    """

    text: str = Field(..., min_length=1, description="Text to synthesize.")
    model: TTSModel = Field(default=TTSModel.orpheus_3b_tts, description="TTS model.")
    platform: TTSPlatform = Field(
        default=TTSPlatform.modal, description="Inference platform."
    )
    voice: Optional[str] = Field(
        default=None,
        description="Voice/speaker. spark-tts: SpeakerID name (e.g. 'luganda_female') "
        "or id (e.g. '248'); orpheus-3b-tts: catalog tag (e.g. 'salt_lug_0001').",
    )
    response_mode: TTSResponseMode = Field(
        default=TTSResponseMode.URL,
        description="url (signed URL), stream (raw audio), or both (SSE). "
        "stream/both require model='spark-tts' on platform='modal'.",
    )
    language: Optional[str] = Field(
        default=None, description="orpheus only (ISO 639-3)."
    )
    temperature: Optional[float] = Field(
        default=None, description="orpheus + runpod-spark."
    )
    top_p: Optional[float] = Field(default=None, description="orpheus only.")
    repetition_penalty: Optional[float] = Field(
        default=None, description="orpheus only."
    )
    max_tokens: Optional[int] = Field(default=None, description="orpheus only.")
    seed: Optional[int] = Field(default=None, description="orpheus only.")
    max_new_audio_tokens: Optional[int] = Field(
        default=None, description="runpod-spark only."
    )

    @field_validator("text")
    @classmethod
    def _strip_text(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("text must not be empty")
        return v


class SpeechResponse(BaseModel):
    """Normalized response for response_mode='url' across all providers."""

    audio_url: str = Field(description="Signed URL to the generated audio.")
    model: str = Field(description="Model used.")
    platform: str = Field(description="Platform used.")
    voice: str = Field(description="Resolved voice/speaker.")
    audio_url_expires_at: Optional[datetime] = Field(default=None)
    language: Optional[str] = Field(default=None)
    sample_rate: Optional[int] = Field(default=None)
    duration_seconds: Optional[float] = Field(default=None)
    gcs_object: Optional[str] = Field(default=None)
    request_id: Optional[str] = Field(default=None)
    timings_ms: Optional[Dict[str, Any]] = Field(default=None)


class SpeechBatchItem(BaseModel):
    """One item in a batch speech request (orpheus-3b-tts only)."""

    text: str = Field(..., min_length=1, description="Text to synthesize.")
    voice: Optional[str] = Field(
        default=None,
        description="orpheus catalog tag (e.g. 'salt_lug_0001'). "
        "If omitted, the service uses salt_lug_0001.",
    )
    language: Optional[str] = Field(
        default=None, description="orpheus ISO 639-3 code (e.g. 'lug')."
    )
    temperature: Optional[float] = Field(default=None)
    top_p: Optional[float] = Field(default=None)
    repetition_penalty: Optional[float] = Field(default=None)
    max_tokens: Optional[int] = Field(default=None)
    seed: Optional[int] = Field(default=None)

    @field_validator("text")
    @classmethod
    def _strip_text(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("text must not be empty")
        return v


class SpeechBatchRequest(BaseModel):
    """Unified batch TTS request (orpheus-3b-tts only)."""

    model: TTSModel = Field(
        default=TTSModel.orpheus_3b_tts,
        description="Only 'orpheus-3b-tts' is supported for batch.",
    )
    items: list[SpeechBatchItem] = Field(
        ..., min_length=1, max_length=128, description="1-128 items."
    )


class SpeechBatchItemResponse(BaseModel):
    """Per-item batch result (mirrors SpeechResponse + status/error)."""

    index: int = Field(description="Zero-based position in the request's items.")
    status: Literal["ok", "error"] = Field(
        description="'ok' if this item synthesized, 'error' if it failed."
    )
    voice: str = Field(description="Resolved orpheus voice/speaker tag.")
    audio_url: Optional[str] = None
    audio_url_expires_at: Optional[datetime] = None
    language: Optional[str] = None
    sample_rate: Optional[int] = None
    duration_seconds: Optional[float] = None
    audio_size_bytes: Optional[int] = None
    gcs_object: Optional[str] = None
    request_id: Optional[str] = None
    error_code: Optional[str] = Field(
        default=None, description="Machine-readable failure code (error items only)."
    )
    error_detail: Optional[str] = Field(
        default=None, description="Human-readable failure detail (error items only)."
    )


class SpeechBatchResponse(BaseModel):
    """Normalized batch response."""

    model: str = Field(description="Model used (always 'orpheus-3b-tts').")
    platform: str = Field(description="Platform used (always 'modal').")
    results: list[SpeechBatchItemResponse] = Field(
        description="Per-item results, in request order."
    )
    request_id: str = Field(description="Unique id for this batch request.")
    timings_ms: Optional[Dict[str, Any]] = Field(default=None)
