# Unified Batch Speech + Stream/Batch Deprecation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a unified batch Text-to-Speech endpoint `POST /tasks/audio/speech/batch` (orpheus-3b-tts only) and deprecate three legacy endpoints (`/tasks/modal/tts/stream`, `/tasks/modal/tts/stream-with-url`, `/tasks/modal/orpheus/tts/batch`).

**Architecture:** New schemas in `app/schemas/speech.py` (unified `voice`-based naming) → new `SpeechService.synthesize_batch()` facade method that maps to and reuses the existing `OrpheusTTSService.synthesize_batch()` → new router handler in `app/routers/audio.py`. Deprecations are additive: `deprecated=True` OpenAPI flag + warning log on all three, plus RFC-8594 headers on the batch endpoint (the two stream endpoints return raw `StreamingResponse`, so headers can't ride along).

**Tech Stack:** FastAPI, Pydantic v2, async SQLAlchemy, pytest (`asyncio_mode=auto`, in-memory SQLite via conftest).

**Spec:** `docs/superpowers/specs/2026-06-02-unified-batch-speech-and-stream-deprecation-design.md`

---

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `app/schemas/speech.py` | Add `SpeechBatchItem`, `SpeechBatchRequest`, `SpeechBatchItemResponse`, `SpeechBatchResponse` | Modify |
| `app/services/speech_service.py` | Add `synthesize_batch()` facade method | Modify |
| `app/routers/audio.py` | Add `create_speech_batch` handler + `_schedule_speech_batch_feedback` helper | Modify |
| `app/utils/deprecation.py` | Add `SUCCESSOR_SPEECH_BATCH` constant | Modify |
| `app/routers/tts.py` | Deprecate `stream_tts`, `stream_tts_with_url` | Modify |
| `app/routers/orpheus_tts.py` | Deprecate `synthesize_tts_batch` + headers | Modify |
| `app/tests/test_speech_batch.py` | Integration + deprecation tests | Create |
| `app/tests/test_speech_service.py` | Service-unit tests for `synthesize_batch` | Modify |

**Conventions to follow** (already established in this codebase):
- Custom exceptions from `app/core/exceptions.py` (`BadRequestError`=400, `ExternalServiceError`=502), never bare `HTTPException`.
- Annotate plain types (not `Optional[X]`) for Swagger-friendly bodies — but batch input is a JSON body model, so this is N/A here.
- Test fixture pattern: override `get_speech_service` with a real `SpeechService(orpheus_service=MagicMock(), ...)` for unified-endpoint tests (see `app/tests/test_voice_speakers.py`); override `get_orpheus_tts_service` for legacy-endpoint tests (see `app/tests/test_routers/test_orpheus_tts.py`).

---

## Task 1: Batch schemas

**Files:**
- Modify: `app/schemas/speech.py`

- [ ] **Step 1: Add the `Literal` import**

In `app/schemas/speech.py`, change the typing import line:

```python
from typing import Any, Dict, Literal, Optional
```

- [ ] **Step 2: Append the four batch schemas to the end of `app/schemas/speech.py`**

```python
class SpeechBatchItem(BaseModel):
    """One item in a batch speech request (orpheus-3b-tts only)."""

    text: str = Field(..., min_length=1, description="Text to synthesize.")
    voice: Optional[str] = Field(
        default=None,
        description="orpheus catalog tag (e.g. 'salt_lug_0001'); "
        "defaults to salt_lug_0001.",
    )
    language: Optional[str] = Field(
        default=None, description="orpheus ISO 639-3 code (e.g. 'lug')."
    )
    temperature: Optional[float] = Field(default=None)
    top_p: Optional[float] = Field(default=None)
    repetition_penalty: Optional[float] = Field(default=None)
    max_tokens: Optional[int] = Field(default=None)
    seed: Optional[int] = Field(default=None)

    @field_validator("text")
    @classmethod
    def _strip_text(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("text must not be empty")
        return v


class SpeechBatchRequest(BaseModel):
    """Unified batch TTS request (orpheus-3b-tts only)."""

    model: TTSModel = Field(
        default=TTSModel.orpheus_3b_tts,
        description="Only 'orpheus-3b-tts' is supported for batch.",
    )
    items: list[SpeechBatchItem] = Field(
        ..., min_length=1, max_length=128, description="1-128 items."
    )


class SpeechBatchItemResponse(BaseModel):
    """Per-item batch result (mirrors SpeechResponse + status/error)."""

    index: int
    status: Literal["ok", "error"]
    voice: str
    audio_url: Optional[str] = None
    audio_url_expires_at: Optional[datetime] = None
    language: Optional[str] = None
    sample_rate: Optional[int] = None
    duration_seconds: Optional[float] = None
    audio_size_bytes: Optional[int] = None
    gcs_object: Optional[str] = None
    request_id: Optional[str] = None
    error_code: Optional[str] = None
    error_detail: Optional[str] = None


class SpeechBatchResponse(BaseModel):
    """Normalized batch response."""

    model: str
    platform: str
    results: list[SpeechBatchItemResponse]
    request_id: str
    timings_ms: Optional[Dict[str, Any]] = None
```

- [ ] **Step 3: Verify the schemas import cleanly**

Run: `python -c "from app.schemas.speech import SpeechBatchItem, SpeechBatchRequest, SpeechBatchItemResponse, SpeechBatchResponse; print('ok')"`
Expected: prints `ok` with no traceback.

- [ ] **Step 4: Verify schema validation behavior**

Run:
```bash
python -c "
from app.schemas.speech import SpeechBatchRequest
from pydantic import ValidationError
# empty items rejected
try:
    SpeechBatchRequest(items=[])
    print('FAIL: empty allowed')
except ValidationError:
    print('ok empty rejected')
# default model
r = SpeechBatchRequest(items=[{'text': 'hi'}])
print('model', r.model.value, 'voice', r.items[0].voice)
"
```
Expected:
```
ok empty rejected
model orpheus-3b-tts voice None
```

- [ ] **Step 5: Commit**

```bash
git add app/schemas/speech.py
git commit -m "feat(schemas): add unified batch speech request/response schemas"
```

---

## Task 2: SpeechService.synthesize_batch facade

**Files:**
- Modify: `app/services/speech_service.py`
- Test: `app/tests/test_speech_service.py`

- [ ] **Step 1: Write the failing service-unit tests**

Append to `app/tests/test_speech_service.py`:

```python
async def test_synthesize_batch_maps_voice_to_speaker_id():
    """voice -> speaker_id, defaulting to salt_lug_0001, tuning fields forwarded."""
    from unittest.mock import AsyncMock, MagicMock

    from app.schemas.speech import SpeechBatchItem, SpeechBatchRequest
    from app.services.orpheus_tts_service import BatchItemResult, BatchResult
    from app.services.speech_service import SpeechService

    orpheus = MagicMock()
    orpheus.synthesize_batch = AsyncMock(
        return_value=BatchResult(
            results=[
                BatchItemResult(index=0, status="ok", speaker_id="salt_lug_0001"),
                BatchItemResult(index=1, status="ok", speaker_id="salt_eng_0001"),
            ],
            inference_ms=1.0,
            upload_ms=1.0,
            total_ms=2.0,
        )
    )
    svc = SpeechService(
        tts_service=MagicMock(),
        orpheus_service=orpheus,
        runpod_spark_service=MagicMock(),
        storage_service=MagicMock(),
    )
    req = SpeechBatchRequest(
        items=[
            SpeechBatchItem(text="hi"),  # no voice -> default
            SpeechBatchItem(text="yo", voice="salt_eng_0001", seed=7, top_p=0.9),
        ]
    )

    await svc.synthesize_batch(req)

    payload = orpheus.synthesize_batch.call_args.args[0]
    assert payload[0]["speaker_id"] == "salt_lug_0001"  # default
    assert payload[0]["text"] == "hi"
    assert payload[1]["speaker_id"] == "salt_eng_0001"
    assert payload[1]["seed"] == 7
    assert payload[1]["top_p"] == 0.9


async def test_synthesize_batch_rejects_non_orpheus_model():
    from unittest.mock import AsyncMock, MagicMock

    import pytest

    from app.core.exceptions import BadRequestError
    from app.schemas.speech import SpeechBatchItem, SpeechBatchRequest, TTSModel
    from app.services.speech_service import SpeechService

    orpheus = MagicMock()
    orpheus.synthesize_batch = AsyncMock()
    svc = SpeechService(
        tts_service=MagicMock(),
        orpheus_service=orpheus,
        runpod_spark_service=MagicMock(),
        storage_service=MagicMock(),
    )
    req = SpeechBatchRequest(
        model=TTSModel.spark_tts, items=[SpeechBatchItem(text="hi")]
    )

    with pytest.raises(BadRequestError):
        await svc.synthesize_batch(req)
    orpheus.synthesize_batch.assert_not_called()


async def test_synthesize_batch_rejects_overlong_item():
    from unittest.mock import AsyncMock, MagicMock

    import pytest

    from app.core.exceptions import BadRequestError
    from app.schemas.speech import SpeechBatchItem, SpeechBatchRequest
    from app.services.speech_service import SpeechService

    orpheus = MagicMock()
    orpheus.synthesize_batch = AsyncMock()
    svc = SpeechService(
        tts_service=MagicMock(),
        orpheus_service=orpheus,
        runpod_spark_service=MagicMock(),
        storage_service=MagicMock(),
    )
    req = SpeechBatchRequest(items=[SpeechBatchItem(text="x" * 2001)])

    with pytest.raises(BadRequestError):
        await svc.synthesize_batch(req)
    orpheus.synthesize_batch.assert_not_called()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest app/tests/test_speech_service.py -k synthesize_batch -v`
Expected: FAIL with `AttributeError: 'SpeechService' object has no attribute 'synthesize_batch'`.

- [ ] **Step 3: Add the import and the method**

In `app/services/speech_service.py`, extend the orpheus-service import to also bring in the batch result types (used for the return annotation):

```python
from app.services.orpheus_tts_service import (
    BatchResult,
    OrpheusTTSService,
    get_orpheus_tts_service,
)
```

Then add this method to the `SpeechService` class, immediately after `synthesize` (before `list_voices`):

```python
    async def synthesize_batch(self, req: "SpeechBatchRequest") -> BatchResult:
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
```

Add `SpeechBatchRequest` to the existing speech-schema import in this file:

```python
from app.schemas.speech import SpeechBatchRequest, SpeechRequest
```

(The `"SpeechBatchRequest"` annotation is a forward-ref string only to avoid any import-ordering surprise; the real import above resolves it. Keep both.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest app/tests/test_speech_service.py -k synthesize_batch -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add app/services/speech_service.py app/tests/test_speech_service.py
git commit -m "feat(speech): add SpeechService.synthesize_batch facade (orpheus-only)"
```

---

## Task 3: Batch router endpoint + feedback

**Files:**
- Modify: `app/routers/audio.py`
- Test: `app/tests/test_speech_batch.py`

- [ ] **Step 1: Write the failing integration tests**

Create `app/tests/test_speech_batch.py`:

```python
"""Integration tests for POST /tasks/audio/speech/batch."""

import datetime as dt
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.api import app
from app.core.exceptions import BadRequestError, ExternalServiceError
from app.deps import get_speech_service
from app.services.orpheus_tts_service import BatchItemResult, BatchResult
from app.services.speech_service import SpeechService


def _speech_with_orpheus(orpheus):
    return SpeechService(
        tts_service=MagicMock(),
        orpheus_service=orpheus,
        runpod_spark_service=MagicMock(),
        storage_service=MagicMock(),
    )


@pytest.fixture
def mixed_batch() -> BatchResult:
    expires_at = dt.datetime(2026, 5, 27, 12, 30, tzinfo=dt.timezone.utc)
    return BatchResult(
        results=[
            BatchItemResult(
                index=0,
                status="ok",
                speaker_id="salt_lug_0001",
                audio_url="https://storage.googleapis.com/u1",
                audio_url_expires_at=expires_at,
                language="lug",
                sample_rate=24000,
                duration_seconds=2.0,
                audio_size_bytes=1000,
                gcs_object="orpheus_tts/2026-05-27/u1.wav",
            ),
            BatchItemResult(
                index=1,
                status="error",
                speaker_id="salt_eng_0001",
                error_code="storage_unavailable",
                error_detail="GCS upload failed",
            ),
        ],
        inference_ms=1200.0,
        upload_ms=300.0,
        total_ms=1500.0,
    )


async def test_batch_happy_and_partial(
    authenticated_client: AsyncClient, test_user, mixed_batch
):
    orpheus = MagicMock()
    orpheus.synthesize_batch = AsyncMock(return_value=mixed_batch)
    app.dependency_overrides[get_speech_service] = lambda: _speech_with_orpheus(orpheus)
    try:
        resp = await authenticated_client.post(
            "/tasks/audio/speech/batch",
            json={"items": [{"text": "hello"}, {"text": "world", "voice": "salt_eng_0001"}]},
        )
    finally:
        app.dependency_overrides.pop(get_speech_service, None)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["model"] == "orpheus-3b-tts"
    assert data["platform"] == "modal"
    assert len(data["results"]) == 2
    ok, err = data["results"]
    assert ok["status"] == "ok"
    assert ok["voice"] == "salt_lug_0001"
    assert ok["audio_url"] == "https://storage.googleapis.com/u1"
    assert ok["request_id"] is not None
    assert err["status"] == "error"
    assert err["error_code"] == "storage_unavailable"
    assert err["request_id"] is None
    assert data["timings_ms"]["total_ms"] == pytest.approx(1500.0)


async def test_batch_all_failed_returns_502(
    authenticated_client: AsyncClient, test_user
):
    orpheus = MagicMock()
    orpheus.synthesize_batch = AsyncMock(
        side_effect=ExternalServiceError(
            service_name="GCS", message="all 2 batch items failed during upload"
        )
    )
    app.dependency_overrides[get_speech_service] = lambda: _speech_with_orpheus(orpheus)
    try:
        resp = await authenticated_client.post(
            "/tasks/audio/speech/batch",
            json={"items": [{"text": "a"}, {"text": "b"}]},
        )
    finally:
        app.dependency_overrides.pop(get_speech_service, None)

    assert resp.status_code == 502
    assert "failed during upload" in resp.json()["message"]


async def test_batch_bad_item_returns_400(
    authenticated_client: AsyncClient, test_user
):
    orpheus = MagicMock()
    orpheus.synthesize_batch = AsyncMock(
        side_effect=BadRequestError(message="item index 0: speaker_id 'x' not found")
    )
    app.dependency_overrides[get_speech_service] = lambda: _speech_with_orpheus(orpheus)
    try:
        resp = await authenticated_client.post(
            "/tasks/audio/speech/batch",
            json={"items": [{"text": "a", "voice": "x"}]},
        )
    finally:
        app.dependency_overrides.pop(get_speech_service, None)

    assert resp.status_code == 400


async def test_batch_non_orpheus_model_returns_400(
    authenticated_client: AsyncClient, test_user
):
    orpheus = MagicMock()
    orpheus.synthesize_batch = AsyncMock()
    app.dependency_overrides[get_speech_service] = lambda: _speech_with_orpheus(orpheus)
    try:
        resp = await authenticated_client.post(
            "/tasks/audio/speech/batch",
            json={"model": "spark-tts", "items": [{"text": "a"}]},
        )
    finally:
        app.dependency_overrides.pop(get_speech_service, None)

    assert resp.status_code == 400
    orpheus.synthesize_batch.assert_not_called()


async def test_batch_empty_items_returns_422(
    authenticated_client: AsyncClient, test_user
):
    resp = await authenticated_client.post(
        "/tasks/audio/speech/batch", json={"items": []}
    )
    assert resp.status_code == 422


async def test_batch_requires_auth(async_client: AsyncClient):
    resp = await async_client.post(
        "/tasks/audio/speech/batch", json={"items": [{"text": "a"}]}
    )
    assert resp.status_code == 401
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest app/tests/test_speech_batch.py -v`
Expected: FAIL — the route does not exist yet (404 instead of 200/502/400, so assertions fail).

- [ ] **Step 3: Add imports to `app/routers/audio.py`**

Extend the speech-schema import:

```python
from app.schemas.speech import (
    SpeechBatchItemResponse,
    SpeechBatchRequest,
    SpeechBatchResponse,
    SpeechRequest,
    SpeechResponse,
    TTSModel,
)
```

- [ ] **Step 4: Add the handler after `create_speech` (before `_schedule_speech_feedback`) in `app/routers/audio.py`**

```python
@router.post(
    "/audio/speech/batch",
    response_model=SpeechBatchResponse,
    summary="Batch-generate speech (unified, orpheus-3b-tts only)",
    description=(
        "Unified batch Text-to-Speech endpoint. Synthesizes 1-128 items in a "
        "single orpheus-3b-tts pass and uploads each result to GCS. Per-item "
        "failures are reported with status='error'; the request returns 200 if "
        "at least one item succeeds, 502 if every item fails. "
        "Replaces /tasks/modal/orpheus/tts/batch."
    ),
    tags=["Text-to-Speech (Unified)"],
)
@limiter.limit(get_account_type_limit)
async def create_speech_batch(
    request: Request,
    background_tasks: BackgroundTasks,
    quota: QuotaServiceDep,
    speech_service: SpeechServiceDep,
    body: SpeechBatchRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> SpeechBatchResponse:
    """Batch-generate speech via orpheus-3b-tts."""
    await check_quota(quota, db, current_user)

    try:
        batch = await speech_service.synthesize_batch(body)
        request_id = uuid.uuid4().hex

        results = [
            SpeechBatchItemResponse(
                index=r.index,
                status=r.status,
                voice=r.speaker_id,
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

        response = SpeechBatchResponse(
            model="orpheus-3b-tts",
            platform="modal",
            results=results,
            request_id=request_id,
            timings_ms={
                "inference_ms": batch.inference_ms,
                "upload_ms": batch.upload_ms,
                "total_ms": batch.total_ms,
            },
        )

        _schedule_speech_batch_feedback(
            background_tasks=background_tasks,
            user=current_user,
            items=body.items,
            batch=batch,
            request_id=request_id,
        )

        return response
    except (
        BadRequestError,
        ValidationError,
        ExternalServiceError,
        ServiceUnavailableError,
    ):
        raise
    except Exception as e:
        logging.error(f"Unexpected error in create_speech_batch: {str(e)}")
        raise ExternalServiceError(
            service_name="Speech Service",
            message="An unexpected error occurred while generating batch speech",
            original_error=str(e),
        )
```

- [ ] **Step 5: Add the feedback helper after `_schedule_speech_feedback` in `app/routers/audio.py`**

```python
def _schedule_speech_batch_feedback(
    *, background_tasks, user, items, batch, request_id
):
    """Best-effort feedback save: one record per successful batch item."""
    try:
        for item, result in zip(items, batch.results):
            if result.status != "ok":
                continue
            voice = result.speaker_id
            background_tasks.add_task(
                save_api_inference,
                item.text,
                {"audio_url": result.audio_url, "gcs_object": result.gcs_object},
                user,
                model_type=f"orpheus-3b-tts:{voice}",
                processing_time=batch.total_ms / 1000.0,
                inference_type=INFERENCE_TYPES["tts"],
                job_details={
                    "model": "orpheus-3b-tts",
                    "platform": "modal",
                    "voice": voice,
                    "audio_url": result.audio_url,
                    "gcs_object": result.gcs_object,
                    "batch_index": result.index,
                    "request_id": request_id,
                },
            )
    except Exception as e:
        logging.warning(f"Failed to schedule batch speech feedback save task: {e}")
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pytest app/tests/test_speech_batch.py -v`
Expected: 6 passed.

- [ ] **Step 7: Commit**

```bash
git add app/routers/audio.py app/tests/test_speech_batch.py
git commit -m "feat(audio): add unified POST /tasks/audio/speech/batch endpoint"
```

---

## Task 4: Deprecate the three legacy endpoints

**Files:**
- Modify: `app/utils/deprecation.py`
- Modify: `app/routers/tts.py`
- Modify: `app/routers/orpheus_tts.py`
- Test: `app/tests/test_speech_batch.py`

- [ ] **Step 1: Write the failing deprecation tests**

Append to `app/tests/test_speech_batch.py`:

```python
async def test_openapi_marks_legacy_endpoints_deprecated(async_client: AsyncClient):
    resp = await async_client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    for path in [
        "/tasks/modal/tts/stream",
        "/tasks/modal/tts/stream-with-url",
        "/tasks/modal/orpheus/tts/batch",
    ]:
        assert paths[path]["post"].get("deprecated") is True, path


async def test_legacy_orpheus_batch_has_deprecation_headers(
    authenticated_client: AsyncClient, test_user, mixed_batch
):
    """/tasks/modal/orpheus/tts/batch carries RFC-8594 headers to the successor."""
    from app.services.orpheus_tts_service import get_orpheus_tts_service

    orpheus = MagicMock()
    orpheus.synthesize_batch = AsyncMock(return_value=mixed_batch)
    app.dependency_overrides[get_orpheus_tts_service] = lambda: orpheus
    try:
        resp = await authenticated_client.post(
            "/tasks/modal/orpheus/tts/batch",
            json={"items": [{"text": "a", "speaker_id": "salt_lug_0001"}]},
        )
    finally:
        app.dependency_overrides.pop(get_orpheus_tts_service, None)

    assert resp.status_code == 200, resp.text
    assert resp.headers.get("Deprecation") == "true"
    assert "Sunset" in resp.headers
    assert "/tasks/audio/speech/batch" in resp.headers.get("Link", "")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest app/tests/test_speech_batch.py -k "deprecated or deprecation" -v`
Expected: FAIL — `deprecated` is not `True` for the three paths; the batch endpoint sends no `Deprecation` header.

- [ ] **Step 3: Add the successor constant in `app/utils/deprecation.py`**

After the existing `SUCCESSOR_VOICES` line:

```python
SUCCESSOR_SPEECH_BATCH = "/tasks/audio/speech/batch"
```

- [ ] **Step 4: Deprecate the two stream endpoints in `app/routers/tts.py`**

Change the `stream_tts` decorator + body. Replace the existing decorator and function header (lines for `@router.post("/tts/stream", ...)` through the `stream_tts` docstring) with:

```python
@router.post(
    "/tts/stream",
    # tags=["TTS"],
    summary="Stream TTS Audio",
    description=(
        "Stream audio chunks as they are generated. "
        "DEPRECATED: use POST /tasks/audio/speech with response_mode='stream'."
    ),
    deprecated=True,
)
async def stream_tts(
    request: TTSRequest,
    tts_service: TTSServiceDep,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Stream audio directly without storing in GCP."""
    logging.warning(
        "Deprecated endpoint /tasks/modal/tts/stream called; "
        "use POST /tasks/audio/speech with response_mode='stream'"
    )
    return await _stream_audio(request, tts_service)
```

Then replace the `stream_tts_with_url` decorator + function header with:

```python
@router.post(
    "/tts/stream-with-url",
    # tags=["TTS"],
    summary="Stream TTS Audio with Final URL",
    description=(
        "Stream audio chunks and return a signed URL at completion. "
        "DEPRECATED: use POST /tasks/audio/speech with response_mode='both'."
    ),
    deprecated=True,
)
async def stream_tts_with_url(
    request: TTSRequest,
    storage_service: LegacyStorageServiceDep,
    tts_service: TTSServiceDep,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Stream audio and provide a URL for the complete file at the end."""
    logging.warning(
        "Deprecated endpoint /tasks/modal/tts/stream-with-url called; "
        "use POST /tasks/audio/speech with response_mode='both'"
    )
    return await _stream_audio_with_url(request, storage_service, tts_service)
```

(No header changes — both return raw `StreamingResponse`; the `deprecated=True` flag + warning log are the deprecation signals.)

- [ ] **Step 5: Deprecate the batch endpoint in `app/routers/orpheus_tts.py`**

Extend the deprecation import:

```python
from app.utils.deprecation import (
    SUCCESSOR_SPEECH,
    SUCCESSOR_SPEECH_BATCH,
    SUCCESSOR_VOICES,
    add_deprecation_headers,
)
```

Change the `/tts/batch` decorator to add `deprecated=True`:

```python
@router.post(
    "/tts/batch",
    response_model=OrpheusTTSBatchResponse,
    summary="Batch-synthesize speech via Orpheus-3B",
    description=(
        "Calls Modal's batched inference endpoint (a single vLLM "
        "continuous-batched pass) and uploads each generated WAV to GCS in "
        "parallel. Per-item failures are reported in the response with "
        '`status: "error"`; the request as a whole returns 200 if at least '
        "one item succeeds, 502 if every item failed. "
        "DEPRECATED: use POST /tasks/audio/speech/batch."
    ),
    deprecated=True,
)
```

Add `http_response: Response` to the signature and the warning log + header call at the top of the body. Change the function signature/opening to:

```python
@limiter.limit(get_account_type_limit)
async def synthesize_tts_batch(
    request: Request,
    body: OrpheusTTSBatchRequest,
    quota: QuotaServiceDep,
    background_tasks: BackgroundTasks,
    http_response: Response,
    db: AsyncSession = Depends(get_db),
    service=Depends(get_orpheus_tts_service),
    current_user=Depends(get_current_user),
) -> OrpheusTTSBatchResponse:
    await check_quota(quota, db, current_user)
    logger.warning(
        "Deprecated endpoint /tasks/modal/orpheus/tts/batch called; "
        "use POST /tasks/audio/speech/batch"
    )
    add_deprecation_headers(http_response, SUCCESSOR_SPEECH_BATCH)
    items_payload = [
```

(The rest of the function body is unchanged.)

- [ ] **Step 6: Run the deprecation tests to verify they pass**

Run: `pytest app/tests/test_speech_batch.py -k "deprecated or deprecation" -v`
Expected: 2 passed.

- [ ] **Step 7: Run the full new test file**

Run: `pytest app/tests/test_speech_batch.py -v`
Expected: 8 passed.

- [ ] **Step 8: Commit**

```bash
git add app/utils/deprecation.py app/routers/tts.py app/routers/orpheus_tts.py app/tests/test_speech_batch.py
git commit -m "feat(tts): deprecate legacy stream + orpheus batch endpoints"
```

---

## Task 5: Full-suite + lint verification

**Files:** none (verification only)

- [ ] **Step 1: Run the related test files together (catch isolation issues)**

Run: `pytest app/tests/test_speech_batch.py app/tests/test_speech_service.py app/tests/test_voice_speakers.py app/tests/test_routers/test_orpheus_tts.py app/tests/test_routers/test_tts.py -v`
Expected: all pass.

- [ ] **Step 2: Run the full suite**

Run: `pytest app/tests/ -v`
Expected: all pass **except** the 4 known pre-existing environment-dependent failures in `app/tests/test_config.py` (the `test_ga_*` tests). If any *other* test fails, investigate — it is not pre-existing.

- [ ] **Step 3: Lint-check the changed files**

Run: `make lint-check`
Expected: black + isort + flake8 clean for all files touched by this plan (`app/schemas/speech.py`, `app/services/speech_service.py`, `app/routers/audio.py`, `app/utils/deprecation.py`, `app/routers/tts.py`, `app/routers/orpheus_tts.py`, `app/tests/test_speech_batch.py`, `app/tests/test_speech_service.py`). If pre-existing unrelated lint debt is reported (e.g. in files this plan did not touch), leave it — it is out of scope.

- [ ] **Step 4: Verify the OpenAPI surface**

Run:
```bash
python -c "
from app.api import app
schema = app.openapi()
paths = schema['paths']
assert '/tasks/audio/speech/batch' in paths, 'new endpoint missing'
op = paths['/tasks/audio/speech/batch']['post']
assert 'Text-to-Speech (Unified)' in op['tags'], op['tags']
for p in ['/tasks/modal/tts/stream', '/tasks/modal/tts/stream-with-url', '/tasks/modal/orpheus/tts/batch']:
    assert paths[p]['post'].get('deprecated') is True, p
print('OpenAPI ok')
"
```
Expected: prints `OpenAPI ok`.

- [ ] **Step 5: Final commit (only if any verification fix was needed)**

If steps 1–4 required no code change, there is nothing to commit. If a lint fix or small correction was needed:

```bash
git add -A
git commit -m "chore(tts): lint + verification fixes for batch speech endpoint"
```

---

## Self-Review

**1. Spec coverage:**
- New endpoint `/tasks/audio/speech/batch` → Task 3. ✓
- orpheus-only, 400 on other model → Task 2 (facade) + Task 3 test. ✓
- Schemas (unified `voice` naming) → Task 1. ✓
- Service facade reusing `synthesize_batch` → Task 2. ✓
- Partial-failure / 502 / 400 / 422 semantics → Task 3 tests. ✓
- Per-item feedback → Task 3 Step 5. ✓
- Deprecate 3 legacy endpoints (flag + log; headers on batch only) → Task 4. ✓
- `SUCCESSOR_SPEECH_BATCH` constant → Task 4 Step 3. ✓
- Tests 1–12 from spec → Tasks 2/3/4 cover all 12. ✓
- DoD (full suite parity + lint + OpenAPI) → Task 5. ✓

**2. Placeholder scan:** No TBD/TODO; every code step shows full code. ✓

**3. Type consistency:** `synthesize_batch(req: SpeechBatchRequest) -> BatchResult`; router maps `BatchItemResult` (`.speaker_id`, `.status`, `.error_code`, `.error_detail`, timings) → `SpeechBatchItemResponse` (`voice`, ...). `voice = r.speaker_id` is consistent across facade input mapping and response mapping. `DEFAULT_ORPHEUS_VOICE` and `ORPHEUS_MAX_TEXT` already exist in `speech_service.py`. ✓
