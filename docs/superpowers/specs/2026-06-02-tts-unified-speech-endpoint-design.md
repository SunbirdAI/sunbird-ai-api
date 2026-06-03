# Phase 2 (TTS): Unified `/tasks/audio/speech` Endpoint + Legacy Deprecation

**Date:** 2026-06-02
**Status:** Approved (design)
**Branch:** `tts-unified-endpoint` (PR targets `api-endpoints-bestpractices`, not `main`)
**Scope:** Phase 2 (Text-to-Speech) of [docs/api-endpoint-refactor.md](../../api-endpoint-refactor.md).
Phase 1 (STT) is complete and is the reference implementation for patterns used here.

## Background

TTS is spread across three systems plus a legacy endpoint, each with different schemas and
response shapes:

| Endpoint | Model | Platform | Service | Returns |
|---|---|---|---|---|
| `POST /tasks/modal/tts` | spark-tts | Modal | `TTSService` (httpx → `settings.tts_api_url`) | signed URL **or** streamed audio (`response_mode`) |
| `POST /tasks/runpod/tts` | spark-tts | RunPod | none — inline `runpod.Endpoint` call | JSON `{output: {audio_url, blob, sample_rate}}` |
| `POST /tasks/modal/orpheus/tts` | orpheus-3b-tts | Modal | `OrpheusTTSService` (Modal vLLM + GCS) | JSON `{audio_url, timings, …}` |
| `POST /tasks/tts` (legacy, already `deprecated=True`) | spark-tts | RunPod | inline | mirrors RunPod |

Goal: one OpenAI-style `POST /tasks/audio/speech` that consolidates **single-utterance synthesis**
across model + platform, with the legacy synthesis endpoints kept functional but deprecated.

Reference inventory of every TTS endpoint, schema, and service is in the codebase as of this
branch's base commit.

## Design Decisions (locked)

1. **Response format:** `response_mode` param (reuse existing `app/schemas/tts.py:TTSResponseMode`):
   `url` (default → normalized JSON with signed GCS URL), `stream` (raw audio bytes), `both`
   (SSE). `stream`/`both` are supported **only** for spark-tts + Modal.
2. **Scope:** single synthesis only. Deprecate the 3 synthesis endpoints (+ already-deprecated
   legacy). Leave speaker-listing, batch, streaming helpers, health, and refresh-url as separate,
   non-deprecated endpoints.
3. **Voice field:** a single `voice: str`, interpreted per model; validated with a 400 on mismatch.
4. **Invalid parameter combinations:** validate and return `400` (`BadRequestError`).
5. **Provider abstraction:** a new `SpeechService` facade routes by (model, platform); a new
   `RunpodSparkTTSService` extracts the inline RunPod call so all three providers have a service
   layer. Legacy endpoints keep their behavior; RunPod's body delegates to the new service.

## Architecture

```
POST /tasks/audio/speech   (added to the existing app/routers/audio.py)
        │  JSON body: SpeechRequest
        ▼
SpeechService              (new: app/services/speech_service.py)
   ├─ validate_request(...) → 400 on invalid model/platform/param/voice/text combos
   └─ dispatch by (model, platform):
        ├─ orpheus-3b-tts + modal  → OrpheusTTSService.synthesize(...)
        ├─ spark-tts + modal       → TTSService.generate_audio(...) / generate_audio_stream(...)
        └─ spark-tts + runpod      → RunpodSparkTTSService.synthesize(...)   ← NEW service
```

The router is thin: auth + quota/RL → build `SpeechRequest` → delegate to the facade → return
`SpeechResponse` (url mode) or a `StreamingResponse` (stream/both modes) → schedule feedback. The
facade owns validation + dispatch + result normalization. No synthesis logic is duplicated.

## Request Schema — `SpeechRequest` (JSON body, `app/schemas/speech.py`)

| Field | Type | Required | Default | Applies to |
|---|---|---|---|---|
| `text` | `str` | yes | — | all (≤2000 for orpheus, ≤10000 for spark — enforced per model in the facade) |
| `model` | `TTSModel` (`orpheus-3b-tts`\|`spark-tts`) | no | `orpheus-3b-tts` | all (new enum) |
| `platform` | `TTSPlatform` (`modal`\|`runpod`) | no | `modal` | all (new enum) |
| `voice` | `Optional[str]` | no | model default (below) | all — interpreted per model |
| `response_mode` | `TTSResponseMode` (`url`\|`stream`\|`both`) | no | `url` | reuses existing enum |
| `language` | `Optional[str]` | no | `None` | orpheus only (ISO 639-3) |
| `temperature` | `Optional[float]` | no | `None` | orpheus + runpod-spark |
| `top_p` | `Optional[float]` | no | `None` | orpheus only |
| `repetition_penalty` | `Optional[float]` | no | `None` | orpheus only |
| `max_tokens` | `Optional[int]` | no | `None` | orpheus only |
| `seed` | `Optional[int]` | no | `None` | orpheus only |
| `max_new_audio_tokens` | `Optional[int]` | no | `None` | runpod-spark only |

