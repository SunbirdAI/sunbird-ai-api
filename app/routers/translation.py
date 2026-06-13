"""
Translation Router Module.

POST /tasks/translate translates text between 32 Ugandan and East African
languages using the Sunflower model — the same inference engine that powers
/tasks/chat/completions. The legacy NLLB code path
(TranslationService.translate) remains in the codebase but is no longer used
by this endpoint.

Architecture:
    Routes -> TranslationService.translate_via_sunflower -> InferenceService
    -> RunPod OpenAI-compatible API (Sunflower-14B)

Spec:
    docs/superpowers/specs/2026-06-12-translate-via-sunflower-design.md
"""

import logging
import time

from dotenv import load_dotenv
from fastapi import APIRouter, BackgroundTasks, Request

from app.core.exceptions import (
    BadRequestError,
    ExternalServiceError,
    ServiceUnavailableError,
)
from app.deps import CurrentUserDep, DbDep, QuotaServiceDep, TranslationServiceDep
from app.schemas.chat import DEFAULT_MODEL
from app.schemas.translation import (
    SunflowerTranslationRequest,
    WorkerTranslationResponse,
)
from app.services.inference_service import InferenceTimeoutError, ModelLoadingError
from app.utils.feedback import INFERENCE_TYPES, save_api_inference
from app.utils.languages import UnsupportedLanguageError, resolve_language
from app.utils.quota_guard import check_quota
from app.utils.rate_limit import get_account_type_limit, limiter

load_dotenv()
logging.basicConfig(level=logging.INFO)

router = APIRouter()


@router.post(
    "/translate",
    response_model=WorkerTranslationResponse,
)
@limiter.limit(get_account_type_limit)
async def translate(  # noqa: C901
    request: Request,
    translation_request: SunflowerTranslationRequest,
    quota: QuotaServiceDep,
    background_tasks: BackgroundTasks,
    db: DbDep,
    current_user: CurrentUserDep,
    service: TranslationServiceDep,
) -> dict:
    """Translate text between supported languages using the Sunflower model.

    Languages are accepted as ISO 639-3 codes (e.g. ``lug``) or full names
    (e.g. ``Luganda``), case-insensitively. ``source_language`` is optional —
    when omitted, Sunflower infers the source language from the text.
    Translation works between any pair of supported languages.

    Supported languages: Acholi (ach), Alur (alz), Aringa (luc), Ateso (teo),
    Bari (bfa), English (eng), Jopadhola (adh), Kakwa (keo),
    Karamojong (kdj), Kinyarwanda (kin), Kumam (kdi), Kupsabiny (kpz),
    Kwamba (rwm), Lango (laj), Lubwisi (tlj), Luganda (lug), Lugbara (lgg),
    Lugungu (rub), Lugwere (gwr), Lumasaba (myx), Lunyole (nuj),
    Lusoga (xog), Ma'di (mhi), Pokot (pok), Rukiga (cgg), Rukonjo (koo),
    Runyankole (nyn), Runyoro (nyo), Ruruuli (ruc), Rutooro (ttj),
    Samia (lsm), Swahili (swa).

    Example:

        Request body:
        {
            "source_language": "eng",
            "target_language": "lug",
            "text": "Hello, how are you?"
        }

        Response:
        {
            "id": "trans-1a2b3c...",
            "status": "COMPLETED",
            "output": {
                "translated_text": "Oli otya?",
                "source_language": "eng",
                "target_language": "lug"
            }
        }

    Raises:

        BadRequestError: Unsupported language, or source == target.
        ServiceUnavailableError: Model loading or inference timeout.
        ExternalServiceError: Empty model output or unexpected failure.
    """
    await check_quota(quota, db, current_user)

    try:
        target = resolve_language(translation_request.target_language)
        source = (
            resolve_language(translation_request.source_language)
            if translation_request.source_language is not None
            else None
        )
    except UnsupportedLanguageError as e:
        raise BadRequestError(message=str(e))

    if source is not None and source.code == target.code:
        raise BadRequestError(message="Source and target languages must be different")

    start_time = time.time()

    try:
        result = await service.translate_via_sunflower(
            text=translation_request.text,
            target_language=target,
            source_language=source,
        )
    except ModelLoadingError as e:
        logging.error(f"Model loading error during translation: {e}")
        raise ServiceUnavailableError(
            message=(
                "The AI model is currently loading. This usually takes "
                "2-3 minutes. Please try again shortly."
            )
        )
    except InferenceTimeoutError as e:
        logging.error(f"Translation timed out: {e}")
        raise ServiceUnavailableError(
            message="The request timed out. Please try again with a shorter text."
        )
    except ValueError as e:
        logging.error(f"Invalid translation request: {e}")
        raise BadRequestError(message=f"Invalid request: {str(e)}")
    except Exception as e:
        logging.error(f"Unexpected error during translation: {e}")
        raise ExternalServiceError(
            service_name="Sunflower Translation Service",
            message=(
                "An unexpected error occurred during translation. " "Please try again."
            ),
            original_error=str(e),
        )

    if not result.translated_text:
        raise ExternalServiceError(
            service_name="Sunflower Model",
            message=(
                "The model returned an empty response. "
                "Please try rephrasing your request."
            ),
        )

    elapsed_time = time.time() - start_time
    logging.info(f"Translation completed in {elapsed_time:.2f} seconds")

    response_payload = WorkerTranslationResponse(
        id=result.job_id,
        status="COMPLETED",
        output={
            "translated_text": result.translated_text,
            "source_language": result.source_language,
            "target_language": result.target_language,
        },
    ).model_dump()

    try:
        job_details = {
            "source_language": result.source_language,
            "target_language": result.target_language,
            "job_id": result.job_id,
        }
        background_tasks.add_task(
            save_api_inference,
            translation_request.text,
            response_payload,
            current_user,
            model_type=DEFAULT_MODEL,
            processing_time=elapsed_time,
            inference_type=INFERENCE_TYPES["translation"],
            job_details={k: v for k, v in job_details.items() if v is not None},
        )
    except Exception as e:
        logging.warning(f"Failed to schedule translation feedback save task: {e}")

    return response_payload
