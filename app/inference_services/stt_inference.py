import base64
from io import BytesIO
from app.inference_services.base import inference_request


def create_payload(audio_file):
    contents = audio_file.file.read()
    audio_bytes = BytesIO(contents)
    encoded_audio = base64.b64encode(audio_bytes.read())

    utf_audio = encoded_audio.decode('utf-8')

    payload = {
        "instances": [
            {
                "audio": utf_audio,
                "task": "asr"
            }
        ]
    }

    return payload

def transcribe(audio_file):
    # TODO: Handle error cases
    payload = create_payload(audio_file)
    response = inference_request(payload).json()
    return response['transcripts'][0]
