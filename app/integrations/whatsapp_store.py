"""
Async WhatsApp data store backed by the application's SQL database.

This module mirrors the previous Firestore helper API so WhatsApp pipeline
code can migrate without changing business behavior.
"""

import logging
from typing import Any, Dict, List, Optional

from app.crud import whatsapp as whatsapp_crud
from app.database.db import async_session_maker

logger = logging.getLogger(__name__)


def _feedback_to_dict(feedback: Any) -> Dict[str, Any]:
    return {
        "feedback_id": feedback.id,
        "user_id": feedback.user_id,
        "sender_name": feedback.sender_name,
        "message_id": feedback.message_id,
        "user_message": feedback.user_message,
        "bot_response": feedback.bot_response,
        "feedback": feedback.feedback,
        "feedback_type": feedback.feedback_type,
        "timestamp": feedback.timestamp,
    }


def _message_to_dict(message: Any) -> Dict[str, Any]:
    return {
        "id": message.id,
        "user_id": message.user_id,
        "message_text": message.message_text,
        "message_type": message.message_type,
        "user_message": message.user_message,
        "message_id": message.message_id,
        "timestamp": message.timestamp,
    }


async def get_user_preference(user_id: str) -> Optional[str]:
    try:
        async with async_session_maker() as db:
            return await whatsapp_crud.get_user_preference(db, user_id)
    except Exception as e:
        logger.error("Error getting user preference for %s: %s", user_id, e)
        return None


async def save_user_preference(
    user_id: str, source_language: str, target_language: str
) -> None:
    try:
        async with async_session_maker() as db:
            await whatsapp_crud.save_user_preference(
                db, user_id, source_language, target_language
            )
    except Exception as e:
        logger.error("Error saving user preference for %s: %s", user_id, e)


async def update_feedback(message_id: str, feedback: str) -> bool:
    try:
        return await save_detailed_feedback(message_id, feedback, feedback_type="reaction")
    except Exception as e:
        logger.error("Error updating feedback for message %s: %s", message_id, e)
        return False


async def save_detailed_feedback(
    message_id: str, feedback: str, feedback_type: str = "reaction"
) -> bool:
    try:
        async with async_session_maker() as db:
            return await whatsapp_crud.save_detailed_feedback(
                db, message_id, feedback, feedback_type
            )
    except Exception as e:
        logger.error("Error saving detailed feedback for message %s: %s", message_id, e)
        return False


async def save_feedback_with_context(
    user_id: str, feedback: str, sender_name: str, feedback_type: str = "button"
) -> bool:
    try:
        async with async_session_maker() as db:
            return await whatsapp_crud.save_feedback_with_context(
                db, user_id, feedback, sender_name, feedback_type
            )
    except Exception as e:
        logger.error("Error saving contextual feedback for %s: %s", user_id, e)
        return False


async def get_user_feedback_history(user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    try:
        async with async_session_maker() as db:
            records = await whatsapp_crud.get_user_feedback_history(db, user_id, limit)
            return [_feedback_to_dict(r) for r in records]
    except Exception as e:
        logger.error("Error retrieving feedback history for %s: %s", user_id, e)
        return []


async def get_all_feedback_summary(limit: int = 100) -> List[Dict[str, Any]]:
    try:
        async with async_session_maker() as db:
            records = await whatsapp_crud.get_all_feedback_summary(db, limit)
            return [_feedback_to_dict(r) for r in records]
    except Exception as e:
        logger.error("Error retrieving feedback summary: %s", e)
        return []


async def save_message(user_id: str, message_text: str) -> str:
    try:
        async with async_session_maker() as db:
            message = await whatsapp_crud.save_message(db, user_id, message_text)
            return str(message.id)
    except Exception as e:
        logger.error("Error saving message for %s: %s", user_id, e)
        return ""


async def save_response(
    user_id: str, user_message: str, bot_response: str, message_id: str = None
) -> str:
    try:
        async with async_session_maker() as db:
            response = await whatsapp_crud.save_response(
                db, user_id, user_message, bot_response, message_id
            )
            return str(response.id)
    except Exception as e:
        logger.error("Error saving response for %s: %s", user_id, e)
        return ""


async def get_user_messages(user_id: str) -> List[Dict[str, Any]]:
    try:
        async with async_session_maker() as db:
            messages = await whatsapp_crud.get_user_messages(db, user_id)
            return [_message_to_dict(msg) for msg in messages]
    except Exception as e:
        logger.error("Error retrieving messages for %s: %s", user_id, e)
        return []


async def get_user_last_five_messages(user_id: str) -> List[Dict[str, Any]]:
    try:
        async with async_session_maker() as db:
            messages = await whatsapp_crud.get_user_last_five_messages(db, user_id)
            return [_message_to_dict(msg) for msg in messages]
    except Exception as e:
        logger.error("Error retrieving last five messages for %s: %s", user_id, e)
        return []


async def get_user_last_five_conversation_pairs(user_id: str) -> list:
    try:
        async with async_session_maker() as db:
            return await whatsapp_crud.get_user_last_five_conversation_pairs(db, user_id)
    except Exception as e:
        logger.error("Error retrieving conversation pairs for %s: %s", user_id, e)
        return []


__all__ = [
    "get_user_preference",
    "save_user_preference",
    "update_feedback",
    "save_detailed_feedback",
    "save_feedback_with_context",
    "get_user_feedback_history",
    "get_all_feedback_summary",
    "save_message",
    "save_response",
    "get_user_messages",
    "get_user_last_five_messages",
    "get_user_last_five_conversation_pairs",
]
