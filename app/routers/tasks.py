import asyncio
import datetime
import json
import logging
import mimetypes
import os
import shutil
import tempfile
import time
import uuid
from datetime import timedelta
from typing import Any, Dict

import aiofiles
import requests
import runpod
from dotenv import load_dotenv
from fastapi import (
    APIRouter,
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
from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError
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
from app.inference_services.runpod_helpers import (
    normalize_runpod_response,
    run_job_and_get_output,
)
from app.inference_services.user_preference import get_user_preference
from app.inference_services.whatsapp_service import WhatsAppService
from app.schemas.tasks import (
    AudioDetectedLanguageResponse,
    ChatRequest,
    ChatResponse,
    LanguageIdRequest,
    LanguageIdResponse,
    NllbLanguage,
    NllbTranslationRequest,
    SttbLanguage,
    STTTranscript,
    SummarisationRequest,
    SummarisationResponse,
    TTSRequest,
    UploadRequest,
    UploadResponse,
    WorkerTranslationResponse,
)
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
    token=os.getenv("WHATSAPP_TOKEN"), phone_number_id=os.getenv("PHONE_NUMBER_ID")
)

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

# Constants for file limits
MAX_AUDIO_FILE_SIZE_MB = 10  # 10MB limit
MAX_AUDIO_DURATION_MINUTES = 10  # 10 minutes limit
CHUNK_SIZE = 1024 * 1024  # 1MB chunks for streaming
ALLOWED_AUDIO_TYPES = {
    "audio/mpeg": [".mp3"],
    "audio/wav": [".wav"],
    "audio/x-wav": [".wav"],
    "audio/ogg": [".ogg"],
    "audio/x-m4a": [".m4a"],
    "audio/aac": [".aac"],
}


def custom_key_func(request: Request):
    header = request.headers.get("Authorization")
    _, _, token = header.partition(" ")
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    account_type: str = payload.get("account_type")
    logging.info(f"account_type: {account_type}")
    return account_type


def get_account_type_limit(key: str) -> str:
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


