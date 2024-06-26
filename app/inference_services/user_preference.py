import os

import firebase_admin
from firebase_admin import credentials, firestore
import logging


logging.basicConfig(level=logging.INFO)

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

# Get Firestore database instance
db = firestore.client()


# Helper function to get user preferences
def get_user_preference(user_id):
    # Retrieve user's source and target language preferences from Firestore
    doc = db.collection("whatsapp_user_preferences").document(user_id).get()
    if doc.exists:
        preferences = doc.to_dict()
        return preferences["source_language"], preferences["target_language"]
    else:
        return None, None


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

def save_translation(user_id, original_text, translated_text, source_language, target_language, message_id):
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

