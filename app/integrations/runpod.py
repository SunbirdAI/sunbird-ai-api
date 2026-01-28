"""
RunPod Integration Module.

This module provides a client for interacting with RunPod's serverless API.
It handles job submission, status polling, and response normalization for
ML inference tasks running on RunPod's infrastructure.

RunPod is used for:
    - Speech-to-text (STT) transcription
    - Translation (NLLB models)
    - Language identification
    - Text summarization

Architecture:
    Services -> RunPodClient -> RunPod Serverless API

Usage:
    from app.integrations.runpod import RunPodClient, get_runpod_client

    # Using the singleton
    client = get_runpod_client()
    output, job_details = await client.run_job({"audio": audio_data})

    # Or create a custom instance
    client = RunPodClient(endpoint_id="my-endpoint", api_key="my-key")
    result = await client.run_job(payload, timeout=300)

Example:
    >>> client = RunPodClient()
    >>> payload = {"input": {"text": "Hello", "target_lang": "lug"}}
    >>> output, details = await client.run_job(payload)
    >>> print(output.get("translated_text"))
    "Oli otya"
"""

import asyncio
import logging
import os
from typing import Any, Dict, Optional, Tuple

import requests
from runpod import AsyncioEndpoint, AsyncioJob, http_client

from app.core.config import settings

# Module-level logger
logger = logging.getLogger(__name__)


class RunPodClient:
    """Client for interacting with RunPod's serverless API.

    This client handles the complexities of RunPod's async job system,
    including job submission, status polling, timeout handling, and
    response normalization.

    Attributes:
        endpoint_id: The RunPod endpoint ID for the serverless function.
        api_key: The RunPod API key for authentication.
        default_timeout: Default timeout in seconds for job completion.

    Example:
        >>> client = RunPodClient()
        >>> payload = {"input": {"text": "Hello world"}}
        >>> output, details = await client.run_job(payload)
        >>> print(output)
        {"translated_text": "Mwasalamu dunia"}
    """

    def __init__(
        self,
        endpoint_id: Optional[str] = None,
        api_key: Optional[str] = None,
        default_timeout: int = 600,
    ) -> None:
        """Initialize the RunPod client.

        Args:
            endpoint_id: RunPod endpoint ID. Defaults to RUNPOD_ENDPOINT_ID env var.
            api_key: RunPod API key. Defaults to RUNPOD_API_KEY env var.
            default_timeout: Default timeout in seconds for job completion.

        Example:
            >>> # Use environment variables
            >>> client = RunPodClient()

            >>> # Use custom configuration
            >>> client = RunPodClient(
            ...     endpoint_id="my-endpoint-id",
            ...     api_key="my-api-key",
            ...     default_timeout=300
            ... )
        """
        self.endpoint_id = endpoint_id or os.getenv("RUNPOD_ENDPOINT_ID")
        self.api_key = api_key or os.getenv("RUNPOD_API_KEY")
        self.default_timeout = default_timeout

        if not self.endpoint_id:
            logger.warning("RUNPOD_ENDPOINT_ID not set - RunPod calls will fail")
        if not self.api_key:
            logger.warning("RUNPOD_API_KEY not set - RunPod calls will fail")

    def _get_job_details_sync(self, endpoint_id: str, job_id: str) -> Dict[str, Any]:
        """Fetch job details from RunPod REST API synchronously.

        This is a fallback method to get detailed job information when
        the async SDK doesn't provide enough details.

        Args:
            endpoint_id: The RunPod endpoint ID.
            job_id: The job ID to fetch details for.

        Returns:
            Dictionary containing job details from the REST API.

        Example:
            >>> details = client._get_job_details_sync("ep-123", "job-456")
            >>> print(details["status"])
            "COMPLETED"
        """
        url = f"https://api.runpod.ai/v2/{endpoint_id}/status/{job_id}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            return resp.json()
        except Exception as e:
            logger.warning(f"Failed to fetch job details: {e}")
            return {"status": "UNKNOWN", "error": str(e)}

    async def run_job(
        self,
        payload: Dict[str, Any],
        timeout: Optional[int] = None,
    ) -> Tuple[Any, Dict[str, Any]]:
        """Run a job on RunPod and wait for the output.

        Submits a job to the RunPod serverless endpoint and polls for
        completion. Handles timeout scenarios with extended polling.

        Args:
            payload: The input payload for the RunPod worker.
            timeout: Timeout in seconds. Defaults to self.default_timeout.

        Returns:
            A tuple of (output, job_details) where:
                - output: The worker's output data (dict or other type)
                - job_details: Metadata about the job from RunPod API

        Raises:
            ValueError: If endpoint_id is not configured.
            TimeoutError: If the job doesn't complete within the timeout.

        Example:
            >>> payload = {"input": {"audio_base64": "..."}}
            >>> output, details = await client.run_job(payload, timeout=300)
            >>> print(output.get("transcription"))
            "Hello world"
        """
        if not self.endpoint_id:
            raise ValueError("RUNPOD_ENDPOINT_ID is not configured")

        timeout = timeout or self.default_timeout

        async with http_client.AsyncClientSession() as session:
            logger.info("Starting RunPod job...")
            logger.debug(f"Payload keys: {list(payload.keys())}")

            endpoint = AsyncioEndpoint(self.endpoint_id, session)
            job: AsyncioJob = await endpoint.run(payload)

            # Fetch initial job details
            status = await job.status()
            logger.info(f"Initial job status: {status}")
            job_details = self._get_job_details_sync(job.endpoint_id, job.job_id)
            logger.debug(f"Job details: {job_details}")

            try:
                # Wait for job output with timeout
                out = await job.output(timeout=timeout)
                job_details = self._get_job_details_sync(job.endpoint_id, job.job_id)
                logger.info("Job completed successfully")
                return out, job_details

            except TimeoutError:
                logger.warning(f"Job timed out after {timeout}s, polling for status...")
                return await self._handle_timeout(job, job_details)

    async def _handle_timeout(
        self,
        job: AsyncioJob,
        initial_details: Dict[str, Any],
    ) -> Tuple[Any, Dict[str, Any]]:
        """Handle job timeout with extended polling.

        When a job times out, this method performs additional polling
        to check if the job completes shortly after the timeout.

        Args:
            job: The AsyncioJob instance.
            initial_details: Initial job details from before timeout.

        Returns:
            A tuple of (output, job_details).
        """
        poll_attempts = 6
        poll_interval = 5

        for attempt in range(poll_attempts):
            await asyncio.sleep(poll_interval)

            status = await job.status()
            logger.info(f"Poll attempt {attempt + 1}/{poll_attempts}: status={status}")

            job_details = self._get_job_details_sync(job.endpoint_id, job.job_id)

            if isinstance(status, dict) and status.get("status") in (
                "COMPLETED",
                "FAILED",
            ):
                try:
                    out = await job.output(timeout=30)
                    logger.info("Job completed after extended polling")
                    return out, job_details
                except TimeoutError:
                    continue

        # Last resort: cancel the job
        logger.warning("Job did not complete after polling, cancelling...")
        job.cancel()
        status = await job.status()
        job_details = self._get_job_details_sync(job.endpoint_id, job.job_id)
        logger.info(f"Job cancelled, final status: {status}")

        return {"status": status}, job_details


