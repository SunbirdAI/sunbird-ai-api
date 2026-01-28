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
    - STTService: Speech-to-Text service for audio transcription
    - TranslationService: Text translation service for NLLB translation
    - LanguageService: Language identification and classification service
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
from app.services.language_service import (
    AudioLanguageResult,
    LanguageClassificationResult,
    LanguageConnectionError,
    LanguageDetectionError,
    LanguageError,
    LanguageIdentificationResult,
    LanguageService,
    LanguageTimeoutError,
    get_language_service,
    reset_language_service,
)
from app.services.message_processor import (
    MessageType,
    OptimizedMessageProcessor,
    ProcessingResult,
    ResponseType,
    clear_processed_messages,
)
from app.services.stt_service import (
    AudioProcessingError,
    AudioValidationError,
    STTService,
    TranscriptionError,
    TranscriptionResult,
    get_stt_service,
    reset_stt_service,
)
from app.services.translation_service import (
    TranslationConnectionError,
    TranslationError,
    TranslationResult,
    TranslationService,
    TranslationTimeoutError,
    TranslationValidationError,
    get_translation_service,
    reset_translation_service,
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
    "STTService",
    "get_stt_service",
    "reset_stt_service",
    "TranscriptionResult",
    "AudioValidationError",
    "AudioProcessingError",
    "TranscriptionError",
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
    "TranslationService",
    "get_translation_service",
    "reset_translation_service",
    "TranslationResult",
    "TranslationError",
    "TranslationTimeoutError",
    "TranslationConnectionError",
    "TranslationValidationError",
    "LanguageService",
    "get_language_service",
    "reset_language_service",
    "LanguageIdentificationResult",
    "LanguageClassificationResult",
    "AudioLanguageResult",
    "LanguageError",
    "LanguageTimeoutError",
    "LanguageConnectionError",
    "LanguageDetectionError",
]
