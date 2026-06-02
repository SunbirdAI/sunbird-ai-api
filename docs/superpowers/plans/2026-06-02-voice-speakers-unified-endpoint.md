# Unified Voice/Speakers Endpoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single `GET /tasks/voice/speakers` endpoint that lists speakers for the selected TTS model (orpheus-3b-tts grouped-by-language, optionally for one language; or spark-tts), reusing the existing logic, and deprecate the three legacy speaker-listing endpoints.

**Architecture:** A thin GET handler on `app/routers/audio.py` parses `model`/`language` query params and delegates to a new `SpeechService.list_voices(model, language)` that validates (`spark-tts`+`language` → 400) and dispatches to `OrpheusTTSService.list_speakers()` / `OrpheusTTSService.speakers_for_language()` / `get_all_speakers()`, returning the native response model unchanged. `response_model=None` (heterogeneous).

**Tech Stack:** FastAPI, pytest (`asyncio_mode=auto`, in-memory SQLite). Orpheus service mocked in tests; spark uses the static `get_all_speakers()`.

**Spec:** [docs/superpowers/specs/2026-06-02-voice-speakers-unified-endpoint-design.md](../specs/2026-06-02-voice-speakers-unified-endpoint-design.md)

---

## File Structure

| File | Responsibility |
|---|---|
| `app/services/speech_service.py` (modify) | Add `list_voices(model, language)` — validate + dispatch + return native response model |
| `app/routers/audio.py` (modify) | Add `GET /voice/speakers` |
| `app/utils/deprecation.py` (modify) | Add `SUCCESSOR_VOICES` constant |
| `app/routers/orpheus_tts.py` (modify) | Deprecate `get_speakers` + `get_speakers_for_language` |
| `app/routers/tts.py` (modify) | Deprecate `list_speakers` |
| `app/tests/test_speech_service.py` (modify) | Facade `list_voices` unit tests |
| `app/tests/test_voice_speakers.py` (create) | Endpoint + deprecation tests |

**Reference signatures (already in the codebase — do not change):**

```python
# app/services/orpheus_tts_service.py
class OrpheusTTSService:
    async def list_speakers(self) -> SpeakerCatalog        # SpeakerCatalog has .default: str and .by_language: dict[str, list[str]]
    async def speakers_for_language(self, language: str) -> list[str]   # raises BadRequestError(400) on unknown language

# app/models/enums.py
def get_all_speakers() -> list[dict]   # [{id, name, display_name, language, gender}, ...] for the 6 SpeakerID members

# app/schemas/orpheus_tts.py
class OrpheusSpeakersResponse(BaseModel): default: str; by_language: dict[str, list[str]]   # computed: total, languages
class OrpheusLanguageSpeakersResponse(BaseModel): language: str; speakers: list[str]          # computed: count

# app/schemas/tts.py
class SpeakerInfo(BaseModel): id: int; name: str; display_name: str; language: str; gender: str
class SpeakersListResponse(BaseModel): speakers: list[SpeakerInfo]

# app/schemas/speech.py (Phase 2)
class TTSModel(str, Enum): orpheus_3b_tts = "orpheus-3b-tts"; spark_tts = "spark-tts"

# app/services/speech_service.py (Phase 2) — SpeechService already holds self._orpheus
# app/core/exceptions.py — BadRequestError -> 400
# app/utils/deprecation.py — add_deprecation_headers(response, successor), SUNSET_DATE
```

> **Test note:** the legacy speaker endpoints (and the new one) require auth but no quota. `conftest`'s autouse `stub_quota_service` is irrelevant here. The orpheus router uses `Depends(get_orpheus_tts_service)` directly; the facade uses its injected `self._orpheus`.

---

## Task 1: `SpeechService.list_voices`

**Files:**
- Modify: `app/services/speech_service.py`
- Test: `app/tests/test_speech_service.py`

- [ ] **Step 1: Write the failing tests**

Append to `app/tests/test_speech_service.py` (it already imports `AsyncMock`, `MagicMock`, `pytest`, `BadRequestError`, and has `make_speech_facade`):

