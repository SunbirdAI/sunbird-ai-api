from typing import List, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.whatsapp import WhatsAppFeedback, WhatsAppMessage, WhatsAppUserPreference


async def get_user_preference(db: AsyncSession, user_id: str) -> Optional[str]:
    result = await db.execute(
        select(WhatsAppUserPreference).where(WhatsAppUserPreference.user_id == user_id)
    )
    preference = result.scalars().first()
    return preference.target_language if preference else None


async def save_user_preference(
    db: AsyncSession, user_id: str, source_language: str, target_language: str
) -> None:
    result = await db.execute(
        select(WhatsAppUserPreference).where(WhatsAppUserPreference.user_id == user_id)
    )
    preference = result.scalars().first()
    if preference:
        preference.source_language = source_language
        preference.target_language = target_language
    else:
        preference = WhatsAppUserPreference(
            user_id=user_id,
            source_language=source_language,
            target_language=target_language,
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
    result = await db.execute(
        select(WhatsAppMessage)
        .where(WhatsAppMessage.user_id == user_id)
        .order_by(desc(WhatsAppMessage.timestamp))
        .limit(10)
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

    return conversation_pairs[-5:]


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
