"""
Language Service Module.

This module provides the LanguageService class for handling language
identification and classification operations. It encapsulates the business
logic for language detection API calls.

Architecture:
    The service follows the BaseService pattern and integrates with:
    - RunPod for ML model inference

Usage:
    from app.services.language_service import (
        LanguageService,
        get_language_service,
    )

    # Get singleton instance
    service = get_language_service()

    # Identify language
    result = await service.identify_language(text="Oli otya?")

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

from app.services.base import BaseService
from app.utils.upload_audio_file_gcp import upload_audio_file

load_dotenv()
logging.basicConfig(level=logging.INFO)


class LanguageError(Exception):
    """Exception raised when language operations fail."""

    pass


class LanguageTimeoutError(LanguageError):
    """Exception raised when language operations time out."""

    pass


class LanguageConnectionError(LanguageError):
    """Exception raised when connection to language service fails."""

    pass


class LanguageDetectionError(LanguageError):
    """Exception raised when language detection fails."""

    pass


@dataclass
class LanguageIdentificationResult:
    """Result of a language identification operation.

    Attributes:
        language: The identified language code.
        raw_response: The raw response from the worker.
    """

    language: str
    raw_response: Optional[Dict[str, Any]] = None


@dataclass
class LanguageClassificationResult:
    """Result of a language classification operation.

    Attributes:
        language: The detected language code or 'language not detected'.
        probability: The confidence probability.
        predictions: Full predictions dictionary from the model.
        raw_response: The raw response from the worker.
    """

    language: str
    probability: Optional[float] = None
    predictions: Optional[Dict[str, float]] = None
    raw_response: Optional[Dict[str, Any]] = None


@dataclass
class AudioLanguageResult:
    """Result of an audio language detection operation.

    Attributes:
        detected_language: The detected language code from the audio.
        blob_name: The GCS blob name of the uploaded audio.
        raw_response: The raw response from the worker.
    """

    detected_language: str
    blob_name: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None


class LanguageService(BaseService):
    """Service for language identification and classification operations.

    This service handles language identification, classification, and audio
    language detection using the RunPod ML models.

    Attributes:
        runpod_endpoint_id: The RunPod endpoint ID for language operations.
        classification_threshold: Threshold for language classification confidence.

    Example:
        service = LanguageService()
        result = await service.identify_language(text="Hello world")
        print(result.language)
    """

    # Default threshold for language classification
    DEFAULT_CLASSIFICATION_THRESHOLD = 0.9

    def __init__(
        self,
        runpod_endpoint_id: Optional[str] = None,
        classification_threshold: float = DEFAULT_CLASSIFICATION_THRESHOLD,
    ) -> None:
        """Initialize the Language service.

        Args:
            runpod_endpoint_id: The RunPod endpoint ID. Defaults to env var.
            classification_threshold: Threshold for classification confidence.
        """
        super().__init__()
        self.runpod_endpoint_id = runpod_endpoint_id or os.getenv("RUNPOD_ENDPOINT_ID")
        self.classification_threshold = classification_threshold
        runpod.api_key = os.getenv("RUNPOD_API_KEY")

        if not self.runpod_endpoint_id:
            self.log_warning("RUNPOD_ENDPOINT_ID not configured")

    async def identify_language(self, text: str) -> LanguageIdentificationResult:
        """Identify the language of text using auto-detection.

        This method uses the 'auto_detect_language' task to identify
        the language of the given text.

        Args:
            text: The text to identify the language of.

        Returns:
            LanguageIdentificationResult containing the identified language.

        Raises:
            LanguageTimeoutError: If the operation times out.
            LanguageError: For other language detection failures.
        """
        self.log_info(f"Starting language identification for text: {text[:50]}...")

        endpoint = runpod.Endpoint(self.runpod_endpoint_id)

        try:
            response = endpoint.run_sync(
                {
                    "input": {
                        "task": "auto_detect_language",
                        "text": text,
                    }
                },
                timeout=60,
            )

            self.log_info(f"Language identification response: {response}")

            # Extract language from response
            language = response.get("language", "unknown") if response else "unknown"

            return LanguageIdentificationResult(
                language=language,
                raw_response=response,
            )

        except TimeoutError as e:
            self.log_error(f"Language identification timeout: {str(e)}")
            raise LanguageTimeoutError(
                "Language identification timed out. Please try again."
            )
        except Exception as e:
            self.log_error(f"Language identification error: {str(e)}")
            raise LanguageError(
                "An unexpected error occurred during language identification"
            )

    async def classify_language(self, text: str) -> LanguageClassificationResult:
        """Classify the language of text with probability scores.

        This method uses the 'language_classify' task to classify
        the language with confidence scores. A language is only
        reported if it exceeds the classification threshold.

        Args:
            text: The text to classify the language of.

        Returns:
            LanguageClassificationResult containing the classification result.

        Raises:
            LanguageTimeoutError: If the operation times out.
            LanguageDetectionError: If the response format is unexpected.
            LanguageError: For other classification failures.
        """
        self.log_info(f"Starting language classification for text: {text[:50]}...")

        endpoint = runpod.Endpoint(self.runpod_endpoint_id)
        # Convert text to lowercase for classification
        normalized_text = text.lower()

        try:
            response = endpoint.run_sync(
                {
                    "input": {
                        "task": "language_classify",
                        "text": normalized_text,
                    }
                },
                timeout=60,
            )

            self.log_info(f"Language classification response: {response}")

            # Extract predictions from the response
            if not isinstance(response, dict) or "predictions" not in response:
                self.log_error(f"Unexpected response format: {response}")
                raise LanguageDetectionError(
                    "Unexpected response format from the language classification service"
                )

            predictions = response["predictions"]

            # Find the language with the highest probability
            detected_language = "language not detected"
            highest_prob = 0.0

            for language, probability in predictions.items():
                if probability > highest_prob:
                    highest_prob = probability
                    detected_language = language

            # Apply threshold
            if highest_prob < self.classification_threshold:
                detected_language = "language not detected"
                highest_prob = None

            return LanguageClassificationResult(
                language=detected_language,
                probability=highest_prob,
                predictions=predictions,
                raw_response=response,
            )

        except TimeoutError as e:
            self.log_error(f"Language classification timeout: {str(e)}")
            raise LanguageTimeoutError(
                "Language classification timed out. Please try again."
            )
        except LanguageDetectionError:
            raise
        except Exception as e:
            self.log_error(f"Language classification error: {str(e)}")
            raise LanguageError(
                "An unexpected error occurred during language classification"
            )

    async def detect_audio_language(
        self,
        file_path: str,
    ) -> AudioLanguageResult:
        """Detect the language of an audio file.

        This method uploads the audio file to cloud storage and then
        calls the 'auto_detect_audio_language' task to detect the language.

        Args:
            file_path: Path to the audio file.

        Returns:
            AudioLanguageResult containing the detected language.

        Raises:
            LanguageTimeoutError: If the operation times out.
            LanguageConnectionError: If connection fails.
            LanguageError: For other detection failures.
        """
        self.log_info(f"Starting audio language detection for: {file_path}")

        # Upload audio file to GCS
        blob_name, blob_url = upload_audio_file(file_path=file_path)

        if not blob_name:
            self.log_error("Failed to upload audio file")
            raise LanguageError("Failed to upload audio file for language detection")

        endpoint = runpod.Endpoint(self.runpod_endpoint_id)

        try:
            response = endpoint.run_sync(
                {
                    "input": {
                        "task": "auto_detect_audio_language",
                        "audio_file": blob_name,
                    }
                },
                timeout=600,
            )

            self.log_info(f"Audio language detection response: {response}")

            # Extract detected language from response
            detected_language = (
                response.get("detected_language", "unknown") if response else "unknown"
            )

            return AudioLanguageResult(
                detected_language=detected_language,
                blob_name=blob_name,
                raw_response=response,
            )

        except TimeoutError as e:
            self.log_error(f"Audio language detection timeout: {str(e)}")
            raise LanguageTimeoutError(
                "Audio language detection timed out. Please try again."
            )
        except ConnectionError as e:
            self.log_error(f"Connection error: {str(e)}")
            raise LanguageConnectionError(
                "Connection error during audio language detection. Please try again."
            )
        except Exception as e:
            self.log_error(f"Audio language detection error: {str(e)}")
            raise LanguageError(
                "An unexpected error occurred during audio language detection"
            )


# Singleton instance
_language_service_instance: Optional[LanguageService] = None


def get_language_service() -> LanguageService:
    """Get the singleton LanguageService instance.

    Returns:
        The LanguageService singleton instance.
    """
    global _language_service_instance
    if _language_service_instance is None:
        _language_service_instance = LanguageService()
    return _language_service_instance


def reset_language_service() -> None:
    """Reset the singleton LanguageService instance.

    Useful for testing to ensure a fresh instance.
    """
    global _language_service_instance
    _language_service_instance = None
