import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

url = f"https://europe-west1-aiplatform.googleapis.com/v1/projects/{os.getenv('PROJECT_ID')}/locations/europe-west1/endpoints/{os.getenv('ENDPOINT_ID')}:rawPredict"  # noqa E501


def inference_request(payload):
    token = os.popen("gcloud auth print-access-token").read().strip()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    response = requests.request("POST", url, headers=headers, data=json.dumps(payload))

    return response
