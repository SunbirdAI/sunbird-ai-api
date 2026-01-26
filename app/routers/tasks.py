import asyncio
import datetime
import hashlib
import json
import logging
import mimetypes
import os
import tempfile
import time
from typing import Any, Dict, Optional

import aiohttp
import requests
import runpod
from dotenv import load_dotenv
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from jose import jwt
from slowapi import Limiter
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.crud.audio_transcription import create_audio_transcription
from app.crud.monitoring import log_endpoint
from app.deps import get_current_user, get_db
from app.schemas.tasks import (
    ChatRequest,
    ChatResponse,
    SummarisationRequest,
    SummarisationResponse,
    TTSRequest,
)
from app.utils.auth import ALGORITHM, SECRET_KEY
from app.utils.upload_audio_file_gcp import upload_file_to_bucket

router = APIRouter()

load_dotenv()
logging.basicConfig(level=logging.INFO)

PER_MINUTE_RATE_LIMIT = os.getenv("PER_MINUTE_RATE_LIMIT", 10)
RUNPOD_ENDPOINT_ID = os.getenv("RUNPOD_ENDPOINT_ID")
# Set RunPod API Key
runpod.api_key = os.getenv("RUNPOD_API_KEY")

# Get feedback URL from environment
FEEDBACK_URL = os.getenv("FEEDBACK_URL")

# Inference type constants — use these when scheduling feedback saves so
# downstream systems can easily classify events.
INFERENCE_CHAT = "chat"
INFERENCE_TTS = "tts"


async def save_api_inference(
    source_text: Any,
    model_results: Any,
    username: Any,
    model_type: Optional[str] = None,
    processing_time: Optional[float] = None,
    inference_type: str = INFERENCE_CHAT,
    job_details: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Persist a compact, JSON-serializable inference record to the configured
    FEEDBACK_URL. This function is idempotent and non-blocking when scheduled
    via FastAPI BackgroundTasks.

    Inputs are deliberately permissive (Any) because callers pass strings,
    dicts or model objects. The function normalizes values to simple types.

    Returns True on a successful POST (2xx), False otherwise.
    """

    if not FEEDBACK_URL:
        logging.debug("FEEDBACK_URL not configured; skipping inference feedback save")
        return False

    # Timestamp in milliseconds
    timestamp = int(datetime.datetime.utcnow().timestamp() * 1000)

    # Normalize username to a short string identifier when possible
    username_str = None
    try:
        if hasattr(username, "id"):
            username_str = str(getattr(username, "id"))
        elif isinstance(username, dict) and username.get("id"):
            username_str = str(username.get("id"))
        elif isinstance(username, str):
            username_str = username
        else:
            # fallback to email/username attributes if present
            username_str = (
                getattr(username, "username", None)
                or getattr(username, "email", None)
                or str(username)
            )
    except Exception:
        username_str = str(username)

    # Serialize inputs safely
    def _serialize(v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, (str, int, float, bool)):
            return v
        try:
            return json.loads(json.dumps(v, ensure_ascii=False))
        except Exception:
            return str(v)

    source_serialized = _serialize(source_text)
    results_serialized = _serialize(model_results)

    payload: Dict[str, Any] = {
        "Timestamp": timestamp,
        "feedback": "api_inference",
        "SourceText": source_serialized,
        "ModelResults": results_serialized,
        "username": username_str,
        "FeedBackType": inference_type,
    }

    if model_type:
        payload["ModelType"] = model_type
    if processing_time is not None:
        payload["ProcessingTime"] = processing_time

    # Compact job details to avoid leaking large blobs
    if job_details and isinstance(job_details, dict):
        jd: Dict[str, Any] = {}
        # Common safe fields
        for k in ("job_id", "model_type", "blob", "sample_rate", "speaker_id"):
            if k in job_details:
                jd[k] = job_details.get(k)

        # For TTS keep a short hash of the source text instead of raw text
        if inference_type == INFERENCE_TTS:
            try:
                text_val = (
                    source_serialized
                    if isinstance(source_serialized, str)
                    else json.dumps(source_serialized, ensure_ascii=False)
                )
                jd.setdefault(
                    "text_hash", hashlib.sha256(text_val.encode("utf-8")).hexdigest()
                )
            except Exception:
                pass

        if jd:
            payload["JobDetails"] = jd

    logging.info(
        f"Saving inference feedback for user: {username_str}, type: {inference_type}"
    )
    logging.debug(f"Feedback payload (truncated): {json.dumps(payload)[:1000]}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=8),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
        reraise=True,
    )
    async def _post_feedback(p: Dict[str, Any]) -> bool:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                FEEDBACK_URL, json=p, headers={"Content-Type": "application/json"}
            ) as resp:
                text = await resp.text()
                if 200 <= resp.status < 300:
                    logging.info("Inference feedback saved successfully")
                    return True
                logging.warning(
                    f"Feedback save failed status={resp.status} body={text}"
                )
                return False

    try:
        return await _post_feedback(payload)
    except Exception as e:
        logging.error(f"Failed to save inference feedback after retries: {e}")
        return False


def custom_key_func(request: Request):
    header = request.headers.get("Authorization")
    if not header:
        return "anonymous"
    _, _, token = header.partition(" ")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        account_type: str = payload.get("account_type", "")
        logging.info(f"account_type: {account_type}")
        return account_type or ""
    except Exception:
        return ""


def get_account_type_limit(key: str) -> str:
    if not key:
        return "50/minute"
    if key.lower() == "admin":
        return "1000/minute"
    if key.lower() == "premium":
        return "100/minute"
    return "50/minute"


# Initialize the Limiter
limiter = Limiter(key_func=custom_key_func)


def get_endpoint_details(endpoint_id: str):
    url = f"https://rest.runpod.io/v1/endpoints/{endpoint_id}"
    headers = {"Authorization": f"Bearer {os.getenv('RUNPOD_API_KEY')}"}
    response = requests.get(url, headers=headers)
    details = response.json()

    return details


endpoint_details = get_endpoint_details(RUNPOD_ENDPOINT_ID)
logging.info(f"Endpoint details: {endpoint_details}")


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
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    This endpoint does anonymised summarisation of a given text. The text languages
    supported for now are English (eng) and Luganda (lug).
    """

    endpoint = runpod.Endpoint(RUNPOD_ENDPOINT_ID)
    request_response = {}
    user = current_user
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

    # Log endpoint in database
    await log_endpoint(db, user, request, start_time, end_time)

    # Calculate the elapsed time
    elapsed_time = end_time - start_time
    logging.info(f"Elapsed time: {elapsed_time} seconds")

    return request_response


# Route for the text-to-speech endpoint
@router.post(
    "/tts",
)
@limiter.limit(get_account_type_limit)
async def text_to_speech(
    request: Request,
    tts_request: TTSRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Endpoint for text-to-speech conversion.
    Converts input text to speech audio using a specified speaker voice.

    Args:
        request (Request): The incoming HTTP request object.
        tts_request (TTSRequest): The request body containing text, speaker ID, and synthesis parameters.
        db (AsyncSession, optional): Database session dependency.
        current_user (User, optional): The authenticated user making the request.

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
    # Log endpoint in database
    await log_endpoint(db, user, request, start_time, end_time)
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