**Default `voice` when omitted:** `salt_lug_0001` (orpheus), `luganda_female` (spark). For spark,
`voice` accepts the `SpeakerID` enum **name** (e.g. `luganda_female`) or its **int** (e.g. `248`);
for orpheus it is the catalog tag string.

New enums live in `app/schemas/speech.py`:
- `TTSModel(str, Enum)`: `orpheus_3b_tts = "orpheus-3b-tts"`, `spark_tts = "spark-tts"`.
- `TTSPlatform(str, Enum)`: `modal = "modal"`, `runpod = "runpod"`.
- `TTSResponseMode` is **reused** from `app/schemas/tts.py` (values `url`/`stream`/`both`).

## Validation Rules (facade → `400` `BadRequestError`)

- `model=orpheus-3b-tts` + `platform=runpod` → 400 (no RunPod-Orpheus deployment).
- `response_mode` ∈ {`stream`, `both`} when not (`spark-tts` + `modal`) → 400 (only Modal spark
  streams).
- Orpheus-only params (`language`, `top_p`, `repetition_penalty`, `max_tokens`, `seed`) provided
  (non-`None`) when `model ≠ orpheus-3b-tts` → 400.
- `max_new_audio_tokens` provided when not (`spark-tts` + `runpod`) → 400.
- `temperature` provided when (`spark-tts` + `modal`) → 400 (Modal spark takes only text + voice).
- `voice`: for spark, must resolve to a valid `SpeakerID` (name or int) else 400; for orpheus, the
  existing `OrpheusTTSService` validates the tag against the live catalog (already raises 400).
- `text` length: orpheus > 2000 → 400; spark > 10000 → 400.

`SpeechRequest` Pydantic field constraints stay permissive (e.g. `text` 1–10000); the per-model
caps and combination rules are enforced in `SpeechService.validate_request` so a single schema
serves all model/platform combinations.

## Dispatch & Result Normalization

`SpeechService.synthesize(...)` returns a normalized `SpeechResult` dataclass that the router maps
to the `SpeechResponse` schema.

| Field (`SpeechResponse`) | Source per provider |
|---|---|
| `audio_url` (required, url mode) | Orpheus `SynthesizeResult.audio_url`; Modal `TTSResponse.audio_url`; RunPod `output.audio_url` |
| `audio_url_expires_at` | Orpheus `audio_url_expires_at`; Modal `expires_at`; RunPod: `None` (worker-managed) |
| `model`, `platform`, `voice` | echoed from the request (resolved voice) |
| `language` | Orpheus `language`; else `None` |
| `sample_rate` | Orpheus `sample_rate` (24000); RunPod `output.sample_rate` (16000); Modal `None` |
| `duration_seconds` | Orpheus `duration_seconds`; Modal `duration_estimate_seconds`; RunPod `None` |
| `gcs_object` | Orpheus `gcs_object`; Modal `file_name`; RunPod `output.blob` |
| `request_id` | Orpheus `request_id`; else `None` |
| `timings_ms` | Orpheus `timings_ms`; else `None` |

**Streaming (`stream`/`both`, spark+modal only):** the router returns a `StreamingResponse`. It
reuses the Modal `TTSService.generate_audio_stream` generator and the existing SSE helper pattern
from `app/routers/tts.py` (`_stream_audio` / `_stream_audio_with_url`) — imported and reused, like
Phase 1 reused `_schedule_stt_feedback`, rather than duplicated. The facade exposes the validated
voice + text; the router constructs the stream.

## `RunpodSparkTTSService` (new — `app/services/runpod_tts_service.py`)

Extracts the inline logic currently in `app/routers/runpod_tts.py`:
- `async synthesize(*, text, speaker_id, temperature, max_new_audio_tokens) -> dict` — builds the
  RunPod `{"input": {"task": "tts", …}}` payload, calls `runpod.Endpoint(RUNPOD_ENDPOINT_ID)
  .run_sync(data, timeout=600)` via the existing tenacity retry wrapper, returns the worker output.
- Singleton `get_runpod_spark_tts_service()` + `reset_runpod_spark_tts_service()`.
- The legacy `POST /tasks/runpod/tts` body is updated to call this service (same behavior); this is
  the one place we change a legacy endpoint beyond markers, justified by the doc's provider-
  abstraction requirement.

## Cross-cutting

- **Auth + quota + rate-limit** on `/tasks/audio/speech` (`check_quota` + `@limiter.limit(
  get_account_type_limit)`), matching the RunPod/Orpheus synthesis endpoints. Intentional,
  flagged difference: Modal spark `generate_tts` currently has **neither** — the unified endpoint
  adds both for the spark+modal path.
- **No DB writes** (no TTS endpoint persists today). Schedule the same `save_api_inference`
  feedback (`inference_type="tts"`, `model_type` reflecting model + voice) via `BackgroundTasks`;
  feedback-save failures never propagate.

