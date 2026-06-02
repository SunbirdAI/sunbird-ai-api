"""Unified audio router (OpenAI-style).

Hosts the consolidated Speech-to-Text endpoint ``POST /tasks/audio/transcriptions``
that supersedes the legacy /stt, /stt_from_gcs, /org/stt, and /modal/stt routes.
Also hosts the unified TTS endpoint ``POST /tasks/audio/speech``.
"""

import logging
import os
import tempfile
import time
import uuid
from typing import Optional

import aiofiles
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Depends,
    File,
    Form,
    Request,
    UploadFile,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BadRequestError,
    ExternalServiceError,
    ServiceUnavailableError,
    ValidationError,
)
from app.crud.audio_transcription import create_audio_transcription
from app.deps import (
    LegacyStorageServiceDep,
    QuotaServiceDep,
    SpeechServiceDep,
    TranscriptionServiceDep,
    TTSServiceDep,
    get_current_user,
    get_db,
)
from app.models.enums import TTSResponseMode
from app.routers.stt import _schedule_stt_feedback
from app.routers.tts import _stream_audio, _stream_audio_with_url
from app.schemas.speech import SpeechRequest, SpeechResponse
from app.schemas.stt import (
    CHUNK_SIZE,
    SttbLanguage,
    STTTranscript,
    TranscriptionPlatform,
)
from app.schemas.tts import TTSRequest as ModalTTSRequest
from app.services.speech_service import SpeechService
from app.services.stt_service import (
    AudioProcessingError,
    AudioValidationError,
    TranscriptionError,
)
from app.utils.audio import get_audio_extension
from app.utils.feedback import INFERENCE_TYPES, save_api_inference
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
    # Annotate as plain ``SttbLanguage`` (not ``Optional[...]``) so the OpenAPI
    # schema is a clean enum ref and Swagger UI renders a dropdown like
    # ``language``; the field stays optional via ``default=None`` and falls back
    # to ``language`` below.
    adapter: SttbLanguage = Form(
        default=None,
        description="Language adapter (RunPod only). Defaults to the language.",
    ),
    # Plain ``bool`` (not ``Optional[bool]``) so Swagger renders a true/false
    # selector instead of a free-text box. RunPod-only; both default to False.
    whisper: bool = Form(default=False, description="Use Whisper (RunPod only)."),
    recognise_speakers: bool = Form(
        default=False,
        description="Enable speaker diarization (RunPod only).",
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


@router.post(
    "/audio/speech",
    response_model=SpeechResponse,
    summary="Generate speech (unified TTS endpoint)",
    description=(
        "Unified Text-to-Speech endpoint. Routes by model (orpheus-3b-tts | "
        "spark-tts) and platform (modal | runpod). Returns a signed audio URL "
        "(response_mode='url'); spark-tts on Modal also supports 'stream'/'both'. "
        "Replaces /tasks/modal/tts, /tasks/runpod/tts, and /tasks/modal/orpheus/tts."
    ),
)
@limiter.limit(get_account_type_limit)
async def create_speech(  # noqa: C901
    request: Request,
    background_tasks: BackgroundTasks,
    quota: QuotaServiceDep,
    speech_service: SpeechServiceDep,
    tts_service: TTSServiceDep,
    storage_service: LegacyStorageServiceDep,
    body: SpeechRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Generate speech via the selected model + platform."""
    await check_quota(quota, db, current_user)
    start_time = time.time()

    speech_service.validate_request(body)

    if body.response_mode in (TTSResponseMode.STREAM, TTSResponseMode.BOTH):
        speaker = SpeechService.resolve_spark_speaker(body.voice)
        modal_req = ModalTTSRequest(
            text=body.text, speaker_id=speaker, response_mode=body.response_mode
        )
        if body.response_mode == TTSResponseMode.STREAM:
            return await _stream_audio(modal_req, tts_service)
        return await _stream_audio_with_url(modal_req, storage_service, tts_service)

    result = await speech_service.synthesize(body)
    request_id = uuid.uuid4().hex

    response = SpeechResponse(
        audio_url=result.audio_url,
        model=result.model,
        platform=result.platform,
        voice=result.voice,
        audio_url_expires_at=result.audio_url_expires_at,
        language=result.language,
        sample_rate=result.sample_rate,
        duration_seconds=result.duration_seconds,
        gcs_object=result.gcs_object,
        request_id=request_id,
        timings_ms=result.timings_ms,
    )

    _schedule_speech_feedback(
        background_tasks=background_tasks,
        user=current_user,
        text=body.text,
        result=result,
        request_id=request_id,
        processing_time=time.time() - start_time,
    )

    return response


def _schedule_speech_feedback(
    *, background_tasks, user, text, result, request_id, processing_time
):
    """Best-effort feedback save for a unified speech request."""
    try:
        background_tasks.add_task(
            save_api_inference,
            text,
            {"audio_url": result.audio_url, "gcs_object": result.gcs_object},
            user,
            model_type=f"{result.model}:{result.voice}",
            processing_time=processing_time,
            inference_type=INFERENCE_TYPES["tts"],
            job_details={
                "model": result.model,
                "platform": result.platform,
                "voice": result.voice,
                "audio_url": result.audio_url,
                "gcs_object": result.gcs_object,
                "request_id": request_id,
            },
        )
    except Exception as e:
        logging.warning(f"Failed to schedule speech feedback save task: {e}")
