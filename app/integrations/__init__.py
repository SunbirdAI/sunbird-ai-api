"""
Integrations Module.

This module contains client classes for external API integrations.
These clients handle the low-level communication with external services,
separate from the business logic in the services layer.

Architecture:
    Services -> Integrations -> External APIs

    - Services contain business logic and orchestration
    - Integrations handle API communication and response parsing
    - External APIs are third-party services (RunPod, OpenAI, WhatsApp, etc.)

Design Principles:
    1. Single Responsibility - Each client handles one external API
    2. Error Handling - Clients wrap API errors in consistent exceptions
    3. Async First - Clients use async/await for I/O operations
    4. Testability - Clients can be mocked for unit testing

Usage:
    from app.integrations.runpod import RunPodClient, get_runpod_client
    from app.integrations.openai_client import OpenAIClient, get_openai_client

    # In a service
    class TranslationService(BaseService):
        def __init__(self, runpod_client: RunPodClient):
            super().__init__()
            self.runpod = runpod_client

        async def translate(self, text: str, target_lang: str) -> str:
            result = await self.runpod.run_job({"text": text, "target": target_lang})
            return result["translated_text"]

Available Clients:
    - RunPodClient: Client for RunPod serverless API
    - OpenAIClient: Client for OpenAI chat completions API
    - WhatsAppAPIClient: Client for WhatsApp Cloud API

Available Integrations:
    - firebase: Firebase/Firestore operations for WhatsApp user data

Note:
    All clients should handle their own error cases and raise
    appropriate exceptions that services can catch and handle.
"""

from app.integrations.firebase import (
    get_all_feedback_summary,
    get_user_feedback_history,
    get_user_last_five_conversation_pairs,
    get_user_last_five_messages,
    get_user_messages,
    get_user_preference,
    save_detailed_feedback,
    save_feedback_with_context,
    save_message,
    save_response,
    save_user_preference,
    update_feedback,
)
from app.integrations.openai_client import OpenAIClient, get_openai_client
from app.integrations.runpod import (
    RunPodClient,
    get_runpod_client,
    normalize_runpod_response,
    run_job_and_get_output,
)
from app.integrations.whatsapp_api import (
    WhatsAppAPIClient,
    get_whatsapp_api_client,
    reset_whatsapp_api_client,
)

__all__ = [
    # RunPod
    "RunPodClient",
    "get_runpod_client",
    "normalize_runpod_response",
    "run_job_and_get_output",
    # OpenAI
    "OpenAIClient",
    "get_openai_client",
    # WhatsApp API
    "WhatsAppAPIClient",
    "get_whatsapp_api_client",
    "reset_whatsapp_api_client",
    # Firebase
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
