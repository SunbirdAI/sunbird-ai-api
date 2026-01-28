"""
Speech-to-Text (STT) Router Module.

This module defines the API endpoints for speech-to-text transcription
operations. It provides endpoints for transcribing audio files from
direct uploads or from Google Cloud Storage.

Endpoints:
    - POST /stt: Upload an audio file and get transcription
    - POST /stt_from_gcs: Transcribe audio from a GCS blob
    - POST /org/stt: Organization-specific transcription

Architecture:
    Routes → STTService → RunPod API
                       → Google Cloud Storage

Usage:
    This router is included in the main application with the /tasks prefix
    to maintain backward compatibility with existing API consumers.

Note:
    This module was extracted from app/routers/tasks.py as part of the
    services layer refactoring to improve modularity.
"""

import datetime
import logging
import os
import shutil
import tempfile
import time
from typing import Optional

import aiofiles
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from jose import jwt
from slowapi import Limiter
from sqlalchemy.ext.asyncio import AsyncSession
from werkzeug.utils import secure_filename

from app.core.exceptions import (
    BadRequestError,
    ExternalServiceError,
    ServiceUnavailableError,
    ValidationError,
)
from app.crud.audio_transcription import create_audio_transcription
from app.deps import get_current_user, get_db
from app.schemas.stt import (
    ALLOWED_AUDIO_TYPES,
    CHUNK_SIZE,
    MAX_AUDIO_DURATION_MINUTES,
    SttbLanguage,
    STTTranscript,
)
from app.services.stt_service import (
    AudioProcessingError,
    AudioValidationError,
    STTService,
    TranscriptionError,
    get_stt_service,
)
from app.utils.audio import get_audio_extension
from app.utils.auth import ALGORITHM, SECRET_KEY

load_dotenv()
logging.basicConfig(level=logging.INFO)

router = APIRouter()


def custom_key_func(request: Request) -> str:
    """Extract account type from JWT token for rate limiting.

    Args:
        request: The FastAPI request object.

    Returns:
        The account type string or empty string if not found.
    """
    header = request.headers.get("Authorization")
    if not header:
        return "anonymous"
    _, _, token = header.partition(" ")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        account_type: str = payload.get("account_type", "")
        return account_type or ""
    except Exception:
        return ""


def get_account_type_limit(key: str) -> str:
    """Get rate limit based on account type.

    Args:
        key: The account type key.

    Returns:
        Rate limit string (e.g., '50/minute').
    """
    if not key:
        return "50/minute"
    if key.lower() == "admin":
        return "1000/minute"
    if key.lower() == "premium":
        return "100/minute"
    return "50/minute"


# Initialize the Limiter
limiter = Limiter(key_func=custom_key_func)


def get_service() -> STTService:
    """Dependency for getting the STT service instance.

    Returns:
        The STTService singleton instance.
    """
    return get_stt_service()


