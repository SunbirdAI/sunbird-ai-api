import asyncio
import logging
import os
from typing import Any, Dict

import requests
from runpod import AsyncioEndpoint, AsyncioJob, http_client

RUNPOD_ENDPOINT_ID = os.getenv("RUNPOD_ENDPOINT_ID")


async def _run_job_and_get_output(payload: dict, timeout: int = 600):
    """Run a runpod asyncio job and attempt to return (output, job_details).

    Returns a tuple (output, job_details) where output may be the worker output dict
    and job_details is the REST API details for the job.
    """
    async with http_client.AsyncClientSession() as session:
        logging.info("Starting RunPod job...")
        logging.info(f"Payload: {payload}")
        endpoint_id = RUNPOD_ENDPOINT_ID
        endpoint = AsyncioEndpoint(endpoint_id, session)
        job: AsyncioJob = await endpoint.run(payload)

        def _get_job_details_sync():
            url = f"https://api.runpod.ai/v2/{job.endpoint_id}/status/{job.job_id}"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {os.getenv('RUNPOD_API_KEY')}",
            }
            resp = requests.get(url, headers=headers)
            try:
                return resp.json()
            except Exception:
                return {"status": "UNKNOWN", "raw": resp.text}

        # Fetch initial job details
        status = await job.status()
        logging.info("Job timed out, status=%s", status)
        job_details = _get_job_details_sync()
        logging.info(f"Job details from Runpod REST API: {job_details}")

        try:
            out = await job.output(timeout=timeout)
            job_details = _get_job_details_sync()
            logging.info(f"Job details from Runpod REST API: {job_details}")
            return out, job_details
        except TimeoutError:
            status = await job.status()
            logging.info("Job timed out, status=%s", status)
            job_details = _get_job_details_sync()
            logging.info(f"Job details from Runpod REST API: {job_details}")
            poll_attempts = 6
            for _ in range(poll_attempts):
                await asyncio.sleep(5)
                status = await job.status()
                logging.info("Polled status: %s", status)
                job_details = _get_job_details_sync()
                logging.info(f"Job details from Runpod REST API: {job_details}")
                if isinstance(status, dict) and status.get("status") in (
                    "COMPLETED",
                    "FAILED",
                ):
                    try:
                        out = await job.output(timeout=30)
                        job_details = _get_job_details_sync()
                        logging.info(f"Job details from Runpod REST API: {job_details}")
                        return out, job_details
                    except TimeoutError:
                        continue
            # Last resort:
            job.cancel()
            status = await job.status()
            job_details = _get_job_details_sync()
            logging.info(
                f"Job details from Runpod REST API after cancellation: {job_details}"
            )
            return {"status": status}, job_details


def _normalize_runpod_response(resp: Any) -> Dict[str, Any]:
    """Normalize a Runpod response into the Worker response shape.

    If the value is not a dict it will be wrapped as the `output` key. If the
    dict already appears to be a full worker response (contains keys like
    "delayTime" or "executionTime") it will be returned unchanged.
    """
    if not isinstance(resp, dict):
        return {
            "delayTime": None,
            "executionTime": None,
            "id": None,
            "output": resp,
            "status": None,
            "workerId": None,
        }
    top_keys = {"delayTime", "executionTime", "id", "status", "workerId"}
    if top_keys & set(resp.keys()):
        return resp
    output = resp.get("output", resp)
    return {
        "delayTime": resp.get("delayTime"),
        "executionTime": resp.get("executionTime"),
        "id": resp.get("id"),
        "output": output,
        "status": resp.get("status") or ("COMPLETED" if output else None),
        "workerId": resp.get("workerId"),
    }


async def run_job_and_get_output(payload: dict, timeout: int = 600):
    """Public wrapper for running a job and getting output.

    Keeps the internal implementation private while providing a public API
    for other modules to import (no leading underscore).
    """
    return await _run_job_and_get_output(payload, timeout=timeout)


def normalize_runpod_response(resp: Any) -> Dict[str, Any]:
    """Public wrapper for normalizing runpod responses.

    Import this in other modules instead of the underscore-prefixed helper.
    """
    return _normalize_runpod_response(resp)


__all__ = [
    "run_job_and_get_output",
    "normalize_runpod_response",
]
