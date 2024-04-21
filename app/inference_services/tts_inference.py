import base64
import os
import uuid

from dotenv import load_dotenv
from google.cloud import storage

from app.inference_services.base import inference_request
from app.schemas.tasks import TTSRequest

load_dotenv()


def create_payload(text):
    payload = {"instances": [{"sentence": text, "task": "tts"}]}

    return payload


def tts(request: TTSRequest):
    payload = create_payload(request.text)

    response = inference_request(payload).json()

    b64_audio = response["base64_audio"][0]

    if not request.return_audio_link:
        return b64_audio
    else:
        local_file = "temp.wav"

        with open(local_file, "wb") as wav_file:
            decoded_audio = base64.decodebytes(b64_audio.encode("utf-8"))
            wav_file.write(decoded_audio)

        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "service_account_key.json"
        bucket_name = os.getenv("GOOGLE_CLOUD_BUCKET_NAME")
        bucket_file = f"{str(uuid.uuid4())}.wav"  # using a uuid for the audio file name
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(bucket_file)
        blob.upload_from_filename(local_file)

        os.remove(local_file)

        url = f"https://storage.googleapis.com/{bucket_name}/{bucket_file}"

        return url
