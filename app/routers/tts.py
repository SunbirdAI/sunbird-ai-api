"""
API Routes

All TTS API endpoints.
"""

import base64
import json
import logging
import time
from io import BytesIO

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    ExternalServiceError,
    NotFoundError,
    ServiceUnavailableError,
)
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
from app.utils.deprecation import SUCCESSOR_SPEECH, add_deprecation_headers
from app.utils.feedback import INFERENCE_TYPES, save_api_inference

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
    deprecated=True,
)
async def generate_tts(
    request: TTSRequest,
    storage_service: LegacyStorageServiceDep,
    tts_service: TTSServiceDep,
    background_tasks: BackgroundTasks,
    http_response: Response,
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
    logging.warning(
        "Deprecated endpoint /tasks/modal/tts called; use POST /tasks/audio/speech"
    )

    # Handle streaming modes
    if request.response_mode == TTSResponseMode.STREAM:
        return await _stream_audio(request, tts_service)
    elif request.response_mode == TTSResponseMode.BOTH:
        return await _stream_audio_with_url(request, storage_service, tts_service)

    # URL mode (default)
    start_time = time.time()
    # Deprecation headers apply to the url-mode (model) response only; the
    # streaming branches above return raw StreamingResponses without them.
    add_deprecation_headers(http_response, SUCCESSOR_SPEECH)
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

        response = TTSResponse(
            success=True,
            audio_url=signed_url,
            expires_at=expires_at,
            file_name=file_name,
            duration_estimate_seconds=round(duration_estimate, 2),
            text_length=len(request.text),
            speaker_id=request.speaker_id,
            speaker_name=request.speaker_id.display_name,
        )

        _schedule_modal_tts_feedback(
            background_tasks=background_tasks,
            user=current_user,
            text=request.text,
            speaker_id=request.speaker_id,
            file_name=file_name,
            audio_url=signed_url,
            processing_time=time.time() - start_time,
        )

        return response

    except httpx.TimeoutException:
        raise ServiceUnavailableError(
            message="TTS service timeout - text may be too long"
        )
    except Exception as e:
        raise ExternalServiceError(
            service_name="TTS",
            message="Failed to generate audio",
            original_error=str(e),
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
        raise NotFoundError(
            resource="Audio file",
            message=f"File not found or error generating URL: {str(e)}",
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


def _schedule_modal_tts_feedback(
    *,
    background_tasks: BackgroundTasks,
    user,
    text: str,
    speaker_id,
    file_name: str,
    audio_url: str,
    processing_time: float,
) -> None:
    """Schedule a best-effort Modal TTS feedback save.

    Wrapped in try/except so a feedback-save failure never propagates to the
    request response. Only metadata is sent; raw audio bytes are excluded and
    the source text is hashed downstream in `save_api_inference`.
    """
    try:
        speaker_name = getattr(speaker_id, "name", None) or str(speaker_id)
        speaker_value = getattr(speaker_id, "value", speaker_id)
        background_tasks.add_task(
            save_api_inference,
            text,
            {"file_name": file_name, "audio_url": audio_url},
            user,
            model_type=speaker_name,
            processing_time=processing_time,
            inference_type=INFERENCE_TYPES["tts_modal"],
            job_details={
                "speaker_id": speaker_value,
                "blob": file_name,
                "audio_url": audio_url,
            },
        )
    except Exception as e:
        logging.warning(f"Failed to schedule Modal TTS feedback save task: {e}")
