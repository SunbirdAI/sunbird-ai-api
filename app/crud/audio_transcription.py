from typing import List

from sqlalchemy.orm import Session

from app.models import audio_transcription as models
from app.models.audio_transcription import AudioTranscription
from app.schemas import audio_transcription as schema


def create_audio_transcription(
    db: Session, user, audio_file_url, filename, transcription
) -> schema.AudioTranscriptionCreate:
    db_audio_transcription = models.AudioTranscription(
        email=user.email,
        username=user.username,
        audio_file_url=audio_file_url,
        filename=filename,
        transcription=transcription,
    )
    db.add(db_audio_transcription)
    db.commit()
    db.refresh(db_audio_transcription)
    return db_audio_transcription


async def get_audio_transcriptions(
    db: Session, username: str
) -> List[AudioTranscription]:
    return (
        db.query(AudioTranscription)
        .filter(AudioTranscription.username == username)
        .all()
    )


async def get_audio_transcription(
    db: Session, id: int, username: str
) -> AudioTranscription:
    return (
        db.query(AudioTranscription)
        .filter(AudioTranscription.id == id, AudioTranscription.username == username)
        .first()
    )
