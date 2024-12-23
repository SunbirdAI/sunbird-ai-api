import datetime
import json
import logging
import mimetypes
import os
import re
import shutil
import time
import uuid

import requests
import runpod
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from jose import jwt
from slowapi import Limiter
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from twilio.rest import Client
from werkzeug.utils import secure_filename

from app.crud.audio_transcription import create_audio_transcription
from app.crud.monitoring import log_endpoint
from app.deps import get_current_user, get_db
from app.inference_services.openai_script import (
    classify_input,
    get_completion_from_messages,
    get_guide_based_on_classification,
    is_json,
)
from app.inference_services.user_preference import (
    get_user_last_five_messages,
    get_user_preference,
    save_message,
    save_translation,
    save_user_preference,
    update_feedback,
)
from app.inference_services.whats_app_services import (
    download_whatsapp_audio,
    fetch_media_url,
    get_audio,
    get_document,
    get_from_number,
    get_image,
    get_interactive_response,
    get_location,
    get_message,
    get_message_id,
    get_messages_from_payload,
    get_name,
    get_phone_number_id,
    get_reaction,
    get_video,
    handle_language_selection,
    help_message,
    query_media_url,
    reply_to_message,
    send_audio,
    send_message,
    set_default_target_language,
    valid_payload,
    welcome_message,
)
from app.schemas.tasks import (
    AudioDetectedLanguageResponse,
    ChatRequest,
    ChatResponse,
    LanguageIdRequest,
    LanguageIdResponse,
    NllbLanguage,
    NllbTranslationRequest,
    NllbTranslationResponse,
    SttbLanguage,
    STTTranscript,
    SummarisationRequest,
    SummarisationResponse,
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


@router.post(
    "/stt",
)
@limiter.limit(get_account_type_limit)
async def speech_to_text(
    request: Request,
    audio: UploadFile(...) = File(...),  # type: ignore
    language: SttbLanguage = Form("lug"),
    adapter: SttbLanguage = Form("lug"),
    recognise_speakers: bool = Form(False),
    whisper: bool = Form(False),
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
            "target_lang": language,
            "adapter": adapter,
            "audio_file": audio_file,
            "whisper": whisper,
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

    # Save transcription in database if it exists
    audio_transcription_id = None
    if (
        transcription is not None
        and isinstance(transcription, str)
        and len(transcription) > 0
    ):
        db_audio_transcription = await create_audio_transcription(
            db, current_user, blob_url, blob_name, transcription, language
        )
        audio_transcription_id = db_audio_transcription.id

        logging.info(
            f"Audio transcription in database :{db_audio_transcription.to_dict()}"
        )

    # Log endpoint in database
    await log_endpoint(db, user, request, start_time, end_time)

    return STTTranscript(
        audio_transcription=request_response.get("audio_transcription"),
        diarization_output=request_response.get("diarization_output", {}),
        formatted_diarization_output=request_response.get(
            "formatted_diarization_output", ""
        ),
        audio_transcription_id=audio_transcription_id,
        audio_url=blob_url,
        language=language,
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
    response_model=NllbTranslationResponse,
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
    data = {
        "input": {
            "task": "translate",
            "source_language": translation_request.source_language,
            "target_language": translation_request.target_language,
            "text": text.strip(),  # Remove leading/trailing spaces
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
async def webhook(payload: dict):
    try:
        logging.info("Received payload: %s", json.dumps(payload, indent=2))

        if not valid_payload(payload):
            return {"status": "ignored"}

        messages = get_messages_from_payload(payload)
        if messages:
            phone_number_id = get_phone_number_id(payload)
            from_number = get_from_number(payload)
            sender_name = get_name(payload)
            target_language = get_user_preference(from_number)

            message = handle_openai_message(
                payload, target_language, from_number, sender_name, phone_number_id
            )

            if message:
                send_message(
                    message, os.getenv("WHATSAPP_TOKEN"), from_number, phone_number_id
                )

        return {"status": "success"}

    except Exception as error:
        logging.error("Error in webhook processing: %s", str(error))
        raise HTTPException(status_code=500, detail="Internal Server Error") from error


@router.get("/webhook")
async def verify_webhook(mode: str, token: str, challenge: str):
    if mode and token:
        if mode != "subscribe" or token != os.getenv("VERIFY_TOKEN"):
            raise HTTPException(status_code=403, detail="Forbidden")

        logging.info("WEBHOOK_VERIFIED")
        return {"challenge": challenge}
    raise HTTPException(status_code=400, detail="Bad Request")


def handle_openai_message(
    payload, target_language, from_number, sender_name, phone_number_id
):
    message_id = get_message_id(payload)  # Extract unique message ID from the payload

    if message_id in processed_messages:
        logging.info("Message ID %s already processed. Skipping.", {message_id})
        return

    # Add message_id to processed messages
    processed_messages.add(message_id)

    logging.info("Message ID %s added to processed messages.", message_id)

    # Language mapping dictionary
    language_mapping = {
        "lug": "Luganda",
        "ach": "Acholi",
        "teo": "Ateso",
        "lgg": "Lugbara",
        "nyn": "Runyankole",
        "eng": "English",
    }

    if interactive_response := get_interactive_response(payload):
        response = interactive_response
        return f"Dear {sender_name}, Thanks for that response."

    if location := get_location(payload):
        response = location
        return f"Dear {sender_name}, We have no support for messages of type locations."

    if image := get_image(payload):
        response = image
        return f"Dear {sender_name}, We have no support for messages of type image."

    if video := get_video(payload):
        response = video
        return f"Dear {sender_name}, We have no support for messages of type video."

    if docs := get_document(payload):
        response = docs
        return f"Dear {sender_name}, We do not support documents."

    # Step 1: Retrieve audio information from the payload
    if audio_info := get_audio(payload):
        if not audio_info:
            logging.error("No audio information provided.")
            return "Failed to transcribe audio."

        send_message(
            "Audio has been received ...",
            os.getenv("WHATSAPP_TOKEN"),
            from_number,
            phone_number_id,
        )

        if not target_language:
            target_language = "lug"

        # Step 2: Fetch the media URL using the WhatsApp token
        audio_url = fetch_media_url(audio_info["id"], os.getenv("WHATSAPP_TOKEN"))
        if not audio_url:
            logging.error("Failed to fetch media URL.")
            return "Failed to transcribe audio."

        # Step 3: Download the audio file locally
        local_audio_path = download_whatsapp_audio(
            audio_url, os.getenv("WHATSAPP_TOKEN")
        )
        if not local_audio_path:
            logging.error("Failed to download audio from WhatsApp.")
            return "Failed to transcribe audio."

        # Upload the audio file to GCS and return the blob and URL
        blob_name, blob_url = upload_audio_file(local_audio_path)

        if blob_name and blob_url:
            logging.info("Audio file successfully uploaded to GCS: %s", blob_url)
        else:
            raise Exception("Failed to upload audio to GCS")

        # Step 4: Notify the user that the audio has been received
        send_message(
            "Audio has been loaded ...",
            os.getenv("WHATSAPP_TOKEN"),
            from_number,
            phone_number_id,
        )

        # Step 5: Initialize the Runpod endpoint for transcription
        endpoint = runpod.Endpoint(RUNPOD_ENDPOINT_ID)

        # logging.info("Audio data found for langauge detection")
        # data = {
        #     "input": {
        #         "task": "auto_detect_audio_language",
        #         "audio_file": blob_name,
        #     }
        # }

        # start_time = time.time()

        # try:
        #     logging.info("Audio file ready for langauge detection")
        #     audio_lang_response = call_endpoint_with_retry(endpoint, data)
        # except TimeoutError as e:

        #     logging.error("Job timed out %s", str(e))
        #     raise HTTPException(
        #         status_code=503, detail="Service unavailable due to timeout."
        #     ) from e

        # except ConnectionError as e:

        #     logging.error("Connection lost: %s", str(e))
        #     raise HTTPException(
        #         status_code=503, detail="Service unavailable due to connection error."
        #     ) from e

        # end_time = time.time()
        # logging.info(
        #     "Audio language auto detection response: %s ",
        #     audio_lang_response.get("detected_language"),
        # )

        # # Calculate the elapsed time
        # elapsed_time = end_time - start_time
        # logging.info(
        #     "Audio language auto detection elapsed time: %s seconds", elapsed_time
        # )

        # audio_language = audio_lang_response.get("detected_language")
        # request_response = {}

        # if audio_language in language_mapping:
        #     # Language is in the mapping
        #     logging.info("Language detected in audio is %s", audio_language)
        # else:
        #     # Language is not in our scope
        #     return "Audio Language not detected"

        try:

            start_time = time.time()

            # Step 6: Notify the user that transcription is in progress
            send_message(
                "Your transcription is being processed ...",
                os.getenv("WHATSAPP_TOKEN"),
                from_number,
                phone_number_id,
            )

            try:
                # Step 7: Call the transcription service with the correct parameters
                request_response = endpoint.run_sync(
                    {
                        "input": {
                            "task": "transcribe",
                            "target_lang": target_language,
                            "adapter": target_language,
                            "audio_file": blob_name,  # Corrected to pass local file path
                            "recognise_speakers": False,
                        }
                    },
                    timeout=150,  # Set a timeout for the transcription job.
                )

                # Step 8: Notify the user that transcription is in progress
                send_message(
                    "Your transcription is ready ...",
                    os.getenv("WHATSAPP_TOKEN"),
                    from_number,
                    phone_number_id,
                )

            except TimeoutError as e:
                logging.error("Transcription job timed out: %s", str(e))
                return "Failed to transcribe audio."
            except Exception as e:
                logging.error("Unexpected error during transcription: %s", str(e))
                return "Failed to transcribe audio."

            # Step 9: Log the time taken for the transcription
            end_time = time.time()
            elapsed_time = end_time - start_time
            logging.info("Here is the response: %s", request_response)
            logging.info("Elapsed time: %s seconds for transcription.", elapsed_time)

            send_message(
                "Translating to your target language if you haven't set a target language the default is Lugande.....",
                os.getenv("WHATSAPP_TOKEN"),
                from_number,
                phone_number_id,
            )

            detected_language = detect_language(
                request_response.get("audio_transcription")
            )
            translation = translate_text(
                request_response.get("audio_transcription"),
                detected_language,
                target_language,
            )

            # Step 10: Return the translation result
            return translation

        finally:
            # Step 11: Clean up the local audio file
            if os.path.exists(local_audio_path):
                os.remove(local_audio_path)
                logging.info("Cleaned up local audio file: %s", request_response)

    elif reaction := get_reaction(payload):
        mess_id = reaction["message_id"]
        emoji = reaction["emoji"]
        update_feedback(mess_id, emoji)
        return f"Dear {sender_name}, Thanks for your feedback {emoji}."

    else:
        # Extract relevant information
        input_text = get_message(payload)
        mess_id = get_message_id(payload)
        save_message(from_number, input_text)

        # Get last five messages for context
        last_five_messages = get_user_last_five_messages(from_number)

        # Format the previous messages for context clarity
        formatted_message_history = "\n".join(
            [
                f"Message {i+1}: {msg['message_text']}"
                for i, msg in enumerate(last_five_messages)
            ]
        )

        # Combine the message context to inform the model
        messages_context = f"Previous messages (starting from the most recent):\n{formatted_message_history}\nCurrent message:\n{input_text}"

        # Classify the user input and get the appropriate guide
        classification = classify_input(input_text)
        guide = get_guide_based_on_classification(classification)

        # Generate response from OpenAI
        messages = [
            {"role": "system", "content": guide},
            {"role": "user", "content": messages_context},
        ]
        response = get_completion_from_messages(messages)

        if is_json(response):
            json_object = json.loads(response)
            # print ("Is valid json? true")
            logging.info("Open AI response: %s", json_object)
            task = json_object["task"]
            # print(task)

            if task == "translation":
                detected_language = detect_language(json_object["text"])
                # save_user_preference(
                #     from_number, detected_language, json_object["target_language"]
                # )
                if json_object["target_language"]:
                    translation = translate_text(
                        json_object["text"],
                        detected_language,
                        json_object["target_language"],
                    )
                elif target_language:
                    translation = translate_text(
                        json_object["text"],
                        detected_language,
                        target_language,
                    )
                else:
                    translation = translate_text(
                        json_object["text"],
                        detected_language,
                        "lug",
                    )

                save_translation(
                    from_number,
                    json_object["text"],
                    translation,
                    detected_language,
                    target_language,
                    mess_id,
                )
                return f""" Here is the translation: {translation} """

            elif task == "greeting":
                detected_language = detect_language(input_text)
                translation = " "
                if target_language:
                    translation = translate_text(
                        input_text,
                        detected_language,
                        target_language,
                    )
                else:
                    translation = translate_text(
                        input_text,
                        detected_language,
                        "lug",
                    )

                target_language = detect_language(translation)
                message = json_object["text"]

                save_translation(
                    from_number,
                    input_text,
                    translation,
                    detected_language,
                    target_language,
                    mess_id,
                )

                send_message(
                    message, os.getenv("WHATSAPP_TOKEN"), from_number, phone_number_id
                )

                # reply_to_message(
                # os.getenv("WHATSAPP_TOKEN"), mess_id,  from_number, phone_number_id, message,
                # )

                return f""" Here is the translation: {translation} """

            elif task == "currentLanguage":
                # Get the full language name using the code
                target_language = get_user_preference(from_number)

                language_name = language_mapping.get(target_language)
                if language_name:
                    return f"Your current target language is {language_name}"
                else:
                    return "You currently don't have a set language."

            elif task == "setLanguage":
                settargetlanguage = json_object["language"]

                logging.info("This language set: %s", settargetlanguage)

                save_user_preference(from_number, None, settargetlanguage)

                language_name = language_mapping.get(settargetlanguage)

                return f"Language set to {language_name}"

            elif task == "conversation":

                detected_language = detect_language(input_text)
                translation = ""
                if target_language:
                    translation = translate_text(
                        input_text,
                        detected_language,
                        target_language,
                    )
                else:
                    translation = translate_text(
                        input_text,
                        detected_language,
                        "lug",
                    )
                target_language = detect_language(translation)
                message = json_object["text"]

                save_translation(
                    from_number,
                    input_text,
                    translation,
                    detected_language,
                    target_language,
                    mess_id,
                )

                send_message(
                    message, os.getenv("WHATSAPP_TOKEN"), from_number, phone_number_id
                )

                # reply_to_message(
                # os.getenv("WHATSAPP_TOKEN"), mess_id,  from_number, phone_number_id, message,
                # )

                return f""" Here is the translation: {translation} """

            elif task == "help":
                detected_language = detect_language(input_text)
                translation = ""
                if target_language:
                    translation = translate_text(
                        input_text,
                        detected_language,
                        target_language,
                    )
                else:
                    translation = translate_text(
                        input_text,
                        detected_language,
                        "lug",
                    )
                target_language = detect_language(translation)
                message = json_object["text"]

                save_translation(
                    from_number,
                    input_text,
                    translation,
                    detected_language,
                    target_language,
                    mess_id,
                )

                send_message(
                    message, os.getenv("WHATSAPP_TOKEN"), from_number, phone_number_id
                )

                # reply_to_message(
                # os.getenv("WHATSAPP_TOKEN"), mess_id,  from_number, phone_number_id, message,
                # )

                return f""" Here is the translation: {translation} """

        else:
            return response


def handle_message(
    payload, from_number, sender_name, source_language, target_language, phone_number_id
):
    if interactive_response := get_interactive_response(payload):
        response = interactive_response
        return f"Dear {sender_name}, Thanks for that response."

    if location := get_location(payload):
        response = location
        return f"Dear {sender_name}, We have no support for messages of type locations."

    if image := get_image(payload):
        response = image
        return f"Dear {sender_name}, We have no support for messages of type image."

    if video := get_video(payload):
        response = video
        return f"Dear {sender_name}, We have no support for messages of type video."

    if docs := get_document(payload):
        response = docs
        return f"Dear {sender_name}, We do not support documents."

    # if audio := get_audio(payload):
    #     return handle_audio_message(audio, target_language, sender_name)

    if reaction := get_reaction(payload):
        mess_id = reaction["message_id"]
        emoji = reaction["emoji"]
        update_feedback(mess_id, emoji)
        return f"Dear {sender_name}, Thanks for your feedback {emoji}."

    return handle_text_message(
        payload, from_number, sender_name, source_language, target_language
    )


def handle_text_message(
    payload, from_number, sender_name, source_language, target_language
):
    msg_body = get_message(payload)

    if not target_language or not source_language:
        set_default_target_language(from_number, save_user_preference)
        return welcome_message(sender_name)

    if msg_body.lower() in ["hi", "start"]:
        return welcome_message(sender_name)

    if msg_body.isdigit() and msg_body in languages_obj:
        return handle_language_selection(
            from_number, msg_body, source_language, save_user_preference, languages_obj
        )

    if msg_body.lower() == "help":
        return help_message()

    if 3 <= len(msg_body) <= 200:
        detected_language = detect_language(msg_body)
        translation = translate_text(msg_body, detected_language, target_language)
        mess_id = send_message(
            translation, whatsapp_token, from_number, get_phone_number_id(payload)
        )

        save_translation(
            from_number,
            msg_body,
            translation,
            detected_language,
            target_language,
            mess_id,
        )
        save_user_preference(from_number, detected_language, target_language)

        return None

    return "_Please send text that contains between 3 and 200 characters (about 30 to 50 words)._"


def translate_text(text, source_language, target_language):
    """
    Translates the given text from source_language to target_language.

    :param text: The text to be translated.
    :param source_language: The source language code.
    :param target_language: The target language code.
    :return: The translated text.
    """
    logging.info("Starting translation process")

    # URL for the endpoint
    url = f"https://api.runpod.ai/v2/{RUNPOD_ENDPOINT_ID}/runsync"
    # logging.info(f"Endpoint URL: {url}")

    # Authorization token
    token = os.getenv("RUNPOD_API_KEY")
    logging.info("Authorization token retrieved")

    # Data to be sent in the request body
    data = {
        "input": {
            "task": "translate",
            "source_language": source_language,
            "target_language": target_language,
            "text": text.strip(),
        }
    }
    # logging.info(f"Request data prepared: {data}")

    # Headers with authorization token
    headers = {"Authorization": token, "Content-Type": "application/json"}
    # logging.info(f"Request headers prepared: {headers}")

    # Sending the request to the API
    logging.info("Sending request to the translation API")
    response = requests.post(url, headers=headers, json=data)
    # logging.info(f"Response received: {response.json()}")

    # Handling the response
    if response.status_code == 200:
        translated_text = response.json()["output"]["translated_text"]
        # logging.info(f"Translation successful: {translated_text}")
    else:
        # logging.error(f"Error {response.status_code}: {response.text}")
        raise Exception(f"Error {response.status_code}: {response.text}")

    return translated_text


def detect_language(text):
    endpoint = runpod.Endpoint(os.getenv("RUNPOD_ENDPOINT_ID"))
    request_response = {}

    try:
        request_response = endpoint.run_sync(
            {
                "input": {
                    "task": "auto_detect_language",
                    "text": text,
                }
            },
            timeout=60,
        )

        logging.info("Request response: %s", request_response)

        if request_response:
            return request_response["language"]
        else:
            raise HTTPException(
                status_code=500,
                detail="Language detection failed. No output from the service.",
            )

    except TimeoutError as e:
        logging.error("Job timed out.")
        raise HTTPException(
            status_code=408,
            detail="The language identification job timed out. Please try again later.",
        ) from e
