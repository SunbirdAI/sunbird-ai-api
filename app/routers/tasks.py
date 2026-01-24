import asyncio
import datetime
import hashlib
import json
import logging
import mimetypes
import os
import shutil
import tempfile
import time
import uuid
from datetime import timedelta
from typing import Any, Dict, Optional

import aiohttp
import requests
import runpod
from dotenv import load_dotenv
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from google.cloud import storage
from jose import jwt
from slowapi import Limiter
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from werkzeug.utils import secure_filename

from app.crud.audio_transcription import create_audio_transcription
from app.crud.monitoring import log_endpoint
from app.deps import get_current_user, get_db
from app.inference_services.user_preference import get_user_preference
from app.inference_services.whatsapp_service import WhatsAppService
from app.schemas.tasks import (
    AudioDetectedLanguageResponse,
    ChatRequest,
    ChatResponse,
    LanguageIdRequest,
    LanguageIdResponse,
    SummarisationRequest,
    SummarisationResponse,
    TTSRequest,
    UploadRequest,
    UploadResponse,
)
from app.services.inference_service import (
    ModelLoadingError,
    SunflowerChatMessage,
    SunflowerChatRequest,
    SunflowerChatResponse,
    SunflowerUsageStats,
    run_inference,
)
from app.services.message_processor import OptimizedMessageProcessor, ResponseType
from app.utils.auth_utils import ALGORITHM, SECRET_KEY
from app.utils.upload_audio_file_gcp import upload_audio_file, upload_file_to_bucket

router = APIRouter()

load_dotenv()
logging.basicConfig(level=logging.INFO)

PER_MINUTE_RATE_LIMIT = os.getenv("PER_MINUTE_RATE_LIMIT", 10)
RUNPOD_ENDPOINT_ID = os.getenv("RUNPOD_ENDPOINT_ID")
# Set RunPod API Key
runpod.api_key = os.getenv("RUNPOD_API_KEY")

# Access token for your app
whatsapp_token = os.getenv("WHATSAPP_TOKEN")
verify_token = os.getenv("VERIFY_TOKEN")

whatsapp_service = WhatsAppService(
    token=whatsapp_token, phone_number_id=os.getenv("PHONE_NUMBER_ID")
)

# Initialize processor
processor = OptimizedMessageProcessor()

processed_messages = set()

languages_obj = {
    "1": "lug",
    "2": "ach",
    "3": "teo",
    "4": "lgg",
    "5": "nyn",
    "6": "eng",
    "7": "lug",
    "8": "ach",
    "9": "teo",
    "10": "lgg",
    "11": "nyn",
}

# Get feedback URL from environment
FEEDBACK_URL = os.getenv("FEEDBACK_URL")

# Inference type constants — use these when scheduling feedback saves so
# downstream systems can easily classify events.
INFERENCE_CHAT = "chat"
INFERENCE_TTS = "tts"
INFERENCE_SUNFLOWER_CHAT = "sunflower_chat"
INFERENCE_SUNFLOWER_SIMPLE = "sunflower_simple"


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


# Route for the Language identification endpoint
@router.post(
    "/language_id",
    response_model=LanguageIdResponse,
)
async def language_id(
    languageId_request: LanguageIdRequest, current_user=Depends(get_current_user)
):
    """
    This endpoint identifies the language of a given text. It supports a limited
    set of local languages including Acholi (ach), Ateso (teo), English (eng),
    Luganda (lug), Lugbara (lgg), and Runyankole (nyn).
    """

    endpoint = runpod.Endpoint(RUNPOD_ENDPOINT_ID)
    request_response = {}

    try:
        request_response = endpoint.run_sync(
            {
                "input": {
                    "task": "auto_detect_language",
                    "text": languageId_request.text,
                }
            },
            timeout=60,  # Timeout in seconds.
        )

        # Log the request for debugging purposes
        logging.info(f"Request response: {request_response}")

    except TimeoutError:
        # Handle timeout error and return a meaningful message to the user
        logging.error("Job timed out.")
        raise HTTPException(
            status_code=408,
            detail="The language identification job timed out. Please try again later.",
        )

    return request_response


