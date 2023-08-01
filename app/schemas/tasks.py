from typing import List
from pydantic import BaseModel, Field
from enum import Enum

class STTTranscript(BaseModel):
    text: str
    confidences: List[int] | None = None

class TranslationResponse(BaseModel):
    text: str
    confidences: List[int] | None = None

class Language(str, Enum):
    acholi = "Acholi"
    ateso = "Ateso"
    english = "English"
    luganda = "Luganda"
    lugbara = "Lugbara"
    runyankole = "Runyankole"

class TranslationRequest(BaseModel):
    source_language: Language | None = None
    target_language: Language
    text: str = Field(min_length=3, max_length=200)
    return_confidences: bool = False

class TranslationBatchRequest(BaseModel):
    requests: List[TranslationRequest]  # TODO: What should be the maximum length of this list?

class TranslationBatchResponse(BaseModel):
    responses: List[TranslationResponse]

class TTSRequest(BaseModel):
    text: str
    return_audio_link: bool = False

class TTSResponse(BaseModel):
    base64_string: str