@router.post("/stt_from_gcs")
async def speech_to_text_from_gcs(
    request: Request,
    gcs_blob_name: str = Form(...),
    language: SttbLanguage = Form(SttbLanguage.luganda),
    adapter: SttbLanguage = Form(SttbLanguage.luganda),
    recognise_speakers: bool = Form(False),
    whisper: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    service: STTService = Depends(get_service),
) -> STTTranscript:
    """Transcribe audio from a Google Cloud Storage blob.

    Accepts a GCS blob name, downloads the file from GCS, trims if >10 minutes,
    uploads a final version (if trimmed), then calls the transcription service.

    Args:
        request: The FastAPI request object.
        gcs_blob_name: Name of the blob in GCS bucket.
        language: Target language for transcription. Defaults to Luganda.
        adapter: Language adapter to use. Defaults to Luganda.
        recognise_speakers: Enable speaker diarization. Defaults to False.
        whisper: Use Whisper model for transcription. Defaults to False.
        db: Database session.
        current_user: The authenticated user.
        service: The STT service instance.

    Returns:
        STTTranscript containing the transcription results.

    Raises:
        BadRequestError: If audio processing fails.
        ExternalServiceError: If transcription service fails.
    """
    try:
        result = await service.transcribe_from_gcs(
            gcs_blob_name=gcs_blob_name,
            language=language.value,
            adapter=adapter.value,
            whisper=whisper,
            recognise_speakers=recognise_speakers,
        )

        # Save transcription to DB if valid
        audio_transcription_id = None
        if result.transcription and len(result.transcription) > 0:
            try:
                db_audio_transcription = await create_audio_transcription(
                    db,
                    current_user,
                    result.audio_url,
                    result.blob_name,
                    result.transcription,
                    language.value,
                )
                audio_transcription_id = db_audio_transcription.id
                logging.info(
                    f"Transcription saved to DB with ID: {audio_transcription_id}"
                )
            except Exception as e:
                logging.error(f"Database error: {str(e)}")

        # Endpoint usage logging is handled automatically by MonitoringMiddleware

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

        # Add warning headers if audio was trimmed
        if result.was_trimmed:
            return Response(
                content=response.model_dump_json(),
                media_type="application/json",
            )

        return response

    except AudioProcessingError as e:
        raise BadRequestError(message=str(e))
    except TranscriptionError as e:
        raise ExternalServiceError(
            service_name="STT Transcription Service",
            message=str(e),
        )
    except (BadRequestError, ExternalServiceError):
        raise
    except Exception as e:
        logging.error(f"Unexpected error in speech_to_text_from_gcs: {str(e)}")
        raise ExternalServiceError(
            service_name="STT Service",
            message="An unexpected error occurred while processing your request",
            original_error=str(e),
        )


@router.post("/stt")
@limiter.limit(get_account_type_limit)
async def speech_to_text(
    request: Request,
    audio: UploadFile = File(..., description="Audio file to transcribe"),
    language: SttbLanguage = Form(SttbLanguage.luganda),
    adapter: SttbLanguage = Form(SttbLanguage.luganda),
    recognise_speakers: bool = Form(False),
    whisper: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    service: STTService = Depends(get_service),
) -> STTTranscript:
    """Upload an audio file and get the transcription text.

    Upload an audio file for transcription. Supports various audio formats
    including MP3, WAV, OGG, M4A, and AAC.

    Limitations:
        - Maximum audio duration: Files longer than 10 minutes will be trimmed
        - Supported formats: MP3, WAV, OGG, M4A, AAC
        - Large files are supported but only first 10 minutes will be transcribed

    Note:
        For files larger than 100MB, please use chunked upload or consider
        splitting the audio file.

    Args:
        request: The FastAPI request object.
        audio: The uploaded audio file.
        language: Target language for transcription. Defaults to Luganda.
        adapter: Language adapter to use. Defaults to Luganda.
        recognise_speakers: Enable speaker diarization. Defaults to False.
        whisper: Use Whisper model for transcription. Defaults to False.
        db: Database session.
        current_user: The authenticated user.
        service: The STT service instance.

    Returns:
        STTTranscript containing the transcription results.

    Raises:
        ValidationError: If audio file validation fails.
        BadRequestError: If audio processing fails.
        ExternalServiceError: If transcription service fails.
    """
    start_time = time.time()

    try:
        # Validate file type
        content_type = audio.content_type
        file_extension = get_audio_extension(audio.filename)

        try:
            service.validate_audio_file(content_type, file_extension)
        except AudioValidationError as e:
            raise ValidationError(
                message=str(e),
                errors=[
                    {
                        "field": "audio",
                        "value": content_type,
                    }
                ],
            )

        # Create temporary file
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=file_extension
        ) as temp_file:
            file_path = temp_file.name
            # Stream the file in chunks to avoid memory issues
            async with aiofiles.open(file_path, "wb") as out_file:
                while content := await audio.read(CHUNK_SIZE):
                    await out_file.write(content)

        # Transcribe
        result = await service.transcribe_uploaded_file(
            file_path=file_path,
            file_extension=file_extension,
            language=language.value,
            adapter=adapter.value,
            whisper=whisper,
            recognise_speakers=recognise_speakers,
        )

        end_time = time.time()
        elapsed_time = end_time - start_time
        logging.info(f"Transcription completed in {elapsed_time:.2f} seconds")

        # Save transcription to database
        audio_transcription_id = None
        if result.transcription and len(result.transcription) > 0:
            try:
                db_audio_transcription = await create_audio_transcription(
                    db,
                    current_user,
                    result.audio_url,
                    result.blob_name,
                    result.transcription,
                    language.value,
                )
                audio_transcription_id = db_audio_transcription.id
                logging.info(
                    f"Transcription saved to database with ID: {audio_transcription_id}"
                )
            except Exception as e:
                logging.error(f"Database error: {str(e)}")

        # Endpoint usage logging is handled automatically by MonitoringMiddleware

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

        # Add warning header if audio was trimmed
        if result.was_trimmed:
            return Response(
                content=response.model_dump_json(),
                media_type="application/json",
            )

        return response

    except AudioProcessingError as e:
        raise BadRequestError(message=str(e))
    except TranscriptionError as e:
        raise ExternalServiceError(
            service_name="STT Transcription Service",
            message=str(e),
        )
    except (BadRequestError, ValidationError, ExternalServiceError):
        raise
    except Exception as e:
        logging.error(f"Unexpected error in speech_to_text: {str(e)}")
        raise ExternalServiceError(
            service_name="STT Service",
            message="An unexpected error occurred while processing your request",
            original_error=str(e),
        )


