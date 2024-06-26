from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, HttpUrl


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
