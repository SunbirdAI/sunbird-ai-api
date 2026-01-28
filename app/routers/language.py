"""
Language Router Module.

This module defines the API endpoints for language identification and
classification operations. It provides endpoints for detecting the language
of text and audio content.

Endpoints:
    - POST /language_id: Identify language of text (auto-detection)
    - POST /classify_language: Classify language with confidence scores
    - POST /auto_detect_audio_language: Detect language from audio file

Architecture:
    Routes -> LanguageService -> RunPod API

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
import time

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, File, Request, UploadFile
from jose import jwt
from slowapi import Limiter
from werkzeug.utils import secure_filename

from app.core.exceptions import ExternalServiceError, ServiceUnavailableError
from app.deps import get_current_user
from app.schemas.language import (
    AudioDetectedLanguageResponse,
    LanguageIdRequest,
    LanguageIdResponse,
)
from app.services.language_service import (
    LanguageConnectionError,
    LanguageDetectionError,
    LanguageError,
    LanguageService,
    LanguageTimeoutError,
    get_language_service,
)
from app.utils.auth import ALGORITHM, SECRET_KEY

load_dotenv()
logging.basicConfig(level=logging.INFO)

router = APIRouter()


def custom_key_func(request: Request) -> str:
    """Extract account type from JWT token for rate limiting.

    Args:
        request: The FastAPI request object.

    Returns:
        The account type string or 'anonymous' if not found.
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


def get_service() -> LanguageService:
    """Dependency for getting the Language service instance.

    Returns:
        The LanguageService singleton instance.
    """
    return get_language_service()


@router.post(
    "/language_id",
    response_model=LanguageIdResponse,
)
async def language_id(
    languageId_request: LanguageIdRequest,
    current_user=Depends(get_current_user),
    service: LanguageService = Depends(get_service),
) -> dict:
    """Identify the language of a given text using auto-detection.

    This endpoint identifies the language of a given text. It supports a limited
    set of local languages including Acholi (ach), Ateso (teo), English (eng),
    Luganda (lug), Lugbara (lgg), and Runyankole (nyn).

    Args:
        languageId_request: The language identification request containing text.
        current_user: The authenticated user.
        service: The language service instance.

    Returns:
        LanguageIdResponse containing the identified language.

    Raises:
        ServiceUnavailableError: If the service times out.
        ExternalServiceError: If language identification service fails.

    Example:
        Request body:
        {
            "text": "Oli otya?"
        }

        Response:
        {
            "language": "lug"
        }
    """
    try:
        result = await service.identify_language(text=languageId_request.text)
        return {"language": result.language}

    except LanguageTimeoutError:
        logging.error("Language identification timed out")
        raise ServiceUnavailableError(
            message="The language identification job timed out. Please try again later."
        )
    except LanguageError as e:
        logging.error(f"Language identification error: {str(e)}")
        raise ExternalServiceError(
            service_name="Language Identification Service",
            message="An error occurred while processing the language identification request",
            original_error=str(e),
        )


@router.post(
    "/classify_language",
    response_model=LanguageIdResponse,
)
async def classify_language(
    languageId_request: LanguageIdRequest,
    current_user=Depends(get_current_user),
    service: LanguageService = Depends(get_service),
) -> dict:
    """Classify the language of a given text with confidence scores.

    This endpoint identifies the language of a given text using a
    classification model with probability scores. A language is only
    reported if confidence exceeds a threshold (default 0.9).

    It supports a limited set of local languages including Acholi (ach),
    Ateso (teo), English (eng), Luganda (lug), Lugbara (lgg), and
    Runyankole (nyn).

    Args:
        languageId_request: The language identification request containing text.
        current_user: The authenticated user.
        service: The language service instance.

    Returns:
        LanguageIdResponse containing the classified language.

    Raises:
        ServiceUnavailableError: If the service times out.
        ExternalServiceError: If language classification service fails or returns unexpected response format.

    Example:
        Request body:
        {
            "text": "Oli otya?"
        }

        Response:
        {
            "language": "lug"
        }

        If confidence is below threshold:
        {
            "language": "language not detected"
        }
    """
    try:
        result = await service.classify_language(text=languageId_request.text)
        return {"language": result.language}

    except LanguageTimeoutError:
        logging.error("Language classification timed out")
        raise ServiceUnavailableError(
            message="The language identification job timed out. Please try again later."
        )
    except LanguageDetectionError as e:
        logging.error(f"Language detection error: {str(e)}")
        raise ExternalServiceError(
            service_name="Language Identification Service",
            message="Unexpected response format from the language identification service",
            original_error=str(e),
        )
    except LanguageError as e:
        logging.error(f"Language classification error: {str(e)}")
        raise ExternalServiceError(
            service_name="Language Classification Service",
            message="An error occurred while processing the language identification request",
            original_error=str(e),
        )


@router.post(
    "/auto_detect_audio_language",
    response_model=AudioDetectedLanguageResponse,
)
@limiter.limit(get_account_type_limit)
async def auto_detect_audio_language(
    request: Request,
    audio: UploadFile = File(...),
    current_user=Depends(get_current_user),
    service: LanguageService = Depends(get_service),
) -> dict:
    """Detect the language of an audio file.

    Upload an audio file and detect the language of the spoken content.
    The audio file is uploaded to cloud storage for processing.

    Args:
        request: The FastAPI request object (required for rate limiting).
        audio: The audio file to analyze.
        current_user: The authenticated user.
        service: The language service instance.

    Returns:
        AudioDetectedLanguageResponse containing the detected language.

    Raises:
        ServiceUnavailableError: If the service times out.
        ExternalServiceError: If language detection service fails or has connection errors.

    Example:
        Response:
        {
            "detected_language": "lug"
        }
    """
    start_time = time.time()

    # Save uploaded file temporarily
    filename = secure_filename(audio.filename or "audio")
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    unique_file_name = f"{timestamp}_{filename}"
    file_path = os.path.join("/tmp", unique_file_name)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(audio.file, buffer)

        result = await service.detect_audio_language(file_path=file_path)

        end_time = time.time()
        elapsed_time = end_time - start_time
        logging.info(
            f"Audio language detection completed in {elapsed_time:.2f} seconds"
        )

        return {"detected_language": result.detected_language}

    except LanguageTimeoutError:
        logging.error("Audio language detection timed out")
        raise ServiceUnavailableError(message="Service unavailable due to timeout")
    except LanguageConnectionError:
        logging.error("Audio language detection connection error")
        raise ExternalServiceError(
            service_name="Language Detection Service",
            message="Service unavailable due to connection error",
        )
    except LanguageError as e:
        logging.error(f"Audio language detection error: {str(e)}")
        raise ExternalServiceError(
            service_name="Language Detection Service",
            message="Audio language detection error",
            original_error=str(e),
        )
    except Exception as e:
        logging.error(f"Unexpected error in auto_detect_audio_language: {str(e)}")
        raise ExternalServiceError(
            service_name="Language Detection Service",
            message="Internal server error",
            original_error=str(e),
        )
    finally:
        # Clean up temporary file
        if os.path.exists(file_path):
            os.remove(file_path)
