import os

import firebase_admin
from firebase_admin import credentials, firestore

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


def save_translation(
    user_id, original_text, translated_text, source_language, target_language
):
    # Save translation details to Firestore
    db.collection("whatsapp_translations").add(
        {
            "user_id": user_id,
            "original_text": original_text,
            "translated_text": translated_text,
            "source_language": source_language,
            "target_language": target_language,
            "timestamp": firestore.SERVER_TIMESTAMP,
        }
    )
