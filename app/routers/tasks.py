import json
import os
import io
import re

from dotenv import load_dotenv
import requests

from fastapi import APIRouter, HTTPException, status, File, UploadFile, Form, Depends
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
    1: "Luganda",
    2: "Acholi",
    3: "Ateso",
    4: "Lugbara",
    5: "Runyankole",
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
        whatsapp_response = None
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
            msg_body = payload["entry"][0]["changes"][0]["value"]["messages"][0]["text"]["body"]

            if msg_body.lower() == "hi":
                whatsapp_response = (
                    "Hi.\nPlease choose a local language to translate to and from English:\n"
                    "1: Luganda (default)\n"
                    "2: Acholi\n"
                    "3: Ateso\n"
                    "4: Lugbara\n"
                    "5: Runyankole"
                )

            elif msg_body in languages_obj:
                print(f"User menu choice: {msg_body}: {languages_obj[msg_body]}")

                whatsapp_response = (
                    f"_Local language set to_ {languages_obj[msg_body]}.\n"
                    "_Please note that language options might take a few minutes to update._"
                )

            elif 3 <= len(msg_body) <= 200:
                translated_text = translate(msg_body, "English", "Luganda")
                whatsapp_response = translated_text["text"]
                print(f"Translated Text: {whatsapp_response}")
            else:
                whatsapp_response = "_Please send text that contains between 3 and 200 characters (about 30 to 50 words)._"
            send_whatsapp_message(phone_number_id, from_number, whatsapp_response)
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


async def send_whatsapp_message(phone_number_id, to, text):
    response = requests.post(
        f"https://graph.facebook.com/v12.0/{phone_number_id}/messages?access_token={token}",
        json={"messaging_product": "whatsapp", "to": to, "text": {"body": text}},
        headers={"Content-Type": "application/json"},
    )
    response.raise_for_status()