## Deprecation (mirrors Phase 1)

Add `deprecated=True` + RFC-8594 headers + a warning log to the three synthesis endpoints, and add
the headers to the already-deprecated legacy endpoint:
- `POST /tasks/modal/tts`, `POST /tasks/runpod/tts`, `POST /tasks/modal/orpheus/tts`
- `POST /tasks/tts` (already `deprecated=True`) gains `Deprecation`/`Sunset`/`Link` headers.

Headers point to the successor `/tasks/audio/speech`. Reuse `app/utils/deprecation.py`: add
`SUCCESSOR_SPEECH = "/tasks/audio/speech"`; generalize the sunset-date constant (introduce a neutral
`SUNSET_DATE` and keep `STT_SUNSET_DATE` as an alias so Phase 1 is untouched).

**Not deprecated (left as-is):** Modal `/tasks/modal/health`, `/tasks/modal/tts/speakers`,
`/tasks/modal/tts/stream`, `/tasks/modal/tts/stream-with-url`, `/tasks/modal/tts/refresh-url`;
Orpheus `/tasks/modal/orpheus/speakers`, `/tasks/modal/orpheus/speakers/{language}`,
`/tasks/modal/orpheus/tts/batch`.

## New / Changed Files

**New:**
- `app/schemas/speech.py` — `TTSModel`, `TTSPlatform`, `SpeechRequest`, `SpeechResponse`.
- `app/services/speech_service.py` — `SpeechService` facade + `validate_request` + `synthesize` +
  `get_speech_service()` / `reset_speech_service()`; a `SpeechResult` normalized dataclass.
- `app/services/runpod_tts_service.py` — `RunpodSparkTTSService` + singleton.
- `app/tests/test_audio_speech.py` — endpoint + facade tests.

**Changed:**
- `app/routers/audio.py` — add `POST /audio/speech` (tag "Text-to-Speech (Unified)").
- `app/deps.py` — add `SpeechServiceDep`, `RunpodSparkTTSServiceDep`.
- `app/utils/deprecation.py` — add `SUCCESSOR_SPEECH`, generalize sunset constant.
- `app/routers/tts.py`, `app/routers/runpod_tts.py`, `app/routers/orpheus_tts.py`,
  `app/routers/tasks.py` — deprecation markers; `runpod_tts.py` also delegates to
  `RunpodSparkTTSService`.

## Testing & Definition of Done

Per [CLAUDE.md](../../../CLAUDE.md):

- **Tests** (`pytest app/tests/ -v` green). Mock at the service layer
  (`TTSService` / `OrpheusTTSService` / `RunpodSparkTTSService`) — never call real Modal/RunPod/GCS.
  Cover:
  - Dispatch: each of the 3 (model, platform) paths returns `200` + correct `SpeechResponse`
    mapping (url mode).
  - `response_mode=stream` for spark+modal returns `audio/wav`; `response_mode=stream`/`both` for
    any other combo → 400.
  - Validation 400 matrix: orpheus+runpod; orpheus-only params on spark; `max_new_audio_tokens`
    off-target; `temperature` on spark+modal; invalid spark `voice`; over-length text per model.
  - Voice resolution: spark accepts enum name and int; omitted voice uses the per-model default.
  - Quota enforcement (reuse the Phase 1 pattern) on the unified endpoint.
  - Deprecation: the 4 legacy endpoints carry `deprecated=True` (OpenAPI) and
    `Deprecation`/`Sunset`/`Link` headers pointing at `/tasks/audio/speech`.
  - `RunpodSparkTTSService` unit test (mocked `runpod.Endpoint`) and that `/tasks/runpod/tts` still
    works via the service.
- **Lint** (`make lint-check` clean for touched files: black + isort + flake8).

## Out of Scope

- Unifying speaker-listing, language-speaker discovery, or batch generation (Orpheus keeps these).
- Removing any legacy endpoint (they remain functional until the sunset date).
- TTS streaming for orpheus or RunPod (neither backend streams today).
- Any STT (Phase 1) changes.

## Risks & Mitigations

- **Heterogeneous result mapping**: each provider returns a different shape; the normalized
  `SpeechResult` dataclass + a mapping table (above) keep the facade the single place that knows
  each provider's shape. Covered by per-provider dispatch tests asserting the mapped fields.
- **Streaming reuse from `tts.py`**: importing `_stream_audio` helpers couples the unified router
  to `tts.py` (same pattern as Phase 1's feedback helper). Acceptable; flagged for a future move to
  a shared `app/utils/` module if it grows.
- **Two `SpeakerID` enums** (`app/models/enums.py` vs `app/schemas/tasks.py`): the facade resolves
  spark `voice` against one canonical enum (`app/models/enums.py:SpeakerID`) to avoid ambiguity;
  documented in the voice-resolution helper.
- **Quota added to the spark+modal path**: a behavior change for that path; documented as
  intentional and covered by a quota test. Legacy `/tasks/modal/tts` keeps its current (no-quota)
  behavior.
