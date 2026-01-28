"""
Upload Schema Definitions.

This module defines Pydantic models for file upload operations,
including request validation and response formatting.

Models:
    - UploadRequest: Request model for generating upload URLs
    - UploadResponse: Response model with signed URL and metadata
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UploadRequest(BaseModel):
    """
    Request model for generating a signed upload URL.

    Attributes:
        file_name: Name of the file to upload.
        content_type: MIME type of the file (e.g., "audio/wav", "image/png").

    Example:
        {
            "file_name": "recording.wav",
            "content_type": "audio/wav"
        }
    """

    file_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Name of the file to upload",
        json_schema_extra={"example": "recording.wav"},
    )
    content_type: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="MIME type of the file",
        json_schema_extra={"example": "audio/wav"},
    )


class UploadResponse(BaseModel):
    """
    Response model for upload URL generation.

    Attributes:
        upload_url: Pre-signed URL for direct upload to GCS.
        file_id: Unique identifier for the uploaded file.
        expires_at: When the upload URL expires.

    Example:
        {
            "upload_url": "https://storage.googleapis.com/...",
            "file_id": "550e8400-e29b-41d4-a716-446655440000",
            "expires_at": "2024-01-15T10:30:00Z"
        }
    """

    upload_url: str = Field(
        ...,
        description="Pre-signed URL for direct upload to GCS",
    )
    file_id: str = Field(
        ...,
        description="Unique identifier for tracking the upload",
    )
    expires_at: datetime = Field(
        ...,
        description="When the upload URL expires",
    )


class DownloadUrlRequest(BaseModel):
    """
    Request model for generating a signed download URL.

    Attributes:
        blob_name: Path to the file in the bucket.
        expiry_minutes: URL expiry time in minutes (optional).
    """

    blob_name: str = Field(
        ...,
        min_length=1,
        description="Path to the file in the bucket",
    )
    expiry_minutes: Optional[int] = Field(
        default=60,
        ge=1,
        le=1440,
        description="URL expiry time in minutes (1-1440)",
    )


class DownloadUrlResponse(BaseModel):
    """
    Response model for download URL generation.

    Attributes:
        download_url: Pre-signed URL for downloading the file.
        expires_at: When the download URL expires.
    """

    download_url: str = Field(
        ...,
        description="Pre-signed URL for downloading the file",
    )
    expires_at: datetime = Field(
        ...,
        description="When the download URL expires",
    )


__all__ = [
    "UploadRequest",
    "UploadResponse",
    "DownloadUrlRequest",
    "DownloadUrlResponse",
]
