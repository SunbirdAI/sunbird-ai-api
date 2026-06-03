# Unified Batch Speech + Stream/Batch Deprecation — Design

**Date:** 2026-06-02
**Status:** Approved (design phase)
**Author:** API endpoint refactor — TTS follow-up

## Goal

Add a unified **batch** Text-to-Speech endpoint (`POST /tasks/audio/speech/batch`,
orpheus-3b-tts only) following the OpenAI-style unified-endpoint conventions
already established by `/tasks/audio/transcriptions`, `/tasks/audio/speech`, and
`/tasks/voice/speakers`. Deprecate three legacy endpoints whose behavior is now
covered by the unified surface.

## Background

The single-synthesis unified endpoint `POST /tasks/audio/speech` already exists
and already covers the two legacy *streaming* cases through its `response_mode`
field:

- `response_mode="stream"` runs the `/tasks/modal/tts/stream` logic (`_stream_audio`)
- `response_mode="both"` runs the `/tasks/modal/tts/stream-with-url` logic (`_stream_audio_with_url`)

So **no new streaming parameters are added** — those two legacy endpoints are
simply deprecated and point clients at `response_mode`.

The legacy batch endpoint `POST /tasks/modal/orpheus/tts/batch` takes a *list* of
items and returns a *list* of results — a shape that does not fit the
single-text `/audio/speech`. It therefore becomes its own unified sibling
endpoint rather than a flag on `/audio/speech`.

## Scope

**In scope**

1. New endpoint `POST /tasks/audio/speech/batch` (orpheus-3b-tts only), tagged
   `Text-to-Speech (Unified)`.
2. New unified request/response schemas (`voice`-based naming, consistent with
   `/audio/speech`).
3. New `SpeechService.synthesize_batch(...)` facade method (validation + payload
   mapping; reuses the existing `OrpheusTTSService.synthesize_batch`).
4. Deprecate three legacy endpoints (OpenAPI `deprecated=True` + warning log,
   plus RFC-8594 headers where deliverable). Logic unchanged.
5. Tests.

**Out of scope**

- Spark-tts batching (not supported upstream; rejected with 400).
- Changing single `/audio/speech` behavior or its `response_mode` semantics.
- Removing any legacy endpoint (deprecation only; sunset `Tue, 01 Dec 2026`).
- Pre-existing lint debt / committing `docs/api-endpoint-refactor.md` (separate).

## Endpoint

```
POST /tasks/audio/speech/batch
Tag:  Text-to-Speech (Unified)
Auth: Bearer token (CurrentUserDep) — required
Quota + SlowAPI per-account rate limit (same as /audio/speech)
```

- **orpheus-3b-tts only.** Optional `model` field defaults to `orpheus-3b-tts`;
  any other value → **400** (`BadRequestError`). Keeps the surface unified and
  future-extensible without pretending to support spark batching.
- Reuses `OrpheusTTSService.synthesize_batch(items: list[dict])` — the same
  engine the legacy endpoint calls. No new synthesis logic.
- **Partial-failure semantics (unchanged from the service):**
  - per-item `status: "ok" | "error"` with `error_code` / `error_detail` on failures
  - all items failed → service raises `ExternalServiceError` → **502**
  - a single invalid item (unknown voice/language) → service raises
    `BadRequestError` → **400** (fail-fast, before GPU time), message prefixed
    with the offending item index
  - batch size > upstream `max_batch_size` → **400**

## Schemas (`app/schemas/speech.py`)

Unified naming: items use `voice` (not the orpheus-native `speaker_id`),
mirroring the single `SpeechRequest`. Only the orpheus-applicable tuning fields
are exposed.

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

(`Literal` from `typing` is added to the existing imports.)

## Service (`app/services/speech_service.py`)

```python
async def synthesize_batch(self, req: SpeechBatchRequest) -> "BatchResult":
    """Validate + dispatch a batch (orpheus-3b-tts only).

    Returns the OrpheusTTSService BatchResult; the router maps it to the
    unified SpeechBatchResponse. Raises BadRequestError (400) for a non-orpheus
    model or any item that is too long; the underlying service raises
    BadRequestError (400) / ExternalServiceError (502) for bad-item / all-fail.
    """
    if req.model.value != "orpheus-3b-tts":
        raise BadRequestError(
            message="batch synthesis is only supported for model='orpheus-3b-tts'."
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

`BatchResult` / `BatchItemResult` are imported from
`app/services/orpheus_tts_service.py` (used for the return-type annotation and by
the router for mapping).

Note: `synthesize_batch` forwards `None` for unset tuning fields. The upstream
Modal worker applies its own defaults for missing keys (parity with how the
single orpheus path only forwards set values). This matches the legacy
`/tasks/modal/orpheus/tts/batch` behavior, which forwards each item's field as-is
(the legacy schema supplies defaults at the Pydantic layer). **Decision:** the
unified batch item leaves tuning fields optional with `None` default and forwards
them verbatim — the worker/`OrpheusTTSRequest` defaults still apply downstream.

## Router (`app/routers/audio.py`)

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
    await check_quota(quota, db, current_user)
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
```

