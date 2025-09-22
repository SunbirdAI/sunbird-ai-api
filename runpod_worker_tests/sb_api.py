import asyncio
import logging
import os
from typing import Any, Dict, Optional

import requests
import runpod
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from runpod import AsyncioEndpoint, AsyncioJob, http_client

load_dotenv()

# Basic logging
logging.basicConfig(level=logging.INFO)

# Load config from env
runpod.api_key = os.getenv("RUNPOD_API_KEY")
RUNPOD_ENDPOINT_ID = os.getenv("RUNPOD_ENDPOINT_ID")

app = FastAPI(title="Sunbird AI Runpod proxy")


class WorkerTranslationOutput(BaseModel):
    text: Optional[str] = None
    translated_text: Optional[str] = None
    source_language: Optional[str] = None
    target_language: Optional[str] = None
    Error: Optional[str] = None


class WorkerTranslationResponse(BaseModel):
    delayTime: Optional[int] = None
    executionTime: Optional[int] = None
    id: Optional[str] = None
    output: Optional[WorkerTranslationOutput] = None
    status: Optional[str] = None
    workerId: Optional[str] = None


def get_job_details(job: AsyncioJob):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f'Bearer {os.getenv("RUNPOD_API_KEY")}',
    }

    url = f"https://api.runpod.ai/v2/{job.endpoint_id}/status/{job.job_id}"
    response = requests.get(url, headers=headers)
    return response.json()


async def _run_job_and_get_output(
    payload: Dict[str, Any], timeout: int = 600
) -> Dict[str, Any]:
    async with http_client.AsyncClientSession() as session:
        endpoint = AsyncioEndpoint(RUNPOD_ENDPOINT_ID, session)
        job: AsyncioJob = await endpoint.run(payload)

        try:
            out = await job.output(timeout=timeout)
            job_details = get_job_details(job)
            logging.info(f"Job details from REST API: {job_details}")
            return out, job_details
        except TimeoutError:
            # try to fetch status and poll briefly
            status = await job.status()
            logging.info("Job timed out, status=%s", status)
            job_details = get_job_details(job)
            logging.info(f"Job details from REST API: {job_details}")
            poll_attempts = 6
            for _ in range(poll_attempts):
                await asyncio.sleep(5)
                status = await job.status()
                logging.info("Polled status: %s", status)
                job_details = get_job_details(job)
                logging.info(f"Job details from REST API: {job_details}")
                if isinstance(status, dict) and status.get("status") in (
                    "COMPLETED",
                    "FAILED",
                ):
                    try:
                        out = await job.output(timeout=30)
                        job_details = get_job_details(job)
                        logging.info(f"Job details from REST API: {job_details}")
                        return out, job_details
                    except TimeoutError:
                        continue
            # Last resort: return last status
            return {"status": status}, job_details


def _normalize_runpod_response(resp: Any) -> Dict[str, Any]:
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


class TranslateRequest(BaseModel):
    source_language: Optional[str] = None
    target_language: Optional[str] = None
    text: str


@app.post("/run-translate", response_model=WorkerTranslationResponse)
async def run_translate(req: TranslateRequest):
    payload = {
        "task": "translate",
        "source_language": req.source_language,
        "target_language": req.target_language,
        "text": req.text,
    }
    try:
        _, job_details = await _run_job_and_get_output(payload)
    except Exception as e:
        logging.exception("Job run failed")
        raise HTTPException(status_code=500, detail=str(e))

    normalized = _normalize_runpod_response(job_details)
    # Validate and return
    try:
        resp = WorkerTranslationResponse.model_validate(normalized)
        return resp.model_dump()
    except Exception as e:
        logging.exception("Failed to validate normalized response")
        raise HTTPException(status_code=500, detail="Invalid response from worker")
