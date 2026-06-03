import json
import logging
import os
import time

import requests
import runpod
from dotenv import load_dotenv
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    Response,
)
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.crud.audio_transcription import create_audio_transcription
from app.deps import QuotaServiceDep, get_current_user, get_db
from app.schemas.tasks import (
    ChatRequest,
    ChatResponse,
    SummarisationRequest,
    SummarisationResponse,
    TTSRequest,
)
from app.utils.deprecation import SUCCESSOR_SPEECH, add_deprecation_headers
from app.utils.feedback import INFERENCE_TYPES, save_api_inference
from app.utils.quota_guard import check_quota
from app.utils.rate_limit import get_account_type_limit, limiter
from app.utils.upload_audio_file_gcp import upload_file_to_bucket

router = APIRouter()

load_dotenv()
logging.basicConfig(level=logging.INFO)

PER_MINUTE_RATE_LIMIT = os.getenv("PER_MINUTE_RATE_LIMIT", 10)
RUNPOD_ENDPOINT_ID = os.getenv("RUNPOD_ENDPOINT_ID")
# Set RunPod API Key
runpod.api_key = os.getenv("RUNPOD_API_KEY")

# Inference type constants — preserved for backward-compatible imports.
INFERENCE_CHAT = INFERENCE_TYPES["chat"]
INFERENCE_TTS = INFERENCE_TYPES["tts"]