@router.post("/org/stt")
@limiter.limit(get_account_type_limit)
async def speech_to_text_org(
    request: Request,
    audio: UploadFile = File(...),
    recognise_speakers: bool = Form(False),
    current_user=Depends(get_current_user),
    service: STTService = Depends(get_service),
) -> STTTranscript:
    """Upload an audio file for organization transcription.

    Simplified endpoint for organization use cases. Automatically
    detects language and provides transcription with optional
    speaker diarization.

    Args:
        request: The FastAPI request object (required for rate limiting).
        audio: The uploaded audio file.
        recognise_speakers: Enable speaker diarization. Defaults to False.
        current_user: The authenticated user (enforces authentication).
        service: The STT service instance.

    Returns:
        STTTranscript containing the transcription results.

    Raises:
        BadRequestError: If audio processing fails.
        ServiceUnavailableError: If service times out.
        ExternalServiceError: If transcription service fails.
    """
    start_time = time.time()

    try:
        # Save uploaded file to temp location
        # Validate file type
        content_type = audio.content_type
        file_extension = get_audio_extension(audio.filename)

        try:
            service.validate_audio_file(content_type, file_extension)
        except AudioValidationError as e:
            raise ValidationError(
                message=str(e),
                errors=[
                    {
                        "field": "audio",
                        "value": content_type,
                    }
                ],
            )

        filename = secure_filename(audio.filename)
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        unique_file_name = f"{timestamp}_{filename}"
        file_path = os.path.join("/tmp", unique_file_name)

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(audio.file, buffer)

        # Transcribe
        result = await service.transcribe_org_audio(
            file_path=file_path,
            recognise_speakers=recognise_speakers,
        )

        end_time = time.time()
        elapsed_time = end_time - start_time
        logging.info(f"Org transcription completed in {elapsed_time:.2f} seconds")

        # Endpoint usage logging is handled automatically by MonitoringMiddleware

        return STTTranscript(
            audio_transcription=result.transcription,
            diarization_output=result.diarization_output,
            formatted_diarization_output=result.formatted_diarization_output,
        )

    except AudioProcessingError as e:
        raise BadRequestError(message=str(e))
    except TranscriptionError as e:
        raise ExternalServiceError(
            service_name="STT Transcription Service",
            message=str(e),
        )
    except TimeoutError:
        raise ServiceUnavailableError(message="Service unavailable due to timeout")
    except ConnectionError:
        raise ExternalServiceError(
            service_name="STT Service",
            message="Service unavailable due to connection error",
        )
    except Exception as e:
        logging.error(f"Unexpected error in speech_to_text_org: {str(e)}")
        raise ExternalServiceError(
            service_name="STT Service",
            message="An unexpected error occurred while processing your request",
            original_error=str(e),
        )
