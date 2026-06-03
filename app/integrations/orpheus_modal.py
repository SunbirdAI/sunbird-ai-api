"""
Orpheus Modal Integration Client.

Async httpx wrapper around the Modal-deployed Orpheus-3B inference app.
Exposes:
    - health()             — liveness probe on Modal /health
    - speakers()           — fetch the speaker catalog ({default, by_language})
    - tts(...)             — single-input synthesis returning raw WAV bytes
    - tts_batch([...])     — batched synthesis (vLLM continuous batching)

Owns the timeout and retry policy: one retry on ``httpx.ReadTimeout`` /
``httpx.HTTPError`` / 5xx with ``orpheus_modal_retry_backoff_seconds`` of
jittered backoff, then raises ``ExternalServiceError`` /
``ServiceUnavailableError`` so route handlers don't need upstream knowledge.

The httpx client is lazily constructed on first use and cached on the
singleton instance; teardown is best-effort via ``close()``.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import random
from dataclasses import dataclass
from typing import Optional

import httpx

from app.core.config import settings
from app.core.exceptions import ExternalServiceError, ServiceUnavailableError

logger = logging.getLogger(__name__)

_RETRY_STATUSES = {502, 503, 504}


@dataclass
class TTSAudio:
    audio_bytes: bytes
    sample_rate: int
    duration_seconds: float
    speaker_id: str
    chunks: Optional[int] = None


class OrpheusModalClient:
    """Async client for the Orpheus-3B Modal app.

    Lazy httpx client: the underlying ``httpx.AsyncClient`` is constructed on
    first awaited call so import-time does not require a configured Modal URL.
    Requests against a client with an unconfigured URL raise
    ``ServiceUnavailableError`` so the caller can return a clean 503.
    """

    EXTERNAL_SERVICE_NAME = "Orpheus Modal"

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        request_timeout: Optional[float] = None,
        connect_timeout: Optional[float] = None,
        retry_backoff_seconds: Optional[float] = None,
    ) -> None:
        self.base_url = (base_url or settings.orpheus_modal_url or "").rstrip("/")
        self.request_timeout = (
            request_timeout
            if request_timeout is not None
            else settings.orpheus_modal_request_timeout_seconds
        )
        self.connect_timeout = (
            connect_timeout
            if connect_timeout is not None
            else settings.orpheus_modal_connect_timeout_seconds
        )
        self.backoff = (
            retry_backoff_seconds
            if retry_backoff_seconds is not None
            else settings.orpheus_modal_retry_backoff_seconds
        )
        self._client: Optional[httpx.AsyncClient] = None
        self._client_lock = asyncio.Lock()

    # ---- public surface ----

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url)

    async def health(self) -> bool:
        """Returns True iff Modal /health responds with a 2xx. Never raises."""
        if not self.is_configured:
            return False
        try:
            client = await self._get_client()
            r = await client.get("/health", timeout=10.0)
        except httpx.HTTPError as exc:
            logger.warning("orpheus_modal_health_unreachable: %s", exc)
            return False
        return r.is_success

    async def speakers(self) -> dict:
        return await self._json_get("/speakers")

    async def tts(
        self,
        *,
        text: str,
        speaker_id: str,
        seed: Optional[int],
        temperature: float,
        top_p: float,
        repetition_penalty: float,
        max_tokens: int,
    ) -> TTSAudio:
        body = {
            "text": text,
            "speaker_id": speaker_id,
            "seed": seed,
            "temperature": temperature,
            "top_p": top_p,
            "repetition_penalty": repetition_penalty,
            "max_tokens": max_tokens,
        }
        resp = await self._post_with_retry("/tts", json=body)
        sr = int(resp.headers.get("X-Sample-Rate", "24000"))
        dur = float(resp.headers.get("X-Duration-Seconds", "0"))
        chunks_hdr = resp.headers.get("X-Chunks")
        try:
            chunks = int(chunks_hdr) if chunks_hdr is not None else None
        except ValueError:
            chunks = None
        return TTSAudio(
            audio_bytes=resp.content,
            sample_rate=sr,
            duration_seconds=dur,
            speaker_id=resp.headers.get("X-Speaker-Id", speaker_id),
            chunks=chunks,
        )

    async def tts_batch(self, items: list[dict]) -> list[TTSAudio]:
        body = {"items": items}
        resp = await self._post_with_retry("/tts/batch", json=body)
        try:
            data = resp.json()
        except ValueError as exc:
            raise ExternalServiceError(
                service_name=self.EXTERNAL_SERVICE_NAME,
                message="non-JSON response from /tts/batch",
                original_error=str(exc),
            ) from exc
        results: list[TTSAudio] = []
        for idx, r in enumerate(data.get("results", [])):
            try:
                wav = base64.b64decode(r["audio_wav_b64"], validate=True)
            except (KeyError, ValueError, binascii.Error) as exc:
                raise ExternalServiceError(
                    service_name=self.EXTERNAL_SERVICE_NAME,
                    message=f"malformed batch result at index {idx}",
                    original_error=str(exc),
                ) from exc
            results.append(
                TTSAudio(
                    audio_bytes=wav,
                    sample_rate=int(r.get("sample_rate", 24000)),
                    duration_seconds=float(r.get("duration_sec", 0.0)),
                    speaker_id=r.get("speaker_id", ""),
                )
            )
        return results

    async def close(self) -> None:
        """Best-effort shutdown of the underlying httpx client."""
        client, self._client = self._client, None
        if client is None:
            return
        try:
            await client.aclose()
        except Exception as exc:  # noqa: BLE001
            logger.warning("orpheus_modal_client_close_failed: %s", exc)

    # ---- internals ----

    async def _get_client(self) -> httpx.AsyncClient:
        if not self.is_configured:
            raise ServiceUnavailableError(
                message=(
                    "Orpheus Modal URL is not configured "
                    "(set ORPHEUS_MODAL_URL to enable)."
                )
            )
        if self._client is not None:
            return self._client
        async with self._client_lock:
            if self._client is None:
                timeout = httpx.Timeout(
                    connect=self.connect_timeout,
                    read=self.request_timeout,
                    write=10.0,
                    pool=10.0,
                )
                self._client = httpx.AsyncClient(
                    base_url=self.base_url,
                    timeout=timeout,
                    transport=httpx.AsyncHTTPTransport(retries=1),
                )
        return self._client

    async def _json_get(self, path: str) -> dict:
        resp = await self._with_retry(lambda c: c.get(path))
        return resp.json()

    async def _post_with_retry(self, path: str, *, json: dict) -> httpx.Response:
        return await self._with_retry(lambda c: c.post(path, json=json))

    async def _with_retry(self, op) -> httpx.Response:
        client = await self._get_client()
        for attempt in (1, 2):
            try:
                resp: httpx.Response = await op(client)
            except httpx.ReadTimeout as exc:
                if attempt == 1:
                    await self._sleep_backoff()
                    continue
                raise ServiceUnavailableError(
                    message=(
                        f"Orpheus Modal request timed out after {attempt} attempt(s)"
                    )
                ) from exc
            except httpx.HTTPError as exc:
                if attempt == 1:
                    await self._sleep_backoff()
                    continue
                raise ExternalServiceError(
                    service_name=self.EXTERNAL_SERVICE_NAME,
                    message="Orpheus Modal request failed",
                    original_error=str(exc),
                ) from exc

            if resp.status_code in _RETRY_STATUSES and attempt == 1:
                await self._sleep_backoff()
                continue
            if resp.is_success:
                return resp
            # 4xx from Modal — surfaces as a 502 to the caller (we already
            # validated speaker/language at the gateway).
            raise ExternalServiceError(
                service_name=self.EXTERNAL_SERVICE_NAME,
                message=f"Orpheus Modal returned {resp.status_code}",
                original_error=resp.text[:200],
            )

        # Defensive: loop above always returns or raises.
        raise AssertionError("unreachable")

    async def _sleep_backoff(self) -> None:
        if self.backoff <= 0:
            return
        await asyncio.sleep(self.backoff + random.uniform(0, self.backoff / 2))


# -----------------------------------------------------------------------------
# Dependency Injection
# -----------------------------------------------------------------------------

_orpheus_modal_client: Optional[OrpheusModalClient] = None


def get_orpheus_modal_client() -> OrpheusModalClient:
    """Return the process-wide OrpheusModalClient singleton."""
    global _orpheus_modal_client
    if _orpheus_modal_client is None:
        _orpheus_modal_client = OrpheusModalClient()
    return _orpheus_modal_client


def reset_orpheus_modal_client() -> None:
    """Reset the singleton (for tests)."""
    global _orpheus_modal_client
    _orpheus_modal_client = None