```python
from types import SimpleNamespace

from app.schemas.orpheus_tts import (
    OrpheusLanguageSpeakersResponse,
    OrpheusSpeakersResponse,
)
from app.schemas.tts import SpeakersListResponse


async def test_list_voices_spark_returns_all_speakers():
    facade, *_ = make_speech_facade()
    result = await facade.list_voices("spark-tts", None)
    assert isinstance(result, SpeakersListResponse)
    assert len(result.speakers) == 6


async def test_list_voices_spark_with_language_rejected():
    facade, *_ = make_speech_facade()
    with pytest.raises(BadRequestError):
        await facade.list_voices("spark-tts", "lug")


async def test_list_voices_orpheus_grouped():
    facade, _, orpheus, _, _ = make_speech_facade()
    orpheus.list_speakers = AsyncMock(
        return_value=SimpleNamespace(
            default="salt_lug_0001",
            by_language={"lug": ["salt_lug_0001"], "eng": ["salt_eng_0001"]},
        )
    )
    result = await facade.list_voices("orpheus-3b-tts", None)
    assert isinstance(result, OrpheusSpeakersResponse)
    assert result.default == "salt_lug_0001"
    assert result.total == 2


async def test_list_voices_orpheus_by_language():
    facade, _, orpheus, _, _ = make_speech_facade()
    orpheus.speakers_for_language = AsyncMock(return_value=["salt_lug_0001"])
    result = await facade.list_voices("orpheus-3b-tts", "lug")
    assert isinstance(result, OrpheusLanguageSpeakersResponse)
    assert result.language == "lug"
    assert result.speakers == ["salt_lug_0001"]
    orpheus.speakers_for_language.assert_awaited_once_with("lug")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest app/tests/test_speech_service.py -k list_voices -v`
Expected: FAIL with `AttributeError: ... has no attribute 'list_voices'`

- [ ] **Step 3: Add `list_voices` to `app/services/speech_service.py`**

Add these imports near the top (with the other imports):

```python
from typing import Union  # extend the existing typing import if present

from app.models.enums import get_all_speakers
from app.schemas.orpheus_tts import (
    OrpheusLanguageSpeakersResponse,
    OrpheusSpeakersResponse,
)
from app.schemas.tts import SpeakerInfo, SpeakersListResponse
```

(`get_all_speakers` is a module-level function in `app/models/enums.py`; `SpeakerID`/`TTSResponseMode` are already imported from there — keep the existing import and add `get_all_speakers`.)

Add this method to the `SpeechService` class (e.g. after `synthesize`):

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest app/tests/test_speech_service.py -k list_voices -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Lint + commit**

```bash
isort app/services/speech_service.py app/tests/test_speech_service.py
black app/services/speech_service.py app/tests/test_speech_service.py
flake8 app/services/speech_service.py app/tests/test_speech_service.py
git add app/services/speech_service.py app/tests/test_speech_service.py
git commit -m "feat(tts): add SpeechService.list_voices (speaker listing dispatch)"
```

---

## Task 2: `GET /tasks/voice/speakers` endpoint

**Files:**
- Modify: `app/routers/audio.py`
- Test: `app/tests/test_voice_speakers.py`

- [ ] **Step 1: Write the failing tests**

Create `app/tests/test_voice_speakers.py`:

