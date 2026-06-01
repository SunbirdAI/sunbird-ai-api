# Phase 1 (STT): Unified `/tasks/audio/transcriptions` Endpoint + Legacy Deprecation

**Date:** 2026-06-02
**Status:** Approved (design)
**Scope:** Phase 1 (Speech-to-Text) only. TTS (Phase 2) is explicitly out of scope per
[docs/api-endpoint-refactor.md](../../api-endpoint-refactor.md) — do not start TTS until STT is
completed and validated.

## Background

The STT surface has grown into four overlapping endpoints in
[app/routers/stt.py](../../../app/routers/stt.py), each calling a shared service layer:

| Endpoint | Platform | Service method | Inputs | Quota/RL | DB save |
|---|---|---|---|---|---|
| `POST /tasks/stt_from_gcs` | RunPod | `STTService.transcribe_from_gcs` | gcs_blob_name, language, adapter, whisper, recognise_speakers | none | yes |
| `POST /tasks/stt` | RunPod | `STTService.transcribe_uploaded_file` | audio, language, adapter, whisper, recognise_speakers | yes | yes |
| `POST /tasks/org/stt` | RunPod | `STTService.transcribe_org_audio` | audio, recognise_speakers | yes | no |
| `POST /tasks/modal/stt` | Modal | `ModalSTTService.transcribe` | audio, language (optional/auto-detect) | yes | no |

The goal is one OpenAI-style endpoint (`POST /tasks/audio/transcriptions`) that consolidates all
four behind a single service abstraction, while the legacy endpoints remain functional but carry
machine-readable deprecation signals.

## Design Decisions (locked)

1. **Deprecation signal:** OpenAPI `deprecated=True` + RFC-8594 response headers
   (`Deprecation` / `Sunset` / `Link`) + a server-side `logger.warning` per legacy call.
2. **Legacy implementations:** keep current logic unchanged; add deprecation markers only
   (doc Option B). No rewiring of legacy endpoints through the new path.
3. **Abstraction:** a new `TranscriptionService` facade routes by `platform`/`org` to the
   existing `STTService` / `ModalSTTService` methods. No business logic is duplicated.
4. **Invalid parameter combinations:** validate and return `400` (`ValidationError`).

## Architecture

```
POST /tasks/audio/transcriptions   (new router: app/routers/audio.py)
        │
        ▼
TranscriptionService               (new facade: app/services/transcription_service.py)
   ├─ validates platform / input / org combinations  → 400 on invalid
   └─ dispatches to existing services (no logic duplicated):
        ├─ runpod + gcs_blob_name → STTService.transcribe_from_gcs
        ├─ runpod + audio + org   → STTService.transcribe_org_audio
        ├─ runpod + audio         → STTService.transcribe_uploaded_file
        └─ modal  + audio         → ModalSTTService.transcribe
```

The new router is thin (parse form → quota/RL → delegate to facade → build `STTTranscript`
response → schedule feedback). The facade owns validation + dispatch. The four legacy endpoints
are untouched functionally.

## New Endpoint Contract — `POST /tasks/audio/transcriptions`

Content type: `multipart/form-data` (accepts file uploads).

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `language` | `SttbLanguage` enum | yes | — | All supported languages; for `modal` passed as a hint, for `org` accepted-but-unused |
| `audio` | file (`UploadFile`) | one of audio/gcs | — | Uploaded audio file |
| `gcs_blob_name` | str | one of audio/gcs | — | RunPod-only |
| `platform` | `TranscriptionPlatform` (`modal`\|`runpod`) | no | `modal` | New enum |
| `adapter` | `SttbLanguage` | no | = `language` | RunPod-only |
| `whisper` | `Optional[bool]` | no | `true` when runpod | RunPod-only |
| `recognise_speakers` | `Optional[bool]` | no | `true` when runpod | RunPod-only |
| `org` | `bool` | no | `false` | RunPod org workflow |

**Response:** the existing `STTTranscript` schema (unchanged).

**Cross-cutting:** the endpoint enforces `check_quota(...)` and `@limiter.limit(get_account_type_limit)`
on every path.

### Intentional differences from legacy (per doc — flagged, not silent)

- RunPod defaults `whisper` and `recognise_speakers` to **`true`** (legacy `/tasks/stt` defaults
  both to `false`). Source: refactor doc "Defaults … whisper: true, recognise_speakers: true when
  RunPod is selected."
- The GCS path now enforces quota + rate limiting (legacy `/tasks/stt_from_gcs` enforces neither).

## Validation Rules (→ `400` `ValidationError`)

- Exactly one of `audio` / `gcs_blob_name` must be present (neither → 400, both → 400).
- `platform=modal` + `gcs_blob_name` provided → 400 (Modal has no GCS code path).
- `platform=modal` + `org=true` → 400 (no Modal org workflow exists).
- `whisper` / `recognise_speakers` are modeled as `Optional[bool] = Form(None)`. If either is
  explicitly set (non-`None`) while `platform=modal` → 400. When `None` and `platform=runpod`,
  apply the `true` defaults.

