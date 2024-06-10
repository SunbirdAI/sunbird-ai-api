import io
import json
import logging
import os
import re
import shutil
import time
import requests
from app.inference_services.stt_inference import transcribe
from app.inference_services.user_preference import get_user_preference, save_translation, save_user_preference
from app.inference_services.whats_app_services import download_media, get_audio, get_document, get_image, get_interactive_response, get_location, get_media_url, get_message_id, get_name, get_video, process_audio_message, send_audio, send_message
import runpod
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi_limiter.depends import RateLimiter
from twilio.rest import Client
from werkzeug.utils import secure_filename

from app.inference_services.translate_inference import translate
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
from app.utils.upload_audio_file_gcp import upload_audio_file

router = APIRouter()

load_dotenv()
logging.basicConfig(level=logging.INFO)

PER_MINUTE_RATE_LIMIT = os.getenv("PER_MINUTE_RATE_LIMIT", 10)
RUNPOD_ENDPOINT_ID = os.getenv("RUNPOD_ENDPOINT_ID")
# Set RunPod API Key
runpod.api_key = os.getenv("RUNPOD_API_KEY")

# Access token for your app
token = os.getenv("WHATSAPP_TOKEN")
verify_token = os.getenv("VERIFY_TOKEN")

languages_obj = {
    "1": "Luganda",
    "2": "Acholi",
    "3": "Ateso",
    "4": "Lugbara",
    "5": "Runyankole",
    "6": "English",
    "7": "Luganda",
    "8": "Acholi",
    "9": "Ateso",
    "10": "Lugbara",
    "11": "Runyankole"
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
                    "adapter": adapter,
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
    return STTTranscript(
        audio_transcription=request_response.get("audio_transcription")
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
    # URL for the endpoint
    url = f"https://api.runpod.ai/v2/{RUNPOD_ENDPOINT_ID}/runsync"

    # Authorization token
    token = os.getenv("RUNPOD_API_KEY")

    # Split text into chunks of 100 words each
    text = translation_request.text
    text_chunks = chunk_text(text, chunk_size=100)
    logging.info(f"text_chunks length: {len(text_chunks)}")

    # Translated chunks will be stored here
    translated_text_chunks = []

    for chunk in text_chunks:
        # Data to be sent in the request body
        data = {
            "input": {
                "task": "translate",
                "source_language": translation_request.source_language,
                "target_language": translation_request.target_language,
                "text": chunk.strip(),  # Remove leading/trailing spaces
            }
        }

        # Headers with authorization token
        headers = {"Authorization": token, "Content-Type": "application/json"}

        response = requests.post(url, headers=headers, json=data)
        logging.info(f"response: {response.json()}")

        if response.status_code == 200:
            translated_chunk = response.json()["output"]["translated_text"]
            translated_text_chunks.append(translated_chunk)
        else:
            raise HTTPException(status_code=response.status_code, detail=response.text)

    logging.info(f"translated_text_chunks: {translated_text_chunks}")
    # Concatenate translated chunks
    final_translated_text = " ".join(translated_text_chunks)
    response = response.json()
    response["output"]["text"] = text
    response["output"]["translated_text"] = final_translated_text

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
        body = payload
        print(json.dumps(payload, indent=2))

        if "object" in payload and (
                        "entry" in payload
                        and payload["entry"]
                        and "changes" in payload["entry"][0]
                        and payload["entry"][0]["changes"]
                        and payload["entry"][0]["changes"][0]
                        and "value" in payload["entry"][0]["changes"][0]
                        and "messages" in payload["entry"][0]["changes"][0]["value"]
                        and payload["entry"][0]["changes"][0]["value"]["messages"]
                    ):
            phone_number_id = payload["entry"][0]["changes"][0]["value"]["metadata"]["phone_number_id"]
            from_number = payload["entry"][0]["changes"][0]["value"]["messages"][0]["from"]
            message_id = get_message_id(payload)
            
            # Get user's whatsapp username.
            sender_name = get_name(body)

            # Get user's language preference
            # Welcome Message and Onboarding
            source_language, target_language = get_user_preference(from_number)

            message = None

            if interactive_response := get_interactive_response(payload):
                message = f"Dear {sender_name}, Thanks for that response."

            elif location := get_location(payload):
                message = f"Dear {sender_name}, We have no support for messages of type locations"

            elif image := get_image(payload):
                message = f"Dear {sender_name}, We have no support for messages of type image"

            elif video := get_video(payload):
                message = f"Dear {sender_name}, We have no support for messages of type video"

            elif docs := get_document(payload):
                message = f"Dear {sender_name}, We do not support documents"

            elif audio := get_audio(payload):
                audio_id = process_audio_message(payload)
                audio_link = get_media_url(audio_id, token)
                # Assume `download_audio_file` is a function you implement to download the audio file
                audio_file_path = download_media(audio_link,token)
                message = "Speech to text currently not supported"
                # Now call your speech_to_text service with the downloaded audio file
                # message = await speech_to_text_whatsapp(audio_file_path, Language("Luganda"))


            # elif audio := get_audio(payload):
            #     audio_link = process_audio_message(payload)
            #     message = f"Dear {sender_name}, Your audio file has been recivced but the functionality is under improvement. Here is your audio Url: {audio_link}"

            else:
                msg_body = payload["entry"][0]["changes"][0]["value"]["messages"][0]["text"]["body"]

                # Check if either source or target language is None, indicating a new user
                if source_language is None or target_language is None:
                    # Set default languages for a new user
                    default_source_language = "English"  # Example default source language
                    default_target_language = "Luganda"  # Example default target language
                    save_user_preference(from_number, default_source_language, default_target_language)

                    # Indicate new user for welcome message
                    # You can send a welcome message here, explaining how to set their preferred languages
                    message = "🌟 Welcome to Sunbird AI Translation Service! 🌟\nWe're delighted to have you here! Whether you need help or want to get started, we're here for you.\nType 'help' for assistance or select your preferred language by typing its corresponding number:\n1: Luganda\n2: Acholi\n3: Ateso\n4: Lugbara\n5: Runyankole"

                elif msg_body.lower() in ["hi", "start"]:
                    message = (
                        f"Hello {sender_name},\n\n"
                        "Welcome to our translation service! 🌍\n\n"
                        "Reply 'help' anytime for instructions on how to use this service.\n\n"
                        "Please choose the language you prefer to translate to:\n"
                        "1: Luganda (default)\n"
                        "2: Acholi\n"
                        "3: Ateso\n"
                        "4: Lugbara\n"
                        "5: Runyankole\n"
                        "6: English\n"
                        "More options coming soon!.\n"
                        "Note\n"
                        "For options 1 to 5 you should transalting from English."
                        )


                elif msg_body.isdigit() and msg_body in languages_obj:
                    
                    if int(msg_body) == 6:
                        save_user_preference(from_number, "Not Set",languages_obj[msg_body])
                        message = (
                            "Please choose a language you are going to translate from:\n"
                            "Reply 'help' anytime for instructions on how to use this service.\n"
                            "7: Luganda\n"
                            "8: Acholi\n"
                            "9: Ateso\n"
                            "10: Lugbara\n"
                            "11: Runyankole\n"
                            "More options coming soon!"
                        )
                    # elif msg_body.isdigit() and int(msg_body) == 7:
                    #     save_user_preference(from_number, languages_obj[msg_body],target_language)
                    #     message = (
                    #         f"Your options now set to {languages_obj[msg_body]}. You can now send texts that will be translated to audio."
                    #     )

                    elif msg_body.isdigit() and int(msg_body) > 6:
                        save_user_preference(from_number,languages_obj[msg_body],"English")
                        message = (
                            f"You are now translating from {languages_obj[msg_body]} to English. You can now send texts to translate."
                        )

                    else:
                        save_user_preference(from_number, "English",languages_obj[msg_body])
                        message = (
                            f"Language set to {languages_obj[msg_body]}. You can now send texts to translate."
                        )

                elif msg_body.lower() == "help":
                    message = "Help: Reply 'hi' to choose another language. Send text to translate."

                elif source_language == "Text to Speech Translations":
                    # Create a TTSRequest object
                    request = TTSRequest(text=message, return_audio_link=True)
                    audio_link = tts(request=request)
                    send_audio(token,audio_link,phone_number_id,from_number)

                elif 3 <= len(msg_body) <= 200:
                    if source_language == "Not Set":
                        message = "Please set your source language first."
                    else:
                        # Translation Feature
                        from_lang = source_language  # Placeholder for auto-detection
                        to_lang = target_language 
                        translated_text = translate(msg_body, from_lang, to_lang)
                        message = translated_text
                    
                        # Save the translation
                        save_translation(from_number, msg_body, message, source_language, target_language)
                        # if to_lang == "Luganda":
                        # # Generate the audio response
                        # # tts_response = text_to_speech_whatsapp(TTSRequest(text=message, return_audio_link=True))
                        # # audio_link = tts_response.audio_link  # Assuming this is the URL to the audio file
                        # # send_audio(token, audio_link,phone_number_id,from_number)
                    
                else:
                    message = "_Please send text that contains between 3 and 200 characters (about 30 to 50 words)._"
            
            send_message(message, token, from_number, phone_number_id)
            
        return {"status": "success"}

    except Exception as error:
        print(f"Error in webhook processing: {str(error)}")
        raise HTTPException(status_code=500, detail="Internal Server Error") from error


@router.get("/webhook")
async def verify_webhook(mode: str, token: str, challenge: str):
    if mode and token:
        if mode != "subscribe" or token != verify_token:
            raise HTTPException(status_code=403, detail="Forbidden")

        print("WEBHOOK_VERIFIED")
        return {"challenge": challenge}
    raise HTTPException(status_code=400, detail="Bad Request")

# def speech_to_text_whatsapp(
#     audio: UploadFile(...) = File(...),
#     language: Language = Form("Luganda"),
#     return_confidences: bool = Form(False),) -> STTTranscript:  # TODO: Make language an enum
#     """
#     We currently only support Luganda.
#     """
#     if not audio.content_type.startswith("audio"):
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="Invalid file type uploaded. Please upload a valid audio file",
#         )
#     if audio.content_type != "audio/wave":
#         # try to convert to wave, if it fails return an error.
#         buf = io.BytesIO()
#         audio_file = audio.file
#         audio = AudioSegment.from_file(audio_file)
#         audio = audio.export(buf, format="wav")

#     response = transcribe(audio)
#     return STTTranscript(text=response)

# def text_to_speech_whatsapp(tts_request: TTSRequest):
#     """
#     Text to Speech endpoint. Returns a base64 string, which can be decoded to a .wav file.
#     """
#     response = tts(tts_request)
#     if tts_request.return_audio_link:
#         return TTSResponse(audio_link=response)
#     return TTSResponse(base64_string=response)