"""
Text-to-Speech Service Module.

This module provides the TTSService class for interacting with external
Text-to-Speech APIs. It supports both synchronous audio generation
(returning complete audio data) and streaming responses for real-time
audio playback.

Architecture:
    The service follows the service layer pattern:
    Router -> TTSService -> External TTS API

    - Routers handle HTTP concerns and request validation
    - TTSService handles business logic and API communication
    - External TTS API performs the actual audio synthesis

Usage:
    from app.services.tts_service import TTSService, get_tts_service

    # In a FastAPI router with dependency injection
    @router.post("/tts")
    async def generate_tts(
        request: TTSRequest,
        tts_service: Annotated[TTSService, Depends(get_tts_service)]
    ):
        audio_data = await tts_service.generate_audio(
            text=request.text,
            speaker_id=request.speaker_id
        )
        return StreamingResponse(io.BytesIO(audio_data), media_type="audio/wav")

Example:
    >>> service = TTSService()
    >>> audio = await service.generate_audio("Hello world", speaker_id=1)
    >>> print(f"Generated {len(audio)} bytes of audio")
    Generated 44100 bytes of audio
"""

from typing import AsyncGenerator, Optional

import httpx

from app.core.config import settings
from app.core.exceptions import ExternalServiceError
from app.models.enums import SpeakerID
from app.services.base import BaseService
from app.utils.audio import estimate_speech_duration


