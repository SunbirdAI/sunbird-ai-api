"""
Translation Router Module.

This module defines the API endpoints for text translation operations.
It provides endpoints for translating text between supported languages
using the NLLB model.

Endpoints:
    - POST /translate: Translate text between languages

Architecture:
    Routes → TranslationService → RunPod API

Usage:
    This router is included in the main application with the /tasks prefix
    to maintain backward compatibility with existing API consumers.

Note:
    This module was extracted from app/routers/tasks.py as part of the
    services layer refactoring to improve modularity.
"""

import logging
import time

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Request
from jose import jwt
from slowapi import Limiter
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.monitoring import log_endpoint
from app.deps import get_current_user, get_db
from app.schemas.translation import NllbTranslationRequest, WorkerTranslationResponse
from app.services.translation_service import (
    TranslationConnectionError,
    TranslationError,
    TranslationService,
    TranslationTimeoutError,
    TranslationValidationError,
    get_translation_service,
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


def get_service() -> TranslationService:
    """Dependency for getting the Translation service instance.

    Returns:
        The TranslationService singleton instance.
    """
    return get_translation_service()


@router.post(
    "/translate",
    response_model=WorkerTranslationResponse,
)
@limiter.limit(get_account_type_limit)
async def translate(
    request: Request,
    translation_request: NllbTranslationRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    service: TranslationService = Depends(get_service),
) -> dict:
    """Translate text between languages using NLLB model.

    Source and Target Language can be one of:
    - ach (Acholi)
    - teo (Ateso)
    - eng (English)
    - lug (Luganda)
    - lgg (Lugbara)
    - nyn (Runyankole)

    We currently only support English to Local languages and Local to English
    translations. When the source language is one of the listed languages,
    the target can be any of the other languages.

    Args:
        request: The FastAPI request object.
        translation_request: The translation request containing source/target
            languages and text to translate.
        db: Database session.
        current_user: The authenticated user.
        service: The translation service instance.

    Returns:
        WorkerTranslationResponse containing the translation result.

    Raises:
        HTTPException: 503 if service is unavailable (timeout/connection error).
        HTTPException: 500 for internal server errors.

    Example:
        Request body:
        {
            "source_language": "eng",
            "target_language": "lug",
            "text": "Hello, how are you?"
        }

        Response:
        {
            "id": "job-123",
            "status": "COMPLETED",
            "output": {
                "translated_text": "Oli otya?",
                "source_language": "eng",
                "target_language": "lug"
            }
        }
    """
    start_time = time.time()

    try:
        # Perform translation
        result = await service.translate(
            text=translation_request.text,
            source_language=translation_request.source_language.value,
            target_language=translation_request.target_language.value,
        )

        end_time = time.time()
        elapsed_time = end_time - start_time
        logging.info(f"Translation completed in {elapsed_time:.2f} seconds")

        # Log endpoint usage
        try:
            await log_endpoint(db, current_user, request, start_time, end_time)
        except Exception as e:
            logging.error(f"Failed to log endpoint usage: {str(e)}")

        # Validate and return response
        if result.raw_response:
            worker_resp = service.validate_and_parse_response(result.raw_response)
            return worker_resp.model_dump()

        # Fallback response if raw_response is missing
        return WorkerTranslationResponse(
            status=result.status,
            id=result.job_id,
            output={
                "translated_text": result.translated_text,
                "source_language": result.source_language,
                "target_language": result.target_language,
            },
        ).model_dump()

    except TranslationTimeoutError as e:
        logging.error(f"Translation timeout: {str(e)}")
        raise HTTPException(
            status_code=503, detail="Service unavailable due to timeout."
        )
    except TranslationConnectionError as e:
        logging.error(f"Translation connection error: {str(e)}")
        raise HTTPException(
            status_code=503, detail="Service unavailable due to connection error."
        )
    except TranslationValidationError as e:
        logging.error(f"Translation validation error: {str(e)}")
        raise HTTPException(status_code=500, detail="Invalid response from worker")
    except TranslationError as e:
        logging.error(f"Translation error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Unexpected error in nllb_translate: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