```python
"""Integration tests for GET /tasks/voice/speakers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.api import app
from app.deps import get_speech_service
from app.services.speech_service import SpeechService


@pytest.fixture
def speech_with_mock_orpheus():
    """Real SpeechService with a mocked OrpheusTTSService; spark uses real data."""
    orpheus = MagicMock()
    orpheus.list_speakers = AsyncMock(
        return_value=SimpleNamespace(
            default="salt_lug_0001",
            by_language={"lug": ["salt_lug_0001"], "eng": ["salt_eng_0001"]},
        )
    )
    orpheus.speakers_for_language = AsyncMock(return_value=["salt_lug_0001"])
    facade = SpeechService(
        tts_service=MagicMock(),
        orpheus_service=orpheus,
        runpod_spark_service=MagicMock(),
        storage_service=MagicMock(),
    )
    app.dependency_overrides[get_speech_service] = lambda: facade
    yield facade, orpheus
    app.dependency_overrides.pop(get_speech_service, None)


async def test_voice_speakers_orpheus_default(
    authenticated_client: AsyncClient, speech_with_mock_orpheus, test_user
):
    resp = await authenticated_client.get("/tasks/voice/speakers")
    assert resp.status_code == 200
    body = resp.json()
    assert body["default"] == "salt_lug_0001"
    assert set(body["by_language"].keys()) == {"lug", "eng"}
    assert body["total"] == 2
    assert body["languages"] == ["eng", "lug"]


async def test_voice_speakers_orpheus_by_language(
    authenticated_client: AsyncClient, speech_with_mock_orpheus, test_user
):
    resp = await authenticated_client.get("/tasks/voice/speakers?language=lug")
    assert resp.status_code == 200
    body = resp.json()
    assert body["language"] == "lug"
    assert body["speakers"] == ["salt_lug_0001"]
    assert body["count"] == 1


async def test_voice_speakers_spark(
    authenticated_client: AsyncClient, speech_with_mock_orpheus, test_user
):
    resp = await authenticated_client.get("/tasks/voice/speakers?model=spark-tts")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["speakers"]) == 6
    assert {"id", "name", "display_name", "language", "gender"} <= set(
        body["speakers"][0].keys()
    )


async def test_voice_speakers_spark_with_language_400(
    authenticated_client: AsyncClient, speech_with_mock_orpheus, test_user
):
    resp = await authenticated_client.get(
        "/tasks/voice/speakers?model=spark-tts&language=lug"
    )
    assert resp.status_code == 400


async def test_voice_speakers_unknown_orpheus_language_400(
    authenticated_client: AsyncClient, speech_with_mock_orpheus, test_user
):
    from app.core.exceptions import BadRequestError

    _, orpheus = speech_with_mock_orpheus
    orpheus.speakers_for_language = AsyncMock(
        side_effect=BadRequestError(message="unknown language")
    )
    resp = await authenticated_client.get("/tasks/voice/speakers?language=zzz")
    assert resp.status_code == 400


async def test_voice_speakers_requires_auth(async_client: AsyncClient):
    resp = await async_client.get("/tasks/voice/speakers")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest app/tests/test_voice_speakers.py -v`
Expected: FAIL — route 404 (not yet added).

- [ ] **Step 3: Add the endpoint to `app/routers/audio.py`**

Add to the imports (merge with existing groups; isort will sort):

```python
from fastapi import Query

from app.schemas.speech import TTSModel
```

(`SpeechServiceDep`, `get_current_user`, `Optional` are already imported. `TTSModel` joins the existing `from app.schemas.speech import SpeechRequest, SpeechResponse` line.)

Append the handler at the end of the module:

```python
@router.get(
    "/voice/speakers",
    response_model=None,
    tags=["Text-to-Speech (Unified)"],
    summary="List speakers/voices (unified)",
    description=(
        "List available speakers for the selected TTS model. "
        "model='orpheus-3b-tts' (default) returns the catalog grouped by "
        "language (OrpheusSpeakersResponse); add 'language' to get one "
        "language's voices (OrpheusLanguageSpeakersResponse). "
        "model='spark-tts' returns the fixed SpeakerID voices "
        "(SpeakersListResponse); 'language' is not allowed for spark-tts. "
        "Replaces /tasks/modal/orpheus/speakers, "
        "/tasks/modal/orpheus/speakers/{language}, and /tasks/modal/tts/speakers."
    ),
)
async def list_voices(
    speech_service: SpeechServiceDep,
    model: TTSModel = Query(
        default=TTSModel.orpheus_3b_tts,
        description="TTS model: 'orpheus-3b-tts' (default) or 'spark-tts'.",
    ),
    language: Optional[str] = Query(
        default=None,
        description="orpheus-only ISO 639-3 code (e.g. 'lug'). Rejected for spark-tts.",
    ),
    current_user=Depends(get_current_user),
):
    """List speakers/voices for the selected model (and optional language)."""
    return await speech_service.list_voices(model.value, language)
```

