from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, constr


class STTTranscript(BaseModel):
    """changes"""

    audio_transcription: Optional[str] = Field(None)
    diarization_output: Optional[dict] = Field(None)
    formatted_diarization_output: Optional[str] = Field(None)
    audio_transcription_id: Optional[int] = Field(None)


class NllbResponseOutputData(BaseModel):
    text: str
    translated_text: str


class NllbTranslationResponse(BaseModel):
    output: NllbResponseOutputData


class LanguageIdRequest(BaseModel):
    text: str = Field(min_length=3, max_length=200)


class LanguageIdResponse(BaseModel):
    language: str


class SummarisationRequest(BaseModel):
    text: str


class SummarisationResponse(BaseModel):
    summarized_text: str


class AudioDetectedLanguageResponse(BaseModel):
    detected_language: str


class TranslationResponse(BaseModel):
    text: str
    # confidences: List[int] | None = None
    confidences: Optional[List[int]] = None


class Language(str, Enum):
    acholi = "Acholi"
    ateso = "Ateso"
    english = "English"
    luganda = "Luganda"
    lugbara = "Lugbara"
    runyankole = "Runyankole"


class NllbLanguage(str, Enum):
    acholi = "ach"
    ateso = "teo"
    english = "eng"
    luganda = "lug"
    lugbara = "lgg"
    runyankole = "nyn"


class NllbTranslationRequest(BaseModel):
    source_language: NllbLanguage
    target_language: NllbLanguage
    text: constr(min_length=1, strip_whitespace=True)  # type: ignore


class TranslationRequest(BaseModel):
    # source_language: Language | None = None
    source_language: Optional[Language] = None
    target_language: Language
    text: str = Field(min_length=3, max_length=200)
    return_confidences: bool = False


class TranslationBatchRequest(BaseModel):
    requests: List[
        TranslationRequest
    ]  # TODO: What should be the maximum length of this list?


class TranslationBatchResponse(BaseModel):
    responses: List[TranslationResponse]


class TTSRequest(BaseModel):
    text: str
    return_audio_link: bool = False


class TTSResponse(BaseModel):
    # base64_string: str | None = None
    # audio_link: str | None = None
    base64_string: Optional[str] = None
    audio_link: Optional[str] = None


class ChatRequest(BaseModel):
    local_language: Language
    text: str = Field(min_length=3, max_length=200)
    from_number: str = Field(min_length=5, max_length=15)
    to_number: str = Field(min_length=5, max_length=15)
    twilio_sid: str = Field(min_length=5, max_length=256)
    twilio_token: str = Field(min_length=5, max_length=256)
    return_confidences: bool = False


class ChatResponse(BaseModel):
    chat_response: str = Field(min_length=2)
