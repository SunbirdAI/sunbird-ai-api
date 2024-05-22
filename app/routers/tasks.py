import os
import re
import shutil
import time

import requests
import runpod
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi_limiter.depends import RateLimiter
from twilio.rest import Client
from werkzeug.utils import secure_filename

from app.inference_services.translate_inference import translate, translate_batch
from app.inference_services.tts_inference import tts
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
    TranslationBatchRequest,
    TranslationBatchResponse,
    TranslationRequest,
    TranslationResponse,
    TTSRequest,
    TTSResponse,
)
from app.utils.helper_utils import chunk_text
from app.utils.upload_audio_file_gcp import upload_audio_file

router = APIRouter()

load_dotenv()
PER_MINUTE_RATE_LIMIT = os.getenv("PER_MINUTE_RATE_LIMIT", 10)
RUNPOD_ENDPOINT_LANGUAGE_ID_ID = os.getenv("RUNPOD_ENDPOINT_LANGUAGE_ID_ID")
# Set RunPod API Key
runpod.api_key = os.getenv("RUNPOD_API_KEY")

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

    # Define the endpoint ID for language identification
    endpoint = runpod.Endpoint(RUNPOD_ENDPOINT_LANGUAGE_ID_ID)

    try:
        # Run the language identification request asynchronously
        run_request = endpoint.run_sync(
            {
                "input": {
                    "text": languageId_request.text,
                }
            },
            timeout=60,  # Timeout in seconds.
        )

        # Log the request for debugging purposes
        print(run_request)

    except TimeoutError:
        # Handle timeout error and return a meaningful message to the user
        print("Job timed out.")
        raise HTTPException(
            status_code=408,
            detail="The language identification job timed out. Please try again later.",
        )

    # Return the result of the language identification request
    return run_request


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
    endpoint = runpod.Endpoint(os.getenv("RUNPOD_ENDPOINT_ASR_STT_ID"))

    filename = secure_filename(audio.filename)
    file_path = os.path.join("/tmp", filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(audio.file, buffer)

    blob_name = upload_audio_file(file_path=file_path)
    audio_file = blob_name
    os.remove(file_path)

    start_time = time.time()
    try:
        run_request = endpoint.run_sync(
            {
                "input": {
                    "target_lang": language,
                    "adapter": adapter,
                    "audio_file": audio_file,
                }
            },
            timeout=600,  # Timeout in seconds.
        )
    except TimeoutError:
        print("Job timed out.")

    end_time = time.time()

    # Calculate the elapsed time
    elapsed_time = end_time - start_time
    print("Elapsed time:", elapsed_time, "seconds")
    return STTTranscript(audio_transcription=run_request.get("audio_transcription"))


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
    ENDPOINT_ID = os.getenv("RUNPOD_ENDPOINT_ID")
    url = f"https://api.runpod.ai/v2/{ENDPOINT_ID}/runsync"

    # Authorization token
    token = os.getenv("RUNPOD_API_KEY")

    # Split text into chunks of 100 words each
    text = translation_request.text
    text_chunks = chunk_text(text, chunk_size=100)
    print(f"text_chunks length: {len(text_chunks)}")

    # Translated chunks will be stored here
    translated_text_chunks = []

    for chunk in text_chunks:
        # Data to be sent in the request body
        data = {
            "input": {
                "source_language": translation_request.source_language,
                "target_language": translation_request.target_language,
                "text": chunk.strip(),  # Remove leading/trailing spaces
            }
        }

        # Headers with authorization token
        headers = {"Authorization": token, "Content-Type": "application/json"}

        response = requests.post(url, headers=headers, json=data)

        if response.status_code == 200:
            translated_chunk = response.json()["output"]["data"]["translated_text"]
            translated_text_chunks.append(translated_chunk)
        else:
            raise HTTPException(status_code=response.status_code, detail=response.text)

    # Concatenate translated chunks
    final_translated_text = " ".join(translated_text_chunks)
    response = response.json()
    response["output"]["data"]["text"] = text
    response["output"]["data"]["translated_text"] = final_translated_text

    return response


@router.post(
    "/translate",
    response_model=TranslationResponse,
    dependencies=[Depends(RateLimiter(times=PER_MINUTE_RATE_LIMIT, seconds=60))],
)
def translate_(
    translation_request: TranslationRequest, current_user=Depends(get_current_user)
):
    """
    Source and Target Language can be one of: Acholi, Ateso, English, Luganda, Lugbara, or Runyankole.
    We currently only support English to Local languages and Local to English languages, so when the
    source language is one of the Local languages, the target can only be English.
    """
    response = translate(
        translation_request.text,
        translation_request.source_language,
        translation_request.target_language,
    )
    return TranslationResponse(text=response)


@router.post(
    "/translate-batch",
    response_model=TranslationBatchResponse,
    dependencies=[Depends(RateLimiter(times=PER_MINUTE_RATE_LIMIT, seconds=60))],
)
def translate_batch_(
    translation_batch_request: TranslationBatchRequest,
    current_user=Depends(get_current_user),
):
    """
    Submit multiple translation queries. See the /translate endpoint for caveats.
    """
    response = translate_batch(translation_batch_request)
    return TranslationBatchResponse(
        responses=[TranslationResponse(text=text) for text in response]
    )


@router.post(
    "/tts",
    response_model=TTSResponse,
    dependencies=[Depends(RateLimiter(times=PER_MINUTE_RATE_LIMIT, seconds=60))],
)
def text_to_speech(tts_request: TTSRequest, current_user=Depends(get_current_user)):
    """
    Text to Speech endpoint. Returns a base64 string, which can be decoded to a .wav file.
    """
    response = tts(tts_request)
    if tts_request.return_audio_link:
        return TTSResponse(audio_link=response)
    return TTSResponse(base64_string=response)


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
