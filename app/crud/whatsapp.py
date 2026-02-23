from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.whatsapp import (
    WhatsAppFeedback,
    WhatsAppMessage,
    WhatsAppUserMemory,
    WhatsAppUserPreference,
)


async def get_user_preference(db: AsyncSession, user_id: str) -> Optional[str]:
    result = await db.execute(
        select(WhatsAppUserPreference).where(WhatsAppUserPreference.user_id == user_id)
    )
    preference = result.scalars().first()
    return preference.target_language if preference else None


async def get_user_mode(db: AsyncSession, user_id: str) -> Optional[str]:
    result = await db.execute(
        select(WhatsAppUserPreference).where(WhatsAppUserPreference.user_id == user_id)
    )
    preference = result.scalars().first()
    return preference.mode if preference else None


async def get_user_tts_enabled(db: AsyncSession, user_id: str) -> Optional[bool]:
    result = await db.execute(
        select(WhatsAppUserPreference).where(WhatsAppUserPreference.user_id == user_id)
    )
    preference = result.scalars().first()
    if preference is None:
        return None
    return bool(preference.tts_enabled)


async def save_user_preference(
    db: AsyncSession,
    user_id: str,
    source_language: str,
    target_language: str,
    mode: Optional[str] = None,
    tts_enabled: Optional[bool] = None,
) -> None:
    result = await db.execute(
        select(WhatsAppUserPreference).where(WhatsAppUserPreference.user_id == user_id)
    )
    preference = result.scalars().first()
    if preference:
        preference.source_language = source_language
        preference.target_language = target_language
        if mode:
            preference.mode = mode
        if tts_enabled is not None:
            preference.tts_enabled = tts_enabled
    else:
        preference = WhatsAppUserPreference(
            user_id=user_id,
            source_language=source_language,
            target_language=target_language,
            mode=mode or "chat",
            tts_enabled=False if tts_enabled is None else bool(tts_enabled),
        )
        db.add(preference)
    await db.commit()


async def save_user_mode(db: AsyncSession, user_id: str, mode: str) -> None:
    result = await db.execute(
        select(WhatsAppUserPreference).where(WhatsAppUserPreference.user_id == user_id)
    )
    preference = result.scalars().first()
    if preference:
        preference.mode = mode
    else:
        preference = WhatsAppUserPreference(
            user_id=user_id,
            source_language="English",
            target_language="eng",
            mode=mode,
            tts_enabled=False,
        )
        db.add(preference)
    await db.commit()


async def save_user_tts_enabled(
    db: AsyncSession, user_id: str, tts_enabled: bool
) -> None:
    result = await db.execute(
        select(WhatsAppUserPreference).where(WhatsAppUserPreference.user_id == user_id)
    )
    preference = result.scalars().first()
    if preference:
        preference.tts_enabled = bool(tts_enabled)
    else:
        preference = WhatsAppUserPreference(
            user_id=user_id,
            source_language="English",
            target_language="eng",
            mode="chat",
            tts_enabled=bool(tts_enabled),
        )
        db.add(preference)
    await db.commit()


