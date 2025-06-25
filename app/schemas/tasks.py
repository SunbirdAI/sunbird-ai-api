from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, constr


class STTTranscript(BaseModel):
    """changes"""

    audio_transcription: Optional[str] = None
    diarization_output: Optional[Dict[str, Any]] = {}
    formatted_diarization_output: Optional[str] = None
    audio_transcription_id: Optional[int] = None
    audio_url: Optional[str] = None
    language: Optional[str] = None
    was_audio_trimmed: Optional[bool] = False
    original_duration_minutes: Optional[float] = None


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


class SttbLanguage(str, Enum):
    acholi = "ach"
    ateso = "teo"
    english = "eng"
    luganda = "lug"
    lugbara = "lgg"
    runyankole = "nyn"
    swahili = "swa"
    kinyarwanda = "kin"
    lusoga = "xog"
    lumasaba = "myx"


# Speaker IDs:
# 241: Acholi (female)
# 242: Ateso (female)
# 243: Runyankore (female)
# 245: Lugbara (female)
# 246: Swahili (male)
# 248: Luganda (female)
class SpeakerID(int, Enum):
    acholi_female = 241
    ateso_female = 242
    runyankore_female = 243
    lugbara_female = 245
    swahili_male = 246
    luganda_female = 248


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
    speaker_id: SpeakerID = SpeakerID.luganda_female
    temperature: float = 0.8
    top_k: int = 50
    top_p: float = 1.0
    max_new_audio_tokens: int = 2048
    normalize: bool = False


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


# Create a schema for the upload request
class UploadRequest(BaseModel):
    file_name: str
    content_type: str


# Create a schema for the upload response
class UploadResponse(BaseModel):
    upload_url: str
    file_id: str
    expires_at: datetime
