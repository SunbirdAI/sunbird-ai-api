"""
Storage Service Module.

This module provides a unified interface for interacting with Google Cloud Storage,
including file uploads, signed URL generation, and file management operations.

Architecture:
    StorageService -> Google Cloud Storage API

Usage:
    from app.services.storage_service import get_storage_service

    service = get_storage_service()
    upload_url, file_id, expires_at = service.generate_upload_url(
        file_name="audio.wav",
        content_type="audio/wav"
    )
"""

import hashlib
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from dotenv import load_dotenv
from google.auth import default
from google.auth.transport.requests import Request
from google.cloud import storage
from google.cloud.storage import Blob, Bucket

from app.services.base import BaseService

load_dotenv()
logging.basicConfig(level=logging.INFO)


class StorageError(Exception):
    """Base exception for storage operations."""

    pass


class StorageConnectionError(StorageError):
    """Raised when connection to storage fails."""

    pass


class StorageUploadError(StorageError):
    """Raised when file upload fails."""

    pass


class StorageService(BaseService):
    """
    Service for interacting with Google Cloud Storage.

    Handles file uploads, signed URL generation, and file management.

    Attributes:
        bucket_name: The GCS bucket name.
        project_id: The GCP project ID.

    Example:
        service = StorageService()
        url, file_id, expires = service.generate_upload_url("file.wav", "audio/wav")
    """

    def __init__(
        self,
        bucket_name: Optional[str] = None,
        project_id: Optional[str] = None,
        service_account_email: Optional[str] = None,
    ) -> None:
        """
        Initialize the Storage service.

        Args:
            bucket_name: GCP bucket name (defaults to environment variable).
            project_id: GCP project ID (defaults to ADC).
            service_account_email: Service account email for IAM signing (defaults to environment variable).
        """
        super().__init__()
        self._bucket_name = bucket_name or os.getenv(
            "AUDIO_CONTENT_BUCKET_NAME", "sb-asr-audio-content-sb-gcp-project-01"
        )
        self._project_id = project_id or os.getenv("GCP_PROJECT_ID")
        self._service_account_email = service_account_email or os.getenv(
            "GCP_SERVICE_ACCOUNT_EMAIL"
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

    def generate_upload_url(
        self,
        file_name: str,
        content_type: str,
        expiry_minutes: int = 10,
        prefix: str = "uploads",
    ) -> Tuple[str, str, datetime]:
        """
        Generate a signed URL for direct upload to GCS.

        This creates a pre-signed URL that allows clients to upload files
        directly to GCS without going through the API server, bypassing
        request size limits.

        Args:
            file_name: The name of the file to upload.
            content_type: MIME type of the file (e.g., "audio/wav").
            expiry_minutes: URL expiry time in minutes (default 10).
            prefix: Directory prefix for the file (default "uploads").

        Returns:
            Tuple of (signed_upload_url, file_id, expiry_datetime).

        Raises:
            StorageError: If URL generation fails.

        Example:
            url, file_id, expires = service.generate_upload_url(
                "recording.wav",
                "audio/wav"
            )
        """
        try:
            self.log_info(f"Generating upload URL for: {file_name}")

            # Generate a unique file ID
            file_id = str(uuid.uuid4())

            # Create blob path with unique ID prefix
            blob_name = f"{prefix}/{file_id}/{file_name}"
            blob = self.bucket.blob(blob_name)

            # Calculate expiry time
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=expiry_minutes)

            # Generate signed URL for PUT method
            # Use IAM-based signing for Cloud Run (no private key required)
            signing_kwargs = {
                "version": "v4",
                "expiration": timedelta(minutes=expiry_minutes),
                "method": "PUT",
                "content_type": content_type,
            }

            # Add service account email and access token for IAM-based signing
            # When running in Cloud Run, we need to explicitly provide an access token
            # to force the library to use the IAM signBlob API instead of trying to sign locally
            if self._service_account_email:
                try:
                    # Get default credentials and refresh to get access token
                    credentials, _ = default()
                    if not credentials.valid:
                        credentials.refresh(Request())

                    signing_kwargs[
                        "service_account_email"
                    ] = self._service_account_email
                    signing_kwargs["access_token"] = credentials.token

                    self.log_info(
                        f"Using IAM-based signing with service account: {self._service_account_email}"
                    )
                except Exception as e:
                    self.log_warning(f"Failed to get access token for IAM signing: {e}")
                    # Fall back to service account email only
                    signing_kwargs[
                        "service_account_email"
                    ] = self._service_account_email

            signed_url = blob.generate_signed_url(**signing_kwargs)

            self.log_info(f"Upload URL generated for file_id: {file_id}")
            return signed_url, file_id, expires_at

        except Exception as e:
            self.log_error(f"Failed to generate upload URL: {e}")
            raise StorageError(f"Error generating upload URL: {str(e)}")

    def generate_download_url(
        self,
        blob_name: str,
        expiry_minutes: int = 60,
    ) -> Tuple[str, datetime]:
        """
        Generate a signed URL for downloading a file.

        Args:
            blob_name: Path to the file in the bucket.
            expiry_minutes: URL expiry time in minutes (default 60).

        Returns:
            Tuple of (signed_download_url, expiry_datetime).

        Raises:
            StorageError: If URL generation fails.
        """
        try:
            blob = self.bucket.blob(blob_name)
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=expiry_minutes)

            # Generate signed URL for GET method
            # Use IAM-based signing for Cloud Run (no private key required)
            signing_kwargs = {
                "version": "v4",
                "expiration": timedelta(minutes=expiry_minutes),
                "method": "GET",
            }

            # Add service account email and access token for IAM-based signing
            # When running in Cloud Run, we need to explicitly provide an access token
            # to force the library to use the IAM signBlob API instead of trying to sign locally
            if self._service_account_email:
                try:
                    # Get default credentials and refresh to get access token
                    credentials, _ = default()
                    if not credentials.valid:
                        credentials.refresh(Request())

                    signing_kwargs[
                        "service_account_email"
                    ] = self._service_account_email
                    signing_kwargs["access_token"] = credentials.token

                    self.log_info(
                        f"Using IAM-based signing with service account: {self._service_account_email}"
                    )
                except Exception as e:
                    self.log_warning(f"Failed to get access token for IAM signing: {e}")
                    # Fall back to service account email only
                    signing_kwargs[
                        "service_account_email"
                    ] = self._service_account_email

            signed_url = blob.generate_signed_url(**signing_kwargs)

            return signed_url, expires_at

        except Exception as e:
            self.log_error(f"Failed to generate download URL: {e}")
            raise StorageError(f"Error generating download URL: {str(e)}")

    def upload_file(
        self,
        file_path: str,
        destination_name: Optional[str] = None,
        make_public: bool = False,
    ) -> Tuple[str, Optional[str]]:
        """
        Upload a file to GCS.

        Args:
            file_path: Local path to the file.
            destination_name: Name in bucket (defaults to file basename).
            make_public: Whether to make the file publicly accessible.

        Returns:
            Tuple of (blob_name, public_url or None).

        Raises:
            StorageUploadError: If upload fails.
        """
        try:
            blob_name = destination_name or os.path.basename(file_path)
            blob = self.bucket.blob(blob_name)
            blob.upload_from_filename(file_path)

            public_url = None
            if make_public:
                blob.make_public()
                public_url = blob.public_url

            self.log_info(f"File uploaded: {blob_name}")
            return blob_name, public_url

        except Exception as e:
            self.log_error(f"Failed to upload file: {e}")
            raise StorageUploadError(f"Error uploading file: {str(e)}")

    def upload_bytes(
        self,
        data: bytes,
        blob_name: str,
        content_type: str = "application/octet-stream",
    ) -> Blob:
        """
        Upload raw bytes to GCS.

        Args:
            data: Raw bytes to upload.
            blob_name: Destination path in bucket.
            content_type: MIME type of the data.

        Returns:
            The uploaded Blob object.

        Raises:
            StorageUploadError: If upload fails.
        """
        try:
            blob = self.bucket.blob(blob_name)
            blob.upload_from_string(data, content_type=content_type)
            self.log_info(f"Bytes uploaded: {blob_name}")
            return blob

        except Exception as e:
            self.log_error(f"Failed to upload bytes: {e}")
            raise StorageUploadError(f"Error uploading bytes: {str(e)}")

    def generate_unique_filename(
        self,
        content: str,
        identifier: str,
        prefix: str = "files",
        extension: str = "bin",
    ) -> str:
        """
        Generate a unique filename based on content hash and timestamp.

        Args:
            content: Content string for hashing.
            identifier: Additional identifier for hashing.
            prefix: Directory prefix for the file.
            extension: File extension (without dot).

        Returns:
            Unique file path like "files/20240115_abc123_def456.bin".
        """
        content_hash = hashlib.md5(f"{content}:{identifier}".encode()).hexdigest()[:8]
        unique_id = uuid.uuid4().hex[:8]
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"{prefix}/{timestamp}_{content_hash}_{unique_id}.{extension}"

    def file_exists(self, blob_name: str) -> bool:
        """
        Check if a file exists in the bucket.

        Args:
            blob_name: Path to the file in the bucket.

        Returns:
            True if file exists, False otherwise.
        """
        blob = self.bucket.blob(blob_name)
        return blob.exists()

    def delete_file(self, blob_name: str) -> bool:
        """
        Delete a file from the bucket.

        Args:
            blob_name: Path to the file in the bucket.

        Returns:
            True if deleted, False if file didn't exist.
        """
        blob = self.bucket.blob(blob_name)
        if blob.exists():
            blob.delete()
            self.log_info(f"File deleted: {blob_name}")
            return True
        return False


# Singleton instance
_storage_service: Optional[StorageService] = None


def get_storage_service() -> StorageService:
    """
    Get or create the storage service singleton.

    Returns:
        StorageService instance.
    """
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService()
    return _storage_service


def reset_storage_service() -> None:
    """Reset the storage service singleton (useful for testing)."""
    global _storage_service
    _storage_service = None
