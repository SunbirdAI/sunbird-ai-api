from fastapi import APIRouter, HTTPException, status, File, UploadFile, Form
from app.models.tasks import STTTranscript

router = APIRouter()


@router.post("/stt")
async def speech_to_text(
        audio: UploadFile(...) = File(...),
        language: str = Form("Luganda"),
        return_confidences: bool = Form(False)) -> STTTranscript:  # TODO: Make language an enum

    return STTTranscript(text="TODO: Some dummy transcript", confidences=[0, 1, 2])

