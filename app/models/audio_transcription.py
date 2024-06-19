from sqlalchemy import Column, Integer, String, Text, DateTime
from app.database.db import Base
from datetime import datetime

class AudioTranscription(Base):
    __tablename__ = 'audio_transcriptions'

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), nullable=False)
    email = Column(String(), nullable=False)
    audio_file_url = Column(String(), nullable=False)
    filename = Column(String(255), nullable=False)
    uploaded = Column(DateTime, default=datetime.utcnow)
    transcription = Column(Text, nullable=True)

#to be removed. for showing the output to the audio_transcription on console
    def to_dict(self):
        return {
        'username': self.username,
        'email': self.email,
        'audio_file_url': self.audio_file_url,
        'filename': self.filename,
        'uploaded': self.uploaded,
        'transcription': self.transcription
        }
