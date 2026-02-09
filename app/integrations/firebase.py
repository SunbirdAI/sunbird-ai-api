"""
Firebase Integration Module.

This module provides Firebase/Firestore integration for WhatsApp user preferences,
messages, and feedback storage. It handles all Firebase operations for the
WhatsApp chatbot functionality.

Architecture:
    - Initializes Firebase Admin SDK with environment credentials
    - Provides CRUD operations for user preferences
    - Manages WhatsApp message and response storage
    - Handles feedback collection and retrieval

Collections:
    - whatsapp_user_preferences: User language preferences
    - whatsapp_messages: All user messages and bot responses
    - whatsapp_translations: Legacy translation records
    - whatsapp_feedback: Detailed feedback with conversation context

Usage:
    from app.integrations.firebase import (
        get_user_preference,
        save_user_preference,
        save_message,
        save_response,
        update_feedback,
    )

    # Get user preference
    target_lang = get_user_preference("user123")

    # Save message
    doc_id = save_message("user123", "Hello")

Note:
    This module was migrated from app/inference_services/user_preference.py
    as part of the refactoring to organize integrations separately.
"""

import logging
import os

from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore

logging.basicConfig(level=logging.INFO)

_db = None


def _init_firebase() -> None:
    global _db
    if _db is not None:
        return
    
    load_dotenv()

    try:
        # Initialize Firebase app
        firebase_config = {
            "type": os.getenv("TYPE"),
            "project_id": os.getenv("PROJECT_ID"),
            "private_key_id": os.getenv("PRIVATE_KEY_ID"),
            "private_key": os.getenv("PRIVATE_KEY").replace('\\n', '\n'),
            "client_email": os.getenv("CLIENT_EMAIL"),
            "token_uri": os.getenv("TOKEN_URI"),
            "auth_provider_x509_cert_url": os.getenv("AUTH_PROVIDER_X509_CERT_URL"),
            "client_x509_cert_url": os.getenv("CLIENT_X509_CERT_URL"),
            "client_id": os.getenv("CLIENT_ID"),
            "auth_uri": os.getenv("AUTH_URI"),
            "universe_domain": os.getenv("UNIVERSE_DOMAIN"),
        }

        cred = credentials.Certificate(firebase_config)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
    except ValueError as e:
        logging.error(f"Value Error: {str(e)}")
        if not firebase_admin._apps:
            firebase_admin.initialize_app()
    except Exception as e:
        logging.error(f"Exception Error: {str(e)}")
        if not firebase_admin._apps:
            firebase_admin.initialize_app()

    _db = firestore.client()


def _get_db():
    _init_firebase()
    return _db


# =============================================================================
# User Preferences
# =============================================================================


def get_user_preference(user_id: str):
    """
    Retrieve user's target language preference from Firestore.

    Args:
        user_id: ID of the user

    Returns:
        str: Target language code if found, None otherwise
    """
    db = _get_db()
    doc = db.collection("whatsapp_user_preferences").document(user_id).get()
    if doc.exists:
        preferences = doc.to_dict()
        return preferences["target_language"]
    else:
        return None


def save_user_preference(user_id: str, source_language: str, target_language: str):
    """
    Save user's language preferences to Firestore.

    Args:
        user_id: ID of the user
        source_language: Source language code
        target_language: Target language code
    """
    db = _get_db()
    db.collection("whatsapp_user_preferences").document(user_id).set(
        {"source_language": source_language, "target_language": target_language}
    )


# =============================================================================
# Feedback Operations
# =============================================================================


def update_feedback(message_id: str, feedback: str) -> bool:
    """
    Update feedback for a specific translation in Firestore.

    This is a legacy function that maintains backward compatibility while
    also saving to the new detailed feedback collection.

    Args:
        message_id: ID of the sent message
        feedback: Feedback to be updated

    Returns:
        bool: True if the update was successful, False otherwise
    """
    try:
        # Update the old way (for backward compatibility)
        db = _get_db()
        translations_ref = db.collection("whatsapp_translations")
        query = translations_ref.where("message_id", "==", message_id).stream()

        updated = False
        for doc in query:
            doc_ref = translations_ref.document(doc.id)
            doc_ref.update({"feedback": feedback})
            logging.info(f"Feedback updated for message ID: {message_id}")
            updated = True

        # Also save to the new detailed feedback collection
        save_detailed_feedback(message_id, feedback, feedback_type="reaction")

        return updated

    except Exception as e:
        logging.error(f"Error updating feedback: {e}")
        return False