## Dispatch & Persistence Behavior

The facade returns a normalized result object (reusing the existing `TranscriptionResult` shape
from `STTService` where applicable). The router maps it to `STTTranscript`.

- **runpod + gcs_blob_name:** `transcribe_from_gcs(...)`; saves to DB via
  `create_audio_transcription` when a non-empty transcription is produced (parity with legacy
  `/stt_from_gcs`).
- **runpod + audio + org=false:** `transcribe_uploaded_file(...)`; saves to DB on success
  (parity with legacy `/stt`). Streams upload to a temp file in chunks (`CHUNK_SIZE`), validates
  content type/extension first.
- **runpod + audio + org=true:** `transcribe_org_audio(...)`; no DB save (parity with `/org/stt`).
- **modal + audio:** `ModalSTTService.transcribe(audio_bytes, language=...)`; no DB save
  (parity with `/modal/stt`).

Feedback is scheduled via `BackgroundTasks` (reuse the existing `_schedule_stt_feedback` helper
pattern; either import/share it or replicate the thin wrapper in the new router). Feedback-save
failures must never propagate to the response.

## Deprecation Mechanics (4 legacy STT endpoints)

- Add `deprecated=True` to each legacy `@router.post(...)` → strikethrough in `/docs` and
  `"deprecated": true` in the OpenAPI schema.
- New helper module `app/utils/deprecation.py`:
  - A constant `STT_SUNSET_DATE` (HTTP-date string for **2026-12-01**).
  - A function that, given a `Response` (or returning headers), sets:
    - `Deprecation: true`
    - `Sunset: <STT_SUNSET_DATE>` (RFC 8594 / RFC 7231 HTTP-date format)
    - `Link: </tasks/audio/transcriptions>; rel="successor-version"`
  - Apply by injecting `response: Response` into each legacy handler and calling the helper, so
    headers are set even on the normal (non-trimmed) return path. The existing trimmed-audio
    branch that returns a raw `Response` must also carry these headers.
- Emit `logger.warning("Deprecated endpoint <path> called; use POST /tasks/audio/transcriptions")`
  once per legacy call to enable monitoring of residual usage.

## New / Changed Files

**New:**
- `app/routers/audio.py` — unified audio router (transcriptions now; speech added in Phase 2).
- `app/services/transcription_service.py` — `TranscriptionService` facade + `get_transcription_service()`
  singleton + dispatch/validation.
- `app/utils/deprecation.py` — sunset constant + header helper.
- `app/tests/test_audio_transcriptions.py` — endpoint + facade tests.

**Changed:**
- `app/schemas/stt.py` — add `TranscriptionPlatform(str, Enum)` with `modal` / `runpod`.
- `app/deps.py` — add `TranscriptionServiceDep` (`Annotated[TranscriptionService, Depends(get_transcription_service)]`),
  register in `__all__`.
- `app/api.py` — import and `include_router(audio_router, prefix="/tasks", tags=["Speech-to-Text (Unified)"])`.
- `app/routers/stt.py` — add `deprecated=True` + deprecation headers + warning log to all four
  endpoints (no functional change otherwise).

## Testing & Definition of Done

Per [CLAUDE.md](../../../CLAUDE.md) Definition of Done:

- **Tests** (`pytest app/tests/ -v` green). Mock at the service layer (`STTService` /
  `ModalSTTService`) per the testing rules — never call real RunPod/Modal/GCS. Cover:
  - Each of the 4 dispatch paths returns `200` + correct `STTTranscript` mapping.
  - Validation 400s: neither/both inputs; `modal`+gcs; `modal`+org; `modal`+explicit
    whisper/recognise_speakers.
  - RunPod default application (`whisper`/`recognise_speakers` default to `true`).
  - Quota enforcement path (reuse existing quota test patterns) on the unified endpoint.
  - Legacy endpoints still return `200` AND carry `Deprecation`/`Sunset`/`Link` headers and the
    `deprecated` flag in OpenAPI.
- **Lint** (`make lint-check` clean: black + isort + flake8).

## Out of Scope

- Any TTS work (Phase 2). Do not modify `tts.py`, `runpod_tts.py`, `orpheus_tts.py`, or
  `tasks.py` in this phase.
- Removing legacy endpoints. They remain fully functional; removal happens after the sunset date
  in a later change.
- Rewiring legacy endpoints to call the unified handler.

## Risks & Mitigations

- **Behavior drift from new RunPod defaults** (`true`/`true`): documented as intentional; covered
  by tests asserting the new defaults. Legacy endpoints keep old defaults, so existing consumers
  are unaffected.
- **Temp-file handling / cleanup** for uploaded audio: reuse the existing streaming-to-temp
  pattern from `/stt` to avoid memory blowups; ensure temp files are cleaned up.
- **`Optional[bool]` form parsing** for explicit-vs-default detection: verify FastAPI parses an
  unset `Form(None)` as `None` (vs `False`) so the modal-validation rule is reliable; covered by a
  dedicated test.