class TTSService(BaseService):
    """Service for interacting with external Text-to-Speech APIs.

    This service provides methods for converting text to speech audio,
    supporting both synchronous (full audio) and streaming responses.
    It inherits from BaseService to leverage standardized logging
    and error handling patterns.

    Attributes:
        api_url: The URL of the external TTS API endpoint.
        timeout: Request timeout in seconds for API calls.

    Example:
        >>> service = TTSService()
        >>> audio = await service.generate_audio("Hello", speaker_id=SpeakerID.FEMALE_1)
        >>> len(audio) > 0
        True

        >>> # With custom configuration
        >>> service = TTSService(
        ...     api_url="https://custom-tts.example.com/synthesize",
        ...     timeout=60
        ... )
    """

    # External service name for error reporting
    EXTERNAL_SERVICE_NAME = "TTS API"

    def __init__(
        self,
        api_url: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> None:
        """Initialize the TTS service.

        Sets up the service with API configuration. Uses settings from
        the application config if not explicitly provided.

        Args:
            api_url: External TTS API URL. Defaults to settings.tts_api_url.
            timeout: Request timeout in seconds. Defaults to settings.request_timeout_seconds.

        Example:
            >>> # Use default configuration
            >>> service = TTSService()

            >>> # Use custom configuration
            >>> service = TTSService(
            ...     api_url="https://tts.example.com/api",
            ...     timeout=30
            ... )
        """
        super().__init__()
        self.api_url = api_url or settings.tts_api_url
        self.timeout = timeout or settings.request_timeout_seconds

        self.log_debug(
            "TTS service initialized",
            extra={"api_url": self.api_url, "timeout": self.timeout},
        )

    def _get_speaker_id_value(self, speaker_id: int | SpeakerID) -> int:
        """Extract integer value from speaker_id.

        Handles both raw integer speaker IDs and SpeakerID enum values,
        ensuring consistent integer representation for API calls.

        Args:
            speaker_id: Either an integer speaker ID or a SpeakerID enum.

        Returns:
            Integer value of the speaker ID.

        Example:
            >>> service = TTSService()
            >>> service._get_speaker_id_value(SpeakerID.FEMALE_1)
            1
            >>> service._get_speaker_id_value(2)
            2
        """
        return speaker_id.value if isinstance(speaker_id, SpeakerID) else speaker_id

    async def generate_audio(
        self,
        text: str,
        speaker_id: int | SpeakerID,
    ) -> bytes:
        """Generate audio from text using the external TTS API.

        Sends a synchronous request to the TTS API and returns the
        complete audio data. Use this method when you need the full
        audio file before processing (e.g., for uploading to storage).

        Args:
            text: Text to convert to speech. Should not be empty.
            speaker_id: Speaker voice ID, either as integer or SpeakerID enum.

        Returns:
            Raw audio bytes in WAV format.

        Raises:
            ExternalServiceError: If the TTS API returns an error or is unreachable.
            BadRequestError: If the input text is invalid.

        Example:
            >>> service = TTSService()
            >>> audio = await service.generate_audio(
            ...     text="Welcome to Sunbird AI",
            ...     speaker_id=SpeakerID.MALE_1
            ... )
            >>> isinstance(audio, bytes)
            True
        """
        sid = self._get_speaker_id_value(speaker_id)

        self.log_info(
            "Generating audio",
            extra={
                "text_length": len(text),
                "speaker_id": sid,
            },
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.api_url,
                    params={"text": text, "speaker_id": str(sid)},
                )

                if response.status_code != 200:
                    self.log_error(
                        "TTS API returned error",
                        extra={
                            "status_code": response.status_code,
                            "response_text": response.text[:500],
                        },
                    )
                    raise self.external_service_error(
                        service_name=self.EXTERNAL_SERVICE_NAME,
                        message=f"TTS API error: {response.text}",
                        original_error=f"HTTP {response.status_code}",
                    )

                self.log_info(
                    "Audio generated successfully",
                    extra={"audio_bytes": len(response.content)},
                )
                return response.content

        except httpx.TimeoutException as e:
            self.log_error("TTS API timeout", exc_info=e)
            raise self.external_service_error(
                service_name=self.EXTERNAL_SERVICE_NAME,
                message="TTS service timeout - text may be too long",
                original_error=str(e),
            )
        except httpx.RequestError as e:
            self.log_error("TTS API request error", exc_info=e)
            raise self.external_service_error(
                service_name=self.EXTERNAL_SERVICE_NAME,
                message="Failed to connect to TTS service",
                original_error=str(e),
            )
        except ExternalServiceError:
            # Re-raise our own errors
            raise
        except Exception as e:
            self.log_error("Unexpected error during audio generation", exc_info=e)
            raise self.external_service_error(
                service_name=self.EXTERNAL_SERVICE_NAME,
                message="Unexpected error during audio generation",
                original_error=str(e),
            )

    async def generate_audio_stream(
        self,
        text: str,
        speaker_id: int | SpeakerID,
        chunk_size: int = 8192,
    ) -> AsyncGenerator[bytes, None]:
        """Stream audio chunks from the TTS API.

        Streams audio data in chunks as they are received from the API.
        Use this method for real-time audio playback or when dealing
        with large audio files to reduce memory usage.

        Args:
            text: Text to convert to speech.
            speaker_id: Speaker voice ID, either as integer or SpeakerID enum.
            chunk_size: Size of each chunk in bytes. Defaults to 8192 (8KB).

        Yields:
            Audio data chunks as bytes.

        Raises:
            ExternalServiceError: If the TTS API returns an error or is unreachable.

        Example:
            >>> service = TTSService()
            >>> chunks = []
            >>> async for chunk in service.generate_audio_stream(
            ...     text="Hello world",
            ...     speaker_id=SpeakerID.FEMALE_1
            ... ):
            ...     chunks.append(chunk)
            >>> total_bytes = sum(len(c) for c in chunks)
        """
        sid = self._get_speaker_id_value(speaker_id)

        self.log_info(
            "Starting audio stream",
            extra={
                "text_length": len(text),
                "speaker_id": sid,
                "chunk_size": chunk_size,
            },
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    self.api_url,
                    params={"text": text, "speaker_id": str(sid)},
                ) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        self.log_error(
                            "TTS API streaming error",
                            extra={
                                "status_code": response.status_code,
                                "error_text": error_text.decode()[:500],
                            },
                        )
                        raise self.external_service_error(
                            service_name=self.EXTERNAL_SERVICE_NAME,
                            message=f"TTS API error: {error_text.decode()}",
                            original_error=f"HTTP {response.status_code}",
                        )

                    total_bytes = 0
                    async for chunk in response.aiter_bytes(chunk_size=chunk_size):
                        total_bytes += len(chunk)
                        yield chunk

                    self.log_info(
                        "Audio stream completed",
                        extra={"total_bytes": total_bytes},
                    )

        except httpx.TimeoutException as e:
            self.log_error("TTS API stream timeout", exc_info=e)
            raise self.external_service_error(
                service_name=self.EXTERNAL_SERVICE_NAME,
                message="TTS service timeout during streaming",
                original_error=str(e),
            )
        except httpx.RequestError as e:
            self.log_error("TTS API stream request error", exc_info=e)
            raise self.external_service_error(
                service_name=self.EXTERNAL_SERVICE_NAME,
                message="Failed to connect to TTS service for streaming",
                original_error=str(e),
            )
        except ExternalServiceError:
            # Re-raise our own errors
            raise
        except Exception as e:
            self.log_error("Unexpected error during audio streaming", exc_info=e)
            raise self.external_service_error(
                service_name=self.EXTERNAL_SERVICE_NAME,
                message="Unexpected error during audio streaming",
                original_error=str(e),
            )

    async def health_check(self) -> bool:
        """Check if the TTS API is reachable and responding.

        Performs a lightweight connectivity check to verify the external
        TTS service is available. Useful for health check endpoints and
        service monitoring.

        Returns:
            True if the API responds with a non-5xx status, False otherwise.

        Example:
            >>> service = TTSService()
            >>> is_healthy = await service.health_check()
            >>> if not is_healthy:
            ...     print("TTS service is unavailable")
        """
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.head(self.api_url)
                is_healthy = response.status_code < 500

                self.log_debug(
                    "Health check completed",
                    extra={
                        "status_code": response.status_code,
                        "is_healthy": is_healthy,
                    },
                )
                return is_healthy

        except Exception as e:
            self.log_warning(
                "Health check failed",
                extra={"error": str(e)},
            )
            return False

    @staticmethod
    def estimate_duration(text: str, words_per_minute: int = 150) -> float:
        """Estimate audio duration based on text length.

        Provides a rough estimate of how long the generated audio will be
        based on an assumed speaking rate. Useful for UI feedback and
        progress indicators.

        Args:
            text: Input text to estimate duration for.
            words_per_minute: Assumed speaking rate. Defaults to 150 WPM,
                which is typical for clear speech synthesis.

        Returns:
            Estimated duration in seconds.

        Example:
            >>> TTSService.estimate_duration("Hello world")
            0.8
            >>> TTSService.estimate_duration("A longer sentence with more words")
            2.8
        """
        return estimate_speech_duration(text, words_per_minute)


# -----------------------------------------------------------------------------
# Dependency Injection
# -----------------------------------------------------------------------------

# Singleton instance for dependency injection
_tts_service: Optional[TTSService] = None


def get_tts_service() -> TTSService:
    """Get or create the TTS service singleton.

    This function implements a singleton pattern for the TTS service,
    ensuring only one instance is created and reused across requests.
    This is efficient for stateless services that only need configuration.

    Returns:
        TTSService instance configured with application settings.

    Example:
        >>> # In a FastAPI dependency
        >>> @router.post("/tts")
        >>> async def generate_tts(
        ...     tts_service: Annotated[TTSService, Depends(get_tts_service)]
        ... ):
        ...     return await tts_service.generate_audio(...)

        >>> # Direct usage
        >>> service = get_tts_service()
        >>> await service.generate_audio("Hello", speaker_id=1)
    """
    global _tts_service
    if _tts_service is None:
        _tts_service = TTSService()
    return _tts_service


def reset_tts_service() -> None:
    """Reset the TTS service singleton.

    Primarily used for testing to ensure a fresh instance is created.
    Should not be called in production code.

    Example:
        >>> # In tests
        >>> reset_tts_service()
        >>> service = get_tts_service()  # Creates new instance
    """
    global _tts_service
    _tts_service = None
