"""Unified audio router (OpenAI-style).

Hosts the consolidated Speech-to-Text endpoint ``POST /tasks/audio/transcriptions``
that supersedes the legacy /stt, /stt_from_gcs, /org/stt, and /modal/stt routes.
The text-to-speech endpoint (/tasks/audio/speech) will be added in Phase 2.
"""

import logging
import os
import tempfile
import time
from typing import Optional

import aiofiles
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BadRequestError,
    ExternalServiceError,
    ServiceUnavailableError,
    ValidationError,
)
from app.crud.audio_transcription import create_audio_transcription
from app.deps import QuotaServiceDep, TranscriptionServiceDep, get_current_user, get_db
from app.routers.stt import _schedule_stt_feedback
from app.schemas.stt import (
    CHUNK_SIZE,
    SttbLanguage,
    STTTranscript,
    TranscriptionPlatform,
)
from app.services.stt_service import (
    AudioProcessingError,
    AudioValidationError,
    TranscriptionError,
)
from app.utils.audio import get_audio_extension
from app.utils.quota_guard import check_quota
from app.utils.rate_limit import get_account_type_limit, limiter

logging.basicConfig(level=logging.INFO)

router = APIRouter()


@router.post(
    "/audio/transcriptions",
    response_model=STTTranscript,
    summary="Transcribe audio (unified STT endpoint)",
    description=(
        "Unified Speech-to-Text endpoint. Accepts an uploaded audio file or a "
        "GCS blob, routes to Modal or RunPod, and supports the RunPod "
        "organization workflow. Replaces /stt, /stt_from_gcs, /org/stt, and "
        "/modal/stt."
    ),
)
@limiter.limit(get_account_type_limit)
async def create_transcription(  # noqa: C901
    request: Request,
    background_tasks: BackgroundTasks,
    quota: QuotaServiceDep,
    transcription_service: TranscriptionServiceDep,
    language: SttbLanguage = Form(..., description="Target language code."),
    # NOTE: annotate as plain ``UploadFile`` (not ``Optional[UploadFile]``) so the
    # OpenAPI schema is a clean ``{type: string, format: binary}`` instead of an
    # ``anyOf`` with null. Swagger UI only renders the file-picker widget for the
    # former; the field stays optional via ``default=None`` (gcs_blob_name is the
    # alternative input).
    audio: UploadFile = File(default=None, description="Audio file to transcribe."),
    gcs_blob_name: Optional[str] = Form(
        default=None, description="GCS blob name (RunPod only)."
    ),
    platform: TranscriptionPlatform = Form(
        default=TranscriptionPlatform.modal,
        description="Transcription platform: 'modal' (default) or 'runpod'.",
    ),
    adapter: Optional[SttbLanguage] = Form(
        default=None,
        description="Language adapter (RunPod only). Defaults to language.",
    ),
    whisper: Optional[bool] = Form(
        default=None, description="Use Whisper (RunPod only). Defaults to true."
    ),
    recognise_speakers: Optional[bool] = Form(
        default=None,
        description="Speaker diarization (RunPod only). Defaults to true.",
    ),
    org: bool = Form(
        default=False, description="Use the RunPod organization workflow."
    ),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> STTTranscript:
    """Transcribe audio via the selected platform and workflow."""
    await check_quota(quota, db, current_user)
    start_time = time.time()

    has_audio = audio is not None and bool(audio.filename)
    resolved_whisper, resolved_speakers = transcription_service.validate_and_normalize(
        platform=platform.value,
        has_audio=has_audio,
        gcs_blob_name=gcs_blob_name,
        org=org,
        whisper=whisper,
        recognise_speakers=recognise_speakers,
    )
    adapter_value = (adapter or language).value

    file_path: Optional[str] = None
    try:
        if platform == TranscriptionPlatform.modal:
            audio_bytes = await audio.read()
            result = await transcription_service.transcribe(
                platform="modal",
                language=language.value,
                adapter=adapter_value,
                audio_bytes=audio_bytes,
            )
        elif gcs_blob_name:
            result = await transcription_service.transcribe(
                platform="runpod",
                language=language.value,
                adapter=adapter_value,
                gcs_blob_name=gcs_blob_name,
                whisper=resolved_whisper,
                recognise_speakers=resolved_speakers,
            )
        else:
            content_type = audio.content_type
            file_extension = get_audio_extension(audio.filename)
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=file_extension
            ) as temp_file:
                file_path = temp_file.name
                async with aiofiles.open(file_path, "wb") as out_file:
                    while content := await audio.read(CHUNK_SIZE):
                        await out_file.write(content)
            result = await transcription_service.transcribe(
                platform="runpod",
                language=language.value,
                adapter=adapter_value,
                org=org,
                whisper=resolved_whisper,
                recognise_speakers=resolved_speakers,
                file_path=file_path,
                file_extension=file_extension,
                content_type=content_type,
            )

        elapsed_time = time.time() - start_time

        audio_transcription_id = None
        should_persist = platform == TranscriptionPlatform.runpod and not org
        if should_persist and result.transcription:
            try:
                db_obj = await create_audio_transcription(
                    db,
                    current_user,
                    result.audio_url,
                    result.blob_name,
                    result.transcription,
                    language.value,
                )
                audio_transcription_id = db_obj.id
            except Exception as e:
                logging.error(f"Database error: {str(e)}")

        response = STTTranscript(
            audio_transcription=result.transcription,
            diarization_output=result.diarization_output,
            formatted_diarization_output=result.formatted_diarization_output,
            audio_transcription_id=audio_transcription_id,
            audio_url=result.audio_url,
            language=language.value,
            was_audio_trimmed=result.was_trimmed,
            original_duration_minutes=result.original_duration
            if result.was_trimmed
            else None,
        )

        _schedule_stt_feedback(
            background_tasks=background_tasks,
            user=current_user,
            source=gcs_blob_name or (audio.filename if audio else "uploaded_audio"),
            transcription=result.transcription,
            audio_url=result.audio_url,
            blob_name=result.blob_name,
            language=language.value,
            adapter=adapter_value,
            whisper=resolved_whisper
            if platform == TranscriptionPlatform.runpod
            else True,
            processing_time=elapsed_time,
            model_type="whisper-modal"
            if platform == TranscriptionPlatform.modal
            else None,
            org=org,
        )

        return response

    except AudioValidationError as e:
        raise ValidationError(
            message=str(e), errors=[{"field": "audio", "value": None}]
        )
    except AudioProcessingError as e:
        raise BadRequestError(message=str(e))
    except TranscriptionError as e:
        raise ExternalServiceError(
            service_name="STT Transcription Service", message=str(e)
        )
    except (
        BadRequestError,
        ValidationError,
        ExternalServiceError,
        ServiceUnavailableError,
    ):
        raise
    except Exception as e:
        logging.error(f"Unexpected error in create_transcription: {str(e)}")
        raise ExternalServiceError(
            service_name="STT Service",
            message="An unexpected error occurred while processing your request",
            original_error=str(e),
        )
    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass
