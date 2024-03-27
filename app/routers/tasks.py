import json
import os
import io
import re

from dotenv import load_dotenv
import requests

from fastapi import APIRouter, HTTPException, status, File, UploadFile, Form, Depends
from app.inference_services.user_preference import get_user_preference, save_translation, save_user_preference
from app.inference_services.whats_app_services import get_audio, get_document, get_image, get_interactive_response, get_location, get_message_id, get_name, get_video, process_audio_message, send_audio, send_message
from app.schemas.tasks import (
    STTTranscript,
    TranslationRequest,
    TranslationResponse,
    TranslationBatchRequest,
    TranslationBatchResponse,
    TTSRequest,
    TTSResponse,
    ChatRequest,
    ChatResponse,
    Language
)

from app.inference_services.stt_inference import transcribe
from app.inference_services.translate_inference import translate, translate_batch
from app.inference_services.tts_inference import tts
from app.routers.auth import get_current_user
from pydub import AudioSegment
from fastapi_limiter.depends import RateLimiter
from twilio.rest import Client


router = APIRouter()

load_dotenv()
PER_MINUTE_RATE_LIMIT = os.getenv('PER_MINUTE_RATE_LIMIT', 10)

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

@router.post("/stt",
             dependencies=[Depends(RateLimiter(times=PER_MINUTE_RATE_LIMIT, seconds=60))])
async def speech_to_text(
        audio: UploadFile(...) = File(...),
        language: Language = Form("Luganda"),
        return_confidences: bool = Form(False),
        current_user=Depends(get_current_user)) -> STTTranscript:  # TODO: Make language an enum
    """
    We currently only support Luganda.
    """
    if not audio.content_type.startswith("audio"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Invalid file type uploaded. Please upload a valid audio file")
    if audio.content_type != "audio/wave":
        # try to convert to wave, if it fails return an error.
        buf = io.BytesIO()
        audio_file = audio.file
        audio = AudioSegment.from_file(audio_file)
        audio = audio.export(buf, format="wav")

    response = transcribe(audio)
    return STTTranscript(text=response)


@router.post("/translate",
             response_model=TranslationResponse,
             dependencies=[Depends(RateLimiter(times=PER_MINUTE_RATE_LIMIT, seconds=60))])
def translate_(translation_request: TranslationRequest, current_user=Depends(get_current_user)):
    """
    Source and Target Language can be one of: Acholi, Ateso, English, Luganda, Lugbara, or Runyankole.
    We currently only support English to Local languages and Local to English languages, so when the source language is one of the Local languages, the target can only be English.
    """
    response = translate(translation_request.text, translation_request.source_language,
                         translation_request.target_language)
    return TranslationResponse(text=response)


@router.post("/translate-batch",
             response_model=TranslationBatchResponse,
             dependencies=[Depends(RateLimiter(times=PER_MINUTE_RATE_LIMIT, seconds=60))])
def translate_batch_(translation_batch_request: TranslationBatchRequest, current_user=Depends(get_current_user)):
    """
    Submit multiple translation queries. See the /translate endpoint for caveats.
    """
    response = translate_batch(translation_batch_request)
    return TranslationBatchResponse(responses=[TranslationResponse(text=text) for text in response])


@router.post("/tts",
             response_model=TTSResponse,
             dependencies=[Depends(RateLimiter(times=PER_MINUTE_RATE_LIMIT, seconds=60))])
def text_to_speech(tts_request: TTSRequest, current_user=Depends(get_current_user)):
    """
    Text to Speech endpoint. Returns a base64 string, which can be decoded to a .wav file.
    """
    response = tts(tts_request)
    if tts_request.return_audio_link:
        return TTSResponse(audio_link=response)
    return TTSResponse(base64_string=response)


@router.post("/chat",
             response_model=ChatResponse,
             dependencies=[Depends(RateLimiter(times=PER_MINUTE_RATE_LIMIT, seconds=60))])
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

    message = client.messages.create(
        from_=f"whatsapp:{from_number}",
        body=response,
        to=f"whatsapp:{to_number}"
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
                audio_link = process_audio_message(payload)
                message = f"Dear {sender_name}, Your audio file has been recivced but the functionality is under improvement. Here is your audio Url: {audio_link}"

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

                        # if to_lang == "Luganda":
                        #     # Create a TTSRequest object
                        #     request = TTSRequest(text=message, return_audio_link=True)
                        #     audio_link = tts(request=request)
                        #     send_audio(token, audio_link,phone_number_id,from_number)
                    
                        # Save the translation
                        save_translation(from_number, msg_body, message, source_language, target_language)
                    
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