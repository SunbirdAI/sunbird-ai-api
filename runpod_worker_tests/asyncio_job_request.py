"""
Example of calling an endpoint using asyncio.
"""

import asyncio
import os

import requests
import runpod
from dotenv import load_dotenv
from runpod import AsyncioEndpoint, AsyncioJob, http_client

load_dotenv()

# asyncio.set_event_loop_policy(
#     asyncio.WindowsSelectorEventLoopPolicy()
# )  # For Windows Users

runpod.api_key = os.getenv("RUNPOD_API_KEY")
RUNPOD_ENDPOINT_ID = os.getenv("RUNPOD_ENDPOINT_ID")


def get_job_details(job: AsyncioJob):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f'Bearer {os.getenv("RUNPOD_API_KEY")}',
    }

    url = f"https://api.runpod.ai/v2/{job.endpoint_id}/status/{job.job_id}"
    response = requests.get(url, headers=headers)
    return response.json()


async def main():
    """
    Function to run the example.
    """
    async with http_client.AsyncClientSession() as session:
        # Invoke API
        payload = {
            "task": "translate",
            "source_language": "eng",
            "target_language": "lug",
            "text": "I am watching an Arsenal game right now",  # Remove leading/trailing spaces
        }
        endpoint = AsyncioEndpoint(RUNPOD_ENDPOINT_ID, session)
        job: AsyncioJob = await endpoint.run(payload)

        print(dir(job))
        print(f"Job details: {job.__dict__}")
        job_details = get_job_details(job)
        print(f"Job details from REST API: {job_details}")

        # Get current job status
        print("Fetching initial job status...")
        status = await job.status()

        # Print status
        print(status)

        # Wait until job is completed or failed
        # Try to get the job output with a generous timeout. If it times out,
        # fetch and print the latest status and optionally poll a few times.
        try:
            output = await job.output(timeout=600)  # wait up to 10 minutes
            print(output)
            job_details = get_job_details(job)
            print(f"Job details from REST API: {job_details}")
        except TimeoutError:
            # The Runpod asyncio runner raises TimeoutError when the wait_for times out.
            print("Job timed out waiting for output. Fetching latest status...")
            status = await job.status()
            print(status)
            job_details = get_job_details(job)
            print(f"Job details from REST API: {job_details}")

            # Poll a few times (short) to see if the job completes shortly after timeout
            poll_attempts = 6
            poll_interval = 5  # seconds
            output = None
            for i in range(poll_attempts):
                await asyncio.sleep(poll_interval)
                status = await job.status()
                print(f"Poll {i+1}/{poll_attempts} status:", status)
                if isinstance(status, dict) and status.get("status") in (
                    "COMPLETED",
                    "FAILED",
                ):
                    try:
                        output = await job.output(timeout=30)
                        print(output)
                        job_details = get_job_details(job)
                        print(f"Job details from REST API: {job_details}")
                        break
                    except TimeoutError:
                        continue

            if output is None:
                # Final fallback: inform user and surface the last known status
                print("No output received after polling. Last known status:", status)


asyncio.run(main())
