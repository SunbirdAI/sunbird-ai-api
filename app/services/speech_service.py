"""SpeechService facade for the unified /tasks/audio/speech endpoint.

Validates a SpeechRequest, routes by (model, platform) to the existing TTS
services, and normalizes each provider's result into a SpeechResult. No
synthesis logic lives here — it composes TTSService (Modal spark),
RunpodSparkTTSService (RunPod spark), and OrpheusTTSService.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional, Union

from app.core.exceptions import BadRequestError, ExternalServiceError
from app.models.enums import SpeakerID, TTSResponseMode, get_all_speakers
from app.schemas.orpheus_tts import (
    OrpheusLanguageSpeakersResponse,
    OrpheusSpeakersResponse,
)
from app.schemas.speech import SpeechBatchRequest, SpeechRequest
from app.schemas.tts import SpeakerInfo, SpeakersListResponse
from app.services.orpheus_tts_service import (
    BatchResult,
    OrpheusTTSService,
    get_orpheus_tts_service,
)
from app.services.runpod_tts_service import (
    RunpodSparkTTSService,
    get_runpod_spark_tts_service,
)
from app.services.tts_service import TTSService, get_tts_service
from app.utils.storage import GCPStorageService
from app.utils.storage import get_storage_service as get_legacy_storage_service

logger = logging.getLogger(__name__)

DEFAULT_ORPHEUS_VOICE = "salt_lug_0001"
RUNPOD_DEFAULT_TEMPERATURE = 0.7
RUNPOD_DEFAULT_MAX_NEW_AUDIO_TOKENS = 2000
ORPHEUS_MAX_TEXT = 2000
SPARK_MAX_TEXT = 10000


@dataclass
class SpeechResult:
    """Normalized synthesis result across providers (url mode)."""

    audio_url: str
    model: str
    platform: str
    voice: str
    audio_url_expires_at: Optional[datetime] = None
    language: Optional[str] = None
    sample_rate: Optional[int] = None
    duration_seconds: Optional[float] = None
    gcs_object: Optional[str] = None
    timings_ms: Optional[Dict[str, Any]] = None


class SpeechService:
    """Validates and dispatches unified TTS requests."""

    def __init__(
        self,
        tts_service: Optional[TTSService] = None,
        orpheus_service: Optional[OrpheusTTSService] = None,
        runpod_spark_service: Optional[RunpodSparkTTSService] = None,
        storage_service: Optional[GCPStorageService] = None,
    ) -> None:
        self._spark_modal = tts_service or get_tts_service()
        self._orpheus = orpheus_service or get_orpheus_tts_service()
        self._runpod_spark = runpod_spark_service or get_runpod_spark_tts_service()
        self._storage = storage_service or get_legacy_storage_service()

    @staticmethod
    def resolve_spark_speaker(voice: Optional[str]) -> SpeakerID:
        """Resolve a spark-tts voice (name or int) to a SpeakerID (400 if unknown)."""
        if voice is None:
            return SpeakerID.LUGANDA_FEMALE
        v = str(voice).strip()
        if v.isdigit():
            try:
                return SpeakerID(int(v))
            except ValueError:
                raise BadRequestError(message=f"Unknown spark-tts voice id '{voice}'.")
        try:
            return SpeakerID[v.upper()]
        except KeyError:
            raise BadRequestError(
                message=f"Unknown spark-tts voice '{voice}'. Use a SpeakerID name or id."
            )

    def validate_request(self, req: SpeechRequest) -> None:
        """Validate model/platform/param/voice/text combinations (400 on error)."""
        model = req.model.value
        platform = req.platform.value

        if model == "orpheus-3b-tts" and platform == "runpod":
            raise BadRequestError(
                message="orpheus-3b-tts is only available on platform='modal'."
            )

        if req.response_mode in (TTSResponseMode.STREAM, TTSResponseMode.BOTH) and not (
            model == "spark-tts" and platform == "modal"
        ):
            raise BadRequestError(
                message="response_mode 'stream'/'both' is only supported for "
                "model='spark-tts' on platform='modal'."
            )

        if model != "orpheus-3b-tts":
            for name, val in (
                ("language", req.language),
                ("top_p", req.top_p),
                ("repetition_penalty", req.repetition_penalty),
                ("max_tokens", req.max_tokens),
                ("seed", req.seed),
            ):
                if val is not None:
                    raise BadRequestError(
                        message=f"'{name}' is only valid for model='orpheus-3b-tts'."
                    )

        if req.max_new_audio_tokens is not None and not (
            model == "spark-tts" and platform == "runpod"
        ):
            raise BadRequestError(
                message="'max_new_audio_tokens' is only valid for model='spark-tts' "
                "on platform='runpod'."
            )

        if req.temperature is not None and model == "spark-tts" and platform == "modal":
            raise BadRequestError(
                message="'temperature' is not supported for model='spark-tts' on "
                "platform='modal'."
            )

        max_len = ORPHEUS_MAX_TEXT if model == "orpheus-3b-tts" else SPARK_MAX_TEXT
        if len(req.text) > max_len:
            raise BadRequestError(
                message=f"`text` is too long for {model} (max {max_len} characters)."
            )

        # Orpheus voice tags are validated against the live catalog inside
        # OrpheusTTSService.synthesize (it raises BadRequestError there); only
        # spark voices are resolved synchronously here.
        if model == "spark-tts":
            self.resolve_spark_speaker(req.voice)

    async def synthesize(self, req: SpeechRequest) -> SpeechResult:
        """Dispatch a url-mode synthesis request and normalize the result.

        Callers must have already run ``validate_request``.
        """
        model = req.model.value
        platform = req.platform.value

        if model == "orpheus-3b-tts":
            kwargs: Dict[str, Any] = {
                "text": req.text,
                "speaker_id": req.voice or DEFAULT_ORPHEUS_VOICE,
            }
            for name, val in (
                ("language", req.language),
                ("seed", req.seed),
                ("temperature", req.temperature),
                ("top_p", req.top_p),
                ("repetition_penalty", req.repetition_penalty),
                ("max_tokens", req.max_tokens),
            ):
                if val is not None:
                    kwargs[name] = val
            r = await self._orpheus.synthesize(**kwargs)
            return SpeechResult(
                audio_url=r.audio_url,
                audio_url_expires_at=r.audio_url_expires_at,
                model=model,
                platform=platform,
                voice=r.speaker_id,
                language=r.language,
                sample_rate=r.sample_rate,
                duration_seconds=r.duration_seconds,
                gcs_object=r.gcs_object,
                timings_ms={
                    "inference_ms": r.inference_ms,
                    "upload_ms": r.upload_ms,
                    "signed_url_ms": r.signed_url_ms,
                    "total_ms": r.total_ms,
                },
            )

        speaker = self.resolve_spark_speaker(req.voice)
        if platform == "modal":
            audio = await self._spark_modal.generate_audio(
                text=req.text, speaker_id=speaker
            )
            file_name = self._storage.generate_file_name(req.text, speaker)
            blob = await self._storage.upload_audio_async(audio, file_name)
            signed_url, expires_at = self._storage.generate_signed_url(blob)
            return SpeechResult(
                audio_url=signed_url,
                audio_url_expires_at=expires_at,
                model=model,
                platform=platform,
                voice=speaker.name.lower(),
                duration_seconds=round(
                    self._spark_modal.estimate_duration(req.text), 2
                ),
                gcs_object=file_name,
            )

        temperature = (
            RUNPOD_DEFAULT_TEMPERATURE if req.temperature is None else req.temperature
        )
        max_new = (
            RUNPOD_DEFAULT_MAX_NEW_AUDIO_TOKENS
            if req.max_new_audio_tokens is None
            else req.max_new_audio_tokens
        )
        output = await self._runpod_spark.synthesize(
            text=req.text,
            speaker_id=speaker.value,
            temperature=temperature,
            max_new_audio_tokens=max_new,
        )
        out = (
            output.get("output")
            if isinstance(output, dict) and "output" in output
            else output
        )
        out = out if isinstance(out, dict) else {}
        audio_url = out.get("audio_url") or out.get("url")
        if not audio_url:
            raise ExternalServiceError(
                service_name="RunPod TTS Worker",
                message="TTS worker did not return an audio URL",
            )
        return SpeechResult(
            audio_url=audio_url,
            model=model,
            platform=platform,
            voice=speaker.name.lower(),
            sample_rate=out.get("sample_rate"),
            gcs_object=out.get("blob"),
        )

    async def synthesize_batch(self, req: SpeechBatchRequest) -> BatchResult:
        """Validate + dispatch a batch (orpheus-3b-tts only).

        Maps unified ``voice`` to the orpheus ``speaker_id`` and forwards tuning
        fields verbatim (the upstream worker applies defaults for unset keys).
        Returns the OrpheusTTSService BatchResult; the router maps it to the
        unified SpeechBatchResponse.

        Raises BadRequestError (400) for a non-orpheus model or an over-length
        item; the underlying service raises BadRequestError (400) for a bad item
        and ExternalServiceError (502) when every item fails.
        """
        if req.model.value != "orpheus-3b-tts":
            raise BadRequestError(
                message="batch synthesis is only supported for "
                "model='orpheus-3b-tts'."
            )
        for i, item in enumerate(req.items):
            if len(item.text) > ORPHEUS_MAX_TEXT:
                raise BadRequestError(
                    message=f"item index {i}: `text` is too long "
                    f"(max {ORPHEUS_MAX_TEXT} characters)."
                )
        items_payload = [
            {
                "text": item.text,
                "speaker_id": item.voice or DEFAULT_ORPHEUS_VOICE,
                "language": item.language,
                "seed": item.seed,
                "temperature": item.temperature,
                "top_p": item.top_p,
                "repetition_penalty": item.repetition_penalty,
                "max_tokens": item.max_tokens,
            }
            for item in req.items
        ]
        return await self._orpheus.synthesize_batch(items_payload)

    async def list_voices(
        self, model: str, language: Optional[str] = None
    ) -> Union[
        OrpheusSpeakersResponse, OrpheusLanguageSpeakersResponse, SpeakersListResponse
    ]:
        """List speakers/voices for the given model.

        - spark-tts: all SpeakerID voices (``language`` is rejected with 400).
        - orpheus-3b-tts: the full catalog grouped by language, or — when
          ``language`` is given — the voices for that one language (400 if the
          language is unknown).
        """
        if model == "spark-tts":
            if language is not None:
                raise BadRequestError(
                    message="'language' is only valid for model='orpheus-3b-tts'."
                )
            return SpeakersListResponse(
                speakers=[SpeakerInfo(**d) for d in get_all_speakers()]
            )

        # orpheus-3b-tts
        if language is not None:
            speakers = await self._orpheus.speakers_for_language(language)
            return OrpheusLanguageSpeakersResponse(language=language, speakers=speakers)

        catalog = await self._orpheus.list_speakers()
        return OrpheusSpeakersResponse(
            default=catalog.default, by_language=catalog.by_language
        )


_speech_service: Optional[SpeechService] = None


def get_speech_service() -> SpeechService:
    """Return the SpeechService singleton."""
    global _speech_service
    if _speech_service is None:
        _speech_service = SpeechService()
    return _speech_service


def reset_speech_service() -> None:
    """Reset the singleton (test helper)."""
    global _speech_service
    _speech_service = None