def normalize_runpod_response(resp: Any) -> Dict[str, Any]:
    """Normalize a RunPod response into a consistent shape.

    RunPod responses can vary in structure. This function normalizes
    them into a consistent dictionary format with standard fields.

    Args:
        resp: The raw response from RunPod (can be dict, string, or other).

    Returns:
        A dictionary with the following structure:
        {
            "delayTime": float or None,
            "executionTime": float or None,
            "id": str or None,
            "output": Any (the actual worker output),
            "status": str or None,
            "workerId": str or None
        }

    Example:
        >>> # Non-dict input gets wrapped
        >>> normalize_runpod_response("plain text")
        {"output": "plain text", "status": None, ...}

        >>> # Dict with output field is normalized
        >>> normalize_runpod_response({"output": {"text": "hello"}})
        {"output": {"text": "hello"}, "status": "COMPLETED", ...}

        >>> # Full response passes through
        >>> normalize_runpod_response({"id": "123", "status": "COMPLETED", ...})
        {"id": "123", "status": "COMPLETED", ...}
    """
    # Non-dict responses get wrapped
    if not isinstance(resp, dict):
        return {
            "delayTime": None,
            "executionTime": None,
            "id": None,
            "output": resp,
            "status": None,
            "workerId": None,
        }

    # Check if already in full response format
    top_keys = {"delayTime", "executionTime", "id", "status", "workerId"}
    if top_keys & set(resp.keys()):
        return resp

    # Normalize partial responses
    output = resp.get("output", resp)
    return {
        "delayTime": resp.get("delayTime"),
        "executionTime": resp.get("executionTime"),
        "id": resp.get("id"),
        "output": output,
        "status": resp.get("status") or ("COMPLETED" if output else None),
        "workerId": resp.get("workerId"),
    }


# -----------------------------------------------------------------------------
# Singleton and Dependency Injection
# -----------------------------------------------------------------------------

_runpod_client: Optional[RunPodClient] = None


def get_runpod_client() -> RunPodClient:
    """Get or create the RunPod client singleton.

    Returns:
        RunPodClient instance configured with environment settings.

    Example:
        >>> client = get_runpod_client()
        >>> output, details = await client.run_job(payload)
    """
    global _runpod_client
    if _runpod_client is None:
        _runpod_client = RunPodClient()
    return _runpod_client


def reset_runpod_client() -> None:
    """Reset the RunPod client singleton.

    Primarily used for testing to ensure a fresh instance.
    """
    global _runpod_client
    _runpod_client = None


# -----------------------------------------------------------------------------
# Backward Compatibility
# -----------------------------------------------------------------------------


async def run_job_and_get_output(
    payload: Dict[str, Any],
    timeout: int = 600,
) -> Tuple[Any, Dict[str, Any]]:
    """Run a RunPod job and get output (backward-compatible function).

    This function provides backward compatibility with the old
    runpod_helpers.py module. New code should use RunPodClient directly.

    Args:
        payload: The input payload for the RunPod worker.
        timeout: Timeout in seconds for job completion.

    Returns:
        A tuple of (output, job_details).

    Example:
        >>> output, details = await run_job_and_get_output(payload)
    """
    client = get_runpod_client()
    return await client.run_job(payload, timeout=timeout)


__all__ = [
    "RunPodClient",
    "get_runpod_client",
    "reset_runpod_client",
    "normalize_runpod_response",
    "run_job_and_get_output",
]