# Route for the Language identification endpoint
@router.post(
    "/classify_language",
    response_model=LanguageIdResponse,
)
async def classify_language(
    languageId_request: LanguageIdRequest, current_user=Depends(get_current_user)
):
    """
    This endpoint identifies the language of a given text. It supports a limited
    set of local languages including Acholi (ach), Ateso (teo), English (eng),
    Luganda (lug), Lugbara (lgg), and Runyankole (nyn).
    """

    endpoint = runpod.Endpoint(RUNPOD_ENDPOINT_ID)
    request_response = {}
    text = languageId_request.text.lower()

    try:
        request_response = endpoint.run_sync(
            {
                "input": {
                    "task": "language_classify",
                    "text": text,
                }
            },
            timeout=60,  # Timeout in seconds.
        )

        # Log the request for debugging purposes
        logging.info(f"Request response: {request_response}")

    except TimeoutError:
        # Handle timeout error and return a meaningful message to the user
        logging.error("Job timed out.")
        raise HTTPException(
            status_code=408,
            detail="The language identification job timed out. Please try again later.",
        )

    except Exception as e:
        # Handle any other exceptions and log them
        logging.error(f"An error occurred: {e}")
        raise HTTPException(
            status_code=500,
            detail="An error occurred while processing the language identification request.",
        )

    # Extract predictions from the response
    if isinstance(request_response, dict) and "predictions" in request_response:
        predictions = request_response["predictions"]

        # Find the language with the highest probability above the threshold
        threshold = 0.9
        detected_language = "language not detected"
        highest_prob = 0.0

        for language, probability in predictions.items():
            if probability > highest_prob:
                highest_prob = probability
                detected_language = language

        if highest_prob < threshold:
            detected_language = "language not detected"

    else:
        # Handle case where response format is unexpected
        logging.error(f"Unexpected response format: {request_response}")
        raise HTTPException(
            status_code=500,
            detail="Unexpected response format from the language identification service.",
        )

    return {"language": detected_language}


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