`_schedule_speech_batch_feedback` mirrors the existing
`orpheus_tts._schedule_batch_feedback`: one best-effort `save_api_inference`
record per successful item (`inference_type=INFERENCE_TYPES["tts"]`,
`model_type=f"orpheus-3b-tts:{voice}"`), wrapped in try/except so a feedback
failure never breaks the response. It lives in `audio.py` next to the existing
`_schedule_speech_feedback`.

Errors are handled by the same `except (BadRequestError, ValidationError,
ExternalServiceError, ServiceUnavailableError): raise` / generic-500 pattern used
by `create_speech`.

## Deprecations

Add to `app/utils/deprecation.py`:

```python
SUCCESSOR_SPEECH_BATCH = "/tasks/audio/speech/batch"
```

| Endpoint | Successor | Headers? |
|----------|-----------|----------|
| `POST /tasks/modal/tts/stream` | `/tasks/audio/speech` (use `response_mode=stream`) | No — returns raw `StreamingResponse` |
| `POST /tasks/modal/tts/stream-with-url` | `/tasks/audio/speech` (use `response_mode=both`) | No — returns raw `StreamingResponse` |
| `POST /tasks/modal/orpheus/tts/batch` | `/tasks/audio/speech/batch` | Yes — returns a model |

**Stream endpoints** (`tts.py: stream_tts`, `stream_tts_with_url`): add
`deprecated=True` to the decorator, a `logging.warning(...)` naming the successor,
and document the successor in the description. They return a raw
`StreamingResponse`, so RFC-8594 headers cannot ride along the streamed body
(same limitation already accepted for the legacy `/tts` streaming branches) —
this is intentional and noted, not faked.

**Batch endpoint** (`orpheus_tts.py: synthesize_tts_batch`): add `deprecated=True`,
inject `http_response: Response`, call
`add_deprecation_headers(http_response, SUCCESSOR_SPEECH_BATCH)`, and a
`logging.warning(...)`. Returns a model, so headers are delivered.

All listed endpoints keep their existing behavior — deprecation is additive.

## Testing (`app/tests/test_speech_batch.py` + additions)

New integration tests (mock `OrpheusTTSService.synthesize_batch` via a
`SpeechService` built with a `MagicMock` orpheus, overriding `get_speech_service`,
following the `test_voice_speakers.py` fixture pattern):

1. **Happy path** — 2-item batch returns 200, `results` length 2, each `ok` with
   `voice`/`audio_url`/`request_id`, `model="orpheus-3b-tts"`, `platform="modal"`,
   `timings_ms` present.
2. **Partial failure** — one `ok` + one `error` item still returns 200; the error
   item carries `error_code`/`error_detail` and `request_id is None`.
3. **All failed → 502** — mock raises `ExternalServiceError`.
4. **Bad item → 400** — mock raises `BadRequestError`.
5. **Non-orpheus model → 400** — `model="spark-tts"` rejected by the facade
   (no service call).
6. **Empty items → 422** — schema `min_length=1`.
7. **Auth required → 401** — unauthenticated client.

Service-level unit tests (`test_speech_service.py` additions):

8. `synthesize_batch` maps `voice` → `speaker_id` (defaulting to
   `salt_lug_0001`) and forwards tuning fields.
9. `synthesize_batch` raises `BadRequestError` for `model="spark-tts"`.
10. `synthesize_batch` raises `BadRequestError` for an over-length item.

Deprecation tests (`test_speech_batch.py` or alongside existing TTS deprecation
tests):

11. OpenAPI marks all three legacy endpoints `deprecated: true`.
12. `/tasks/modal/orpheus/tts/batch` round-trip carries RFC-8594 headers pointing
    at `/tasks/audio/speech/batch` (mock `synthesize_batch`).

(Stream endpoints get the OpenAPI `deprecated` assertion only; header round-trips
are N/A for raw streaming responses.)

## Definition of Done

- `pytest app/tests/ -v` — all new tests pass; full suite at parity (only the
  known pre-existing environment-dependent `test_config` GA failures remain).
- `make lint-check` clean for all new/modified files.
- New endpoint visible + correctly tagged in `/openapi.json`; three legacy
  endpoints flagged `deprecated`.
```
