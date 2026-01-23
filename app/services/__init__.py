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
    from app.services.tts_service import TTSService

    # Services are typically injected via FastAPI dependencies
    @router.post("/tts")
    async def generate_tts(
        request: TTSRequest,
        tts_service: Annotated[TTSService, Depends(get_tts_service)]
    ):
        return await tts_service.generate_speech(request)

Available Services:
    - BaseService: Abstract base class for all services

Note:
    All services should inherit from BaseService to ensure
    consistent error handling, logging, and interface patterns.
"""

from app.services.base import BaseService

__all__ = ["BaseService"]
