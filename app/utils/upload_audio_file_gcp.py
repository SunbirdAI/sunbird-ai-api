import os

from dotenv import load_dotenv
from google.cloud import storage

load_dotenv()


def upload_audio_file(file_path):
    try:
        # Initialize a client and get the bucket
        storage_client = storage.Client()
        bucket_name = os.getenv("AUDIO_CONTENT_BUCKET_NAME")
        bucket = storage_client.bucket(bucket_name)

        blob_name = os.path.basename(file_path)

        # Upload the file to the bucket
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(file_path)

        return blob_name
    except Exception as e:
        print(f"An error occurred: {e}")
        return None
    
def upload_file_to_bucket(file_path):
    """
    Uploads a file to a Google Cloud Storage bucket.

    Args:
        file_path (str): The path to the file to upload.
        bucket_name (str): The name of the bucket to upload to.

    Returns:
        str: The name of the blob in the bucket.
    """
    try:
        storage_client = storage.Client()
        bucket_name = os.getenv("AUDIO_CONTENT_BUCKET_NAME")
        bucket = storage_client.bucket(bucket_name)
        blob_name = os.path.basename(file_path)
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(file_path)
        return blob_name
    except Exception as e:
        raise Exception(f"An error occurred while uploading the file: {e}")
