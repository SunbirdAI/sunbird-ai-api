from sqlalchemy.orm import Session

from app.models import audio_transcription as models
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
