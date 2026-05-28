"""
Pydantic schemas for the Orpheus-3B TTS gateway endpoints.

These mirror the response shape of the upstream Orpheus FastAPI service so
clients that already integrate with it can switch endpoints without changing
their data models. Source: orpheus-3B/api/models.py.
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, HttpUrl, computed_field

# ----- TTS request -----


class OrpheusTTSRequest(BaseModel):
    text: str = Field(
        ..., min_length=1, max_length=2000, description="Text to synthesize."
    )
    speaker_id: str = Field(
        "salt_lug_0001",
        description="Speaker tag from the Orpheus finetune set (see GET /speakers).",
    )
    language: Optional[str] = Field(
        None,
        description=(
            "Optional ISO 639-3 language code (e.g. 'lug', 'eng'). "
            "If set, speaker_id must belong to it."
        ),
    )
    seed: Optional[int] = Field(None, description="RNG seed for reproducibility.")
    temperature: float = Field(0.6, ge=0.0, le=2.0)
    top_p: float = Field(0.95, gt=0.0, le=1.0)
    repetition_penalty: float = Field(1.1, ge=1.0, le=2.0)
    max_tokens: int = Field(1200, ge=64, le=4096)


class OrpheusTTSBatchRequest(BaseModel):
    items: list[OrpheusTTSRequest] = Field(..., min_length=1, max_length=128)


# ----- Timings -----


class OrpheusTimings(BaseModel):
    inference_ms: float
    upload_ms: float
    signed_url_ms: float
    total_ms: float


class OrpheusBatchTimings(BaseModel):
    inference_ms: float
    upload_ms: float
    total_ms: float


# ----- TTS response (single) -----


class OrpheusTTSResponse(BaseModel):
    audio_url: HttpUrl
    audio_url_expires_at: datetime
    speaker_id: str
    language: Optional[str] = None
    sample_rate: int = 24000
    duration_seconds: float
    chunks: Optional[int] = None
    audio_size_bytes: int
    gcs_object: str
    request_id: str
    timings_ms: OrpheusTimings


# ----- Batch results -----


class OrpheusTTSBatchItemResult(BaseModel):
    index: int
    status: Literal["ok", "error"]
    speaker_id: str

    # success-only
    audio_url: Optional[HttpUrl] = None
    audio_url_expires_at: Optional[datetime] = None
    language: Optional[str] = None
    sample_rate: int = 24000
    duration_seconds: Optional[float] = None
    audio_size_bytes: Optional[int] = None
    gcs_object: Optional[str] = None
    request_id: Optional[str] = None

    # error-only
    error_code: Optional[str] = None
    error_detail: Optional[str] = None


class OrpheusTTSBatchResponse(BaseModel):
    results: list[OrpheusTTSBatchItemResult]
    timings_ms: OrpheusBatchTimings
    request_id: str


# ----- Speaker catalog -----


class OrpheusSpeakersResponse(BaseModel):
    default: str
    by_language: dict[str, list[str]]

    @computed_field
    @property
    def total(self) -> int:
        return sum(len(v) for v in self.by_language.values())

    @computed_field
    @property
    def languages(self) -> list[str]:
        return sorted(self.by_language.keys())


class OrpheusLanguageSpeakersResponse(BaseModel):
    language: str
    speakers: list[str]

    @computed_field
    @property
    def count(self) -> int:
        return len(self.speakers)