def save_detailed_feedback(
    message_id: str, feedback: str, feedback_type: str = "reaction"
) -> bool:
    """
    Save detailed feedback with full context including user message and bot response.

    Args:
        message_id: ID of the message being reacted to
        feedback: Feedback content (emoji or rating)
        feedback_type: Type of feedback ("reaction" or "button")

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # First, try to find the bot response this feedback is about
        db = _get_db()
        messages_ref = db.collection("whatsapp_messages")

        # Find the specific message by message_id
        target_message = None
        query = messages_ref.where("message_id", "==", message_id).limit(1).stream()
        for doc in query:
            target_message = doc.to_dict()
            break

        if target_message:
            user_id = target_message.get("user_id")
            bot_response = target_message.get("message_text", "")
            user_message = target_message.get("user_message", "")

            # Save comprehensive feedback record
            feedback_doc = {
                "user_id": user_id,
                "message_id": message_id,
                "user_message": user_message,
                "bot_response": bot_response,
                "feedback": feedback,
                "feedback_type": feedback_type,
                "timestamp": firestore.SERVER_TIMESTAMP,
            }

            db = _get_db()
            doc_ref = db.collection("whatsapp_feedback").add(feedback_doc)
            logging.info(f"Detailed feedback saved with ID: {doc_ref[1].id}")
            return True
        else:
            logging.warning(f"Could not find message with ID: {message_id}")
            return False

    except Exception as e:
        logging.error(f"Error saving detailed feedback: {e}")
        return False


def save_feedback_with_context(
    user_id: str, feedback: str, sender_name: str, feedback_type: str = "button"
) -> bool:
    """
    Save feedback with context from the most recent conversation.

    Args:
        user_id: User ID
        feedback: Feedback content
        sender_name: Name of the user providing feedback
        feedback_type: Type of feedback

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Get the most recent conversation pair for this user
        conversation_pairs = get_user_last_five_conversation_pairs(user_id)

        if conversation_pairs:
            # Get the most recent conversation
            latest_conversation = conversation_pairs[-1]
            user_message = latest_conversation.get("user_message", "")
            bot_response = latest_conversation.get("bot_response", "")

            # Save comprehensive feedback record
            feedback_doc = {
                "user_id": user_id,
                "sender_name": sender_name,
                "user_message": user_message,
                "bot_response": bot_response,
                "feedback": feedback,
                "feedback_type": feedback_type,
                "timestamp": firestore.SERVER_TIMESTAMP,
                "message_id": None,  # No specific message_id for button feedback
            }

            db = _get_db()
            doc_ref = db.collection("whatsapp_feedback").add(feedback_doc)
            logging.info(f"Contextual feedback saved with ID: {doc_ref[1].id}")
            return True
        else:
            logging.warning(f"No conversation history found for user: {user_id}")
            # Save basic feedback without context
            feedback_doc = {
                "user_id": user_id,
                "sender_name": sender_name,
                "user_message": "",
                "bot_response": "",
                "feedback": feedback,
                "feedback_type": feedback_type,
                "timestamp": firestore.SERVER_TIMESTAMP,
                "message_id": None,
            }

            db = _get_db()
            doc_ref = db.collection("whatsapp_feedback").add(feedback_doc)
            logging.info(f"Basic feedback saved with ID: {doc_ref[1].id}")
            return True

    except Exception as e:
        logging.error(f"Error saving contextual feedback: {e}")
        return False


def get_user_feedback_history(user_id: str, limit: int = 10) -> list:
    """
    Retrieve feedback history for a specific user.

    Args:
        user_id: User ID
        limit: Maximum number of feedback records to return

    Returns:
        list: List of feedback records with full context
    """
    try:
        db = _get_db()
        feedback_ref = db.collection("whatsapp_feedback")
        query = (
            feedback_ref.where("user_id", "==", user_id)
            .order_by("timestamp", direction=firestore.Query.DESCENDING)
            .limit(limit)
            .stream()
        )

        feedback_history = []
        for doc in query:
            feedback_data = doc.to_dict()
            feedback_data["feedback_id"] = doc.id
            feedback_history.append(feedback_data)

        return feedback_history

    except Exception as e:
        logging.error(f"Error retrieving feedback history: {e}")
        return []


