from typing import List

from pydantic import BaseModel

class STTTranscript(BaseModel):
    text: str
    confidences: List[int] | None = None

class TranslationResponse(BaseModel):
    text: str
    confidences: List[int] | None = None

class TranslationRequest(BaseModel):
    source_language: str | None = None  # TODO: Make this an enum
    target_language: str  # TODO: Make this an enum
    text: str
    return_confidences: bool = False
