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
from typing import Any, Dict, Optional

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

# Get feedback URL from environment
FEEDBACK_URL = os.getenv("FEEDBACK_URL")

# Inference type constants for classifying feedback events
INFERENCE_TYPES = {
    "chat": "chat",
    "tts": "tts",
    "sunflower_chat": "sunflower_chat",
    "sunflower_simple": "sunflower_simple",
}


async def save_api_inference(
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
        logging.debug("FEEDBACK_URL not configured; skipping inference feedback save")
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
        if inference_type == INFERENCE_TYPES["tts"]:
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

    logging.info(
        f"Saving inference feedback for user: {username_str}, type: {inference_type}"
    )
    logging.debug(f"Feedback payload (truncated): {json.dumps(payload)[:1000]}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=8),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
        reraise=True,
    )
    async def _post_feedback(p: Dict[str, Any]) -> bool:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                FEEDBACK_URL, json=p, headers={"Content-Type": "application/json"}
            ) as resp:
                text = await resp.text()
                if 200 <= resp.status < 300:
                    logging.info("Inference feedback saved successfully")
                    return True
                logging.warning(
                    f"Feedback save failed status={resp.status} body={text}"
                )
                return False

    try:
        return await _post_feedback(payload)
    except Exception as e:
        logging.error(f"Failed to save inference feedback after retries: {e}")
        return False
