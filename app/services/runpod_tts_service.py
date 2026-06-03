"""RunPod spark-tts service.

Extracts the inline RunPod TTS call (payload build + tenacity retry + error
mapping) out of the router so the unified SpeechService and the legacy
/tasks/runpod/tts endpoint share one implementation.
"""

import asyncio
import logging
import os
from typing import Optional

import runpod
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.exceptions import (
    BadRequestError,
    ExternalServiceError,
    ServiceUnavailableError,
)

logger = logging.getLogger(__name__)

runpod.api_key = os.getenv("RUNPOD_API_KEY")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=1, max=60),
    retry=retry_if_exception_type((TimeoutError, ConnectionError)),
    reraise=True,
)
async def _run_sync_with_retry(endpoint, data):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, lambda: endpoint.run_sync(data, timeout=600)
    )


class RunpodSparkTTSService:
    """Calls the RunPod spark-tts worker."""

    def __init__(self, endpoint_id: Optional[str] = None) -> None:
        self.endpoint_id = endpoint_id or os.getenv("RUNPOD_ENDPOINT_ID")

    async def synthesize(
        self,
        *,
        text: str,
        speaker_id: int,
        temperature: float,
        max_new_audio_tokens: int,
    ) -> dict:
        """Run RunPod spark-tts and return the raw worker output.

        Raises:
            ServiceUnavailableError, ExternalServiceError, BadRequestError.
        """
        data = {
            "input": {
                "task": "tts",
                "text": text.strip(),
                "speaker_id": speaker_id,
                "temperature": temperature,
                "max_new_audio_tokens": max_new_audio_tokens,
            }
        }
        endpoint = runpod.Endpoint(self.endpoint_id)
        try:
            return await _run_sync_with_retry(endpoint, data)
        except TimeoutError as e:
            logger.error(f"RunPod TTS timed out: {e}")
            raise ServiceUnavailableError(message="Service unavailable due to timeout")
        except ConnectionError as e:
            logger.error(f"RunPod TTS connection error: {e}")
            raise ExternalServiceError(
                service_name="RunPod TTS Service",
                message="Service unavailable due to connection error",
                original_error=str(e),
            )
        except ValueError as e:
            logger.error(f"RunPod TTS worker bad request: {e}")
            raise BadRequestError(message=f"Invalid request to TTS worker: {e}")
        except Exception as e:
            logger.exception("Unexpected error calling RunPod TTS worker")
            raise ExternalServiceError(
                service_name="RunPod TTS Worker",
                message="TTS worker error",
                original_error=str(e),
            )


_runpod_spark_tts_service: Optional[RunpodSparkTTSService] = None


def get_runpod_spark_tts_service() -> RunpodSparkTTSService:
    global _runpod_spark_tts_service
    if _runpod_spark_tts_service is None:
        _runpod_spark_tts_service = RunpodSparkTTSService()
    return _runpod_spark_tts_service


def reset_runpod_spark_tts_service() -> None:
    global _runpod_spark_tts_service
    _runpod_spark_tts_service = None