> The router is already mounted under `/tasks` (Phase 1), so `/voice/speakers` resolves to
> `/tasks/voice/speakers` with no `app/api.py` change. No quota / rate-limit (matches the legacy
> listing endpoints).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest app/tests/test_voice_speakers.py -v`
Expected: PASS (6 tests). If `test_voice_speakers_spark_with_language_400` returns 422, the facade
raised the wrong type — STOP and report (do not weaken the assertion).

- [ ] **Step 5: Lint + commit**

```bash
isort app/routers/audio.py app/tests/test_voice_speakers.py
black app/routers/audio.py app/tests/test_voice_speakers.py
flake8 app/routers/audio.py app/tests/test_voice_speakers.py
git add app/routers/audio.py app/tests/test_voice_speakers.py
git commit -m "feat(tts): add unified GET /tasks/voice/speakers endpoint"
```

---

## Task 3: Deprecate the 3 legacy speaker endpoints

**Files:**
- Modify: `app/utils/deprecation.py`, `app/routers/orpheus_tts.py`, `app/routers/tts.py`
- Test: `app/tests/test_voice_speakers.py`

- [ ] **Step 1: Write the failing tests**

Append to `app/tests/test_voice_speakers.py`:

```python
async def test_openapi_marks_legacy_speaker_endpoints_deprecated(
    async_client: AsyncClient,
):
    resp = await async_client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    for path in [
        "/tasks/modal/orpheus/speakers",
        "/tasks/modal/orpheus/speakers/{language}",
        "/tasks/modal/tts/speakers",
    ]:
        assert paths[path]["get"].get("deprecated") is True, path