async def save_message(db: AsyncSession, user_id: str, message_text: str) -> WhatsAppMessage:
    message = WhatsAppMessage(
        user_id=user_id,
        message_text=message_text,
        message_type="user_message",
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


async def save_response(
    db: AsyncSession,
    user_id: str,
    user_message: str,
    bot_response: str,
    message_id: Optional[str] = None,
) -> WhatsAppMessage:
    response = WhatsAppMessage(
        user_id=user_id,
        message_text=bot_response,
        message_type="bot_response",
        user_message=user_message,
        message_id=message_id,
    )
    db.add(response)
    await db.commit()
    await db.refresh(response)
    return response


async def get_user_messages(db: AsyncSession, user_id: str) -> List[WhatsAppMessage]:
    result = await db.execute(
        select(WhatsAppMessage)
        .where(WhatsAppMessage.user_id == user_id)
        .order_by(desc(WhatsAppMessage.timestamp))
    )
    return result.scalars().all()


async def get_user_last_five_messages(db: AsyncSession, user_id: str) -> List[WhatsAppMessage]:
    result = await db.execute(
        select(WhatsAppMessage)
        .where(WhatsAppMessage.user_id == user_id)
        .order_by(desc(WhatsAppMessage.timestamp))
        .limit(5)
    )
    return result.scalars().all()


async def get_user_last_five_conversation_pairs(db: AsyncSession, user_id: str) -> list:
    return await get_user_conversation_pairs(db, user_id, limit_pairs=5)


async def get_user_conversation_pairs(
    db: AsyncSession, user_id: str, limit_pairs: int = 30
) -> list:
    result = await db.execute(
        select(WhatsAppMessage)
        .where(WhatsAppMessage.user_id == user_id)
        .order_by(desc(WhatsAppMessage.timestamp))
        .limit(max(limit_pairs * 4, 40))
    )
    all_messages = list(reversed(result.scalars().all()))

    conversation_pairs = []
    current_user_msg = None
    for msg in all_messages:
        if msg.message_type == "user_message":
            current_user_msg = msg
        elif msg.message_type == "bot_response" and current_user_msg:
            conversation_pairs.append(
                {
                    "user_message": current_user_msg.message_text or "",
                    "bot_response": msg.message_text or "",
                    "timestamp": msg.timestamp,
                }
            )
            current_user_msg = None

    return conversation_pairs[-limit_pairs:]


async def save_detailed_feedback(
    db: AsyncSession,
    message_id: str,
    feedback: str,
    feedback_type: str = "reaction",
) -> bool:
    result = await db.execute(
        select(WhatsAppMessage)
        .where(WhatsAppMessage.message_id == message_id)
        .order_by(desc(WhatsAppMessage.timestamp))
        .limit(1)
    )
    target_message = result.scalars().first()
    if not target_message:
        return False

    feedback_row = WhatsAppFeedback(
        user_id=target_message.user_id,
        message_id=message_id,
        user_message=target_message.user_message or "",
        bot_response=target_message.message_text or "",
        feedback=feedback,
        feedback_type=feedback_type,
    )
    db.add(feedback_row)
    await db.commit()
    return True


async def save_feedback_with_context(
    db: AsyncSession,
    user_id: str,
    feedback: str,
    sender_name: str,
    feedback_type: str = "button",
) -> bool:
    conversation_pairs = await get_user_last_five_conversation_pairs(db, user_id)
    latest_conversation = conversation_pairs[-1] if conversation_pairs else {}

    feedback_row = WhatsAppFeedback(
        user_id=user_id,
        sender_name=sender_name,
        message_id=None,
        user_message=latest_conversation.get("user_message", ""),
        bot_response=latest_conversation.get("bot_response", ""),
        feedback=feedback,
        feedback_type=feedback_type,
    )
    db.add(feedback_row)
    await db.commit()
    return True


async def get_user_feedback_history(
    db: AsyncSession, user_id: str, limit: int = 10
) -> List[WhatsAppFeedback]:
    result = await db.execute(
        select(WhatsAppFeedback)
        .where(WhatsAppFeedback.user_id == user_id)
        .order_by(desc(WhatsAppFeedback.timestamp))
        .limit(limit)
    )
    return result.scalars().all()


async def get_all_feedback_summary(db: AsyncSession, limit: int = 100) -> List[WhatsAppFeedback]:
    result = await db.execute(
        select(WhatsAppFeedback).order_by(desc(WhatsAppFeedback.timestamp)).limit(limit)
    )
    return result.scalars().all()


async def get_user_memory_note(db: AsyncSession, user_id: str) -> Optional[str]:
    result = await db.execute(
        select(WhatsAppUserMemory).where(WhatsAppUserMemory.user_id == user_id)
    )
    row = result.scalars().first()
    if not row:
        return None
    return row.memory_note or None


async def upsert_user_memory_note(
    db: AsyncSession,
    user_id: str,
    memory_note: str,
) -> None:
    result = await db.execute(
        select(WhatsAppUserMemory).where(WhatsAppUserMemory.user_id == user_id)
    )
    row = result.scalars().first()
    if row:
        row.memory_note = memory_note
        row.last_summarized_at = datetime.now(timezone.utc)
    else:
        row = WhatsAppUserMemory(
            user_id=user_id,
            memory_note=memory_note,
            last_summarized_at=datetime.now(timezone.utc),
        )
        db.add(row)
    await db.commit()
