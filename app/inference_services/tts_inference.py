from app.inference_services.base import inference_request
from app.schemas.tasks import TTSRequest

def create_payload(text):
    payload = {
        "instances": [
            {
                "sentence": text,
                "task": "tts"
            }
        ]
    }

    return payload


def tts(request: TTSRequest):
    payload = create_payload(request.text)

    response = inference_request(payload).json()

    b64_audio = response["base64_audio"][0]

    return b64_audio
