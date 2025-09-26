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
    

def update_feedback(message_id, feedback):
    """
    Update feedback for a specific translation in Firestore (legacy function)
    Now also saves to the new detailed feedback collection

    Args:
        message_id (str): ID of the sent message
        feedback (str): Feedback to be updated

    Returns:
        bool: True if the update was successful, False otherwise
    """
    try:
        # Update the old way (for backward compatibility)
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


def save_detailed_feedback(message_id, feedback, feedback_type="reaction"):
    """
    Save detailed feedback with full context including user message and bot response

    Args:
        message_id (str): ID of the message being reacted to
        feedback (str): Feedback content (emoji or rating)
        feedback_type (str): Type of feedback ("reaction" or "button")

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # First, try to find the bot response this feedback is about
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
            
            doc_ref = db.collection("whatsapp_feedback").add(feedback_doc)
            logging.info(f"Detailed feedback saved with ID: {doc_ref[1].id}")
            return True
        else:
            logging.warning(f"Could not find message with ID: {message_id}")
            return False
            
    except Exception as e:
        logging.error(f"Error saving detailed feedback: {e}")
        return False


def save_feedback_with_context(user_id, feedback, sender_name, feedback_type="button"):
    """
    Save feedback with context from the most recent conversation

    Args:
        user_id (str): User ID
        feedback (str): Feedback content
        sender_name (str): Name of the user providing feedback
        feedback_type (str): Type of feedback

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
                "message_id": None  # No specific message_id for button feedback
            }
            
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
                "message_id": None
            }
            
            doc_ref = db.collection("whatsapp_feedback").add(feedback_doc)
            logging.info(f"Basic feedback saved with ID: {doc_ref[1].id}")
            return True
            
    except Exception as e:
        logging.error(f"Error saving contextual feedback: {e}")
        return False


def get_user_feedback_history(user_id, limit=10):
    """
    Retrieve feedback history for a specific user

    Args:
        user_id (str): User ID
        limit (int): Maximum number of feedback records to return

    Returns:
        list: List of feedback records with full context
    """
    try:
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


def get_all_feedback_summary(limit=100):
    """
    Get a summary of all feedback for analytics

    Args:
        limit (int): Maximum number of records to retrieve

    Returns:
        list: List of all feedback records
    """
    try:
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
