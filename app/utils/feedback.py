"""
Feedback Utility Module.

This module provides utilities for saving inference feedback to external
services. It handles saving API inference records in a non-blocking manner
via background tasks.

Usage:
    from app.utils.feedback import save_api_inference, INFERENCE_TYPES

    # In a route handler
    background_tasks.add_task(
        save_api_inference,
        source_text="Hello",
        model_results="Hi there!",
        username=current_user,
        model_type="qwen",
        processing_time=1.5,
        inference_type=INFERENCE_TYPES["sunflower_chat"],
    )

Note:
    This module was extracted from app/routers/tasks.py as part of the
    inference router refactoring to allow sharing the feedback functionality
    across multiple routers.
"""

import asyncio
import datetime
import hashlib
import json
import logging
import os
import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import aiohttp
from dotenv import load_dotenv
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

load_dotenv()
logging.basicConfig(level=logging.INFO)

# Module-level logger so log lines are namespaced (`app.utils.feedback`) and
# easy to grep / filter independently of root.
logger = logging.getLogger(__name__)

# Get feedback URL from environment
FEEDBACK_URL = os.getenv("FEEDBACK_URL")


def _feedback_host() -> str:
    """Return the FEEDBACK_URL host for log lines (never the full URL)."""
    if not FEEDBACK_URL:
        return "<unset>"
    try:
        return urlparse(FEEDBACK_URL).netloc or FEEDBACK_URL
    except Exception:
        return FEEDBACK_URL


# Inference type constants for classifying feedback events
INFERENCE_TYPES = {
    "chat": "chat",
    "tts": "tts",
    "sunflower_chat": "sunflower_chat",
    "sunflower_simple": "sunflower_simple",
    "stt": "stt",
    "translation": "translation",
    "language_id": "language_id",
    "tts_modal": "tts",
    "tts_orpheus": "tts",
}


async def save_api_inference(  # noqa: C901
    source_text: Any,
    model_results: Any,
    username: Any,
    model_type: Optional[str] = None,
    processing_time: Optional[float] = None,
    inference_type: str = "chat",
    job_details: Optional[Dict[str, Any]] = None,
) -> bool:
    """Persist a compact, JSON-serializable inference record to the configured FEEDBACK_URL.

    This function is idempotent and non-blocking when scheduled via FastAPI
    BackgroundTasks.

    Inputs are deliberately permissive (Any) because callers pass strings,
    dicts or model objects. The function normalizes values to simple types.

    Args:
        source_text: The source text or input for the inference.
        model_results: The results from the model inference.
        username: The user who made the request (can be User object, dict, or string).
        model_type: The type of model used (e.g., 'qwen').
        processing_time: Total processing time in seconds.
        inference_type: Type of inference (from INFERENCE_TYPES).
        job_details: Additional job details to include.

    Returns:
        True on a successful POST (2xx), False otherwise.

    Example:
        >>> await save_api_inference(
        ...     source_text="Hello",
        ...     model_results="Hi there!",
        ...     username="user123",
        ...     model_type="qwen",
        ...     processing_time=1.5,
        ...     inference_type="sunflower_chat",
        ... )
        True
    """
    if not FEEDBACK_URL:
        logger.info(
            "[FEEDBACK] skipped — FEEDBACK_URL not configured (type=%s)",
            inference_type,
        )
        return False

    # Timestamp in milliseconds
    timestamp = int(datetime.datetime.utcnow().timestamp() * 1000)

    # Normalize username to a short string identifier when possible
    username_str = None
    try:
        if hasattr(username, "id"):
            username_str = str(getattr(username, "id"))
        elif isinstance(username, dict) and username.get("id"):
            username_str = str(username.get("id"))
        elif isinstance(username, str):
            username_str = username
        else:
            # fallback to email/username attributes if present
            username_str = (
                getattr(username, "username", None)
                or getattr(username, "email", None)
                or str(username)
            )
    except Exception:
        username_str = str(username)

    # Serialize inputs safely
    def _serialize(v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, (str, int, float, bool)):
            return v
        try:
            return json.loads(json.dumps(v, ensure_ascii=False))
        except Exception:
            return str(v)

    source_serialized = _serialize(source_text)
    results_serialized = _serialize(model_results)

    payload: Dict[str, Any] = {
        "Timestamp": timestamp,
        "feedback": "api_inference",
        "SourceText": source_serialized,
        "ModelResults": results_serialized,
        "username": username_str,
        "FeedBackType": inference_type,
    }

    if model_type:
        payload["ModelType"] = model_type
    if processing_time is not None:
        payload["ProcessingTime"] = processing_time

    # Compact job details to avoid leaking large blobs
    if job_details and isinstance(job_details, dict):
        jd: Dict[str, Any] = {}
        # Common safe fields
        for k in ("job_id", "model_type", "blob", "sample_rate", "speaker_id"):
            if k in job_details:
                jd[k] = job_details.get(k)

        # For TTS keep a short hash of the source text instead of raw text
        if inference_type in (
            INFERENCE_TYPES["tts"],
            INFERENCE_TYPES["tts_modal"],
            INFERENCE_TYPES["tts_orpheus"],
        ):
            try:
                text_val = (
                    source_serialized
                    if isinstance(source_serialized, str)
                    else json.dumps(source_serialized, ensure_ascii=False)
                )
                jd.setdefault(
                    "text_hash", hashlib.sha256(text_val.encode("utf-8")).hexdigest()
                )
            except Exception:
                pass

        if jd:
            payload["JobDetails"] = jd

    payload_bytes = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    host = _feedback_host()
    logger.info(
        "[FEEDBACK] → POST %s type=%s user=%s size=%dB",
        host,
        inference_type,
        username_str,
        payload_bytes,
    )
    logger.debug(
        "[FEEDBACK]   payload (truncated): %s",
        json.dumps(payload, ensure_ascii=False)[:1000],
    )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=8),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
        reraise=True,
    )
    async def _post_feedback(p: Dict[str, Any]) -> bool:
        timeout = aiohttp.ClientTimeout(total=10)
        t0 = time.monotonic()
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                FEEDBACK_URL, json=p, headers={"Content-Type": "application/json"}
            ) as resp:
                text = await resp.text()
                elapsed_ms = (time.monotonic() - t0) * 1000.0
                if 200 <= resp.status < 300:
                    logger.info(
                        "[FEEDBACK] ✓ saved in %.0fms type=%s user=%s status=%d",
                        elapsed_ms,
                        inference_type,
                        username_str,
                        resp.status,
                    )
                    return True
                logger.warning(
                    "[FEEDBACK] ✗ rejected status=%d in %.0fms type=%s user=%s body=%s",
                    resp.status,
                    elapsed_ms,
                    inference_type,
                    username_str,
                    text[:300],
                )
                return False

    try:
        return await _post_feedback(payload)
    except Exception as e:
        logger.error(
            "[FEEDBACK] ✗ post failed after retries type=%s user=%s: %s",
            inference_type,
            username_str,
            e,
        )
        return False
