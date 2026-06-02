"""
Orpheus-3B TTS Router.

Gateway endpoints in front of the Modal-deployed Orpheus-3B inference app:

    POST /tasks/modal/orpheus/tts              — single synthesis
    POST /tasks/modal/orpheus/tts/batch        — batched synthesis
    GET  /tasks/modal/orpheus/speakers         — full speaker catalog
    GET  /tasks/modal/orpheus/speakers/{lang}  — speakers for one language

All endpoints require Bearer-token authentication via ``CurrentUserDep`` and
share the per-account SlowAPI tier (admin 1000/min, premium 100/min,
default 50/min) on POST routes. Successful syntheses emit a best-effort
FEEDBACK_URL record via BackgroundTasks (``inference_type=tts_orpheus``).

Audio is uploaded to ``AUDIO_CONTENT_BUCKET_NAME`` under the
``orpheus_tts/<YYYY-MM-DD>/<uuid>.wav`` prefix and returned as a v4 signed
URL with the configured expiry (default 30 minutes).
"""

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import QuotaServiceDep, get_current_user, get_db, get_orpheus_tts_service
from app.schemas.orpheus_tts import (
    OrpheusBatchTimings,
    OrpheusLanguageSpeakersResponse,
    OrpheusSpeakersResponse,
    OrpheusTimings,
    OrpheusTTSBatchItemResult,
    OrpheusTTSBatchRequest,
    OrpheusTTSBatchResponse,
    OrpheusTTSRequest,
    OrpheusTTSResponse,
)
from app.utils.deprecation import SUCCESSOR_SPEECH, add_deprecation_headers
from app.utils.feedback import INFERENCE_TYPES, save_api_inference
from app.utils.quota_guard import check_quota
from app.utils.rate_limit import get_account_type_limit, limiter

logger = logging.getLogger(__name__)

router = APIRouter()


# ----- Speakers -----


@router.get(
    "/speakers",
    response_model=OrpheusSpeakersResponse,
    summary="List Orpheus speakers grouped by language",
    description=(
        "Returns the full Orpheus speaker catalog. `total` and `languages` are "
        "derived convenience fields. Auth required."
    ),
)
async def get_speakers(
    service=Depends(get_orpheus_tts_service),
    current_user=Depends(get_current_user),
) -> OrpheusSpeakersResponse:
    catalog = await service.list_speakers()
    return OrpheusSpeakersResponse(
        default=catalog.default, by_language=catalog.by_language
    )


@router.get(
    "/speakers/{language}",
    response_model=OrpheusLanguageSpeakersResponse,
    summary="List Orpheus speakers for one language",
    description=(
        "Convenience endpoint for two-step pickers (language then speaker). "
        "Returns 400 invalid_request if the language code is not in the catalog."
    ),
)
async def get_speakers_for_language(
    language: str,
    service=Depends(get_orpheus_tts_service),
    current_user=Depends(get_current_user),
) -> OrpheusLanguageSpeakersResponse:
    speakers = await service.speakers_for_language(language)
    return OrpheusLanguageSpeakersResponse(language=language, speakers=speakers)


# ----- TTS -----


@router.post(
    "/tts",
    response_model=OrpheusTTSResponse,
    summary="Synthesize speech for one input via Orpheus-3B",
    description=(
        "Calls the Orpheus-3B Modal vLLM inference app, uploads the generated "
        "WAV to Google Cloud Storage, and returns a v4 presigned download URL "
        "valid for the configured expiry window (default 30 minutes), together "
        "with metadata and stage-by-stage latency timings."
    ),
    deprecated=True,
)
@limiter.limit(get_account_type_limit)
async def synthesize_tts(
    request: Request,
    body: OrpheusTTSRequest,
    quota: QuotaServiceDep,
    background_tasks: BackgroundTasks,
    http_response: Response,
    db: AsyncSession = Depends(get_db),
    service=Depends(get_orpheus_tts_service),
    current_user=Depends(get_current_user),
) -> OrpheusTTSResponse:
    await check_quota(quota, db, current_user)
    logger.warning(
        "Deprecated endpoint /tasks/modal/orpheus/tts called; use POST /tasks/audio/speech"
    )
    add_deprecation_headers(http_response, SUCCESSOR_SPEECH)
    result = await service.synthesize(
        text=body.text,
        speaker_id=body.speaker_id,
        language=body.language,
        seed=body.seed,
        temperature=body.temperature,
        top_p=body.top_p,
        repetition_penalty=body.repetition_penalty,
        max_tokens=body.max_tokens,
    )
    request_id = uuid.uuid4().hex

    response = OrpheusTTSResponse(
        audio_url=result.audio_url,
        audio_url_expires_at=result.audio_url_expires_at,
        speaker_id=result.speaker_id,
        language=result.language,
        sample_rate=result.sample_rate,
        duration_seconds=result.duration_seconds,
        chunks=result.chunks,
        audio_size_bytes=result.audio_size_bytes,
        gcs_object=result.gcs_object,
        request_id=request_id,
        timings_ms=OrpheusTimings(
            inference_ms=result.inference_ms,
            upload_ms=result.upload_ms,
            signed_url_ms=result.signed_url_ms,
            total_ms=result.total_ms,
        ),
    )

    _schedule_feedback(
        background_tasks=background_tasks,
        user=current_user,
        text=body.text,
        speaker_id=body.speaker_id,
        gcs_object=result.gcs_object,
        audio_url=result.audio_url,
        processing_time=result.total_ms / 1000.0,
        request_id=request_id,
        language=result.language,
    )

    return response


