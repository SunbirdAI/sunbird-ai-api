import json
import logging
import os
import re
import shutil
import time

import requests
import runpod
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi_limiter.depends import RateLimiter
from sqlalchemy.orm import Session
from twilio.rest import Client
from werkzeug.utils import secure_filename

from app.crud.audio_transcription import create_audio_transcription
from app.deps import get_db
from app.inference_services.translate_inference import translate
from app.inference_services.user_preference import (
    get_user_preference,
    save_translation,
    save_user_preference,
    update_feedback,
)
from app.inference_services.whats_app_services import (
    get_phone_number_id, get_from_number, get_name, help_message,
    get_interactive_response, get_location, get_image, get_video, get_document, 
    get_audio, get_reaction, get_message, query_media_url, download_media, send_message, 
    valid_payload, welcome_message, handle_language_selection, set_default_target_language

)
from app.routers.auth import get_current_user
from app.schemas.tasks import (
    ChatRequest,
    ChatResponse,
    LanguageIdRequest,
    LanguageIdResponse,
    NllbLanguage,
    NllbTranslationRequest,
    NllbTranslationResponse,
    STTTranscript,
    SummarisationRequest,
    SummarisationResponse,
)
from app.utils.helper_utils import chunk_text
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


# Route for the Language identification endpoint
@router.post(
    "/language_id",
    response_model=LanguageIdResponse,
    dependencies=[Depends(RateLimiter(times=PER_MINUTE_RATE_LIMIT, seconds=60))],
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
    dependencies=[Depends(RateLimiter(times=PER_MINUTE_RATE_LIMIT, seconds=60))],
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

    try:
        request_response = endpoint.run_sync(
            {
                "input": {
                    "task": "language_classify",
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
    dependencies=[Depends(RateLimiter(times=PER_MINUTE_RATE_LIMIT, seconds=60))],
)
async def summarise(
    input_text: SummarisationRequest, current_user=Depends(get_current_user)
):
    """
    This endpoint does anonymised summarisation of a given text. The text languages
    supported for now are English (eng) and Luganda (lug).
    """

    endpoint = runpod.Endpoint(RUNPOD_ENDPOINT_ID)
    request_response = {}

    try:
        request_response = endpoint.run_sync(
            {
                "input": {
                    "task": "summarise",
                    "text": input_text.text,
                }
            },
            timeout=600,  # Timeout in seconds.
        )

        # Log the request for debugging purposes
        logging.info(f"Request response: {request_response}")

    except TimeoutError:
        logging.error("Job timed out.")
        raise HTTPException(
            status_code=408,
            detail="The summarisation job timed out. Please try again later.",
        )

    return request_response


@router.post(
    "/stt", dependencies=[Depends(RateLimiter(times=PER_MINUTE_RATE_LIMIT, seconds=60))]
)
async def speech_to_text(
    audio: UploadFile(...) = File(...),
    language: NllbLanguage = Form("lug"),
    adapter: NllbLanguage = Form("lug"),
    recognise_speakers: bool = Form(False),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> STTTranscript:
    """
    Upload an audio file and get the transcription text of the audio
    """
    endpoint = runpod.Endpoint(RUNPOD_ENDPOINT_ID)

    filename = secure_filename(audio.filename)
    file_path = os.path.join("/tmp", filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(audio.file, buffer)

    blob_name, blob_url = upload_audio_file(file_path=file_path)
    audio_file = blob_name
    os.remove(file_path)
    request_response = {}

    start_time = time.time()
    try:
        request_response = endpoint.run_sync(
            {
                "input": {
                    "task": "transcribe",
                    "target_lang": language,
                    "adapter": adapter,
                    "audio_file": audio_file,
                    "recognise_speakers": recognise_speakers,
                }
            },
            timeout=600,  # Timeout in seconds.
        )
    except TimeoutError:
        logging.error("Job timed out.")

    end_time = time.time()
    logging.info(f"Response: {request_response}")

    # Calculate the elapsed time
    elapsed_time = end_time - start_time
    logging.info(f"Elapsed time: {elapsed_time} seconds")
    transcription = request_response.get("audio_transcription")

    # Save transcription in database if it exists
    if (
        transcription is not None
        and isinstance(transcription, str)
        and len(transcription) > 0
    ):
        db_audio_transcription = create_audio_transcription(
            db, current_user, blob_url, blob_name, transcription
        )

        logging.info(
            f"Audio transcription in database :{db_audio_transcription.to_dict()}"
        )

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
    dependencies=[Depends(RateLimiter(times=PER_MINUTE_RATE_LIMIT, seconds=60))],
)
async def nllb_translate(
    translation_request: NllbTranslationRequest, current_user=Depends(get_current_user)
):
    """
    Source and Target Language can be one of: ach(Acholi), teo(Ateso), eng(English),
    lug(Luganda), lgg(Lugbara), or nyn(Runyankole).We currently only support English to Local
    languages and Local to English languages, so when the source language is one of the
    languages listed, the target can be any of the other languages.
    """
    endpoint = runpod.Endpoint(RUNPOD_ENDPOINT_ID)

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
        request_response = endpoint.run_sync(
            data,
            timeout=600,  # Timeout in seconds.
        )
    except TimeoutError:
        logging.error("Job timed out.")

    end_time = time.time()
    logging.info(f"Response: {request_response}")

    # Calculate the elapsed time
    elapsed_time = end_time - start_time
    logging.info(f"Elapsed time: {elapsed_time} seconds")

    response = {}
    response["output"] = request_response

    return response


@router.post(
    "/chat",
    response_model=ChatResponse,
    dependencies=[Depends(RateLimiter(times=PER_MINUTE_RATE_LIMIT, seconds=60))],
)
async def chat(chat_request: ChatRequest, current_user=Depends(get_current_user)):
    """
    Chat endpoint. Returns a WhatsApp chat response to user text sent in via WhatsApp chat
    """
    # Translate from English to the local language and if it returns
    # the same thing, then translate from the local language to English.
    # Note: This is a temporary solution until language detection is implemented
    response = translate(chat_request.text, "English", chat_request.local_language)
    if re.fullmatch(f"{chat_request.text}[.?]?", response):
        response = translate(chat_request.text, chat_request.local_language, "English")

    # Send message via chat
    account_sid = chat_request.twilio_sid
    auth_token = chat_request.twilio_token
    from_number = chat_request.from_number
    to_number = chat_request.to_number
    client = Client(account_sid, auth_token)

    _ = client.messages.create(
        from_=f"whatsapp:{from_number}", body=response, to=f"whatsapp:{to_number}"
    )

    return ChatResponse(chat_response=response)


@router.post("/webhook")
async def webhook(payload: dict):
    try:
        logging.info(f"Received payload: {json.dumps(payload, indent=2)}")

        if not valid_payload(payload):
            return {"status": "invalid payload"}

        phone_number_id = get_phone_number_id(payload)
        from_number = get_from_number(payload)
        sender_name = get_name(payload)
        source_language, target_language = get_user_preference(from_number)

        message = handle_message(payload, from_number, sender_name, source_language, target_language, phone_number_id)

        if message:
            send_message(message, os.getenv("WHATSAPP_TOKEN"), from_number, phone_number_id)

        return {"status": "success"}

    except Exception as error:
        logging.error(f"Error in webhook processing: {str(error)}")
        raise HTTPException(status_code=500, detail="Internal Server Error") from error

@router.get("/webhook")
async def verify_webhook(mode: str, token: str, challenge: str):
    if mode and token:
        if mode != "subscribe" or token != os.getenv("VERIFY_TOKEN"):
            raise HTTPException(status_code=403, detail="Forbidden")

        logging.info("WEBHOOK_VERIFIED")
        return {"challenge": challenge}
    raise HTTPException(status_code=400, detail="Bad Request")

def handle_message(payload, from_number, sender_name, source_language, target_language, phone_number_id):
    if interactive_response := get_interactive_response(payload):
        return f"Dear {sender_name}, Thanks for that response."
    
    if location := get_location(payload):
        return f"Dear {sender_name}, We have no support for messages of type locations."
    
    if image := get_image(payload):
        return f"Dear {sender_name}, We have no support for messages of type image."
    
    if video := get_video(payload):
        return f"Dear {sender_name}, We have no support for messages of type video."
    
    if docs := get_document(payload):
        return f"Dear {sender_name}, We do not support documents."
    
    if audio := get_audio(payload):
        return handle_audio_message(audio, target_language, sender_name)
    
    if reaction := get_reaction(payload):
        mess_id = reaction["message_id"]
        emoji = reaction["emoji"]
        update_feedback(mess_id, emoji)
        return f"Dear {sender_name}, Thanks for your feedback {emoji}."
    
    return handle_text_message(payload, from_number, sender_name, source_language, target_language)

def handle_audio_message(audio, target_language, sender_name):
    try:
        audio_id = audio["id"]
        mime_type = audio["mime_type"]

        if target_language:
            file_path = download_media(query_media_url(audio_id, os.getenv("WHATSAPP_TOKEN")), os.getenv("WHATSAPP_TOKEN"))
            transcription = process_speech_to_text(file_path, target_language)
            if transcription:
                return transcription
            else:
                return "Sorry, there was an issue processing your audio file."
        else:
            return f"Dear {sender_name}, Please specify the language for transcription."
    
    except Exception as e:
        logging.error(f"Error processing audio file: {str(e)}")
        return "Sorry, there was an issue processing your audio file."

def handle_text_message(payload, from_number, sender_name, source_language, target_language):
    msg_body = get_message(payload)

    if not target_language or not source_language:
        set_default_target_language(from_number,save_user_preference)
        return welcome_message(sender_name)
    
    if msg_body.lower() in ["hi", "start"]:
        return welcome_message(sender_name)
    
    if msg_body.isdigit() and msg_body in languages_obj:
        return handle_language_selection(from_number, msg_body, source_language,save_user_preference, languages_obj)
    
    if msg_body.lower() == "help":
        return help_message()
    
    if 3 <= len(msg_body) <= 200:
        detected_language = detect_language(msg_body)
        translation = translate_text(msg_body, detected_language, target_language)
        mess_id = send_message(translation, whatsapp_token, from_number, get_phone_number_id(payload))
        
        save_translation(from_number, msg_body, translation, detected_language, target_language, mess_id)
        save_user_preference(from_number, detected_language, target_language)

        return translation

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
    logging.info(f"Endpoint URL: {url}")

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
    logging.info(f"Request data prepared: {data}")

    # Headers with authorization token
    headers = {"Authorization": token, "Content-Type": "application/json"}
    logging.info(f"Request headers prepared: {headers}")

    # Sending the request to the API
    logging.info("Sending request to the translation API")
    response = requests.post(url, headers=headers, json=data)
    logging.info(f"Response received: {response.json()}")

    # Handling the response
    if response.status_code == 200:
        translated_text = response.json()["output"]["translated_text"]
        logging.info(f"Translation successful: {translated_text}")
    else:
        logging.error(f"Error {response.status_code}: {response.text}")
        raise Exception(f"Error {response.status_code}: {response.text}")

    return translated_text

def process_speech_to_text(file_path, language: str):
    endpoint = runpod.Endpoint(RUNPOD_ENDPOINT_ID)

    logging.info(f"File path: {file_path}")
    blob_name = upload_audio_file(file_path=file_path)
    audio_file = blob_name
    os.remove(file_path)
    request_response = {}

    start_time = time.time()
    try:
        request_response = endpoint.run_sync(
            {
                "input": {
                    "task": "transcribe",
                    "target_lang": language,
                    "adapter": language,
                    "audio_file": audio_file,
                }
            },
            timeout=600,  # Timeout in seconds.
        )
    except TimeoutError:
        logging.error("Job timed out.")

    end_time = time.time()
    logging.info(f"Response: {request_response}")

    # Calculate the elapsed time
    elapsed_time = end_time - start_time
    logging.info(f"Elapsed time: {elapsed_time} seconds")

    return request_response.get("audio_transcription")

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

        logging.info(f"Request response: {request_response}")

        if request_response:
            return request_response["language"]
        else:
            raise HTTPException(
                status_code=500,
                detail="Language detection failed. No output from the service.",
            )

    except TimeoutError:
        logging.error("Job timed out.")
        raise HTTPException(
            status_code=408,
            detail="The language identification job timed out. Please try again later.",
        )