"""TranscriptionService facade for the unified STT endpoint.

Routes a transcription request to the correct underlying service based on the
selected platform and the organization flag, after validating that the
requested combination of inputs is supported. No transcription business logic
lives here — it composes the existing STTService and ModalSTTService.
"""

import logging
from typing import Optional, Tuple

from app.core.exceptions import BadRequestError
from app.services.modal_stt_service import ModalSTTService, get_modal_stt_service
from app.services.stt_service import STTService, TranscriptionResult, get_stt_service

logger = logging.getLogger(__name__)


class TranscriptionService:
    """Dispatches transcription requests across Modal and RunPod backends."""

    def __init__(
        self,
        stt_service: Optional[STTService] = None,
        modal_stt_service: Optional[ModalSTTService] = None,
    ) -> None:
        self._stt = stt_service or get_stt_service()
        self._modal = modal_stt_service or get_modal_stt_service()

    def validate_and_normalize(
        self,
        *,
        platform: str,
        has_audio: bool,
        gcs_blob_name: Optional[str],
        org: bool,
        whisper: Optional[bool],
        recognise_speakers: Optional[bool],
    ) -> Tuple[bool, bool]:
        """Validate the request combination and resolve RunPod defaults.

        Returns:
            (whisper, recognise_speakers) resolved for RunPod. For Modal the
            returned values are unused.

        Raises:
            BadRequestError: If the input combination is unsupported (HTTP 400).
        """
        if platform not in ("modal", "runpod"):
            raise BadRequestError(
                message=f"Unsupported platform '{platform}'. Use 'modal' or 'runpod'."
            )

        has_gcs = bool(gcs_blob_name)
        if has_audio and has_gcs:
            raise BadRequestError(
                message="Provide either 'audio' or 'gcs_blob_name', not both."
            )
        if not has_audio and not has_gcs:
            raise BadRequestError(
                message="One of 'audio' or 'gcs_blob_name' is required."
            )

        if platform == "modal":
            if has_gcs:
                raise BadRequestError(
                    message="GCS input is not supported on the 'modal' platform; "
                    "use platform='runpod'."
                )
            if org:
                raise BadRequestError(
                    message="The organization workflow (org=true) is only available "
                    "on the 'runpod' platform."
                )
            if whisper is not None or recognise_speakers is not None:
                raise BadRequestError(
                    message="'whisper' and 'recognise_speakers' are RunPod-only "
                    "options; omit them when platform='modal'."
                )
            return (False, False)

        # RunPod: default both flags to True when not explicitly provided.
        resolved_whisper = True if whisper is None else whisper
        resolved_speakers = True if recognise_speakers is None else recognise_speakers
        return (resolved_whisper, resolved_speakers)

    async def transcribe(
        self,
        *,
        platform: str,
        language: str,
        adapter: str,
        org: bool = False,
        whisper: bool = False,
        recognise_speakers: bool = False,
        file_path: Optional[str] = None,
        file_extension: Optional[str] = None,
        content_type: Optional[str] = None,
        audio_bytes: Optional[bytes] = None,
        gcs_blob_name: Optional[str] = None,
    ) -> TranscriptionResult:
        """Dispatch to the appropriate backend and return a TranscriptionResult.

        Callers must have already run ``validate_and_normalize``.
        """
        if platform == "modal":
            text = await self._modal.transcribe(audio_bytes, language=language)
            return TranscriptionResult(
                transcription=text,
                diarization_output={},
                formatted_diarization_output="",
            )

        # RunPod from GCS.
        if gcs_blob_name:
            return await self._stt.transcribe_from_gcs(
                gcs_blob_name=gcs_blob_name,
                language=language,
                adapter=adapter,
                whisper=whisper,
                recognise_speakers=recognise_speakers,
            )

        # RunPod from an uploaded file (org or standard). Validate type first,
        # preserving the legacy endpoints' behavior.
        self._stt.validate_audio_file(content_type, file_extension)

        if org:
            return await self._stt.transcribe_org_audio(
                file_path=file_path,
                recognise_speakers=recognise_speakers,
            )

        return await self._stt.transcribe_uploaded_file(
            file_path=file_path,
            file_extension=file_extension,
            language=language,
            adapter=adapter,
            whisper=whisper,
            recognise_speakers=recognise_speakers,
        )


_transcription_service_instance: Optional[TranscriptionService] = None


def get_transcription_service() -> TranscriptionService:
    """Return the TranscriptionService singleton."""
    global _transcription_service_instance
    if _transcription_service_instance is None:
        _transcription_service_instance = TranscriptionService()
    return _transcription_service_instance


def reset_transcription_service() -> None:
    """Reset the singleton (test helper)."""
    global _transcription_service_instance
    _transcription_service_instance = None
