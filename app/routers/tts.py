"""
API Routes

All TTS API endpoints.
"""

import base64
import json
from io import BytesIO

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.deps import LegacyStorageServiceDep, TTSServiceDep, get_current_user, get_db
from app.models.enums import SpeakerID, TTSResponseMode, get_all_speakers
from app.schemas.tts import (
    ErrorResponse,
    HealthResponse,
    SpeakerInfo,
    SpeakersListResponse,
    TTSRequest,
    TTSResponse,
    TTSStreamFinalResponse,
)

router = APIRouter()


# =============================================================================
# Health Check
# =============================================================================


@router.get(
    "/health",
    response_model=HealthResponse,
    # tags=["Health"],
    summary="Health Check",
)
async def health_check():
    """Check if the service is healthy."""
    return HealthResponse(
        status="healthy", service="tts-api", version=settings.app_version
    )


# =============================================================================
# Speaker Endpoints
# =============================================================================


@router.get(
    "/tts/speakers",
    response_model=SpeakersListResponse,
    # tags=["Speakers"],
    summary="List Available Speakers",
    description="Get all available speaker voices for TTS generation.",
)
async def list_speakers(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return a list of all available speaker voices."""
    speakers = [SpeakerInfo(**speaker_data) for speaker_data in get_all_speakers()]
    return SpeakersListResponse(speakers=speakers)


# =============================================================================
# TTS Endpoints
# =============================================================================


@router.post(
    "/tts",
    response_model=TTSResponse,
    responses={
        200: {"description": "Audio generated successfully", "model": TTSResponse},
        400: {"description": "Invalid request", "model": ErrorResponse},
        500: {"description": "Server error", "model": ErrorResponse},
    },
    # tags=["TTS"],
    summary="Generate Text-to-Speech Audio",
    description="Convert text to speech and return a signed URL to the audio file.",
)
async def generate_tts(
    request: TTSRequest,
    storage_service: LegacyStorageServiceDep,
    tts_service: TTSServiceDep,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Generate TTS audio from text.

    - **text**: The text to convert to speech
    - **speaker_id**: Voice/speaker selection ID
    - **response_mode**: How to return the audio (url, stream, or both)

    Returns a signed GCP Storage URL valid for 30 minutes.
    """
    # Handle streaming modes
    if request.response_mode == TTSResponseMode.STREAM:
        return await _stream_audio(request, tts_service)
    elif request.response_mode == TTSResponseMode.BOTH:
        return await _stream_audio_with_url(request, storage_service, tts_service)

    # URL mode (default)
    try:
        # Generate audio from TTS service
        audio_data = await tts_service.generate_audio(
            text=request.text, speaker_id=request.speaker_id
        )

        # Upload to GCP Storage
        file_name = storage_service.generate_file_name(request.text, request.speaker_id)
        blob = await storage_service.upload_audio_async(audio_data, file_name)

        # Generate signed URL
        signed_url, expires_at = storage_service.generate_signed_url(blob)

        # Estimate duration
        duration_estimate = tts_service.estimate_duration(request.text)

        return TTSResponse(
            success=True,
            audio_url=signed_url,
            expires_at=expires_at,
            file_name=file_name,
            duration_estimate_seconds=round(duration_estimate, 2),
            text_length=len(request.text),
            speaker_id=request.speaker_id,
            speaker_name=request.speaker_id.display_name,
        )

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504, detail="TTS service timeout - text may be too long"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate audio: {str(e)}"
        )


