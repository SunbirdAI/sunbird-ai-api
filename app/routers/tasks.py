from fastapi import APIRouter, HTTPException, status, File, UploadFile, Form
from app.models.tasks import STTTranscript
from app.inference_services.stt_inference import transcribe

router = APIRouter()


@router.post("/stt")
async def speech_to_text(
        audio: UploadFile(...) = File(...),
        language: str = Form("Luganda"),
        return_confidences: bool = Form(False)) -> STTTranscript:  # TODO: Make language an enum

    response = transcribe(audio)
    return STTTranscript(text=response.json()['transcript'])