def get_endpoint_details(endpoint_id: str):
    """Fetch RunPod endpoint details from the API.

    Args:
        endpoint_id: The RunPod endpoint ID.

    Returns:
        dict: Endpoint details from the RunPod API.

    Raises:
        requests.exceptions.RequestException: If the API call fails.
    """
    url = f"https://rest.runpod.io/v1/endpoints/{endpoint_id}"
    headers = {"Authorization": f"Bearer {os.getenv('RUNPOD_API_KEY')}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    details = response.json()

    return details


# Try to fetch endpoint details for logging, but don't fail module import if it fails
# This allows the application to start even if RunPod API is unavailable
try:
    if RUNPOD_ENDPOINT_ID and os.getenv("RUNPOD_API_KEY"):
        endpoint_details = get_endpoint_details(RUNPOD_ENDPOINT_ID)
        logging.info(f"RunPod endpoint details fetched: {endpoint_details}")
    else:
        logging.warning(
            "RUNPOD_ENDPOINT_ID or RUNPOD_API_KEY not set - skipping endpoint details fetch"
        )
except Exception as e:
    logging.warning(
        f"Failed to fetch RunPod endpoint details: {e}. "
        "This is not critical - the application will continue to function."
    )


@retry(
    stop=stop_after_attempt(3),  # Retry up to 3 times
    wait=wait_exponential(
        min=1, max=60
    ),  # Exponential backoff starting at 1s up to 60s
    retry=retry_if_exception_type(
        (TimeoutError, ConnectionError)
    ),  # Retry on these exceptions
    reraise=True,  # Reraise the exception if all retries fail
)
async def call_endpoint_with_retry(endpoint, data):
    return endpoint.run_sync(data, timeout=600)  # Timeout in seconds


@router.post(
    "/summarise",
    response_model=SummarisationResponse,
)
@limiter.limit(get_account_type_limit)
async def summarise(
    request: Request,
    input_text: SummarisationRequest,
    quota: QuotaServiceDep,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    This endpoint does anonymised summarisation of a given text. The text languages
    supported for now are English (eng) and Luganda (lug).
    """
    await check_quota(quota, db, current_user)
    endpoint = runpod.Endpoint(RUNPOD_ENDPOINT_ID)
    request_response = {}
    data = {
        "input": {
            "task": "summarise",
            "text": input_text.text,
        }
    }

    start_time = time.time()

    try:
        request_response = await call_endpoint_with_retry(endpoint, data)
        logging.info(f"Response: {request_response}")
    except TimeoutError as e:
        logging.error(f"Job timed out: {str(e)}")
        raise HTTPException(
            status_code=503, detail="Service unavailable due to timeout."
        )
    except ConnectionError as e:
        logging.error(f"Connection lost: {str(e)}")
        raise HTTPException(
            status_code=503, detail="Service unavailable due to connection error."
        )

    end_time = time.time()

    # Endpoint usage logging is handled automatically by MonitoringMiddleware

    # Calculate the elapsed time
    elapsed_time = end_time - start_time
    logging.info(f"Elapsed time: {elapsed_time} seconds")

    return request_response


# Route for the text-to-speech endpoint
@router.post(
    "/tts",
    deprecated=True,
)
@limiter.limit(get_account_type_limit)
async def text_to_speech(  # noqa: C901
    request: Request,
    tts_request: TTSRequest,
    quota: QuotaServiceDep,
    background_tasks: BackgroundTasks,
    http_response: Response,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    **DEPRECATED**: This endpoint is maintained for backward compatibility only.

    Please use the new endpoint at `/tasks/runpod/tts` instead.

    Legacy RunPod text-to-speech endpoint.
    Converts input text to speech audio using a specified speaker voice.

    Args:
        request (Request): The incoming HTTP request object (required for rate limiting).
        tts_request (TTSRequest): The request body containing text, speaker ID, and synthesis parameters.
        background_tasks (BackgroundTasks): FastAPI background tasks for logging.
        current_user (User): The authenticated user making the request.

    Returns:
        dict: A dictionary containing the generated speech audio with signed URL and metadata.

    Raises:
        HTTPException: Returns 503 if the service is unavailable due to timeout or connection error.
        HTTPException: Returns 500 for any other internal server errors.

    Speaker IDs:
        241: Acholi (female)
        242: Ateso (female)
        243: Runyankore (female)
        245: Lugbara (female)
        246: Swahili (male)
        248: Luganda (female)

    Example Response:
        {
            "output": {
                "audio_url": "https:...",
                "blob": "tts/20251003082338_f2ff97b3-9cb9-42fb-850d-0657f51e539e.mp3",
                "sample_rate": 16000
            }
        }
    """
    await check_quota(quota, db, current_user)
    logging.warning(
        "Deprecated endpoint /tasks/tts called; use POST /tasks/audio/speech"
    )
    add_deprecation_headers(http_response, SUCCESSOR_SPEECH)

    endpoint = runpod.Endpoint(RUNPOD_ENDPOINT_ID)
    user = current_user

    text = tts_request.text
    # Validate inputs early and return informative 4xx errors
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(
            status_code=400,
            detail="`text` is required for TTS and must be a non-empty string",
        )

    # Limit text size to avoid worker-side errors
    MAX_TTS_CHARS = 10000
    if len(text) > MAX_TTS_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"`text` is too long for TTS (max {MAX_TTS_CHARS} characters)",
        )

    # Validate speaker_id, temperature and token limits
    try:
        speaker_id_val = tts_request.speaker_id.value
    except Exception:
        raise HTTPException(
            status_code=400, detail="Invalid or missing `speaker_id` in TTS request"
        )

    try:
        temperature = float(tts_request.temperature)
        if not (0.0 <= temperature <= 2.0):
            raise HTTPException(
                status_code=400, detail="`temperature` must be between 0.0 and 2.0"
            )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid `temperature` value")

    try:
        max_new_audio_tokens = int(tts_request.max_new_audio_tokens)
        if max_new_audio_tokens < 1:
            raise HTTPException(
                status_code=400, detail="`max_new_audio_tokens` must be >= 1"
            )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=400, detail="Invalid `max_new_audio_tokens` value"
        )

    # Data to be sent in the request body
    data = {
        "input": {
            "task": "tts",
            "text": text.strip(),  # Remove leading/trailing spaces
            "speaker_id": speaker_id_val,
            "temperature": temperature,
            "max_new_audio_tokens": max_new_audio_tokens,
        }
    }

    start_time = time.time()
    try:
        request_response = await call_endpoint_with_retry(endpoint, data)
    except TimeoutError as e:
        logging.error(f"Job timed out: {str(e)}")
        raise HTTPException(
            status_code=503, detail="Service unavailable due to timeout"
        )
    except ConnectionError as e:
        logging.error(f"Connection lost: {str(e)}")
        raise HTTPException(
            status_code=503, detail="Service unavailable due to connection error"
        )
    except ValueError as e:
        # Worker reported a bad request / invalid input
        logging.error(f"Bad request to worker: {e}")
        raise HTTPException(
            status_code=400, detail=f"Invalid request to TTS worker: {e}"
        )
    except Exception as e:
        logging.exception("Unexpected error when calling TTS worker")
        raise HTTPException(status_code=502, detail=f"TTS worker error: {str(e)}")

    end_time = time.time()
    # Endpoint usage logging is handled automatically by MonitoringMiddleware

    logging.info(f"Response: {request_response}")

    # Calculate the elapsed time
    elapsed_time = end_time - start_time
    logging.info(f"Elapsed time: {elapsed_time} seconds")

    response = {}
    response["output"] = request_response

    # Schedule saving minimal TTS inference details for reproducibility (best-effort)
    try:
        # Normalize job details from the worker response if present
        job_info = {}
        # worker returns structure like {"audio_url":..., "blob":..., "sample_rate":...}
        if isinstance(request_response, dict):
            out = request_response.get("output") or request_response
            if isinstance(out, dict):
                # prefer canonical keys
                job_info["blob"] = (
                    out.get("blob") or out.get("output_blob") or out.get("audio_blob")
                )
                job_info["sample_rate"] = out.get("sample_rate")
                # include job_id if the worker provided it
                job_info["job_id"] = out.get("job_id") or request_response.get("job_id")
                # also include audio_url if provided
                job_info["audio_url"] = out.get("audio_url") or out.get("url")
        # include speaker id
        try:
            job_info["speaker_id"] = tts_request.speaker_id.value
        except Exception:
            pass

        # Safely convert model results for background task: keep as dict or string
        model_results_to_save = request_response
        try:
            if not isinstance(model_results_to_save, (dict, list, str)):
                model_results_to_save = json.loads(
                    json.dumps(model_results_to_save, ensure_ascii=False)
                )
        except Exception:
            model_results_to_save = str(model_results_to_save)

        background_tasks.add_task(
            save_api_inference,
            tts_request.text,
            model_results_to_save,
            user,
            model_type=(
                tts_request.speaker_id.name
                if hasattr(tts_request.speaker_id, "name")
                else None
            ),
            processing_time=(end_time - start_time),
            inference_type=INFERENCE_TTS,
            job_details=job_info,
        )
    except Exception as e:
        logging.warning(f"Failed to schedule TTS feedback save task: {e}")

    return response
