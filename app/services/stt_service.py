"""
Speech-to-Text (STT) Service Module.

This module provides the STTService class for handling speech-to-text
transcription operations. It encapsulates the business logic for audio
file processing, cloud storage interactions, and RunPod API calls.

Architecture:
    The service follows the BaseService pattern and integrates with:
    - Google Cloud Storage for audio file storage
    - RunPod for ML model inference
    - Local file system for temporary file handling

Usage:
    from app.services.stt_service import STTService, get_stt_service

    # Get singleton instance
    service = get_stt_service()

    # Transcribe audio file
    result = await service.transcribe_audio_file(
        file_path="/path/to/audio.mp3",
        language="lug",
        adapter="lug",
    )

Note:
    This module was created as part of the services layer refactoring.
    Business logic was extracted from app/routers/tasks.py.
"""

import asyncio
import logging
import os
import tempfile
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import runpod
from dotenv import load_dotenv
from google.cloud import storage
from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError

from app.integrations.runpod import run_job_and_get_output
from app.schemas.stt import (
    ALLOWED_AUDIO_TYPES,
    CHUNK_SIZE,
    MAX_AUDIO_DURATION_MINUTES,
    SttbLanguage,
)
from app.services.base import BaseService
from app.utils.audio import get_audio_extension
from app.utils.upload_audio_file_gcp import upload_audio_file

load_dotenv()
logging.basicConfig(level=logging.INFO)


@dataclass
class TranscriptionResult:
    """Result of a transcription operation.

    Attributes:
        transcription: The transcribed text.
        diarization_output: Speaker diarization data.
        formatted_diarization_output: Human-readable diarization.
        audio_url: URL to the audio file.
        blob_name: Name of the blob in storage.
        was_trimmed: Whether the audio was trimmed.
        original_duration: Original duration if trimmed.
        processing_time: Time taken for transcription.
    """

    transcription: Optional[str]
    diarization_output: Dict[str, Any]
    formatted_diarization_output: str
    audio_url: Optional[str] = None
    blob_name: Optional[str] = None
    was_trimmed: bool = False
    original_duration: Optional[float] = None
    processing_time: Optional[float] = None


class AudioValidationError(Exception):
    """Exception raised when audio file validation fails."""

    pass


class AudioProcessingError(Exception):
    """Exception raised when audio processing fails."""

    pass


class TranscriptionError(Exception):
    """Exception raised when transcription fails."""

    pass


