# Unified `GET /tasks/voice/speakers` Endpoint + Legacy Deprecation

**Date:** 2026-06-02
**Status:** Approved (design)
**Branch:** `tts-unified-endpoint` (extends Phase 2 PR #215; targets `api-endpoints-bestpractices`)
**Scope:** A follow-on to Phase 2 (TTS). Adds a single speaker-listing endpoint across the two TTS
models and deprecates the three legacy speaker-listing endpoints. Synthesis (`/tasks/audio/speech`)
is unchanged.

## Background

Speaker discovery is currently split across three endpoints with different shapes:

| Endpoint | Logic | Returns |
|---|---|---|
| `GET /tasks/modal/orpheus/speakers` | `OrpheusTTSService.list_speakers()` | `OrpheusSpeakersResponse` `{default, by_language, total, languages}` |
| `GET /tasks/modal/orpheus/speakers/{language}` | `OrpheusTTSService.speakers_for_language(language)` | `OrpheusLanguageSpeakersResponse` `{language, speakers, count}` (400 on unknown language) |
| `GET /tasks/modal/tts/speakers` | `get_all_speakers()` (from `app/models/enums.py`) | `SpeakersListResponse` `{speakers: [SpeakerInfo{id,name,display_name,language,gender}]}` |

Goal: one OpenAI-style `GET /tasks/voice/speakers` that selects the model and reuses the existing
logic, with the three legacy endpoints kept functional but deprecated.

## Design Decisions (locked)

1. **Response format:** native pass-through. The endpoint returns the exact response model of the
   underlying logic for each case (no reshaping). The response schema therefore varies by `model`
   and `language`.
2. **Method/params:** `GET` with query params `model` and `language`.
3. **Auth:** authentication required; **no** quota / rate-limit (matches the legacy listing
   endpoints, which are cheap reads).
4. **Invalid combination:** `model=spark-tts` + `language` provided → `400 BadRequestError`
   (`language` is orpheus-only).
5. **Dispatch lives in the facade:** a new `SpeechService.list_voices(model, language)` validates
   and dispatches, consistent with Phase 2 (`SpeechService` already wraps `OrpheusTTSService`).

## Endpoint Contract — `GET /tasks/voice/speakers`

Added to `app/routers/audio.py`, tag **"Text-to-Speech (Unified)"**. Mounted under `/tasks`, so the
path is `/tasks/voice/speakers`.

| Query param | Type | Required | Default | Notes |
|---|---|---|---|---|
| `model` | `TTSModel` (`orpheus-3b-tts` \| `spark-tts`) | no | `orpheus-3b-tts` | Reuses the Phase 2 enum |
| `language` | `Optional[str]` | no | `None` | orpheus-only (ISO 639-3, e.g. `lug`). 400 if set with `spark-tts`. |

- **Auth:** `current_user=Depends(get_current_user)` (401 if unauthenticated).
- **`response_model=None`** (the response is heterogeneous). The handler returns the native Pydantic
  model instance; FastAPI serializes it via `jsonable_encoder`, including computed fields
  (`total`/`languages`/`count`). The three possible shapes are documented in the route description.
- **No quota, no `@limiter.limit`.**

### Dispatch — `SpeechService.list_voices(model: str, language: Optional[str])`

```
spark-tts + language set      -> raise BadRequestError (400)
spark-tts                     -> SpeakersListResponse(speakers=[SpeakerInfo(**d) for d in get_all_speakers()])
orpheus-3b-tts + language     -> OrpheusLanguageSpeakersResponse(language=language,
                                     speakers=await self._orpheus.speakers_for_language(language))
                                  # speakers_for_language raises BadRequestError(400) on unknown language
orpheus-3b-tts                -> catalog = await self._orpheus.list_speakers()
                                  OrpheusSpeakersResponse(default=catalog.default, by_language=catalog.by_language)
```

The facade imports the three response schemas (`OrpheusSpeakersResponse`,
`OrpheusLanguageSpeakersResponse` from `app/schemas/orpheus_tts.py`; `SpeakersListResponse`,
`SpeakerInfo` from `app/schemas/tts.py`) and `get_all_speakers` from `app/models/enums.py`. The
method returns one of the three models (typed as a `Union` for clarity). No data is reshaped — it
mirrors exactly what the legacy handlers build.

The router is thin: resolve `model`/`language` query params → `await speech_service.list_voices(...)`
→ return the result.

## Deprecation (mirrors Phase 2)

Add `deprecated=True` + RFC-8594 headers + a warning log to the three legacy listing endpoints,
pointing at the successor `/tasks/voice/speakers`:
- `GET /tasks/modal/orpheus/speakers` (`get_speakers`)
- `GET /tasks/modal/orpheus/speakers/{language}` (`get_speakers_for_language`)
- `GET /tasks/modal/tts/speakers` (`list_speakers`)

Each handler returns a Pydantic model, so injecting `http_response: Response` and calling
`add_deprecation_headers(http_response, SUCCESSOR_VOICES)` merges the headers into the response.

Add `SUCCESSOR_VOICES = "/tasks/voice/speakers"` to `app/utils/deprecation.py`.

## New / Changed Files

**Changed:**
- `app/utils/deprecation.py` — add `SUCCESSOR_VOICES`.
- `app/services/speech_service.py` — add `list_voices(model, language)`.
- `app/routers/audio.py` — add `GET /voice/speakers`.
- `app/routers/orpheus_tts.py` — deprecate `get_speakers` + `get_speakers_for_language`.
- `app/routers/tts.py` — deprecate `list_speakers`.

**New:**
- `app/tests/test_voice_speakers.py` — endpoint tests.
- Facade `list_voices` unit tests appended to `app/tests/test_speech_service.py`.

## Testing & Definition of Done

Per [CLAUDE.md](../../../CLAUDE.md):

- **Tests** (`pytest app/tests/ -v` green). Mock at the service layer (`OrpheusTTSService`) — never
  call real Modal/GCS. Cover:
  - `model=orpheus-3b-tts` (no language) → 200 + `OrpheusSpeakersResponse` shape (default,
    by_language, computed total/languages).
  - `model=orpheus-3b-tts` + `language=lug` → 200 + `OrpheusLanguageSpeakersResponse` shape;
    unknown language → 400.
  - `model=spark-tts` → 200 + `SpeakersListResponse` (6 speakers from `get_all_speakers`).
  - `model=spark-tts` + `language` → 400.
  - Unauthenticated → 401.
  - Default model (omitted `model`) → orpheus grouped response.
  - Deprecation: the 3 legacy endpoints carry `deprecated=True` (OpenAPI) and
    `Deprecation`/`Sunset`/`Link` headers pointing at `/tasks/voice/speakers`.
  - Facade `list_voices` unit tests for all four dispatch branches (mocked `OrpheusTTSService`).
- **Lint** (`make lint-check` clean for touched files: black + isort + flake8).

## Out of Scope

- Unifying TTS synthesis (done in Phase 2), batch generation, health, refresh-url, or the streaming
  helpers — those remain as-is.
- Removing any legacy endpoint (they remain functional until the sunset date).
- Normalizing the three response shapes into one envelope (explicitly rejected — native pass-through
  chosen).

## Risks & Mitigations

- **Heterogeneous response (`response_model=None`)**: OpenAPI shows no single schema for the
  endpoint. Mitigation: document the three shapes in the route description; tests assert each shape.
- **Facade scope creep**: `SpeechService` gains a listing concern alongside synthesis. Acceptable —
  it is the unified TTS facade and already wraps `OrpheusTTSService`; `list_voices` is small and
  independently testable.
- **Spark `language` silently ignored**: prevented — `spark-tts` + `language` is an explicit 400.
