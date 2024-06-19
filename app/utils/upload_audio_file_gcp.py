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

         # Get the public URL of the uploaded file
        blob_url = blob.public_url

        return blob_name, blob_url
    except Exception as e:
        print(f"An error occurred: {e}")
        return None