async def test_legacy_spark_speakers_has_deprecation_headers(
    authenticated_client: AsyncClient, test_user
):
    """/tasks/modal/tts/speakers still returns 200 and carries RFC-8594 headers."""
    resp = await authenticated_client.get("/tasks/modal/tts/speakers")
    assert resp.status_code == 200
    assert resp.headers.get("Deprecation") == "true"
    assert "Sunset" in resp.headers
    assert "/tasks/voice/speakers" in resp.headers.get("Link", "")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest app/tests/test_voice_speakers.py -k "deprecated or deprecation_headers" -v`
Expected: FAIL — `deprecated` absent / headers missing.

- [ ] **Step 3a: Add the successor constant**

In `app/utils/deprecation.py`, next to `SUCCESSOR_SPEECH`, add:

```python
SUCCESSOR_VOICES = "/tasks/voice/speakers"
```

- [ ] **Step 3b: Deprecate the spark speaker endpoint (`app/routers/tts.py` `list_speakers`)**

`tts.py` already imports `Response`, `add_deprecation_headers`, and `SUCCESSOR_SPEECH` (Phase 2).
Update the import line to also bring in `SUCCESSOR_VOICES`:

```python
from app.utils.deprecation import (
    SUCCESSOR_SPEECH,
    SUCCESSOR_VOICES,
    add_deprecation_headers,
    deprecation_headers,
)
```

Change the decorator to `@router.get("/tts/speakers", response_model=SpeakersListResponse, deprecated=True, ...)` (add `deprecated=True` to the existing kwargs). Add `http_response: Response` to the signature (before the `db`/`current_user` defaulted params), and add the warning + headers as the first body statements:

```python
async def list_speakers(
    http_response: Response,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return a list of all available speaker voices."""
    logging.warning(
        "Deprecated endpoint /tasks/modal/tts/speakers called; "
        "use GET /tasks/voice/speakers"
    )
    add_deprecation_headers(http_response, SUCCESSOR_VOICES)
    speakers = [SpeakerInfo(**speaker_data) for speaker_data in get_all_speakers()]
    return SpeakersListResponse(speakers=speakers)
```

- [ ] **Step 3c: Deprecate the orpheus speaker endpoints (`app/routers/orpheus_tts.py`)**

`orpheus_tts.py` already imports `Response`, `add_deprecation_headers`, `SUCCESSOR_SPEECH` (Phase 2).
Add `SUCCESSOR_VOICES` to that import. Then, for `get_speakers`:

```python
@router.get(
    "/speakers",
    response_model=OrpheusSpeakersResponse,
    deprecated=True,
    summary="List Orpheus speakers grouped by language",
    description=(
        "Returns the full Orpheus speaker catalog. `total` and `languages` are "
        "derived convenience fields. Auth required."
    ),
)
async def get_speakers(
    http_response: Response,
    service=Depends(get_orpheus_tts_service),
    current_user=Depends(get_current_user),
) -> OrpheusSpeakersResponse:
    logger.warning(
        "Deprecated endpoint /tasks/modal/orpheus/speakers called; "
        "use GET /tasks/voice/speakers"
    )
    add_deprecation_headers(http_response, SUCCESSOR_VOICES)
    catalog = await service.list_speakers()
    return OrpheusSpeakersResponse(
        default=catalog.default, by_language=catalog.by_language
    )
```

And for `get_speakers_for_language` — add `deprecated=True` to its `@router.get("/speakers/{language}", ...)` decorator, inject `http_response: Response` as the FIRST parameter (before `language: str`), and add the warning + headers:

```python
async def get_speakers_for_language(
    http_response: Response,
    language: str,
    service=Depends(get_orpheus_tts_service),
    current_user=Depends(get_current_user),
) -> OrpheusLanguageSpeakersResponse:
    logger.warning(
        "Deprecated endpoint /tasks/modal/orpheus/speakers/{language} called; "
        "use GET /tasks/voice/speakers"
    )
    add_deprecation_headers(http_response, SUCCESSOR_VOICES)
    speakers = await service.speakers_for_language(language)
    return OrpheusLanguageSpeakersResponse(language=language, speakers=speakers)
```

> `http_response: Response` must precede `language: str`? No — both are non-default, order among
> non-default params is free. Place `http_response` first for clarity. The path param `language`
> is still captured by name from the URL regardless of position.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest app/tests/test_voice_speakers.py -v`
Expected: PASS (all 8).

Confirm no regression in the orpheus router tests and app import:
Run: `python -c "import app.api"` (no error)
Run: `pytest app/tests/test_routers/test_orpheus_tts.py -v` (passes; if a test asserted exact handler signature it may need no change — these are HTTP-level tests)

- [ ] **Step 5: Lint + commit**

```bash
isort app/utils/deprecation.py app/routers/orpheus_tts.py app/routers/tts.py app/tests/test_voice_speakers.py
black app/utils/deprecation.py app/routers/orpheus_tts.py app/routers/tts.py app/tests/test_voice_speakers.py
flake8 app/utils/deprecation.py app/routers/orpheus_tts.py app/routers/tts.py app/tests/test_voice_speakers.py
git add app/utils/deprecation.py app/routers/orpheus_tts.py app/routers/tts.py app/tests/test_voice_speakers.py
git commit -m "feat(tts): deprecate legacy speaker-listing endpoints (flag + headers + log)"
```

flake8 must be clean for these files (the touched handlers are small; pre-existing F401 in `tts.py`
like unused `Request`/`SpeakerID` may remain — do NOT remove pre-existing unused imports).

---

## Task 4: Full verification (Definition of Done)

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `pytest app/tests/ -q`
Expected: no NEW failures vs the branch base. (The 4 pre-existing `test_config.py` GA failures are
environment-dependent and unrelated — confirm the count is unchanged.)

- [ ] **Step 2: Lint the touched files**

Run:
```bash
flake8 app/services/speech_service.py app/routers/audio.py app/utils/deprecation.py app/routers/orpheus_tts.py app/routers/tts.py app/tests/test_speech_service.py app/tests/test_voice_speakers.py
```
Expected: clean for the new/core files; only pre-existing issues (if any) remain in the legacy
routers. Fix anything attributable to this work.

- [ ] **Step 3: Commit any lint fixes**

```bash
git add -A
git commit -m "style(tts): lint fixes for unified voice/speakers endpoint"
```

(Skip if nothing to commit.)

---

## Self-Review Notes

- **Spec coverage:** `list_voices` dispatch + validation (Task 1); `GET /tasks/voice/speakers` with
  `model`/`language` query params, auth, `response_model=None` (Task 2); deprecation of the 3 legacy
  endpoints + `SUCCESSOR_VOICES` (Task 3); tests for all four dispatch branches, auth 401, unknown
  language 400, spark+language 400, and deprecation flags + headers (Tasks 1–3); full suite + lint
  (Task 4). Native pass-through preserved (no reshaping). Out-of-scope items untouched ✅.
- **Type consistency:** `SpeechService.list_voices(model: str, language: Optional[str])` returns one
  of `OrpheusSpeakersResponse` / `OrpheusLanguageSpeakersResponse` / `SpeakersListResponse`; the
  router passes `model.value` (the `TTSModel` enum's string) and returns the result directly with
  `response_model=None`. Schema field names (`default`, `by_language`, `language`, `speakers`,
  `total`/`languages`/`count` computed) match the existing schemas.
- **Known choice:** `response_model=None` means OpenAPI shows no response schema for the unified
  endpoint; the three shapes are documented in the route description and asserted per-case in tests.
- **No quota/RL** on the unified endpoint, matching the legacy listing endpoints (cheap reads).
