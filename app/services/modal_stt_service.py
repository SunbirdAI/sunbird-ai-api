"""
Modal Speech-to-Text Service Module.

This module provides the ModalSTTService class for interacting with the
Modal-hosted Whisper ASR inference server. It sends raw audio bytes and
receives transcription results.

Architecture:
    Router -> ModalSTTService -> Modal Whisper ASR API

Usage:
    from app.services.modal_stt_service import ModalSTTService, get_modal_stt_service

    @router.post("/modal/stt")
    async def transcribe(
        audio: UploadFile,
        service: Annotated[ModalSTTService, Depends(get_modal_stt_service)]
    ):
        audio_data = await audio.read()
        transcription = await service.transcribe(audio_data)
        return {"transcription": transcription}
"""

from typing import Dict, Optional

import httpx

from app.core.config import settings
from app.core.exceptions import ExternalServiceError, ValidationError
from app.services.base import BaseService

# Mapping of language names (lowercase) to ISO 639-2/3 codes
LANGUAGE_NAME_TO_CODE: Dict[str, str] = {
    "english": "eng",
    "luganda": "lug",
    "runyankole": "nyn",
    "acholi": "ach",
    "ateso": "teo",
    "lugbara": "lgg",
    "swahili": "swa",
    "kinyarwanda": "kin",
    "lusoga": "xog",
    "lumasaba": "myx",
}

# Set of valid language codes for quick lookup
VALID_LANGUAGE_CODES = set(LANGUAGE_NAME_TO_CODE.values())


def resolve_language(language: str) -> str:
    """Resolve a language name or code to a valid ISO 639-2/3 code.

    Accepts either a 3-letter code (e.g. "eng") or a full language name
    (e.g. "english", "English") and returns the corresponding code.

    Args:
        language: Language name or ISO 639-2/3 code.

    Returns:
        The resolved language code.

    Raises:
        ValueError: If the language is not recognized.
    """
    normalized = language.strip().lower()

    # Check if it's already a valid code
    if normalized in VALID_LANGUAGE_CODES:
        return normalized

    # Try to resolve from name
    if normalized in LANGUAGE_NAME_TO_CODE:
        return LANGUAGE_NAME_TO_CODE[normalized]

    valid_options = sorted(VALID_LANGUAGE_CODES | set(LANGUAGE_NAME_TO_CODE.keys()))
    raise ValueError(
        f"Unsupported language: '{language}'. "
        f"Valid options: {', '.join(valid_options)}"
    )


