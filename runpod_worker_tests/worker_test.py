import logging
import os

import runpod
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)

RUNPOD_ENDPOINT_ID = os.getenv("RUNPOD_ENDPOINT_ID")
# Set RunPod API Key
runpod.api_key = os.getenv("RUNPOD_API_KEY")

endpoint = runpod.Endpoint(RUNPOD_ENDPOINT_ID)

data = {
    "input": {
        "task": "translate",
        "source_language": "eng",
        "target_language": "lug",
        "text": "I am watching an Arsenal game right now",  # Remove leading/trailing spaces
    }
}

response = endpoint.run_sync(data, timeout=600)
logging.info(f"RunPod response: {response}")
