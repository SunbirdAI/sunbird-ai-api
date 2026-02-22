import logging
import os
from typing import Optional, Tuple

from dotenv import load_dotenv
from google.cloud import storage

load_dotenv()

logger = logging.getLogger(__name__)


def _get_bucket_name() -> str:
    bucket_name = os.getenv("AUDIO_CONTENT_BUCKET_NAME")
    if not bucket_name:
        raise ValueError("AUDIO_CONTENT_BUCKET_NAME is not configured")
    return bucket_name


def upload_audio_file(file_path: str) -> Optional[Tuple[str, str]]:
    """Upload audio file to GCS as a private object.

    Returns:
        Tuple[blob_name, gs_uri] when successful, otherwise None.
    """
    try:
        storage_client = storage.Client()
        bucket_name = _get_bucket_name()
        bucket = storage_client.bucket(bucket_name)

        blob_name = os.path.basename(file_path)
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(file_path)

        # Keep object private; downstream workers should access via service account.
        blob_uri = f"gs://{bucket_name}/{blob_name}"
        return blob_name, blob_uri
    except Exception as e:
        logger.error(f"An error occurred while uploading audio file: {e}")
        return None


def delete_audio_file(blob_name: str) -> bool:
    """Delete uploaded audio blob from GCS."""
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(_get_bucket_name())
        blob = bucket.blob(blob_name)
        if blob.exists():
            blob.delete()
        return True
    except Exception as e:
        logger.error(f"An error occurred while deleting audio blob {blob_name}: {e}")
        return False


def upload_file_to_bucket(file_path: str) -> str:
    """
    Uploads a file to a Google Cloud Storage bucket.

    Args:
        file_path (str): The path to the file to upload.

    Returns:
        str: The name of the blob in the bucket.
    """
    try:
        storage_client = storage.Client()
        bucket_name = _get_bucket_name()
        bucket = storage_client.bucket(bucket_name)
        blob_name = os.path.basename(file_path)
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(file_path)
        return blob_name
    except Exception as e:
        raise Exception(f"An error occurred while uploading the file: {e}")
