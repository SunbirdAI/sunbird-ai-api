"""
Translation Service Module.

This module provides the TranslationService class for handling text translation
operations. It encapsulates the business logic for NLLB translation API calls.

Architecture:
    The service follows the BaseService pattern and integrates with:
    - RunPod for ML model inference via the run_job_and_get_output helper

Usage:
    from app.services.translation_service import (
        TranslationService,
        get_translation_service,
    )

    # Get singleton instance
    service = get_translation_service()

    # Translate text
    result = await service.translate(
        text="Hello world",
        source_language="eng",
        target_language="lug",
    )

Note:
    This module was created as part of the services layer refactoring.
    Business logic was extracted from app/routers/tasks.py.
"""

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import runpod
from dotenv import load_dotenv

from app.inference_services.runpod_helpers import (
    normalize_runpod_response,
    run_job_and_get_output,
)
from app.schemas.translation import (
    NllbLanguage,
    WorkerTranslationOutput,
    WorkerTranslationResponse,
)
from app.services.base import BaseService

load_dotenv()
logging.basicConfig(level=logging.INFO)


class TranslationError(Exception):
    """Exception raised when translation fails."""

    pass


class TranslationTimeoutError(TranslationError):
    """Exception raised when translation times out."""

    pass


class TranslationConnectionError(TranslationError):
    """Exception raised when connection to translation service fails."""

    pass


class TranslationValidationError(TranslationError):
    """Exception raised when translation response validation fails."""

    pass


@dataclass
class TranslationResult:
    """Result of a translation operation.

    Attributes:
        translated_text: The translated text.
        source_language: The source language code.
        target_language: The target language code.
        delay_time: Time spent waiting in queue (ms).
        execution_time: Time spent executing (ms).
        job_id: The RunPod job ID.
        worker_id: The worker that processed the request.
        status: Job status (COMPLETED, FAILED, etc.).
        raw_response: The raw response from the worker.
    """

    translated_text: Optional[str]
    source_language: str
    target_language: str
    delay_time: Optional[int] = None
    execution_time: Optional[int] = None
    job_id: Optional[str] = None
    worker_id: Optional[str] = None
    status: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None


class TranslationService(BaseService):
    """Service for text translation operations.

    This service handles text translation using the NLLB model via RunPod.

    Attributes:
        runpod_endpoint_id: The RunPod endpoint ID for translation.

    Example:
        service = TranslationService()
        result = await service.translate(
            text="Hello",
            source_language="eng",
            target_language="lug",
        )
        print(result.translated_text)
    """

    def __init__(
        self,
        runpod_endpoint_id: Optional[str] = None,
    ) -> None:
        """Initialize the Translation service.

        Args:
            runpod_endpoint_id: The RunPod endpoint ID. Defaults to env var.
        """
        super().__init__()
        self.runpod_endpoint_id = runpod_endpoint_id or os.getenv("RUNPOD_ENDPOINT_ID")
        runpod.api_key = os.getenv("RUNPOD_API_KEY")

        if not self.runpod_endpoint_id:
            self.log_warning("RUNPOD_ENDPOINT_ID not configured")

    def validate_languages(self, source_language: str, target_language: str) -> None:
        """Validate source and target languages.

        Args:
            source_language: The source language code.
            target_language: The target language code.

        Raises:
            TranslationValidationError: If languages are invalid.
        """
        valid_codes = {lang.value for lang in NllbLanguage}

        if source_language not in valid_codes:
            raise TranslationValidationError(
                f"Invalid source language: {source_language}. "
                f"Valid options: {', '.join(valid_codes)}"
            )

        if target_language not in valid_codes:
            raise TranslationValidationError(
                f"Invalid target language: {target_language}. "
                f"Valid options: {', '.join(valid_codes)}"
            )

        if source_language == target_language:
            raise TranslationValidationError(
                "Source and target languages must be different"
            )

    async def translate(
        self,
        text: str,
        source_language: str,
        target_language: str,
    ) -> TranslationResult:
        """Translate text from source to target language.

        Args:
            text: The text to translate.
            source_language: The source language code.
            target_language: The target language code.

        Returns:
            TranslationResult containing the translated text and metadata.

        Raises:
            TranslationTimeoutError: If the translation times out.
            TranslationConnectionError: If connection fails.
            TranslationError: For other translation failures.
        """
        self.log_info(f"Starting translation: {source_language} -> {target_language}")

        # Build payload for RunPod
        payload = {
            "task": "translate",
            "source_language": source_language,
            "target_language": target_language,
            "text": text.strip(),
        }

        try:
            raw_resp, job_details = await run_job_and_get_output(payload)
            self.log_info("Translation response received")
            logging.info(f"Raw response: {raw_resp}")
            logging.info(f"Job details: {job_details}")

        except TimeoutError as e:
            self.log_error(f"Translation timeout: {str(e)}")
            raise TranslationTimeoutError(
                "Translation service timed out. Please try again."
            )
        except ConnectionError as e:
            self.log_error(f"Connection error: {str(e)}")
            raise TranslationConnectionError(
                "Connection error while translating. Please try again."
            )
        except Exception as e:
            self.log_error(f"Translation error: {str(e)}")
            raise TranslationError("An unexpected error occurred during translation")

        # Normalize the response
        normalized = normalize_runpod_response(
            job_details if job_details is not None else raw_resp
        )

        # Extract translated text from output
        translated_text = None
        output = normalized.get("output", {})
        if isinstance(output, dict):
            translated_text = output.get("translated_text") or output.get("text")

        return TranslationResult(
            translated_text=translated_text,
            source_language=source_language,
            target_language=target_language,
            delay_time=normalized.get("delayTime"),
            execution_time=normalized.get("executionTime"),
            job_id=normalized.get("id"),
            worker_id=normalized.get("workerId"),
            status=normalized.get("status"),
            raw_response=normalized,
        )

    def validate_and_parse_response(
        self, response: Dict[str, Any]
    ) -> WorkerTranslationResponse:
        """Validate and parse the worker response.

        Args:
            response: The raw response from the worker.

        Returns:
            Validated WorkerTranslationResponse.

        Raises:
            TranslationValidationError: If response validation fails.
        """
        try:
            return WorkerTranslationResponse.model_validate(response)
        except Exception as e:
            self.log_error(f"Failed to validate worker response: {e}")
            raise TranslationValidationError("Invalid response from translation worker")


# Singleton instance
_translation_service_instance: Optional[TranslationService] = None


def get_translation_service() -> TranslationService:
    """Get the singleton TranslationService instance.

    Returns:
        The TranslationService singleton instance.
    """
    global _translation_service_instance
    if _translation_service_instance is None:
        _translation_service_instance = TranslationService()
    return _translation_service_instance


def reset_translation_service() -> None:
    """Reset the singleton TranslationService instance.

    Useful for testing to ensure a fresh instance.
    """
    global _translation_service_instance
    _translation_service_instance = None
