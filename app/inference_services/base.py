import json
import requests
from dotenv import load_dotenv
import os

load_dotenv()

url = f"https://europe-west1-aiplatform.googleapis.com/v1/projects/{os.getenv('PROJECT_ID')}/locations/europe-west1/endpoints/{os.getenv('ENDPOINT_ID')}:rawPredict"

TOKEN = os.popen('gcloud auth print-access-token').read().strip()
headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

def inference_request(payload):
    response = requests.request(
        "POST",
        url,
        headers=headers,
        data=json.dumps(payload)
    )

    return response