def get_all_feedback_summary(limit: int = 100) -> list:
    """
    Get a summary of all feedback for analytics.

    Args:
        limit: Maximum number of records to retrieve

    Returns:
        list: List of all feedback records
    """
    try:
        db = _get_db()
        feedback_ref = db.collection("whatsapp_feedback")
        query = (
            feedback_ref.order_by("timestamp", direction=firestore.Query.DESCENDING)
            .limit(limit)
            .stream()
        )

        all_feedback = []
        for doc in query:
            feedback_data = doc.to_dict()
            feedback_data["feedback_id"] = doc.id
            all_feedback.append(feedback_data)

        return all_feedback

    except Exception as e:
        logging.error(f"Error retrieving feedback summary: {e}")
        return []


# =============================================================================
# Message Operations
# =============================================================================


def save_message(user_id: str, message_text: str) -> str:
    """
    Save message details to Firestore.

    Args:
        user_id: ID of the user
        message_text: Text of the message sent

    Returns:
        str: Document ID of the saved message
    """
    db = _get_db()
    doc_ref = db.collection("whatsapp_messages").add(
        {
            "user_id": user_id,
            "message_text": message_text,
            "message_type": "user_message",
            "timestamp": firestore.SERVER_TIMESTAMP,
        }
    )
    logging.info(f"Message saved with document ID: {doc_ref[1].id}")
    return doc_ref[1].id


def save_response(
    user_id: str, user_message: str, bot_response: str, message_id: str = None
) -> str:
    """
    Save bot response details to Firestore along with the user message it responds to.

    Args:
        user_id: ID of the user
        user_message: Original user message that triggered the response
        bot_response: Bot's response to the user message
        message_id: Optional message ID for linking

    Returns:
        str: Document ID of the saved response
    """
    db = _get_db()
    doc_ref = db.collection("whatsapp_messages").add(
        {
            "user_id": user_id,
            "message_text": bot_response,
            "message_type": "bot_response",
            "user_message": user_message,
            "message_id": message_id,
            "timestamp": firestore.SERVER_TIMESTAMP,
        }
    )
    logging.info(f"Bot response saved with document ID: {doc_ref[1].id}")
    return doc_ref[1].id


def get_user_messages(user_id: str) -> list:
    """
    Retrieve all messages sent by a specific user from Firestore.

    Args:
        user_id: ID of the user

    Returns:
        list: List of all messages sent by the user
    """
    db = _get_db()
    messages_ref = db.collection("whatsapp_messages")
    query = messages_ref.where("user_id", "==", user_id).stream()
    messages = []
    for doc in query:
        messages.append(doc.to_dict())
    return messages


def get_user_last_five_messages(user_id: str) -> list:
    """
    Retrieve the last five messages sent by a specific user from Firestore.

    Args:
        user_id: ID of the user

    Returns:
        list: List of the last five messages sent by the user
    """
    db = _get_db()
    messages_ref = db.collection("whatsapp_messages")
    # Order the messages by timestamp descending and limit to the last 5
    query = (
        messages_ref.where("user_id", "==", user_id)
        .order_by("timestamp", direction=firestore.Query.DESCENDING)
        .limit(5)
        .stream()
    )
    messages = []
    for doc in query:
        messages.append(doc.to_dict())
    return messages


def get_user_last_five_conversation_pairs(user_id: str) -> list:
    """
    Retrieve the last five conversation pairs (user message + bot response) for context.

    Args:
        user_id: ID of the user

    Returns:
        list: List of conversation pairs with user messages and bot responses
    """
    db = _get_db()
    messages_ref = db.collection("whatsapp_messages")
    # Get last 10 messages to ensure we capture conversation pairs
    query = (
        messages_ref.where("user_id", "==", user_id)
        .order_by("timestamp", direction=firestore.Query.DESCENDING)
        .limit(10)
        .stream()
    )

    all_messages = []
    for doc in query:
        message_data = doc.to_dict()
        all_messages.append(message_data)

    # Sort by timestamp ascending to process chronologically
    all_messages.sort(key=lambda x: x.get("timestamp", 0))

    # Group into conversation pairs
    conversation_pairs = []
    current_user_msg = None

    for msg in all_messages:
        if msg.get("message_type") == "user_message":
            current_user_msg = msg
        elif msg.get("message_type") == "bot_response" and current_user_msg:
            conversation_pairs.append(
                {
                    "user_message": current_user_msg.get("message_text", ""),
                    "bot_response": msg.get("message_text", ""),
                    "timestamp": msg.get("timestamp"),
                }
            )
            current_user_msg = None

    # Return last 5 conversation pairs
    return (
        conversation_pairs[-5:] if len(conversation_pairs) > 5 else conversation_pairs
    )


# =============================================================================
# Exports
# =============================================================================

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