@router.post(
    "/tts/batch",
    response_model=OrpheusTTSBatchResponse,
    summary="Batch-synthesize speech via Orpheus-3B",
    description=(
        "Calls Modal's batched inference endpoint (a single vLLM "
        "continuous-batched pass) and uploads each generated WAV to GCS in "
        "parallel. Per-item failures are reported in the response with "
        '`status: "error"`; the request as a whole returns 200 if at least '
        "one item succeeds, 502 if every item failed."
    ),
)
@limiter.limit(get_account_type_limit)
async def synthesize_tts_batch(
    request: Request,
    body: OrpheusTTSBatchRequest,
    quota: QuotaServiceDep,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    service=Depends(get_orpheus_tts_service),
    current_user=Depends(get_current_user),
) -> OrpheusTTSBatchResponse:
    await check_quota(quota, db, current_user)
    items_payload = [
        {
            "text": it.text,
            "speaker_id": it.speaker_id,
            "language": it.language,
            "seed": it.seed,
            "temperature": it.temperature,
            "top_p": it.top_p,
            "repetition_penalty": it.repetition_penalty,
            "max_tokens": it.max_tokens,
        }
        for it in body.items
    ]
    batch = await service.synthesize_batch(items_payload)
    request_id = uuid.uuid4().hex

    results = [
        OrpheusTTSBatchItemResult(
            index=r.index,
            status=r.status,
            speaker_id=r.speaker_id,
            audio_url=r.audio_url,
            audio_url_expires_at=r.audio_url_expires_at,
            language=r.language,
            sample_rate=r.sample_rate,
            duration_seconds=r.duration_seconds,
            audio_size_bytes=r.audio_size_bytes,
            gcs_object=r.gcs_object,
            request_id=request_id if r.status == "ok" else None,
            error_code=r.error_code,
            error_detail=r.error_detail,
        )
        for r in batch.results
    ]

    response = OrpheusTTSBatchResponse(
        results=results,
        timings_ms=OrpheusBatchTimings(
            inference_ms=batch.inference_ms,
            upload_ms=batch.upload_ms,
            total_ms=batch.total_ms,
        ),
        request_id=request_id,
    )

    _schedule_batch_feedback(
        background_tasks=background_tasks,
        user=current_user,
        items=body.items,
        batch=batch,
        request_id=request_id,
    )

    return response


# ----- Helpers -----


def _schedule_feedback(
    *,
    background_tasks: BackgroundTasks,
    user,
    text: str,
    speaker_id: str,
    gcs_object: str,
    audio_url: str,
    processing_time: float,
    request_id: str,
    language,
) -> None:
    try:
        background_tasks.add_task(
            save_api_inference,
            text,
            {"audio_url": audio_url, "gcs_object": gcs_object},
            user,
            model_type=f"orpheus:{speaker_id}",
            processing_time=processing_time,
            inference_type=INFERENCE_TYPES["tts_orpheus"],
            job_details={
                "speaker_id": speaker_id,
                "blob": gcs_object,
                "audio_url": audio_url,
                "language": language,
                "request_id": request_id,
            },
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Failed to schedule Orpheus TTS feedback save task: {e}")


def _schedule_batch_feedback(
    *,
    background_tasks: BackgroundTasks,
    user,
    items,
    batch,
    request_id: str,
) -> None:
    """Emit one feedback record per successful batch item.

    Each item is logged separately so per-speaker / per-language analytics
    aggregate correctly downstream. Failures are not logged (the error path
    already returns the error_code/error_detail in the response).
    """
    try:
        for item, result in zip(items, batch.results):
            if result.status != "ok":
                continue
            background_tasks.add_task(
                save_api_inference,
                item.text,
                {"audio_url": result.audio_url, "gcs_object": result.gcs_object},
                user,
                model_type=f"orpheus:{item.speaker_id}",
                processing_time=batch.total_ms / 1000.0,
                inference_type=INFERENCE_TYPES["tts_orpheus"],
                job_details={
                    "speaker_id": item.speaker_id,
                    "blob": result.gcs_object,
                    "audio_url": result.audio_url,
                    "language": result.language,
                    "batch_index": result.index,
                    "request_id": request_id,
                },
            )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Failed to schedule Orpheus TTS batch feedback save task: {e}")
