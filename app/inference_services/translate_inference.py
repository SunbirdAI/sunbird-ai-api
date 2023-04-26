from app.inference_services.base import inference_request

def create_payload(text, source_language=None, target_language=None):
    task = 'translate_from_english' if target_language != 'English' else 'translate_to_english'
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
