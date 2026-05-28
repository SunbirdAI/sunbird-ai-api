"""
RunPod Text-to-Speech Router.

This module provides TTS endpoints using the RunPod inference server.
Handles text-to-speech conversion with various speaker voices for Ugandan languages.

Endpoints:
    POST /tasks/runpod/tts - Convert text to speech audio
"""

import json
import logging
import os
import time

import runpod
from dotenv import load_dotenv
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.exceptions import (
    BadRequestError,
    ExternalServiceError,
    ServiceUnavailableError,
    ValidationError,
)
from app.deps import get_current_user
from app.schemas.tasks import TTSRequest
from app.utils.feedback import INFERENCE_TYPES, save_api_inference
from app.utils.rate_limit import get_account_type_limit, limiter

router = APIRouter()

load_dotenv()
logging.basicConfig(level=logging.INFO)

PER_MINUTE_RATE_LIMIT = os.getenv("PER_MINUTE_RATE_LIMIT", 10)
RUNPOD_ENDPOINT_ID = os.getenv("RUNPOD_ENDPOINT_ID")
# Set RunPod API Key
runpod.api_key = os.getenv("RUNPOD_API_KEY")

# Inference type constant — RunPod TTS uses the legacy "tts" classifier so
# existing dashboards keep working unchanged.
INFERENCE_TTS = INFERENCE_TYPES["tts"]


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
    "/tts",
)
@limiter.limit(get_account_type_limit)
async def text_to_speech(
    request: Request,
    tts_request: TTSRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
):
    """
    RunPod Text-to-Speech endpoint.
    Converts input text to speech audio using a specified speaker voice.

    This endpoint uses the RunPod inference server for TTS generation.

    Args:

        request (Request): The incoming HTTP request object (required for rate limiting).
        tts_request (TTSRequest): The request body containing text, speaker ID, and synthesis parameters.
        background_tasks (BackgroundTasks): FastAPI background tasks for logging.
        current_user (User): The authenticated user making the request.

    Returns:

        dict: A dictionary containing the generated speech audio with signed URL and metadata.

    Raises:

        BadRequestError: For invalid input parameters.
        ValidationError: For invalid speaker_id, temperature, or max_new_audio_tokens.
        ServiceUnavailableError: If the service is unavailable due to timeout.
        ExternalServiceError: For connection errors or worker errors.

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
        raise BadRequestError(
            message="`text` is required for TTS and must be a non-empty string"
        )

    # Limit text size to avoid worker-side errors
    MAX_TTS_CHARS = 10000
    if len(text) > MAX_TTS_CHARS:
        raise BadRequestError(
            message=f"`text` is too long for TTS (max {MAX_TTS_CHARS} characters)"
        )

    # Validate speaker_id, temperature and token limits
    try:
        speaker_id_val = tts_request.speaker_id.value
    except Exception:
        raise ValidationError(
            message="Invalid or missing `speaker_id` in TTS request",
            field="speaker_id",
        )

    try:
        temperature = float(tts_request.temperature)
        if not (0.0 <= temperature <= 2.0):
            raise ValidationError(
                message="`temperature` must be between 0.0 and 2.0",
                field="temperature",
                value=str(temperature),
            )
    except ValidationError:
        raise
    except Exception:
        raise ValidationError(
            message="Invalid `temperature` value",
            field="temperature",
        )

    try:
        max_new_audio_tokens = int(tts_request.max_new_audio_tokens)
        if max_new_audio_tokens < 1:
            raise ValidationError(
                message="`max_new_audio_tokens` must be >= 1",
                field="max_new_audio_tokens",
                value=str(max_new_audio_tokens),
            )
    except ValidationError:
        raise
    except Exception:
        raise ValidationError(
            message="Invalid `max_new_audio_tokens` value",
            field="max_new_audio_tokens",
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
        raise ServiceUnavailableError(message="Service unavailable due to timeout")
    except ConnectionError as e:
        logging.error(f"Connection lost: {str(e)}")
        raise ExternalServiceError(
            service_name="RunPod TTS Service",
            message="Service unavailable due to connection error",
            original_error=str(e),
        )
    except ValueError as e:
        # Worker reported a bad request / invalid input
        logging.error(f"Bad request to worker: {e}")
        raise BadRequestError(message=f"Invalid request to TTS worker: {e}")
    except Exception as e:
        logging.exception("Unexpected error when calling TTS worker")
        raise ExternalServiceError(
            service_name="RunPod TTS Worker",
            message="TTS worker error",
            original_error=str(e),
        )

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