@router.post("/stt_from_gcs")
async def speech_to_text_from_gcs(
    request: Request,
    gcs_blob_name: str = Form(...),
    language: SttbLanguage = Form("lug"),
    adapter: SttbLanguage = Form("lug"),
    recognise_speakers: bool = Form(False),
    whisper: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> STTTranscript:
    """
    Accepts a GCS blob name, downloads the file from GCS,
    trims if >10 minutes, uploads a final version (if trimmed),
    then calls the transcription service.
    """
    was_audio_trimmed = False
    original_duration = None
    bucket_name = os.getenv("AUDIO_CONTENT_BUCKET_NAME")

    try:
        # 1. Download the file from GCS
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(gcs_blob_name)

        if not blob.exists():
            raise HTTPException(
                status_code=400, detail=f"GCS blob {gcs_blob_name} does not exist."
            )

        # Create a local temp file
        file_extension = os.path.splitext(gcs_blob_name)[1].lower() or ".mp3"
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=file_extension
        ) as temp_file:
            file_path = temp_file.name
            blob.download_to_filename(file_path)

        trimmed_file_path = os.path.join(
            os.path.dirname(file_path), f"trimmed_{os.path.basename(file_path)}"
        )

        try:
            # 2. Load and validate/trim duration if > 10 minutes
            audio_segment = AudioSegment.from_file(file_path)
            duration_minutes = len(audio_segment) / (1000 * 60)

            if duration_minutes > MAX_AUDIO_DURATION_MINUTES:
                was_audio_trimmed = True
                original_duration = duration_minutes
                trimmed_audio = audio_segment[
                    : (MAX_AUDIO_DURATION_MINUTES * 60 * 1000)
                ]
                trimmed_audio.export(trimmed_file_path, format=file_extension[1:])
                os.remove(file_path)
                file_path = trimmed_file_path
                logging.info(
                    f"Audio file trimmed from {duration_minutes:.1f} to {MAX_AUDIO_DURATION_MINUTES} minutes."
                )

        except CouldntDecodeError:
            os.remove(file_path)
            if os.path.exists(trimmed_file_path):
                os.remove(trimmed_file_path)
            raise HTTPException(
                status_code=400,
                detail="Could not decode audio file. Please ensure the file is not corrupted.",
            )

        # 3. Upload final version (trimmed or original) back to GCS if you wish
        #    This is optional. If you want the final audio stored in GCS as well, do something like:
        #    new_blob_name = f"processed/{gcs_blob_name}"
        #    new_blob = bucket.blob(new_blob_name)
        #    new_blob.upload_from_filename(file_path)
        #    # Then you can store new_blob_name or new_blob.public_url as needed.

        # 4. Prepare transcription request to your runpod endpoint
        endpoint = runpod.Endpoint(RUNPOD_ENDPOINT_ID)
        data = {
            "input": {
                "task": "transcribe",
                "target_lang": language,
                "adapter": adapter,
                "audio_file": gcs_blob_name,
                "whisper": whisper,
                "recognise_speakers": recognise_speakers,
            }
        }

        # 5. Process transcription
        start_time = time.time()
        request_response = {}
        try:
            request_response = await call_endpoint_with_retry(endpoint, data)
        except TimeoutError as e:
            logging.error(f"Transcription timeout: {str(e)}")
            raise HTTPException(
                status_code=503,
                detail="Transcription service timed out. Please try again with a shorter audio file.",
            )
        except ConnectionError as e:
            logging.error(f"Connection error: {str(e)}")
            raise HTTPException(
                status_code=503,
                detail="Connection error while transcribing. Please try again.",
            )
        except Exception as e:
            logging.error(f"Transcription error: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail="An unexpected error occurred during transcription",
            )
        end_time = time.time()

        transcription = request_response.get("audio_transcription")
        if not transcription:
            raise HTTPException(
                status_code=422,
                detail="No transcription was generated. The audio might be silent or unclear.",
            )

        # 6. Save transcription to DB if needed
        audio_transcription_id = None
        if isinstance(transcription, str) and len(transcription) > 0:
            try:
                db_audio_transcription = await create_audio_transcription(
                    db,
                    current_user,
                    f"gs://{bucket_name}/{gcs_blob_name}",
                    gcs_blob_name,
                    transcription,
                    language,
                )
                audio_transcription_id = db_audio_transcription.id
                logging.info(
                    f"Transcription saved to DB with ID: {audio_transcription_id}"
                )
            except Exception as e:
                logging.error(f"Database error: {str(e)}")
                # Don't raise an exception, continue to return transcription

        # 7. Log usage
        try:
            await log_endpoint(db, current_user, request, start_time, end_time)
        except Exception as e:
            logging.error(f"Failed to log endpoint usage: {str(e)}")

        # 8. Return response
        response = STTTranscript(
            audio_transcription=transcription,
            diarization_output=request_response.get("diarization_output", {}),
            formatted_diarization_output=request_response.get(
                "formatted_diarization_output", ""
            ),
            audio_transcription_id=audio_transcription_id,
            audio_url=f"gs://{bucket_name}/{gcs_blob_name}",
            language=language,
            was_audio_trimmed=was_audio_trimmed,
            original_duration_minutes=original_duration if was_audio_trimmed else None,
        )

        # Handle trimming warnings
        if was_audio_trimmed:
            headers = {
                "X-Audio-Trimmed": "true",
                "X-Original-Duration": f"{original_duration:.1f}",
                "X-Transcribed-Duration": f"{MAX_AUDIO_DURATION_MINUTES}",
                "Warning": f"Audio trimmed from {original_duration:.1f} min to {MAX_AUDIO_DURATION_MINUTES} min.",
            }
            return Response(
                content=response.model_dump_json(),
                media_type="application/json",
                # headers
            )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Unexpected error in speech_to_text_from_gcs: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while processing your request",
        )
    finally:
        # Cleanup local files
        if os.path.exists(file_path):
            os.remove(file_path)
        if os.path.exists(trimmed_file_path):
            os.remove(trimmed_file_path)


