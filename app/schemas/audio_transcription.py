from pydantic import BaseModel, EmailStr, HttpUrl
from datetime import datetime
from typing import Optional

class AudioTranscriptionBase(BaseModel):
    username: str
    email: EmailStr
    audio_file_url: HttpUrl
    filename: str
    uploaded: Optional[datetime] = None
    transcription: Optional[str] = None

class AudioTranscriptionCreate(AudioTranscriptionBase):
    pass

    class Config:
        orm_mode = True


