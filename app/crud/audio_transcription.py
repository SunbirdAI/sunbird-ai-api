from typing import List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models import audio_transcription as models
from app.models.audio_transcription import AudioTranscription
from app.schemas import audio_transcription as schema


async def create_audio_transcription(
    db: AsyncSession, user, audio_file_url, filename, transcription
) -> schema.AudioTranscriptionCreate:
    db_audio_transcription = models.AudioTranscription(
        email=user.email,
        username=user.username,
        audio_file_url=audio_file_url,
        filename=filename,
        transcription=transcription,
    )
    db.add(db_audio_transcription)
    await db.commit()
    await db.refresh(db_audio_transcription)
    return db_audio_transcription


async def get_audio_transcriptions(
    db: AsyncSession, username: str, params
) -> List[AudioTranscription]:
    order_column = getattr(AudioTranscription, params.order_by)
    if params.descending:
        order_column = order_column.desc()

    result = await db.execute(
        select(AudioTranscription)
        .filter(AudioTranscription.username == username)
        .order_by(order_column)
    )
    return result.scalars().all()


async def get_audio_transcription(
    db: AsyncSession, id: int, username: str
) -> AudioTranscription:
    result = await db.execute(
        select(AudioTranscription).filter(
            AudioTranscription.id == id, AudioTranscription.username == username
        )
    )
    return result.scalars().first()