@router.post(
    "/stt",
)
@limiter.limit(get_account_type_limit)
async def speech_to_text(
    request: Request,
    audio: UploadFile = File(..., description="Audio file to transcribe"),
    language: SttbLanguage = Form("lug"),
    adapter: SttbLanguage = Form("lug"),
    recognise_speakers: bool = Form(False),
    whisper: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> STTTranscript:
    """
    Upload an audio file and get the transcription text of the audio.

    Limitations:
    - Maximum audio duration: Files longer than 10 minutes will be trimmed to first 10 minutes
    - Supported formats: MP3, WAV, OGG, M4A, AAC
    - Large files are supported but only first 10 minutes will be transcribed

    Note: For files larger than 100MB, please use chunked upload or consider splitting the audio file.
    """
    was_audio_trimmed = False
    original_duration = None

    try:
        # 1. Validate file type first to fail fast if unsupported
        content_type = audio.content_type
        file_extension = os.path.splitext(audio.filename)[1].lower()
        if (
            content_type not in ALLOWED_AUDIO_TYPES
            or file_extension not in ALLOWED_AUDIO_TYPES.get(content_type, [])
        ):
            raise HTTPException(
                status_code=415,
                detail=f"Unsupported file type. Supported formats: {', '.join([ext for exts in ALLOWED_AUDIO_TYPES.values() for ext in exts])}",
            )

        # 2. Create temporary files
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=file_extension
        ) as temp_file:
            file_path = temp_file.name
            # Stream the file in chunks to avoid memory issues
            async with aiofiles.open(file_path, "wb") as out_file:
                while content := await audio.read(CHUNK_SIZE):
                    await out_file.write(content)

        trimmed_file_path = os.path.join(
            os.path.dirname(file_path), f"trimmed_{os.path.basename(file_path)}"
        )

        try:
            # 3. Load and validate/trim duration
            audio_segment = AudioSegment.from_file(file_path)
            duration_minutes = len(audio_segment) / (1000 * 60)  # Convert to minutes

            if duration_minutes > MAX_AUDIO_DURATION_MINUTES:
                # Trim to first 10 minutes
                was_audio_trimmed = True
                original_duration = duration_minutes
                trimmed_audio = audio_segment[
                    : (MAX_AUDIO_DURATION_MINUTES * 60 * 1000)
                ]  # Convert minutes to milliseconds
                trimmed_audio.export(
                    trimmed_file_path, format=file_extension[1:]
                )  # Remove dot from extension
                os.remove(file_path)  # Remove original file
                file_path = trimmed_file_path  # Use trimmed file for further processing
                logging.info(
                    f"Audio file trimmed from {duration_minutes:.1f} minutes to {MAX_AUDIO_DURATION_MINUTES} minutes"
                )

        except CouldntDecodeError:
            os.remove(file_path)
            if os.path.exists(trimmed_file_path):
                os.remove(trimmed_file_path)
            raise HTTPException(
                status_code=400,
                detail="Could not decode audio file. Please ensure the file is not corrupted.",
            )

        # 4. Upload to cloud storage
        try:
            blob_name, blob_url = upload_audio_file(file_path=file_path)
            if not blob_name or not blob_url:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to upload audio file to cloud storage",
                )
        except Exception as e:
            logging.error(f"Cloud storage upload error: {str(e)}")
            raise HTTPException(
                status_code=500, detail="Failed to upload audio file to cloud storage"
            )
        finally:
            # Clean up temporary files
            if os.path.exists(file_path):
                os.remove(file_path)
            if os.path.exists(trimmed_file_path):
                os.remove(trimmed_file_path)

        # 5. Prepare transcription request
        # endpoint = runpod.Endpoint(RUNPOD_ENDPOINT_ID)
        # request_response = {}
        payload = {
            "task": "transcribe",
            "target_lang": language,
            "adapter": adapter,
            "audio_file": blob_name,
            "whisper": whisper,
            "recognise_speakers": recognise_speakers,
        }

        # 6. Process transcription
        start_time = time.time()
        try:
            # request_response = await call_endpoint_with_retry(endpoint, data)
            raw_resp, job_details = await run_job_and_get_output(payload)
            logging.info(f"Raw response: {raw_resp}")
            logging.info(f"Job details: {job_details}")
        except TimeoutError as e:
            logging.error(f"Transcription timeout: {str(e)}")
            raise HTTPException(
                status_code=503,
                detail="Transcription service timed out. Please try again with a shorter audio file.",
            )
        except ConnectionError as e:
            logging.error(f"Connection error: {str(e)}")
            raise HTTPException(
                status_code=503,
                detail="Connection error while transcribing. Please try again.",
            )
        except Exception as e:
            logging.error(f"Transcription error: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail="An unexpected error occurred during transcription",
            )

        end_time = time.time()
        elapsed_time = end_time - start_time
        logging.info(f"Transcription completed in {elapsed_time:.2f} seconds")

        # 7. Process and validate transcription result
        transcription = raw_resp.get("audio_transcription")
        if not transcription:
            raise HTTPException(
                status_code=422,
                detail="No transcription was generated. The audio might be silent or unclear.",
            )

        # 8. Save transcription to database
        audio_transcription_id = None
        if isinstance(transcription, str) and len(transcription) > 0:
            try:
                db_audio_transcription = await create_audio_transcription(
                    db, current_user, blob_url, blob_name, transcription, language
                )
                audio_transcription_id = db_audio_transcription.id
                logging.info(
                    f"Transcription saved to database with ID: {audio_transcription_id}"
                )
            except Exception as e:
                logging.error(f"Database error: {str(e)}")
                # Don't raise an exception here as we still want to return the transcription

        # 9. Log the endpoint usage
        try:
            await log_endpoint(db, current_user, request, start_time, end_time)
        except Exception as e:
            logging.error(f"Failed to log endpoint usage: {str(e)}")

        # 10. Return response
        response = STTTranscript(
            audio_transcription=transcription,
            diarization_output=raw_resp.get("diarization_output", {}),
            formatted_diarization_output=raw_resp.get(
                "formatted_diarization_output", ""
            ),
            audio_transcription_id=audio_transcription_id,
            audio_url=blob_url,
            language=language,
            was_audio_trimmed=was_audio_trimmed,
            original_duration_minutes=original_duration if was_audio_trimmed else None,
        )

        # Add warning header if audio was trimmed
        if was_audio_trimmed:
            headers = {
                "X-Audio-Trimmed": "true",
                "X-Original-Duration": f"{original_duration:.1f}",
                "X-Transcribed-Duration": f"{MAX_AUDIO_DURATION_MINUTES}",
                "Warning": f"Audio file was trimmed from {original_duration:.1f} minutes to {MAX_AUDIO_DURATION_MINUTES} minutes. Only the first {MAX_AUDIO_DURATION_MINUTES} minutes were transcribed.",
            }
            return Response(
                content=response.model_dump_json(),
                media_type="application/json",
                headers=headers,
            )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Unexpected error in speech_to_text: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while processing your request",
        )