class STTService(BaseService):
    """Service for Speech-to-Text transcription operations.

    This service handles audio file processing, validation, cloud storage
    upload, and RunPod API calls for transcription.

    Attributes:
        runpod_endpoint_id: The RunPod endpoint ID for transcription.
        audio_bucket_name: The GCS bucket name for audio storage.

    Example:
        service = STTService()
        result = await service.transcribe_audio_file(
            file_path="/path/to/audio.mp3",
            language="lug",
        )
        print(result.transcription)
    """

    def __init__(
        self,
        runpod_endpoint_id: Optional[str] = None,
        audio_bucket_name: Optional[str] = None,
    ) -> None:
        """Initialize the STT service.

        Args:
            runpod_endpoint_id: The RunPod endpoint ID. Defaults to env var.
            audio_bucket_name: The GCS bucket name. Defaults to env var.
        """
        super().__init__()
        self.runpod_endpoint_id = runpod_endpoint_id or os.getenv("RUNPOD_ENDPOINT_ID")
        self.audio_bucket_name = audio_bucket_name or os.getenv(
            "AUDIO_CONTENT_BUCKET_NAME"
        )
        runpod.api_key = os.getenv("RUNPOD_API_KEY")

        if not self.runpod_endpoint_id:
            self.log_warning("RUNPOD_ENDPOINT_ID not configured")

    def validate_audio_file(self, content_type: str, file_extension: str) -> None:
        """Validate audio file type.

        Args:
            content_type: The MIME type of the audio file.
            file_extension: The file extension (e.g., '.mp3').

        Raises:
            AudioValidationError: If the file type is not supported.
        """
        if (
            content_type not in ALLOWED_AUDIO_TYPES
            or file_extension not in ALLOWED_AUDIO_TYPES.get(content_type, [])
        ):
            supported_formats = ", ".join(
                ext for exts in ALLOWED_AUDIO_TYPES.values() for ext in exts
            )
            raise AudioValidationError(
                f"Unsupported file type. Supported formats: {supported_formats}"
            )

    def process_audio_duration(
        self, file_path: str, file_extension: str
    ) -> Tuple[str, bool, Optional[float]]:
        """Process audio file and trim if necessary.

        Loads the audio file, checks its duration, and trims it to the
        maximum allowed duration if it exceeds the limit.

        Args:
            file_path: Path to the audio file.
            file_extension: The file extension for export format.

        Returns:
            Tuple containing:
                - Path to the (possibly trimmed) audio file
                - Whether the audio was trimmed
                - Original duration in minutes if trimmed, None otherwise

        Raises:
            AudioProcessingError: If the audio file cannot be decoded.
        """
        trimmed_file_path = os.path.join(
            os.path.dirname(file_path),
            f"trimmed_{os.path.basename(file_path)}",
        )

        try:
            audio_segment = AudioSegment.from_file(file_path)
            duration_minutes = len(audio_segment) / (1000 * 60)

            if duration_minutes > MAX_AUDIO_DURATION_MINUTES:
                # Trim to max duration
                trimmed_audio = audio_segment[
                    : (MAX_AUDIO_DURATION_MINUTES * 60 * 1000)
                ]
                export_format = (
                    file_extension[1:]
                    if file_extension.startswith(".")
                    else file_extension
                )
                trimmed_audio.export(trimmed_file_path, format=export_format)
                os.remove(file_path)

                self.log_info(
                    f"Audio trimmed from {duration_minutes:.1f} to "
                    f"{MAX_AUDIO_DURATION_MINUTES} minutes"
                )

                return trimmed_file_path, True, duration_minutes

            return file_path, False, None

        except CouldntDecodeError:
            # Clean up files on error
            if os.path.exists(file_path):
                os.remove(file_path)
            if os.path.exists(trimmed_file_path):
                os.remove(trimmed_file_path)
            raise AudioProcessingError(
                "Could not decode audio file. Please ensure the file is not corrupted."
            )

    async def upload_to_storage(self, file_path: str) -> Tuple[str, str]:
        """Upload audio file to cloud storage.

        Args:
            file_path: Path to the audio file to upload.

        Returns:
            Tuple of (blob_name, blob_url).

        Raises:
            AudioProcessingError: If upload fails.
        """
        try:
            blob_name, blob_url = upload_audio_file(file_path=file_path)
            if not blob_name or not blob_url:
                raise AudioProcessingError(
                    "Failed to upload audio file to cloud storage"
                )
            return blob_name, blob_url
        except Exception as e:
            self.log_error(f"Cloud storage upload error: {str(e)}")
            raise AudioProcessingError("Failed to upload audio file to cloud storage")

    async def call_transcription_api(
        self,
        blob_name: str,
        language: str,
        adapter: str,
        whisper: bool = False,
        recognise_speakers: bool = False,
        organisation: bool = False,
    ) -> Dict[str, Any]:
        """Call the RunPod transcription API.

        Args:
            blob_name: Name of the audio blob in storage.
            language: Target language code.
            adapter: Language adapter code.
            whisper: Whether to use Whisper model.
            recognise_speakers: Whether to enable speaker diarization.
            organisation: Whether this is an organization transcription.

        Returns:
            Dictionary containing transcription results.

        Raises:
            TranscriptionError: If transcription fails.
        """
        if organisation:
            payload = {
                "task": "transcribe",
                "audio_file": blob_name,
                "organisation": True,
                "recognise_speakers": recognise_speakers,
            }
        else:
            payload = {
                "task": "transcribe",
                "target_lang": language,
                "adapter": adapter,
                "audio_file": blob_name,
                "whisper": whisper,
                "recognise_speakers": recognise_speakers,
            }

        try:
            raw_resp, job_details = await run_job_and_get_output(payload)
            self.log_info(f"Transcription response received")
            return raw_resp
        except TimeoutError as e:
            self.log_error(f"Transcription timeout: {str(e)}")
            raise TranscriptionError(
                "Transcription service timed out. Please try again with a shorter audio file."
            )
        except ConnectionError as e:
            self.log_error(f"Connection error: {str(e)}")
            raise TranscriptionError(
                "Connection error while transcribing. Please try again."
            )
        except Exception as e:
            self.log_error(f"Transcription error: {str(e)}")
            raise TranscriptionError(
                "An unexpected error occurred during transcription"
            )

    async def call_transcription_api_sync(
        self,
        blob_name: str,
        language: str,
        adapter: str,
        whisper: bool = False,
        recognise_speakers: bool = False,
    ) -> Dict[str, Any]:
        """Call the RunPod transcription API using sync endpoint.

        This method uses the RunPod sync endpoint for GCS-based transcription.

        Args:
            blob_name: Name of the audio blob in storage.
            language: Target language code.
            adapter: Language adapter code.
            whisper: Whether to use Whisper model.
            recognise_speakers: Whether to enable speaker diarization.

        Returns:
            Dictionary containing transcription results.

        Raises:
            TranscriptionError: If transcription fails.
        """
        endpoint = runpod.Endpoint(self.runpod_endpoint_id)
        data = {
            "input": {
                "task": "transcribe",
                "target_lang": language,
                "adapter": adapter,
                "audio_file": blob_name,
                "whisper": whisper,
                "recognise_speakers": recognise_speakers,
            }
        }

        try:
            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, lambda: endpoint.run_sync(data, timeout=600)
            )
            self.log_info("Transcription response received (sync)")
            return response
        except TimeoutError as e:
            self.log_error(f"Transcription timeout: {str(e)}")
            raise TranscriptionError(
                "Transcription service timed out. Please try again with a shorter audio file."
            )
        except ConnectionError as e:
            self.log_error(f"Connection error: {str(e)}")
            raise TranscriptionError(
                "Connection error while transcribing. Please try again."
            )
        except Exception as e:
            self.log_error(f"Transcription error: {str(e)}")
            raise TranscriptionError(
                "An unexpected error occurred during transcription"
            )

    async def transcribe_from_gcs(
        self,
        gcs_blob_name: str,
        language: str = "lug",
        adapter: str = "lug",
        whisper: bool = False,
        recognise_speakers: bool = False,
    ) -> TranscriptionResult:
        """Transcribe audio from a GCS blob.

        Downloads the audio from GCS, processes it (trim if needed),
        and calls the transcription API.

        Args:
            gcs_blob_name: Name of the blob in GCS.
            language: Target language code.
            adapter: Language adapter code.
            whisper: Whether to use Whisper model.
            recognise_speakers: Whether to enable speaker diarization.

        Returns:
            TranscriptionResult containing the transcription and metadata.

        Raises:
            AudioProcessingError: If audio processing fails.
            TranscriptionError: If transcription fails.
        """
        self.log_info(f"Starting transcription from GCS: {gcs_blob_name}")

        storage_client = storage.Client()
        bucket = storage_client.bucket(self.audio_bucket_name)
        blob = bucket.blob(gcs_blob_name)

        if not blob.exists():
            raise AudioProcessingError(f"GCS blob {gcs_blob_name} does not exist.")

        # Download to temp file
        file_extension = get_audio_extension(gcs_blob_name) or ".mp3"
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=file_extension
        ) as temp_file:
            file_path = temp_file.name
            blob.download_to_filename(file_path)

        trimmed_file_path = os.path.join(
            os.path.dirname(file_path),
            f"trimmed_{os.path.basename(file_path)}",
        )

        try:
            # Process audio duration
            file_path, was_trimmed, original_duration = self.process_audio_duration(
                file_path, file_extension
            )

            # Call transcription API
            response = await self.call_transcription_api_sync(
                blob_name=gcs_blob_name,
                language=language,
                adapter=adapter,
                whisper=whisper,
                recognise_speakers=recognise_speakers,
            )

            transcription = response.get("audio_transcription")
            if not transcription:
                raise TranscriptionError(
                    "No transcription was generated. The audio might be silent or unclear."
                )

            return TranscriptionResult(
                transcription=transcription,
                diarization_output=response.get("diarization_output", {}),
                formatted_diarization_output=response.get(
                    "formatted_diarization_output", ""
                ),
                audio_url=f"gs://{self.audio_bucket_name}/{gcs_blob_name}",
                blob_name=gcs_blob_name,
                was_trimmed=was_trimmed,
                original_duration=original_duration,
            )

        finally:
            # Cleanup
            if os.path.exists(file_path):
                os.remove(file_path)
            if os.path.exists(trimmed_file_path):
                os.remove(trimmed_file_path)

    async def transcribe_uploaded_file(
        self,
        file_path: str,
        file_extension: str,
        language: str = "lug",
        adapter: str = "lug",
        whisper: bool = False,
        recognise_speakers: bool = False,
    ) -> TranscriptionResult:
        """Transcribe an uploaded audio file.

        Processes the uploaded file, uploads to cloud storage,
        and calls the transcription API.

        Args:
            file_path: Path to the uploaded audio file.
            file_extension: The file extension.
            language: Target language code.
            adapter: Language adapter code.
            whisper: Whether to use Whisper model.
            recognise_speakers: Whether to enable speaker diarization.

        Returns:
            TranscriptionResult containing the transcription and metadata.

        Raises:
            AudioProcessingError: If audio processing fails.
            TranscriptionError: If transcription fails.
        """
        self.log_info("Starting transcription of uploaded file")

        trimmed_file_path = os.path.join(
            os.path.dirname(file_path),
            f"trimmed_{os.path.basename(file_path)}",
        )

        try:
            # Process audio duration
            file_path, was_trimmed, original_duration = self.process_audio_duration(
                file_path, file_extension
            )

            # Upload to cloud storage
            blob_name, blob_url = await self.upload_to_storage(file_path)

            # Call transcription API
            response = await self.call_transcription_api(
                blob_name=blob_name,
                language=language,
                adapter=adapter,
                whisper=whisper,
                recognise_speakers=recognise_speakers,
            )

            transcription = response.get("audio_transcription")
            if not transcription:
                raise TranscriptionError(
                    "No transcription was generated. The audio might be silent or unclear."
                )

            return TranscriptionResult(
                transcription=transcription,
                diarization_output=response.get("diarization_output", {}),
                formatted_diarization_output=response.get(
                    "formatted_diarization_output", ""
                ),
                audio_url=blob_url,
                blob_name=blob_name,
                was_trimmed=was_trimmed,
                original_duration=original_duration,
            )

        finally:
            # Cleanup
            if os.path.exists(file_path):
                os.remove(file_path)
            if os.path.exists(trimmed_file_path):
                os.remove(trimmed_file_path)

    async def transcribe_org_audio(
        self,
        file_path: str,
        recognise_speakers: bool = False,
    ) -> TranscriptionResult:
        """Transcribe audio for organization endpoint.

        Simplified transcription for organization use cases.

        Args:
            file_path: Path to the audio file.
            recognise_speakers: Whether to enable speaker diarization.

        Returns:
            TranscriptionResult containing the transcription and metadata.

        Raises:
            AudioProcessingError: If audio processing fails.
            TranscriptionError: If transcription fails.
        """
        self.log_info("Starting organization audio transcription")

        try:
            # Upload to cloud storage
            blob_name, blob_url = await self.upload_to_storage(file_path)

            # Call transcription API with organisation flag
            response = await self.call_transcription_api(
                blob_name=blob_name,
                language="",
                adapter="",
                recognise_speakers=recognise_speakers,
                organisation=True,
            )

            return TranscriptionResult(
                transcription=response.get("audio_transcription"),
                diarization_output=response.get("diarization_output", {}),
                formatted_diarization_output=response.get(
                    "formatted_diarization_output", ""
                ),
                audio_url=blob_url,
                blob_name=blob_name,
            )

        finally:
            # Cleanup
            if os.path.exists(file_path):
                os.remove(file_path)


# Singleton instance
_stt_service_instance: Optional[STTService] = None


def get_stt_service() -> STTService:
    """Get the singleton STTService instance.

    Returns:
        The STTService singleton instance.
    """
    global _stt_service_instance
    if _stt_service_instance is None:
        _stt_service_instance = STTService()
    return _stt_service_instance


def reset_stt_service() -> None:
    """Reset the singleton STTService instance.

    Useful for testing to ensure a fresh instance.
    """
    global _stt_service_instance
    _stt_service_instance = None
