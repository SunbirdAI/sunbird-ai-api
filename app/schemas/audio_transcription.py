from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, EmailStr, HttpUrl


class OrderBy(str, Enum):
    id = "id"
    uploaded = "uploaded"


class ItemQueryParams(BaseModel):
    order_by: OrderBy = OrderBy.uploaded
    descending: bool = False


class AudioTranscriptionBase(BaseModel):
    id: str
    username: str
    email: EmailStr
    audio_file_url: HttpUrl
    filename: str
    uploaded: Optional[datetime] = None
    transcription: Optional[str] = None


class AudioTranscriptionCreate(AudioTranscriptionBase):
    class Config:
        orm_mode = True