@router.post(
    "/org/stt",
)
@limiter.limit(get_account_type_limit)
async def speech_to_text(
    request: Request,
    audio: UploadFile(...) = File(...),  # type: ignore
    recognise_speakers: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> STTTranscript:
    """
    Upload an audio file and get the transcription text of the audio
    """
    endpoint = runpod.Endpoint(RUNPOD_ENDPOINT_ID)
    user = current_user

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
            "task": "transcribe",
            "audio_file": audio_file,
            "organisation": True,
            "recognise_speakers": recognise_speakers,
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
    transcription = request_response.get("audio_transcription")

    # Log endpoint in database
    await log_endpoint(db, user, request, start_time, end_time)

    return STTTranscript(
        audio_transcription=request_response.get("audio_transcription"),
        diarization_output=request_response.get("diarization_output", {}),
        formatted_diarization_output=request_response.get(
            "formatted_diarization_output", ""
        ),
    )


# Route for the nllb translation endpoint
@router.post(
    "/nllb_translate",
    response_model=WorkerTranslationResponse,
)
@limiter.limit(get_account_type_limit)
async def nllb_translate(
    request: Request,
    translation_request: NllbTranslationRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Source and Target Language can be one of: ach(Acholi), teo(Ateso), eng(English),
    lug(Luganda), lgg(Lugbara), or nyn(Runyankole).We currently only support English to Local
    languages and Local to English languages, so when the source language is one of the
    languages listed, the target can be any of the other languages.
    """
    endpoint = runpod.Endpoint(RUNPOD_ENDPOINT_ID)
    user = current_user

    text = translation_request.text
    # Data to be sent in the request body
    # Build payload compatible with `sb_api._run_job_and_get_output`
    payload = {
        "task": "translate",
        "source_language": translation_request.source_language,
        "target_language": translation_request.target_language,
        "text": text.strip(),
    }

    start_time = time.time()
    try:
        raw_resp, job_details = await run_job_and_get_output(payload)
        logging.info(f"Raw response: {raw_resp}")
        logging.info(f"Job details: {job_details}")
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
    except Exception as e:
        logging.error(f"Error calling worker: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

    end_time = time.time()
    # Log endpoint in database
    await log_endpoint(db, user, request, start_time, end_time)

    # Calculate the elapsed time
    elapsed_time = end_time - start_time
    logging.info(f"Elapsed time: {elapsed_time} seconds")

    # Normalize and validate the response to the `WorkerTranslationResponse` shape
    normalized = normalize_runpod_response(
        job_details if job_details is not None else raw_resp
    )
    try:
        # Use the pydantic model imported at module top
        worker_resp = WorkerTranslationResponse.model_validate(normalized)
    except Exception as e:
        logging.error(f"Failed to validate worker response: {e}")
        raise HTTPException(status_code=500, detail="Invalid response from worker")

    return worker_resp.model_dump()


# Route for the text-to-speech endpoint
@router.post(
    "/tts",
)
@limiter.limit(get_account_type_limit)
async def text_to_speech(
    request: Request,
    tts_request: TTSRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Endpoint for text-to-speech conversion.
    """
    endpoint = runpod.Endpoint(RUNPOD_ENDPOINT_ID)
    user = current_user

    text = tts_request.text
    # Data to be sent in the request body
    data = {
        "input": {
            "task": "tts",
            "text": text.strip(),  # Remove leading/trailing spaces
            "speaker_id": tts_request.speaker_id.value,
            "temperature": tts_request.temperature,
            "max_new_audio_tokens": tts_request.max_new_audio_tokens,
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
    except Exception as e:
        logging.error(f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

    end_time = time.time()
    # Log endpoint in database
    await log_endpoint(db, user, request, start_time, end_time)
    logging.info(f"Response: {request_response}")

    # Calculate the elapsed time
    elapsed_time = end_time - start_time
    logging.info(f"Elapsed time: {elapsed_time} seconds")

    response = {}
    response["output"] = request_response

    return response


@router.post("/webhook")
@router.post("/webhook/")
async def webhook(payload: dict):
    try:
        logging.info("Received payload: %s", json.dumps(payload, indent=2))

        if not whatsapp_service.valid_payload(payload):
            return {"status": "ignored"}

        messages = whatsapp_service.get_messages_from_payload(payload)
        if messages:
            phone_number_id = whatsapp_service.get_phone_number_id(payload)
            from_number = whatsapp_service.get_from_number(payload)
            sender_name = whatsapp_service.get_name(payload)
            target_language = get_user_preference(from_number)

            # Use the new UG40 model for message processing
            message, is_template, template = whatsapp_service.handle_ug40_message(
                payload,
                target_language,
                from_number,
                sender_name,
                phone_number_id,
                processed_messages,
                call_endpoint_with_retry,
            )

            if is_template:
                if template == "custom_feedback":
                    whatsapp_service.send_template(
                        token=os.getenv("WHATSAPP_TOKEN"),
                        template=template,
                        phone_number_id=phone_number_id,
                        recipient_id=from_number,
                    )
                elif template == "welcome_message":
                    whatsapp_service.send_template(
                        token=os.getenv("WHATSAPP_TOKEN"),
                        template="welcome_message",
                        phone_number_id=phone_number_id,
                        recipient_id=from_number,
                        components=[
                            {
                                "type": "body",
                                "parameters": [{"type": "text", "text": sender_name}],
                            }
                        ],
                    )
                elif template == "choose_language":
                    whatsapp_service.send_template(
                        token=os.getenv("WHATSAPP_TOKEN"),
                        template="choose_language",
                        phone_number_id=phone_number_id,
                        recipient_id=from_number,
                    )
            else:
                whatsapp_service.send_message(
                    message, os.getenv("WHATSAPP_TOKEN"), from_number, phone_number_id
                )

        return {"status": "success"}

    except Exception as error:
        logging.error("Error in webhook processing: %s", str(error))
        raise HTTPException(status_code=500, detail="Internal Server Error") from error


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