@router.post(
    "/auto_detect_audio_language",
    response_model=AudioDetectedLanguageResponse,
)
@limiter.limit(get_account_type_limit)
async def auto_detect_audio_language(
    request: Request,
    audio: UploadFile(...) = File(...),  # type: ignore
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Upload an audio file and get the language of the audio
    """
    endpoint = runpod.Endpoint(RUNPOD_ENDPOINT_ID)
    _ = current_user

    filename = secure_filename(audio.filename)
    # Add a timestamp to the file name
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    unique_file_name = f"{timestamp}_{filename}"
    file_path = os.path.join("/tmp", unique_file_name)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(audio.file, buffer)

    blob_name, blob_url = upload_audio_file(file_path=file_path)
    audio_file = blob_name
    os.remove(file_path)
    request_response = {}

    data = {
        "input": {
            "task": "auto_detect_audio_language",
            "audio_file": audio_file,
        }
    }

    start_time = time.time()

    try:
        request_response = await call_endpoint_with_retry(endpoint, data)
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
    logging.info(f"Response: {request_response}")

    # Calculate the elapsed time
    elapsed_time = end_time - start_time
    logging.info(f"Elapsed time: {elapsed_time} seconds")

    return request_response


@router.post("/generate-upload-url", response_model=UploadResponse)
async def generate_upload_url(request: UploadRequest):
    """
    Generate a signed URL for direct upload to Google Cloud Storage.
    This bypasses the Cloud Run request size limits.
    """
    try:
        # Initialize the storage client
        storage_client = storage.Client()

        # Get the bucket - use the same bucket you mentioned in your config
        bucket = storage_client.bucket("sb-asr-audio-content-sb-gcp-project-01")

        # Generate a unique file ID
        file_id = str(uuid.uuid4())

        # Create a blob with the unique ID as prefix
        blob_name = f"uploads/{file_id}/{request.file_name}"
        blob = bucket.blob(blob_name)

        # Generate a signed URL for uploading
        expires_at = datetime.utcnow() + timedelta(minutes=10)

        # Create the signed URL with PUT method
        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=10),
            method="PUT",
            content_type=request.content_type,
        )

        return UploadResponse(
            upload_url=signed_url, file_id=file_id, expires_at=expires_at
        )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error generating upload URL: {str(e)}"
        )


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


@router.post(
    "/sunflower_inference",
    response_model=SunflowerChatResponse,
)
@limiter.limit(get_account_type_limit)
async def sunflower_inference(
    request: Request,
    chat_request: SunflowerChatRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Professional Sunflower inference endpoint for multilingual chat completions.

    This endpoint provides access to Sunbird AI's Sunflower model, specialized in:
    - Multilingual conversations in Ugandan languages (Luganda, Acholi, Ateso, etc.)
    - Cross-lingual translations and explanations
    - Cultural context understanding
    - Educational content in local languages

    Features:
    - Automatic retry with exponential backoff
    - Context-aware responses
    - Usage tracking and monitoring
    - Support for custom system messages
    - Message history management

    Example message list with previous chat:
    [
        {"role": "system", "content": "You are Sunflower, a multilingual assistant for Ugandan languages made by Sunbird AI. You specialise in accurate translations, explanations, summaries and other cross-lingual tasks."},
        {"role": "user", "content": "Translate 'How are you?' to Luganda."},
        {"role": "assistant", "content": "In Luganda, 'How are you?' is 'Oli otya?'."},
        {"role": "user", "content": "How do I say 'Good morning' in Acholi?"}
    ]

    Example message list without previous chat:
    [
        {"role": "user", "content": "Explain the meaning of 'Ubuntu'."}
    ]

    Suggested system prompt:
    "You are Sunflower, a multilingual assistant for Ugandan languages made by Sunbird AI. You specialise in accurate translations, explanations, summaries and other cross-lingual tasks. Always provide clear, culturally relevant, and educational responses."
    """

    start_time = time.time()
    user = current_user

    try:
        # Validate input
        if not chat_request.messages:
            raise HTTPException(
                status_code=400, detail="At least one message is required"
            )

        # Validate message format
        valid_roles = {"system", "user", "assistant"}
        for i, message in enumerate(chat_request.messages):
            if not hasattr(message, "role") or not hasattr(message, "content"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Message {i} must have 'role' and 'content' fields",
                )
            if message.role not in valid_roles:
                raise HTTPException(
                    status_code=400,
                    detail=f"Message {i} role must be one of: {', '.join(valid_roles)}",
                )
            if not message.content or not message.content.strip():
                raise HTTPException(
                    status_code=400, detail=f"Message {i} content cannot be empty"
                )

        # Convert messages to dict format for the inference function
        messages_dict = [
            {"role": msg.role, "content": msg.content.strip()}
            for msg in chat_request.messages
        ]

        # Add default system message if none provided
        has_system_message = any(msg["role"] == "system" for msg in messages_dict)
        if not has_system_message:
            default_system = "You are Sunflower, a multilingual assistant for Ugandan languages made by Sunbird AI. You specialise in accurate translations, explanations, summaries and other cross-lingual tasks."
            messages_dict.insert(0, {"role": "system", "content": default_system})

        # Log the inference attempt
        logging.info(
            f"UG40 inference requested by user {user.id} with {len(messages_dict)} messages"
        )
        logging.info(f"Model type: {chat_request.model_type}")
        logging.info(f"Temperature: {chat_request.temperature}")

        # Call the UG40 inference with retry logic
        try:
            response = run_inference(
                messages=messages_dict,
                model_type=chat_request.model_type,
                stream=chat_request.stream,
                custom_system_message=chat_request.system_message,
            )

            logging.info(f"UG40 inference successful for user {user.id}")

        except ModelLoadingError as e:
            logging.error(f"Model loading error: {e}")
            raise HTTPException(
                status_code=503,
                detail="The AI model is currently loading. This usually takes 2-3 minutes. Please try again shortly.",
            )
        except TimeoutError as e:
            logging.error(f"Inference timeout: {e}")
            raise HTTPException(
                status_code=504,
                detail="The request timed out. Please try again with a shorter prompt or check your network connection.",
            )
        except ValueError as e:
            logging.error(f"Invalid request: {e}")
            raise HTTPException(status_code=400, detail=f"Invalid request: {str(e)}")
        except Exception as e:
            logging.error(f"Unexpected inference error: {e}")
            raise HTTPException(
                status_code=500,
                detail="An unexpected error occurred during inference. Please try again.",
            )

        # Process the response
        if not response or not response.get("content"):
            raise HTTPException(
                status_code=502,
                detail="The model returned an empty response. Please try rephrasing your request.",
            )

        end_time = time.time()
        total_time = end_time - start_time

        # Save to DynamoDB via HTTP endpoint (non-blocking)
        # Use the request's BackgroundTasks instance to schedule the job
        try:
            background_tasks.add_task(
                save_api_inference,
                messages_dict,
                response.get("content", ""),
                user,
                model_type=chat_request.model_type,
                processing_time=total_time,
                inference_type=INFERENCE_SUNFLOWER_CHAT,
            )
        except Exception as e:
            logging.warning(f"Failed to schedule feedback save task: {e}")

        # Create response object
        chat_response = SunflowerChatResponse(
            content=response["content"],
            model_type=response.get("model_type", chat_request.model_type),
            usage={
                "completion_tokens": response.get("usage", {}).get("completion_tokens"),
                "prompt_tokens": response.get("usage", {}).get("prompt_tokens"),
                "total_tokens": response.get("usage", {}).get("total_tokens"),
            },
            processing_time=total_time,
            inference_time=response.get("processing_time", 0),
            message_count=len(messages_dict),
        )

        # Log endpoint usage in database
        try:
            await log_endpoint(db, user, request, start_time, end_time)
        except Exception as e:
            logging.error(f"Failed to log endpoint usage: {e}")
            # Don't fail the request due to logging issues

        logging.info(
            f"UG40 inference completed in {total_time:.2f}s (model: {response.get('processing_time', 0):.2f}s)"
        )

        return chat_response

    except HTTPException:
        raise
    except Exception as e:
        end_time = time.time()
        total_time = end_time - start_time

        logging.error(
            f"Unexpected error in ug40_inference after {total_time:.2f}s: {e}"
        )
        raise HTTPException(
            status_code=500,
            detail="An unexpected server error occurred. Please try again later.",
        )


@router.post(
    "/sunflower_simple",
    response_model=Dict[str, Any],
)
@limiter.limit(get_account_type_limit)
async def sunflower_simple_inference(
    request: Request,
    background_tasks: BackgroundTasks,
    instruction: str = Form(..., description="The instruction or question for the AI"),
    model_type: str = Form("qwen", description="Model type (qwen or gemma)"),
    temperature: float = Form(0.3, ge=0.0, le=2.0, description="Sampling temperature"),
    system_message: str = Form(None, description="Custom system message"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Simple Sunflower inference endpoint for single instruction/response.

    This is a simplified interface for users who want to send a single instruction
    rather than managing conversation history.

    Parameters:
    - instruction: The question or instruction for the AI
    - model_type: Either 'qwen' (default) or 'gemma'
    - temperature: Controls randomness (0.0 = deterministic, 1.0 = creative)
    - system_message: Optional custom system message
    """

    start_time = time.time()
    user = current_user

    try:
        # Validate input
        if not instruction or not instruction.strip():
            raise HTTPException(status_code=400, detail="Instruction cannot be empty")

        if len(instruction.strip()) > 4000:
            raise HTTPException(
                status_code=400,
                detail="Instruction too long. Please limit to 4000 characters.",
            )

        # Validate model type
        if model_type not in ["qwen", "gemma"]:
            raise HTTPException(
                status_code=400, detail="Model type must be either 'qwen' or 'gemma'"
            )

        logging.info(f"Simple UG40 inference requested by user {user.id}")
        logging.info(f"Instruction length: {len(instruction)} characters")

        # Call the inference
        try:
            response = run_inference(
                instruction=instruction.strip(),
                model_type=model_type,
                stream=False,
                custom_system_message=system_message,
            )

        except ModelLoadingError as e:
            logging.error(f"Model loading error: {e}")
            raise HTTPException(
                status_code=503,
                detail="The AI model is currently loading. Please wait 2-3 minutes and try again.",
            )
        except TimeoutError as e:
            logging.error(f"Inference timeout: {e}")
            raise HTTPException(
                status_code=504,
                detail="Request timed out. Please try again with a shorter instruction.",
            )
        except Exception as e:
            logging.error(f"Inference error: {e}")
            raise HTTPException(
                status_code=500, detail="Inference failed. Please try again."
            )

        end_time = time.time()
        total_time = end_time - start_time

        # Save to DynamoDB via HTTP endpoint (non-blocking)
        try:
            background_tasks.add_task(
                save_api_inference,
                instruction.strip(),
                response.get("content", ""),
                user,
                model_type=model_type,
                processing_time=total_time,
                inference_type=INFERENCE_SUNFLOWER_SIMPLE,
            )
        except Exception as e:
            logging.warning(f"Failed to schedule feedback save task: {e}")

        # Log usage
        try:
            await log_endpoint(db, user, request, start_time, end_time)
        except Exception as e:
            logging.error(f"Failed to log endpoint usage: {e}")

        # Return simple response
        result = {
            "response": response.get("content", ""),
            "model_type": response.get("model_type", model_type),
            "processing_time": total_time,
            "usage": response.get("usage", {}),
            "success": True,
        }

        logging.info(f"Simple UG40 inference completed in {total_time:.2f}s")
        return result

    except HTTPException:
        raise
    except Exception as e:
        end_time = time.time()
        total_time = end_time - start_time

        logging.error(f"Unexpected error in simple inference: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


# Webhook handlers
@router.post("/webhook")
@router.post("/webhook/")
async def webhook(payload: dict, background_tasks: BackgroundTasks):
    """
    Optimized webhook handler for WhatsApp
    - Fast text responses (2-4 seconds)
    - Background processing for heavy operations
    - No external caching dependencies
    """
    start_time = time.time()

    try:
        # Quick validation
        if not whatsapp_service.valid_payload(payload):
            logging.info("Invalid payload received")
            return {"status": "ignored"}

        messages = whatsapp_service.get_messages_from_payload(payload)
        if not messages:
            return {"status": "no_messages"}

        # Extract message details
        try:
            phone_number_id = payload["entry"][0]["changes"][0]["value"]["metadata"][
                "phone_number_id"
            ]
            from_number = payload["entry"][0]["changes"][0]["value"]["messages"][0][
                "from"
            ]
            sender_name = payload["entry"][0]["changes"][0]["value"]["contacts"][0][
                "profile"
            ]["name"]
        except (KeyError, IndexError) as e:
            logging.error(f"Error extracting message details: {e}")
            return {"status": "invalid_message_format"}

        # Get user preference
        target_language = get_user_preference(from_number)

        if not target_language:
            target_language = "eng"  # Default to English if no preference set

        # Process message
        result = await processor.process_message(
            payload, from_number, sender_name, target_language, phone_number_id
        )

        # Handle response
        if result.response_type == ResponseType.SKIP:
            pass
        elif result.response_type == ResponseType.TEMPLATE:
            background_tasks.add_task(
                send_template_response,
                result.template_name,
                phone_number_id,
                from_number,
                sender_name,
            )
        elif result.response_type == ResponseType.BUTTON and result.button_data:
            try:
                whatsapp_service.send_button(
                    button=result.button_data,
                    phone_number_id=phone_number_id,
                    recipient_id=from_number,
                )
            except Exception as e:
                logging.error(f"Error sending button: {e}")
                # Fallback to text message
                whatsapp_service.send_message(
                    result.message
                    or "I'm having trouble with interactive buttons. Please try typing your request.",
                    whatsapp_token,
                    from_number,
                    phone_number_id,
                )
        elif result.response_type == ResponseType.TEXT and result.message:
            try:
                whatsapp_service.send_message(
                    result.message, whatsapp_token, from_number, phone_number_id
                )
            except Exception as e:
                logging.error(f"Error sending message: {e}")

        # Log performance
        total_time = time.time() - start_time
        logging.info(
            f"Webhook processed in {total_time:.3f}s (processing: {result.processing_time:.3f}s)"
        )

        return {"status": "success", "processing_time": total_time}

    except Exception as error:
        total_time = time.time() - start_time
        logging.error(f"Webhook error after {total_time:.3f}s: {str(error)}")

        # Try to send error message
        try:
            if "from_number" in locals() and "phone_number_id" in locals():
                whatsapp_service.send_message(
                    "I'm experiencing technical difficulties. Please try again.",
                    whatsapp_token,
                    from_number,
                    phone_number_id,
                )
        except:
            pass

        return {"status": "error", "processing_time": total_time}


async def send_template_response(
    template_name: str, phone_number_id: str, from_number: str, sender_name: str
):
    """Send template responses"""
    try:
        if template_name == "custom_feedback":
            whatsapp_service.send_button(
                button=processor.create_feedback_button(),
                phone_number_id=phone_number_id,
                recipient_id=from_number,
            )

        elif template_name == "welcome_message":
            whatsapp_service.send_button(
                button=processor.create_welcome_button(),
                phone_number_id=phone_number_id,
                recipient_id=from_number,
            )

        elif template_name == "choose_language":
            whatsapp_service.send_button(
                button=processor.create_language_selection_button(),
                phone_number_id=phone_number_id,
                recipient_id=from_number,
            )

    except Exception as e:
        logging.error(f"Error sending template {template_name}: {e}")


@router.get("/webhook")
@router.get("/webhook/")
async def verify_webhook(
    request: Request,
    hub_mode: str = None,
    hub_challenge: str = None,
    hub_verify_token: str = None,
):
    """
    Webhook verification endpoint for WhatsApp
    WhatsApp sends: hub.mode, hub.challenge, hub.verify_token
    """
    # Extract query parameters - WhatsApp uses hub.mode, hub.challenge, hub.verify_token
    mode = request.query_params.get("hub.mode")
    challenge = request.query_params.get("hub.challenge")
    token = request.query_params.get("hub.verify_token")

    logging.info(
        f"Webhook verification request - Mode: {mode}, Challenge: {challenge}, Token: {token}"
    )

    if mode and token and challenge:
        if mode != "subscribe" or token != os.getenv("VERIFY_TOKEN"):
            logging.error(
                f"Webhook verification failed - Expected token: {os.getenv('VERIFY_TOKEN')}, Received: {token}"
            )
            raise HTTPException(status_code=403, detail="Forbidden")

        logging.info("WEBHOOK_VERIFIED")
        # WhatsApp expects a plain text response with just the challenge value
        return Response(content=challenge, media_type="text/plain")

    logging.error("Missing required parameters for webhook verification")
    raise HTTPException(status_code=400, detail="Bad Request")