@router.post(
    "/tts/stream",
    # tags=["TTS"],
    summary="Stream TTS Audio",
    description="Stream audio chunks as they are generated.",
)
async def stream_tts(
    request: TTSRequest,
    tts_service: TTSServiceDep,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Stream audio directly without storing in GCP."""
    return await _stream_audio(request, tts_service)


@router.post(
    "/tts/stream-with-url",
    # tags=["TTS"],
    summary="Stream TTS Audio with Final URL",
    description="Stream audio chunks and return a signed URL at completion.",
)
async def stream_tts_with_url(
    request: TTSRequest,
    storage_service: LegacyStorageServiceDep,
    tts_service: TTSServiceDep,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Stream audio and provide a URL for the complete file at the end."""
    return await _stream_audio_with_url(request, storage_service, tts_service)


@router.get(
    "/tts/refresh-url",
    response_model=TTSResponse,
    # tags=["TTS"],
    summary="Refresh Signed URL",
    description="Generate a new signed URL for an existing audio file.",
)
async def refresh_signed_url(
    storage_service: LegacyStorageServiceDep,
    file_name: str = Query(..., description="The file name in GCP Storage"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Generate a fresh signed URL for an existing audio file."""
    try:
        signed_url, expires_at = storage_service.get_signed_url_for_file(file_name)

        return TTSResponse(
            success=True,
            audio_url=signed_url,
            expires_at=expires_at,
            file_name=file_name,
        )

    except Exception as e:
        raise HTTPException(
            status_code=404, detail=f"File not found or error generating URL: {str(e)}"
        )


# =============================================================================
# Helper Functions
# =============================================================================


async def _stream_audio(
    request: TTSRequest,
    tts_service: TTSServiceDep,
) -> StreamingResponse:
    """Create a streaming response for audio data."""

    async def audio_generator():
        async for chunk in tts_service.generate_audio_stream(
            text=request.text, speaker_id=request.speaker_id
        ):
            yield chunk

    return StreamingResponse(
        audio_generator(),
        media_type="audio/wav",
        headers={
            "Content-Disposition": 'attachment; filename="tts_output.wav"',
            "X-Speaker-ID": str(request.speaker_id.value),
            "X-Speaker-Name": request.speaker_id.display_name,
            "X-Text-Length": str(len(request.text)),
        },
    )


async def _stream_audio_with_url(
    request: TTSRequest,
    storage_service: LegacyStorageServiceDep,
    tts_service: TTSServiceDep,
) -> StreamingResponse:
    """
    Stream audio chunks and upload the complete audio to GCP Storage.

    Uses Server-Sent Events (SSE) format to send:
    1. Audio chunks (base64 encoded)
    2. Final message with signed URL
    """

    async def audio_generator_with_upload():
        audio_buffer = BytesIO()
        total_bytes = 0

        try:
            # Stream audio chunks
            async for chunk in tts_service.generate_audio_stream(
                text=request.text, speaker_id=request.speaker_id
            ):
                audio_buffer.write(chunk)
                total_bytes += len(chunk)

                # Send chunk as SSE event
                chunk_b64 = base64.b64encode(chunk).decode("utf-8")
                event_data = json.dumps(
                    {"event": "audio_chunk", "data": chunk_b64, "bytes": len(chunk)}
                )
                yield f"data: {event_data}\n\n"

            # Upload complete audio to GCP
            audio_data = audio_buffer.getvalue()
            file_name = storage_service.generate_file_name(
                request.text, request.speaker_id
            )
            blob = await storage_service.upload_audio_async(audio_data, file_name)

            # Generate signed URL
            signed_url, expires_at = storage_service.generate_signed_url(blob)

            # Send final event with URL
            final_response = TTSStreamFinalResponse(
                audio_url=signed_url,
                expires_at=expires_at,
                file_name=file_name,
                total_bytes=total_bytes,
            )
            yield f"data: {final_response.model_dump_json()}\n\n"

        except Exception as e:
            error_event = json.dumps({"event": "error", "error": str(e)})
            yield f"data: {error_event}\n\n"

    return StreamingResponse(
        audio_generator_with_upload(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Speaker-ID": str(request.speaker_id.value),
            "X-Speaker-Name": request.speaker_id.display_name,
            "X-Text-Length": str(len(request.text)),
        },
    )
