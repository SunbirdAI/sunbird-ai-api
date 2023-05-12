from app.inference_services.base import inference_request
from typing import List
from app.schemas.tasks import TranslationBatchRequest


def get_task(target_language):
    return 'translate_from_english' if target_language != 'English' else 'translate_to_english'


def create_payload(text, source_language=None, target_language=None):
    task = get_task(target_language)
    payload = {
        "instances": [
            {
                "sentence": text,
                "task": task,
                "target_language": target_language
            }
        ]
    }

    return payload

def create_batch_payload(request: TranslationBatchRequest):
    payload = {
        "instances": [
            {
                "sentence": request.text,
                "task": get_task(request.target_language),
                "target_language": request.target_language
            }
            for request in request.requests
        ]
    }

    return payload

def translate(text, source_language=None, target_language=None):
    payload = create_payload(text, source_language, target_language)
    response = inference_request(payload).json()
    # TODO: Handle error cases i.e if there's an error from the inference server.
    # print(response)
    if target_language == 'English':
        response = response["to_english_translations"][0]
    else:
        response = response["from_english_translations"][0]
    return response

def translate_batch(request: TranslationBatchRequest):
    payload = create_batch_payload(request)
    response = inference_request(payload).json()
    response_list = []
    if 'to_english_translations' in response:
        response_list = response['to_english_translations']
    if 'from_english_translations' in response:
        response_list.extend(response['from_english_translations'])

    return response_list
