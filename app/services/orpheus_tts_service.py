"""
Orpheus TTS Service.

Orchestrates the gateway flow for the Modal-deployed Orpheus-3B inference app:

    Router -> OrpheusTTSService -> OrpheusModalClient (httpx -> Modal vLLM)
                                -> GCPStorageService (WAV upload + signed URL)
                                -> SpeakersCache (TTL-cached catalog)

Owns:
    - A TTL-cached speaker catalog (warmed at app startup).
    - Up-front validation of speaker_id (and optional language) so bad input
      fails fast at the gateway with a 400 instead of consuming GPU time.
    - GCS upload + v4 signed URL generation under the configured object
      prefix (orpheus_tts/<YYYY-MM-DD>/<uuid>.wav).

Errors:
    Validation errors raise ``BadRequestError``. Modal errors propagate as
    ``ExternalServiceError`` / ``ServiceUnavailableError`` from
    ``OrpheusModalClient``. Storage errors raise ``ExternalServiceError``
    with ``service_name="GCS"``.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from app.core.config import settings
from app.core.exceptions import BadRequestError, ExternalServiceError
from app.integrations.orpheus_modal import (
    OrpheusModalClient,
    TTSAudio,
    get_orpheus_modal_client,
)
from app.utils.storage import GCPStorageService

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Speaker catalog
# -----------------------------------------------------------------------------


@dataclass
class SpeakerCatalog:
    default: str
    by_language: dict[str, list[str]]
    speaker_to_language: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: dict) -> "SpeakerCatalog":
        by_lang = payload.get("by_language", {}) or {}
        s2l: dict[str, str] = {}
        for lang, speakers in by_lang.items():
            for sp in speakers:
                s2l[sp] = lang
        return cls(
            default=payload.get("default", ""),
            by_language=by_lang,
            speaker_to_language=s2l,
        )


class SpeakersCache:
    """TTL-cached speaker catalog with fail-open validation.

    The cache is fetched lazily on first call and refreshed when older than
    ``ttl_seconds``. If the upstream fetch fails, the cache stays unwarmed and
    ``validate_speaker`` falls open (requests proceed; unknown-speaker errors
    surface from Modal as 502).
    """

    def __init__(self, modal: OrpheusModalClient, ttl_seconds: int) -> None:
        self.modal = modal
        self.ttl = ttl_seconds
        self._catalog: Optional[SpeakerCatalog] = None
        self._loaded_at: float = 0.0
        self._lock = asyncio.Lock()

    @property
    def is_warm(self) -> bool:
        return self._catalog is not None

    async def try_warm(self) -> None:
        """Attempt initial load. Never raises — failure leaves cache cold."""
        try:
            await self._refresh()
        except Exception as exc:  # noqa: BLE001
            logger.warning("orpheus_speakers_cache_warm_failed: %s", exc)

    async def get(self) -> SpeakerCatalog:
        if self._catalog is None or (time.monotonic() - self._loaded_at) > self.ttl:
            await self._refresh()
        assert self._catalog is not None  # _refresh raises on failure
        return self._catalog

    async def _refresh(self) -> None:
        async with self._lock:
            if (
                self._catalog is not None
                and (time.monotonic() - self._loaded_at) <= self.ttl
            ):
                return
            payload = await self.modal.speakers()
            self._catalog = SpeakerCatalog.from_payload(payload)
            self._loaded_at = time.monotonic()

    async def language_for(self, speaker_id: str) -> Optional[str]:
        """Reverse lookup: speaker_id -> language. Never raises.

        Reads the cached catalog directly without triggering a refresh.
        Returns None if the cache is cold or the speaker is unknown — used in
        success paths after synthesis has already completed, so a transient
        Modal blip must not fail the response.
        """
        if self._catalog is None:
            return None
        return self._catalog.speaker_to_language.get(speaker_id)

    async def validate_speaker(
        self, speaker_id: str, *, language: Optional[str]
    ) -> None:
        """Raise ``BadRequestError`` if invalid. Falls open if cache cold."""
        if not self.is_warm:
            return  # fail-open
        cat = await self.get()
        if speaker_id not in cat.speaker_to_language:
            raise BadRequestError(
                message=f"speaker_id '{speaker_id}' not found; see /speakers",
                details=[{"error_code": "invalid_speaker"}],
            )
        if language is not None:
            if language not in cat.by_language:
                raise BadRequestError(
                    message=(
                        f"language '{language}' not supported; "
                        f"supported: {sorted(cat.by_language)}"
                    ),
                    details=[{"error_code": "unknown_language"}],
                )
            actual = cat.speaker_to_language[speaker_id]
            if actual != language:
                raise BadRequestError(
                    message=(
                        f"speaker '{speaker_id}' is for language '{actual}', "
                        f"not '{language}'; see /speakers/{language}"
                    ),
                    details=[{"error_code": "invalid_speaker_for_language"}],
                )


# -----------------------------------------------------------------------------
# Result dataclasses (router converts these to Pydantic responses)
# -----------------------------------------------------------------------------


@dataclass
class UploadResult:
    gcs_object: str
    audio_url: str
    audio_url_expires_at: dt.datetime
    audio_size_bytes: int
    upload_ms: float
    signed_url_ms: float


@dataclass
class SynthesizeResult:
    audio_url: str
    audio_url_expires_at: dt.datetime
    speaker_id: str
    language: Optional[str]
    sample_rate: int
    duration_seconds: float
    chunks: Optional[int]
    audio_size_bytes: int
    gcs_object: str
    inference_ms: float
    upload_ms: float
    signed_url_ms: float
    total_ms: float


@dataclass
class BatchItemResult:
    index: int
    status: str  # "ok" | "error"
    speaker_id: str
    # success
    audio_url: Optional[str] = None
    audio_url_expires_at: Optional[dt.datetime] = None
    language: Optional[str] = None
    sample_rate: int = 24000
    duration_seconds: Optional[float] = None
    audio_size_bytes: Optional[int] = None
    gcs_object: Optional[str] = None
    # error
    error_code: Optional[str] = None
    error_detail: Optional[str] = None


@dataclass
class BatchResult:
    results: list[BatchItemResult]
    inference_ms: float
    upload_ms: float
    total_ms: float


# -----------------------------------------------------------------------------
# Service
# -----------------------------------------------------------------------------


class OrpheusTTSService:
    """High-level gateway service for Orpheus-3B TTS."""

    EXTERNAL_SERVICE_NAME = "Orpheus TTS"

    def __init__(
        self,
        *,
        modal_client: Optional[OrpheusModalClient] = None,
        storage_service: Optional[GCPStorageService] = None,
        object_prefix: Optional[str] = None,
        signed_url_expiry_minutes: Optional[int] = None,
        speakers_cache_ttl_seconds: Optional[int] = None,
        max_batch_size: Optional[int] = None,
    ) -> None:
        self.modal = modal_client or get_orpheus_modal_client()
        # Orpheus audio lands in the AUDIO_CONTENT_BUCKET_NAME alongside other
        # gateway-managed audio assets. Fall back to settings.gcp_bucket_name
        # if the env var is unset so local dev doesn't fail.
        bucket = os.getenv("AUDIO_CONTENT_BUCKET_NAME") or settings.gcp_bucket_name
        self.storage = storage_service or GCPStorageService(bucket_name=bucket)
        self.object_prefix = (
            object_prefix or settings.orpheus_gcs_object_prefix
        ).strip("/")
        self.signed_url_expiry_minutes = (
            signed_url_expiry_minutes
            if signed_url_expiry_minutes is not None
            else settings.orpheus_signed_url_expiry_minutes
        )
        self.max_batch_size = (
            max_batch_size
            if max_batch_size is not None
            else settings.orpheus_max_batch_size
        )
        self.speakers = SpeakersCache(
            modal=self.modal,
            ttl_seconds=(
                speakers_cache_ttl_seconds
                if speakers_cache_ttl_seconds is not None
                else settings.orpheus_speakers_cache_ttl_seconds
            ),
        )

    # ---- speaker catalog ----

    async def warm_speakers_cache(self) -> None:
        """Best-effort startup warm-up. Never raises."""
        if not self.modal.is_configured:
            logger.info("orpheus_modal_url_not_configured — skipping speakers warm-up")
            return
        await self.speakers.try_warm()
        logger.info(
            "orpheus_speakers_warm=%s",
            self.speakers.is_warm,
        )

    async def list_speakers(self) -> SpeakerCatalog:
        return await self.speakers.get()

    async def speakers_for_language(self, language: str) -> list[str]:
        cat = await self.speakers.get()
        if language not in cat.by_language:
            raise BadRequestError(
                message=(
                    f"language '{language}' not supported; "
                    f"supported: {sorted(cat.by_language)}"
                ),
                details=[{"error_code": "unknown_language"}],
            )
        return cat.by_language[language]

    # ---- single synthesis ----

    async def synthesize(
        self,
        *,
        text: str,
        speaker_id: str,
        language: Optional[str] = None,
        seed: Optional[int] = None,
        temperature: float = 0.6,
        top_p: float = 0.95,
        repetition_penalty: float = 1.1,
        max_tokens: int = 1200,
    ) -> SynthesizeResult:
        await self.speakers.validate_speaker(speaker_id, language=language)

        t_total = time.monotonic()
        t_inf = time.monotonic()
        audio = await self.modal.tts(
            text=text,
            speaker_id=speaker_id,
            seed=seed,
            temperature=temperature,
            top_p=top_p,
            repetition_penalty=repetition_penalty,
            max_tokens=max_tokens,
        )
        inference_ms = (time.monotonic() - t_inf) * 1000.0

        upload = await self._upload_and_sign(audio.audio_bytes)
        total_ms = (time.monotonic() - t_total) * 1000.0
        resolved_language = await self.speakers.language_for(speaker_id)

        return SynthesizeResult(
            audio_url=upload.audio_url,
            audio_url_expires_at=upload.audio_url_expires_at,
            speaker_id=speaker_id,
            language=resolved_language,
            sample_rate=audio.sample_rate,
            duration_seconds=audio.duration_seconds,
            chunks=audio.chunks,
            audio_size_bytes=upload.audio_size_bytes,
            gcs_object=upload.gcs_object,
            inference_ms=inference_ms,
            upload_ms=upload.upload_ms,
            signed_url_ms=upload.signed_url_ms,
            total_ms=total_ms,
        )

    # ---- batch synthesis ----

    async def synthesize_batch(
        self,
        items: list[dict],
    ) -> BatchResult:
        """Synthesize a batch. Items are dicts matching ``OrpheusTTSRequest``.

        Pre-validates every item against the catalog (fail fast on first bad
        item) before sending to Modal so we don't pay GPU time for a request
        that will be rejected.
        """
        if len(items) > self.max_batch_size:
            raise BadRequestError(
                message=(
                    f"batch size {len(items)} exceeds max_batch_size "
                    f"{self.max_batch_size}"
                ),
                details=[{"error_code": "invalid_request"}],
            )

        for idx, item in enumerate(items):
            try:
                await self.speakers.validate_speaker(
                    item["speaker_id"], language=item.get("language")
                )
            except BadRequestError as exc:
                # Prefix the bad item's index so the client knows which one.
                exc.message = f"item index {idx}: {exc.message}"
                raise

        t_total = time.monotonic()
        t_inf = time.monotonic()
        audios = await self.modal.tts_batch(items)
        inference_ms = (time.monotonic() - t_inf) * 1000.0

        t_up = time.monotonic()
        uploads = await asyncio.gather(
            *[self._upload_and_sign(a.audio_bytes) for a in audios],
            return_exceptions=True,
        )
        upload_ms = (time.monotonic() - t_up) * 1000.0

        results: list[BatchItemResult] = []
        ok_count = 0
        for i, (item, audio, up) in enumerate(zip(items, audios, uploads)):
            if isinstance(up, Exception):
                results.append(
                    BatchItemResult(
                        index=i,
                        status="error",
                        speaker_id=item["speaker_id"],
                        error_code=getattr(up, "error_code", "storage_unavailable"),
                        error_detail=str(up),
                    )
                )
                continue
            ok_count += 1
            language = await self.speakers.language_for(item["speaker_id"])
            results.append(
                BatchItemResult(
                    index=i,
                    status="ok",
                    speaker_id=item["speaker_id"],
                    audio_url=up.audio_url,
                    audio_url_expires_at=up.audio_url_expires_at,
                    language=language,
                    sample_rate=audio.sample_rate,
                    duration_seconds=audio.duration_seconds,
                    audio_size_bytes=up.audio_size_bytes,
                    gcs_object=up.gcs_object,
                )
            )

        total_ms = (time.monotonic() - t_total) * 1000.0
        if ok_count == 0:
            raise ExternalServiceError(
                service_name="GCS",
                message=f"all {len(items)} batch items failed during upload",
            )

        return BatchResult(
            results=results,
            inference_ms=inference_ms,
            upload_ms=upload_ms,
            total_ms=total_ms,
        )

    # ---- internals ----

    def _object_name(self) -> str:
        date = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        return f"{self.object_prefix}/{date}/{uuid.uuid4().hex}.wav"

    async def _upload_and_sign(self, audio_bytes: bytes) -> UploadResult:
        name = self._object_name()
        t0 = time.monotonic()
        try:
            blob = await self.storage.upload_audio_async(
                audio_bytes, name, content_type="audio/wav"
            )
        except Exception as exc:  # noqa: BLE001
            raise ExternalServiceError(
                service_name="GCS",
                message="Orpheus audio upload failed",
                original_error=str(exc),
            ) from exc
        upload_ms = (time.monotonic() - t0) * 1000.0

        t1 = time.monotonic()
        try:
            signed_url, expires_at = self.storage.generate_signed_url(
                blob, expiry_minutes=self.signed_url_expiry_minutes
            )
        except Exception as exc:  # noqa: BLE001
            raise ExternalServiceError(
                service_name="GCS",
                message="Orpheus signed URL generation failed",
                original_error=str(exc),
            ) from exc
        signed_url_ms = (time.monotonic() - t1) * 1000.0

        return UploadResult(
            gcs_object=name,
            audio_url=signed_url,
            audio_url_expires_at=expires_at,
            audio_size_bytes=len(audio_bytes),
            upload_ms=upload_ms,
            signed_url_ms=signed_url_ms,
        )


# -----------------------------------------------------------------------------
# Dependency Injection
# -----------------------------------------------------------------------------

_orpheus_tts_service: Optional[OrpheusTTSService] = None


def get_orpheus_tts_service() -> OrpheusTTSService:
    """Return the process-wide OrpheusTTSService singleton."""
    global _orpheus_tts_service
    if _orpheus_tts_service is None:
        _orpheus_tts_service = OrpheusTTSService()
    return _orpheus_tts_service


def reset_orpheus_tts_service() -> None:
    """Reset the singleton (for tests)."""
    global _orpheus_tts_service
    _orpheus_tts_service = None


__all__ = [
    "BatchItemResult",
    "BatchResult",
    "OrpheusTTSService",
    "SpeakerCatalog",
    "SpeakersCache",
    "SynthesizeResult",
    "TTSAudio",
    "UploadResult",
    "get_orpheus_tts_service",
    "reset_orpheus_tts_service",
]
