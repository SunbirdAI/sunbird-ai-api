"""
Services Module.

This module contains the business logic layer for the Sunbird AI API.
Services encapsulate complex operations and provide a clean interface
between routers and external integrations/data access layers.

Architecture:
    Routers -> Services -> Integrations/CRUD

    - Routers handle HTTP concerns (request/response, validation)
    - Services contain business logic and orchestration
    - Integrations handle external API communication
    - CRUD handles database operations

Usage:
    from app.services.base import BaseService
    from app.services.tts_service import TTSService, get_tts_service

    # Services are typically injected via FastAPI dependencies
    @router.post("/tts")
    async def generate_tts(
        request: TTSRequest,
        tts_service: Annotated[TTSService, Depends(get_tts_service)]
    ):
        return await tts_service.generate_speech(request)

Available Services:
    - BaseService: Abstract base class for all services
    - TTSService: Text-to-Speech service for audio generation
    - WhatsAppBusinessService: WhatsApp messaging business logic
    - OptimizedMessageProcessor: WhatsApp message processing service
    - InferenceService: Language model inference service

Note:
    All services should inherit from BaseService to ensure
    consistent error handling, logging, and interface patterns.
"""

from app.services.base import BaseService
from app.services.inference_service import (
    InferenceService,
    InferenceTimeoutError,
    ModelLoadingError,
    SunflowerChatMessage,
    SunflowerChatRequest,
    SunflowerChatResponse,
    SunflowerUsageStats,
    get_inference_service,
    reset_inference_service,
    run_inference,
)
from app.services.message_processor import (
    MessageType,
    OptimizedMessageProcessor,
    ProcessingResult,
    ResponseType,
    clear_processed_messages,
)
from app.services.tts_service import TTSService, get_tts_service
from app.services.whatsapp_service import (
    InteractiveButtonBuilder,
    WebhookParser,
    WhatsAppBusinessService,
    get_whatsapp_service,
)

__all__ = [
    "BaseService",
    "TTSService",
    "get_tts_service",
    "WhatsAppBusinessService",
    "get_whatsapp_service",
    "WebhookParser",
    "InteractiveButtonBuilder",
    "OptimizedMessageProcessor",
    "MessageType",
    "ResponseType",
    "ProcessingResult",
    "clear_processed_messages",
    "InferenceService",
    "get_inference_service",
    "reset_inference_service",
    "run_inference",
    "ModelLoadingError",
    "InferenceTimeoutError",
    "SunflowerChatMessage",
    "SunflowerChatRequest",
    "SunflowerUsageStats",
    "SunflowerChatResponse",
]
