"""
Pydantic Schemas

Request and response models for the TTS API.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.models.enums import SpeakerID, TTSResponseMode

# =============================================================================
# Request Models
# =============================================================================


class TTSRequest(BaseModel):
    """Request model for TTS generation."""

    text: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="Text to convert to speech",
        examples=["Hello, this is a text-to-speech test."],
    )
    speaker_id: SpeakerID = Field(
        default=SpeakerID.LUGANDA_FEMALE,
        description="Speaker voice for TTS generation",
        examples=[SpeakerID.LUGANDA_FEMALE, SpeakerID.SWAHILI_MALE],
    )
    response_mode: TTSResponseMode = Field(
        default=TTSResponseMode.URL,
        description="How to return the audio: 'url' for signed URL, 'stream' for streaming, 'both' for streaming with final URL",
    )

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        """Strip whitespace and validate text content."""
        v = v.strip()
        if not v:
            raise ValueError("Text cannot be empty or whitespace only")
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "text": "I am a nurse who takes care of many people.",
                    "speaker_id": 248,
                    "response_mode": "url",
                }
            ]
        }
    }


# =============================================================================
# Response Models
# =============================================================================


class TTSResponse(BaseModel):
    """Response model for TTS generation (URL mode)."""

    success: bool = Field(description="Whether the request was successful")
    audio_url: str = Field(description="Signed URL to access the audio file")
    expires_at: datetime = Field(description="When the signed URL expires")
    file_name: str = Field(description="Name of the audio file in storage")
    duration_estimate_seconds: Optional[float] = Field(
        default=None, description="Estimated audio duration in seconds"
    )
    text_length: Optional[int] = Field(
        default=None, description="Length of the input text"
    )
    speaker_id: Optional[SpeakerID] = Field(
        default=None, description="Speaker voice used for generation"
    )
    speaker_name: Optional[str] = Field(
        default=None, description="Human-readable speaker name"
    )


class TTSStreamFinalResponse(BaseModel):
    """Final response sent after streaming completes (BOTH mode)."""

    event: str = Field(default="complete", description="Event type")
    audio_url: str = Field(description="Signed URL to access the complete audio file")
    expires_at: datetime = Field(description="When the signed URL expires")
    file_name: str = Field(description="Name of the audio file in storage")
    total_bytes: int = Field(description="Total bytes of audio data")


class ErrorResponse(BaseModel):
    """Error response model."""

    success: bool = Field(default=False)
    error: str = Field(description="Error message")
    detail: Optional[str] = Field(
        default=None, description="Detailed error information"
    )


# =============================================================================
# Speaker Models
# =============================================================================


class SpeakerInfo(BaseModel):
    """Information about a speaker voice."""

    id: int = Field(description="Speaker ID")
    name: str = Field(description="Speaker enum name")
    display_name: str = Field(description="Human-readable name")
    language: str = Field(description="Language")
    gender: str = Field(description="Gender")


class SpeakersListResponse(BaseModel):
    """Response containing all available speakers."""

    speakers: list[SpeakerInfo] = Field(description="List of available speakers")


# =============================================================================
# Health Check Models
# =============================================================================


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(description="Service status")
    service: str = Field(description="Service name")
    version: Optional[str] = Field(default=None, description="Service version")
