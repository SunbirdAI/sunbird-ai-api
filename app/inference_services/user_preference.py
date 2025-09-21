import logging
import os

import firebase_admin
from firebase_admin import credentials, firestore

logging.basicConfig(level=logging.INFO)

try:
    # Initialize Firebase app
    firebase_config = {
        "type": os.getenv("TYPE"),
        "project_id": os.getenv("PROJECT_ID"),
        "private_key_id": os.getenv("PRIVATE_KEY_ID"),
        "private_key": os.getenv("PRIVATE_KEY"),
        "client_email": os.getenv("CLIENT_EMAIL"),
        "token_uri": os.getenv("TOKEN_URI"),
        "auth_provider_x509_cert_url": os.getenv("AUTH_PROVIDER_X509_CERT_URL"),
        "client_x509_cert_url": os.getenv("CLIENT_X509_CERT_URL"),
        "client_id": os.getenv("CLIENT_ID"),
        "auth_uri": os.getenv("AUTH_URI"),
        "universe_domain": os.getenv("UNIVERSE_DOMAIN"),
    }

    cred = credentials.Certificate(firebase_config)
    firebase_admin.initialize_app(cred)
except ValueError as e:
    logging.error(f"Value Error: {str(e)}")
    firebase_admin.initialize_app()
except Exception as e:
    logging.error(f"Exception Error: {str(e)}")

# Get Firestore database instance
db = firestore.client()


# Helper function to get user preferences
def get_user_preference(user_id):
    # Retrieve user's source and target language preferences from Firestore
    doc = db.collection("whatsapp_user_preferences").document(user_id).get()
    if doc.exists:
        preferences = doc.to_dict()
        return preferences["target_language"]
    else:
        return None


# Helper function to save user preference
def save_user_preference(user_id, source_language, target_language):
    # Save user's source and target language preferences to Firestore
    db.collection("whatsapp_user_preferences").document(user_id).set(
        {"source_language": source_language, "target_language": target_language}
    )


# def save_translation(
#     user_id, original_text, translated_text, source_language, target_language
# ):
#     # Save translation details to Firestore
#     db.collection("whatsapp_translations").add(
#         {
#             "user_id": user_id,
#             "original_text": original_text,
#             "translated_text": translated_text,
#             "source_language": source_language,
#             "target_language": target_language,
#             "timestamp": firestore.SERVER_TIMESTAMP,
#         }
#     )


def save_translation(
    user_id,
    original_text,
    translated_text,
    source_language,
    target_language,
    message_id,
):
    """
    Save translation details to Firestore

    Args:
        user_id (str): ID of the user
        original_text (str): Original text to be translated
        translated_text (str): Translated text
        source_language (str): Source language code
        target_language (str): Target language code
        message_id (str): ID of the sent message

    Returns:
        str: Document ID of the saved translation
    """
    doc_ref = db.collection("whatsapp_translations").add(
        {
            "user_id": user_id,
            "original_text": original_text,
            "translated_text": translated_text,
            "source_language": source_language,
            "target_language": target_language,
            "message_id": message_id,
            "feedback": None,  # Initialize feedback as None
            "timestamp": firestore.SERVER_TIMESTAMP,
        }
    )
    logging.info(f"Translation saved with document ID: {doc_ref[1].id}")
    return doc_ref[1].id


def update_feedback(message_id, feedback):
    """
    Update feedback for a specific translation in Firestore

    Args:
        message_id (str): ID of the sent message
        feedback (str): Feedback to be updated

    Returns:
        bool: True if the update was successful, False otherwise
    """
    try:
        translations_ref = db.collection("whatsapp_translations")
        query = translations_ref.where("message_id", "==", message_id).stream()

        for doc in query:
            doc_ref = translations_ref.document(doc.id)
            doc_ref.update({"feedback": feedback})
            logging.info(f"Feedback updated for message ID: {message_id}")
            return True
        logging.error(f"No document found with message ID: {message_id}")
        return False
    except Exception as e:
        logging.error(f"Error updating feedback: {e}")
        return False

    # Method to save all messages sent by users


def save_message(user_id, message_text):
    """
    Save message details to Firestore

    Args:
        user_id (str): ID of the user
        message_text (str): Text of the message sent

    Returns:
        str: Document ID of the saved message
    """
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


def save_response(user_id, user_message, bot_response, message_id=None):
    """
    Save bot response details to Firestore along with the user message it responds to

    Args:
        user_id (str): ID of the user
        user_message (str): Original user message that triggered the response
        bot_response (str): Bot's response to the user message
        message_id (str): Optional message ID for linking

    Returns:
        str: Document ID of the saved response
    """
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


# Method to retrieve all messages sent by a specific user
def get_user_messages(user_id):
    """
    Retrieve all messages sent by a specific user from Firestore

    Args:
        user_id (str): ID of the user

    Returns:
        list: List of all messages sent by the user
    """
    messages_ref = db.collection("whatsapp_messages")
    query = messages_ref.where("user_id", "==", user_id).stream()
    messages = []
    for doc in query:
        messages.append(doc.to_dict())
    return messages


# Method to retrieve the last five messages sent by a specific user
def get_user_last_five_messages(user_id):
    """
    Retrieve the last five messages sent by a specific user from Firestore

    Args:
        user_id (str): ID of the user

    Returns:
        list: List of the last five messages sent by the user
    """
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


def get_user_last_five_conversation_pairs(user_id):
    """
    Retrieve the last five conversation pairs (user message + bot response) for context

    Args:
        user_id (str): ID of the user

    Returns:
        list: List of conversation pairs with user messages and bot responses
    """
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
