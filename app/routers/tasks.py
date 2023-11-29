import os
import io

from dotenv import load_dotenv

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


@router.post("/chat", response_model=None, dependencies=None)
def chat(chat_request: ChatRequest, current_user=Depends(get_current_user)):
    """
    Chat endpoint. Returns a WhatsApp chat response to user text sent in via WhatsApp chat
    """
    response = translate(chat_request.text, chat_request.source_language,
                         chat_request.target_language)
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

    return ChatResponse(chat_response=response.text)