class ModalSTTService(BaseService):
    """Service for interacting with the Modal Whisper ASR API.

    Sends raw audio bytes to the Modal endpoint and returns
    the transcribed text.

    Attributes:
        api_url: The URL of the Modal Whisper ASR endpoint.
        timeout: Request timeout in seconds for API calls.
    """

    EXTERNAL_SERVICE_NAME = "Modal STT API"

    def __init__(
        self,
        api_url: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> None:
        """Initialize the Modal STT service.

        Args:
            api_url: Modal ASR API URL. Defaults to settings.modal_stt_api_url.
            timeout: Request timeout in seconds. Defaults to settings.request_timeout_seconds.
        """
        super().__init__()
        self.api_url = api_url or settings.modal_stt_api_url
        self.timeout = timeout or settings.request_timeout_seconds

        self.log_debug(
            "Modal STT service initialized",
            extra={"api_url": self.api_url, "timeout": self.timeout},
        )

    async def transcribe(
        self, audio_data: bytes, language: Optional[str] = None
    ) -> str:
        """Transcribe audio using the Modal Whisper ASR API.

        Sends raw audio bytes to the endpoint and parses the response.
        The Modal endpoint returns: {"text": [{"text": "transcribed text..."}]}

        Args:
            audio_data: Raw audio bytes to transcribe.
            language: Optional language code or name to guide transcription.
                Accepts ISO 639-2/3 codes (e.g. "eng", "lug") or full names
                (e.g. "english", "luganda"). If not provided, the model
                will auto-detect the language.

        Returns:
            Concatenated transcription text from all segments.

        Raises:
            ValidationError: If the provided language is not recognized.
            ExternalServiceError: If the API returns an error or is unreachable.
        """
        # Resolve language if provided
        resolved_language = None
        if language:
            try:
                resolved_language = resolve_language(language)
            except ValueError as e:
                raise self.validation_error(
                    message=str(e),
                    errors=[{"field": "language", "value": language}],
                )

        self.log_info(
            "Transcribing audio",
            extra={
                "audio_bytes": len(audio_data),
                "language": resolved_language,
            },
        )

        try:
            params = {}
            if resolved_language:
                params["language"] = resolved_language

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.api_url,
                    content=audio_data,
                    headers={"Content-Type": "application/octet-stream"},
                    params=params,
                )

                if response.status_code != 200:
                    self.log_error(
                        "Modal STT API returned error",
                        extra={
                            "status_code": response.status_code,
                            "response_text": response.text[:500],
                        },
                    )
                    raise self.external_service_error(
                        service_name=self.EXTERNAL_SERVICE_NAME,
                        message=f"STT API error: {response.text}",
                        original_error=f"HTTP {response.status_code}",
                    )

                result = response.json()
                self.log_info(f"Result received from Modal STT API: {result}")
                transcription = self._parse_transcription(result)

                self.log_info(
                    "Transcription completed",
                    extra={"transcription_length": len(transcription)},
                )
                return transcription

        except httpx.TimeoutException as e:
            self.log_error("Modal STT API timeout", exc_info=e)
            raise self.external_service_error(
                service_name=self.EXTERNAL_SERVICE_NAME,
                message="STT service timeout - audio may be too long",
                original_error=str(e),
            )
        except httpx.RequestError as e:
            self.log_error("Modal STT API request error", exc_info=e)
            raise self.external_service_error(
                service_name=self.EXTERNAL_SERVICE_NAME,
                message="Failed to connect to STT service",
                original_error=str(e),
            )
        except (ExternalServiceError, ValidationError):
            raise
        except Exception as e:
            self.log_error("Unexpected error during transcription", exc_info=e)
            raise self.external_service_error(
                service_name=self.EXTERNAL_SERVICE_NAME,
                message="Unexpected error during transcription",
                original_error=str(e),
            )

    def _parse_transcription(self, result: dict) -> str:
        """Parse the Modal API response into a transcription string.

        The response format is: {"text": [{"text": "segment 1"}, {"text": "segment 2"}]}

        Args:
            result: The JSON response from the Modal API.

        Returns:
            Concatenated transcription text from all segments.

        Raises:
            ExternalServiceError: If the response format is unexpected.
        """
        try:
            segments = result
            return " ".join(segment["text"].strip() for segment in segments).strip()
        except (KeyError, TypeError, IndexError) as e:
            self.log_error(
                "Failed to parse transcription response",
                extra={"response": str(result)[:500]},
            )
            raise self.external_service_error(
                service_name=self.EXTERNAL_SERVICE_NAME,
                message="Unexpected response format from STT service",
                original_error=str(e),
            )

    async def health_check(self) -> bool:
        """Check if the Modal STT API is reachable.

        Returns:
            True if the API responds with a non-5xx status, False otherwise.
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


# -----------------------------------------------------------------------------
# Dependency Injection
# -----------------------------------------------------------------------------

_modal_stt_service: Optional[ModalSTTService] = None


def get_modal_stt_service() -> ModalSTTService:
    """Get or create the Modal STT service singleton.

    Returns:
        ModalSTTService instance configured with application settings.
    """
    global _modal_stt_service
    if _modal_stt_service is None:
        _modal_stt_service = ModalSTTService()
    return _modal_stt_service


def reset_modal_stt_service() -> None:
    """Reset the Modal STT service singleton. Used for testing."""
    global _modal_stt_service
    _modal_stt_service = None
