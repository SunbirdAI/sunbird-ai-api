"""
GCP Storage Service

Handles all interactions with Google Cloud Storage including:
- Uploading audio files
- Generating signed URLs
- File management
"""

import asyncio
import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Optional

from dotenv import load_dotenv
from google.cloud import storage
from google.cloud.storage import Blob, Bucket

from app.core.config import settings
from app.models.enums import SpeakerID

load_dotenv()


class GCPStorageService:
    """
    Service for interacting with Google Cloud Storage.

    Handles audio file uploads and signed URL generation.
    """

    def __init__(
        self,
        bucket_name: Optional[str] = None,
        project_id: Optional[str] = None,
        service_account_email: Optional[str] = None,
    ):
        """
        Initialize the GCP Storage service.

        Args:
            bucket_name: GCP bucket name (defaults to settings)
            project_id: GCP project ID (defaults to settings or ADC)
            service_account_email: Service account email for IAM signing (defaults to settings)
        """
        self._bucket_name = bucket_name or settings.gcp_bucket_name
        self._project_id = project_id or settings.gcp_project_id
        self._service_account_email = (
            service_account_email or settings.gcp_service_account_email
        )
        self._client: Optional[storage.Client] = None
        self._bucket: Optional[Bucket] = None

    @property
    def client(self) -> storage.Client:
        """Lazy-load the storage client."""
        if self._client is None:
            self._client = storage.Client(project=self._project_id)
        return self._client

    @property
    def bucket(self) -> Bucket:
        """Lazy-load the bucket reference."""
        if self._bucket is None:
            self._bucket = self.client.bucket(self._bucket_name)
        return self._bucket

    def generate_file_name(
        self, text: str, speaker_id: int | SpeakerID, prefix: str = "tts_audio"
    ) -> str:
        """
        Generate a unique file name based on content hash and timestamp.

        Args:
            text: The input text (used for hashing)
            speaker_id: Speaker ID (used for hashing)
            prefix: Directory prefix for the file

        Returns:
            Unique file path like "tts_audio/20240115_abc123_def456.wav"
        """
        sid = speaker_id.value if isinstance(speaker_id, SpeakerID) else speaker_id
        content_hash = hashlib.md5(f"{text}:{sid}".encode()).hexdigest()[:8]
        unique_id = uuid.uuid4().hex[:8]
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        return f"{prefix}/{timestamp}_{content_hash}_{unique_id}.wav"

    def upload_audio(
        self, audio_data: bytes, file_name: str, content_type: str = "audio/wav"
    ) -> Blob:
        """
        Upload audio data to GCP Storage.

        Args:
            audio_data: Raw audio bytes
            file_name: Destination file path in bucket
            content_type: MIME type of the audio

        Returns:
            The uploaded Blob object
        """
        blob = self.bucket.blob(file_name)
        blob.upload_from_string(audio_data, content_type=content_type)
        return blob

    async def upload_audio_async(
        self, audio_data: bytes, file_name: str, content_type: str = "audio/wav"
    ) -> Blob:
        """
        Upload audio data to GCP Storage asynchronously.

        Runs the synchronous upload in a thread pool executor.

        Args:
            audio_data: Raw audio bytes
            file_name: Destination file path in bucket
            content_type: MIME type of the audio

        Returns:
            The uploaded Blob object
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.upload_audio, audio_data, file_name, content_type
        )

    def generate_signed_url(
        self, blob: Blob, expiry_minutes: Optional[int] = None
    ) -> tuple[str, datetime]:
        """
        Generate a signed URL for a blob.

        Args:
            blob: The Blob to generate a URL for
            expiry_minutes: URL expiry time in minutes (defaults to settings)

        Returns:
            Tuple of (signed_url, expiry_datetime)
        """
        expiry = expiry_minutes or settings.signed_url_expiry_minutes
        expires_at = datetime.now(UTC) + timedelta(minutes=expiry)

        # Generate signed URL with IAM-based signing for Cloud Run (no private key required)
        signing_kwargs = {
            "version": "v4",
            "expiration": timedelta(minutes=expiry),
            "method": "GET",
        }

        # Add service account email for IAM signing if available
        if self._service_account_email:
            signing_kwargs["service_account_email"] = self._service_account_email

        signed_url = blob.generate_signed_url(**signing_kwargs)

        return signed_url, expires_at

    def get_signed_url_for_file(
        self, file_name: str, expiry_minutes: Optional[int] = None
    ) -> tuple[str, datetime]:
        """
        Get a signed URL for an existing file.

        Args:
            file_name: Path to the file in the bucket
            expiry_minutes: URL expiry time in minutes

        Returns:
            Tuple of (signed_url, expiry_datetime)
        """
        blob = self.bucket.blob(file_name)
        return self.generate_signed_url(blob, expiry_minutes)

    def delete_file(self, file_name: str) -> bool:
        """
        Delete a file from the bucket.

        Args:
            file_name: Path to the file in the bucket

        Returns:
            True if deleted, False if file didn't exist
        """
        blob = self.bucket.blob(file_name)
        if blob.exists():
            blob.delete()
            return True
        return False

    def file_exists(self, file_name: str) -> bool:
        """
        Check if a file exists in the bucket.

        Args:
            file_name: Path to the file in the bucket

        Returns:
            True if file exists
        """
        blob = self.bucket.blob(file_name)
        return blob.exists()


# Singleton instance for dependency injection
_storage_service: Optional[GCPStorageService] = None


def get_storage_service() -> GCPStorageService:
    """
    Get or create the storage service singleton.

    Returns:
        GCPStorageService instance
    """
    global _storage_service
    if _storage_service is None:
        _storage_service = GCPStorageService()
    return _storage_service
