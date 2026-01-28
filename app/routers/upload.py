"""
Upload Router Module.

This module defines the API endpoints for file upload operations.
It provides endpoints for generating signed URLs that allow direct
uploads to Google Cloud Storage, bypassing API server size limits.

Endpoints:
    - POST /generate-upload-url: Generate a signed URL for direct upload

Architecture:
    Routes -> StorageService -> Google Cloud Storage

Usage:
    This router is included in the main application with the /tasks prefix
    to maintain backward compatibility with existing API consumers.

Note:
    This module was extracted from app/routers/tasks.py as part of the
    services layer refactoring to improve modularity.
"""

import logging

from fastapi import APIRouter

from app.core.exceptions import BadRequestError, ExternalServiceError
from app.schemas.upload import UploadRequest, UploadResponse
from app.services.storage_service import (
    StorageError,
    StorageService,
    get_storage_service,
)

logging.basicConfig(level=logging.INFO)

router = APIRouter()


def get_service() -> StorageService:
    """Dependency for getting the Storage service instance.

    Returns:
        The StorageService singleton instance.
    """
    return get_storage_service()


@router.post(
    "/generate-upload-url",
    response_model=UploadResponse,
    summary="Generate Upload URL",
    description="Generate a signed URL for direct upload to Google Cloud Storage.",
)
async def generate_upload_url(
    request: UploadRequest,
) -> UploadResponse:
    """
    Generate a signed URL for direct upload to Google Cloud Storage.

    This endpoint creates a pre-signed URL that allows clients to upload files
    directly to GCS without going through the API server. This approach:
    - Bypasses Cloud Run request size limits
    - Reduces server load for large file transfers
    - Provides secure, time-limited upload access

    Args:
        request: The upload request containing file_name and content_type.

    Returns:
        UploadResponse containing the signed URL, file ID, and expiry time.

    Raises:
        BadRequestError: If request validation fails.
        ExternalServiceError: If URL generation fails.

    Example:
        Request:
        ```json
        {
            "file_name": "recording.wav",
            "content_type": "audio/wav"
        }
        ```

        Response:
        ```json
        {
            "upload_url": "https://storage.googleapis.com/...",
            "file_id": "550e8400-e29b-41d4-a716-446655440000",
            "expires_at": "2024-01-15T10:30:00Z"
        }
        ```

    Usage:
        After receiving the signed URL, the client should:
        1. Make a PUT request to the upload_url
        2. Include the Content-Type header matching the request
        3. Send the file data in the request body
        4. Use the file_id to reference the file in subsequent API calls
    """
    try:
        # Validate file name (basic security check)
        if ".." in request.file_name or request.file_name.startswith("/"):
            raise BadRequestError(
                message="Invalid file name: path traversal not allowed"
            )

        # Get storage service and generate URL
        service = get_service()
        upload_url, file_id, expires_at = service.generate_upload_url(
            file_name=request.file_name,
            content_type=request.content_type,
        )

        logging.info(f"Upload URL generated for file: {request.file_name}")

        return UploadResponse(
            upload_url=upload_url,
            file_id=file_id,
            expires_at=expires_at,
        )

    except BadRequestError:
        raise
    except StorageError as e:
        logging.error(f"Storage error generating upload URL: {e}")
        raise ExternalServiceError(
            service_name="Google Cloud Storage",
            message="Error generating upload URL",
            original_error=str(e),
        )
    except Exception as e:
        logging.error(f"Unexpected error generating upload URL: {e}")
        raise ExternalServiceError(
            service_name="Google Cloud Storage",
            message="Error generating upload URL",
            original_error=str(e),
        )
