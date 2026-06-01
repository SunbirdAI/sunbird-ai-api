# STT Unified Transcription Endpoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single OpenAI-style `POST /tasks/audio/transcriptions` endpoint that consolidates the four legacy STT endpoints behind a service facade, and mark the legacy endpoints deprecated (OpenAPI flag + RFC-8594 headers + log).

**Architecture:** A new thin router (`app/routers/audio.py`) parses the multipart request, enforces quota/rate-limit, and delegates to a new `TranscriptionService` facade (`app/services/transcription_service.py`). The facade validates platform/input/org combinations (→ 400) and dispatches to the existing `STTService` / `ModalSTTService` methods — no business logic is duplicated. The four legacy endpoints in `app/routers/stt.py` keep their bodies and only gain deprecation markers.

**Tech Stack:** FastAPI, async SQLAlchemy, pytest (`asyncio_mode=auto`, in-memory SQLite), RunPod + Modal (mocked in tests).

**Spec:** [docs/superpowers/specs/2026-06-02-stt-unified-endpoint-design.md](../specs/2026-06-02-stt-unified-endpoint-design.md)

---

## File Structure

| File | Responsibility |
|---|---|
| `app/schemas/stt.py` (modify) | Add `TranscriptionPlatform` enum (`modal`/`runpod`) |
| `app/utils/deprecation.py` (create) | Sunset constant + successor URL + header helpers (RFC 8594) |
| `app/services/transcription_service.py` (create) | `TranscriptionService` facade: validate combos + dispatch; `get_transcription_service()` / `reset_transcription_service()` |
| `app/deps.py` (modify) | Register `TranscriptionServiceDep` |
| `app/routers/audio.py` (create) | Unified `POST /tasks/audio/transcriptions` router |
| `app/api.py` (modify) | Mount the audio router under `/tasks` |
| `app/routers/stt.py` (modify) | Add `deprecated=True` + deprecation headers + warning log to the 4 legacy endpoints |
| `app/tests/test_transcription_service.py` (create) | Facade unit tests (validation + dispatch, mocked services) |
| `app/tests/test_audio_transcriptions.py` (create) | Endpoint integration tests + legacy deprecation tests |

**Reference signatures (already in the codebase — do not change):**

```python
# app/services/stt_service.py
@dataclass
class TranscriptionResult:
    transcription: Optional[str]
    diarization_output: Dict[str, Any]
    formatted_diarization_output: str
    audio_url: Optional[str] = None
    blob_name: Optional[str] = None
    was_trimmed: bool = False
    original_duration: Optional[float] = None
    processing_time: Optional[float] = None

class STTService:
    def validate_audio_file(self, content_type: str, file_extension: str) -> None  # raises AudioValidationError
    async def transcribe_from_gcs(self, gcs_blob_name, language="lug", adapter="lug", whisper=False, recognise_speakers=False) -> TranscriptionResult
    async def transcribe_uploaded_file(self, file_path, file_extension, language="lug", adapter="lug", whisper=False, recognise_speakers=False) -> TranscriptionResult
    async def transcribe_org_audio(self, file_path, recognise_speakers=False) -> TranscriptionResult

# app/services/modal_stt_service.py
class ModalSTTService:
    async def transcribe(self, audio_data: bytes, language: Optional[str] = None) -> str

# app/utils/quota_guard.py
async def check_quota(quota: QuotaService, db: AsyncSession, user) -> None  # raises RateLimitError (429)

# app/crud/audio_transcription.py
async def create_audio_transcription(db, user, audio_file_url, filename, transcription, language)  # returns ORM obj with .id

# app/core/exceptions.py — BadRequestError -> 400, ValidationError -> 422, ExternalServiceError -> 502
```

> **Test note:** `conftest.py` has an autouse `stub_quota_service` fixture that makes `check_quota` always allow unless a test is marked `@pytest.mark.real_quota`. New tests therefore do **not** need to set up quota. Feedback background tasks call `app.utils.feedback.save_api_inference`; stub it in endpoint tests to avoid network calls (pattern shown in Task 6).

---

## Task 1: Add `TranscriptionPlatform` enum

**Files:**
- Modify: `app/schemas/stt.py`
- Test: `app/tests/test_transcription_service.py`

- [ ] **Step 1: Write the failing test**

Create `app/tests/test_transcription_service.py`:

```python
"""Unit tests for the TranscriptionService facade and its schema."""

from app.schemas.stt import TranscriptionPlatform


def test_transcription_platform_values():
    assert TranscriptionPlatform.modal.value == "modal"
    assert TranscriptionPlatform.runpod.value == "runpod"
    assert TranscriptionPlatform("modal") is TranscriptionPlatform.modal
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest app/tests/test_transcription_service.py::test_transcription_platform_values -v`
Expected: FAIL with `ImportError: cannot import name 'TranscriptionPlatform'`

- [ ] **Step 3: Add the enum**

In `app/schemas/stt.py`, after the existing `SttbLanguage` enum block, add:

```python
class TranscriptionPlatform(str, Enum):
    """Supported transcription platforms for the unified endpoint.

    Attributes:
        modal: Modal-hosted Whisper ASR.
        runpod: RunPod serverless transcription.
    """

    modal = "modal"
    runpod = "runpod"
```

(`Enum` is already imported at the top of the file.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest app/tests/test_transcription_service.py::test_transcription_platform_values -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/schemas/stt.py app/tests/test_transcription_service.py
git commit -m "feat(stt): add TranscriptionPlatform enum for unified endpoint"
```

---

## Task 2: Deprecation header helper

**Files:**
- Create: `app/utils/deprecation.py`
- Test: `app/tests/test_transcription_service.py`

- [ ] **Step 1: Write the failing test**

Append to `app/tests/test_transcription_service.py`:

```python
from app.utils.deprecation import (
    STT_SUNSET_DATE,
    SUCCESSOR_TRANSCRIPTIONS,
    deprecation_headers,
)


def test_deprecation_headers_contents():
    headers = deprecation_headers(SUCCESSOR_TRANSCRIPTIONS)
    assert headers["Deprecation"] == "true"
    assert headers["Sunset"] == STT_SUNSET_DATE
    assert headers["Link"] == '</tasks/audio/transcriptions>; rel="successor-version"'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest app/tests/test_transcription_service.py::test_deprecation_headers_contents -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.utils.deprecation'`

- [ ] **Step 3: Create the helper**

Create `app/utils/deprecation.py`:

```python
"""Helpers for marking legacy endpoints deprecated via RFC 8594 headers.

Adds standard ``Deprecation`` / ``Sunset`` / ``Link`` response headers so that
programmatic clients can detect a deprecated endpoint and discover its
successor. Pair with ``deprecated=True`` on the route decorator for the
OpenAPI/Swagger signal.
"""

from typing import Dict

from fastapi import Response

# RFC 7231 HTTP-date. 2026-12-01 is a Tuesday.
STT_SUNSET_DATE = "Tue, 01 Dec 2026 00:00:00 GMT"

# Successor endpoint for the legacy STT routes.
SUCCESSOR_TRANSCRIPTIONS = "/tasks/audio/transcriptions"


def deprecation_headers(successor: str, sunset: str = STT_SUNSET_DATE) -> Dict[str, str]:
    """Build RFC-8594 deprecation headers pointing at a successor endpoint.

    Args:
        successor: Path of the replacement endpoint.
        sunset: HTTP-date string for the planned removal date.

    Returns:
        A dict of header name -> value.
    """
    return {
        "Deprecation": "true",
        "Sunset": sunset,
        "Link": f'<{successor}>; rel="successor-version"',
    }


def add_deprecation_headers(
    response: Response, successor: str, sunset: str = STT_SUNSET_DATE
) -> None:
    """Set RFC-8594 deprecation headers on an injected FastAPI ``Response``.

    Use this when the handler returns a Pydantic model (FastAPI merges the
    injected response's headers into the final response). For handlers that
    return a raw ``Response`` object, pass ``deprecation_headers(...)`` to that
    object's ``headers=`` argument instead.
    """
    for key, value in deprecation_headers(successor, sunset).items():
        response.headers[key] = value
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest app/tests/test_transcription_service.py::test_deprecation_headers_contents -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/utils/deprecation.py app/tests/test_transcription_service.py
git commit -m "feat(stt): add RFC-8594 deprecation header helper"
```

---

## Task 3: `TranscriptionService` facade

**Files:**
- Create: `app/services/transcription_service.py`
- Test: `app/tests/test_transcription_service.py`

- [ ] **Step 1: Write the failing tests**

Append to `app/tests/test_transcription_service.py`:

```python
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import BadRequestError
from app.services.stt_service import TranscriptionResult
from app.services.transcription_service import TranscriptionService


def make_facade():
    stt = MagicMock()
    stt.validate_audio_file = MagicMock(return_value=None)
    stt.transcribe_from_gcs = AsyncMock(
        return_value=TranscriptionResult(
            transcription="gcs text",
            diarization_output={},
            formatted_diarization_output="",
            audio_url="gs://bucket/a.wav",
            blob_name="a.wav",
        )
    )
    stt.transcribe_uploaded_file = AsyncMock(
        return_value=TranscriptionResult(
            transcription="upload text",
            diarization_output={},
            formatted_diarization_output="",
            audio_url="gs://bucket/u.wav",
            blob_name="u.wav",
        )
    )
    stt.transcribe_org_audio = AsyncMock(
        return_value=TranscriptionResult(
            transcription="org text",
            diarization_output={},
            formatted_diarization_output="",
        )
    )
    modal = MagicMock()
    modal.transcribe = AsyncMock(return_value="modal text")
    return TranscriptionService(stt_service=stt, modal_stt_service=modal), stt, modal


# --- validate_and_normalize ---

def test_validate_runpod_defaults_true_when_omitted():
    facade, _, _ = make_facade()
    whisper, speakers = facade.validate_and_normalize(
        platform="runpod", has_audio=True, gcs_blob_name=None,
        org=False, whisper=None, recognise_speakers=None,
    )
    assert whisper is True
    assert speakers is True


def test_validate_runpod_respects_explicit_false():
    facade, _, _ = make_facade()
    whisper, speakers = facade.validate_and_normalize(
        platform="runpod", has_audio=True, gcs_blob_name=None,
        org=False, whisper=False, recognise_speakers=False,
    )
    assert whisper is False
    assert speakers is False


def test_validate_rejects_no_input():
    facade, _, _ = make_facade()
    with pytest.raises(BadRequestError):
        facade.validate_and_normalize(
            platform="runpod", has_audio=False, gcs_blob_name=None,
            org=False, whisper=None, recognise_speakers=None,
        )


def test_validate_rejects_both_inputs():
    facade, _, _ = make_facade()
    with pytest.raises(BadRequestError):
        facade.validate_and_normalize(
            platform="runpod", has_audio=True, gcs_blob_name="a.wav",
            org=False, whisper=None, recognise_speakers=None,
        )


def test_validate_rejects_modal_with_gcs():
    facade, _, _ = make_facade()
    with pytest.raises(BadRequestError):
        facade.validate_and_normalize(
            platform="modal", has_audio=False, gcs_blob_name="a.wav",
            org=False, whisper=None, recognise_speakers=None,
        )


def test_validate_rejects_modal_with_org():
    facade, _, _ = make_facade()
    with pytest.raises(BadRequestError):
        facade.validate_and_normalize(
            platform="modal", has_audio=True, gcs_blob_name=None,
            org=True, whisper=None, recognise_speakers=None,
        )


def test_validate_rejects_modal_with_runpod_only_flags():
    facade, _, _ = make_facade()
    with pytest.raises(BadRequestError):
        facade.validate_and_normalize(
            platform="modal", has_audio=True, gcs_blob_name=None,
            org=False, whisper=True, recognise_speakers=None,
        )


# --- transcribe dispatch ---

async def test_transcribe_dispatches_modal():
    facade, stt, modal = make_facade()
    result = await facade.transcribe(
        platform="modal", language="lug", adapter="lug", audio_bytes=b"xx",
    )
    modal.transcribe.assert_awaited_once_with(b"xx", language="lug")
    assert result.transcription == "modal text"
    stt.transcribe_uploaded_file.assert_not_called()


async def test_transcribe_dispatches_gcs():
    facade, stt, _ = make_facade()
    result = await facade.transcribe(
        platform="runpod", language="lug", adapter="lug",
        gcs_blob_name="a.wav", whisper=True, recognise_speakers=True,
    )
    stt.transcribe_from_gcs.assert_awaited_once()
    assert result.transcription == "gcs text"


async def test_transcribe_dispatches_uploaded():
    facade, stt, _ = make_facade()
    result = await facade.transcribe(
        platform="runpod", language="lug", adapter="lug", org=False,
        whisper=True, recognise_speakers=True,
        file_path="/tmp/u.wav", file_extension=".wav", content_type="audio/wav",
    )
    stt.validate_audio_file.assert_called_once_with("audio/wav", ".wav")
    stt.transcribe_uploaded_file.assert_awaited_once()
    assert result.transcription == "upload text"


async def test_transcribe_dispatches_org():
    facade, stt, _ = make_facade()
    result = await facade.transcribe(
        platform="runpod", language="lug", adapter="lug", org=True,
        recognise_speakers=True,
        file_path="/tmp/o.wav", file_extension=".wav", content_type="audio/wav",
    )
    stt.validate_audio_file.assert_called_once_with("audio/wav", ".wav")
    stt.transcribe_org_audio.assert_awaited_once_with(
        file_path="/tmp/o.wav", recognise_speakers=True
    )
    assert result.transcription == "org text"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest app/tests/test_transcription_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.transcription_service'`

- [ ] **Step 3: Create the facade**

Create `app/services/transcription_service.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest app/tests/test_transcription_service.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Commit**

```bash
git add app/services/transcription_service.py app/tests/test_transcription_service.py
git commit -m "feat(stt): add TranscriptionService facade with validation and dispatch"
```

---

## Task 4: Register `TranscriptionServiceDep`

**Files:**
- Modify: `app/deps.py`

- [ ] **Step 1: Write the failing test**

Append to `app/tests/test_transcription_service.py`:

```python
def test_transcription_service_dep_is_exported():
    import app.deps as deps

    assert hasattr(deps, "TranscriptionServiceDep")
    assert "TranscriptionServiceDep" in deps.__all__
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest app/tests/test_transcription_service.py::test_transcription_service_dep_is_exported -v`
Expected: FAIL with `AssertionError`

- [ ] **Step 3: Register the dependency**

In `app/deps.py`:

1. Add the import near the other service imports (after the `stt_service` import line ~56):

```python
from app.services.transcription_service import (
    TranscriptionService,
    get_transcription_service,
)
```

2. Add the alias near the other `*ServiceDep` aliases (after `ModalSTTServiceDep` ~line 71):

```python
TranscriptionServiceDep = Annotated[
    TranscriptionService, Depends(get_transcription_service)
]
```

3. Add `"TranscriptionServiceDep"` and `"TranscriptionService"` to the `__all__` list (next to `"ModalSTTServiceDep"` and `"ModalSTTService"` respectively).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest app/tests/test_transcription_service.py::test_transcription_service_dep_is_exported -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/deps.py app/tests/test_transcription_service.py
git commit -m "feat(deps): register TranscriptionServiceDep"
```

---

## Task 5: Unified `POST /tasks/audio/transcriptions` router

**Files:**
- Create: `app/routers/audio.py`
- Modify: `app/api.py`
- Test: `app/tests/test_audio_transcriptions.py`

- [ ] **Step 1: Write the failing tests**

Create `app/tests/test_audio_transcriptions.py`:

```python
"""Integration tests for the unified POST /tasks/audio/transcriptions endpoint."""

import io
from typing import Dict
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.api import app
from app.deps import get_transcription_service
from app.services.stt_service import TranscriptionResult


@pytest.fixture(autouse=True)
def stub_feedback(monkeypatch):
    """Prevent the BackgroundTasks feedback save from making network calls."""
    async def noop_save(*args, **kwargs):
        return None

    import app.utils.feedback as feedback_module
    monkeypatch.setattr(feedback_module, "save_api_inference", noop_save, raising=False)
    import app.routers.stt as stt_module
    monkeypatch.setattr(stt_module, "save_api_inference", noop_save, raising=False)
    yield


@pytest.fixture
def fake_facade():
    """Override the facade dependency with a mock; restore afterward."""
    facade = MagicMock()
    facade.validate_and_normalize = MagicMock(return_value=(True, True))
    facade.transcribe = AsyncMock(
        return_value=TranscriptionResult(
            transcription="hello world",
            diarization_output={},
            formatted_diarization_output="",
            audio_url="gs://bucket/a.wav",
            blob_name="a.wav",
        )
    )
    app.dependency_overrides[get_transcription_service] = lambda: facade
    yield facade
    app.dependency_overrides.pop(get_transcription_service, None)


def audio_part():
    return {"audio": ("sample.wav", io.BytesIO(b"RIFFfake"), "audio/wav")}


async def test_modal_upload_returns_200(
    authenticated_client: AsyncClient, fake_facade, test_user: Dict
):
    resp = await authenticated_client.post(
        "/tasks/audio/transcriptions",
        data={"language": "lug", "platform": "modal"},
        files=audio_part(),
    )
    assert resp.status_code == 200
    assert resp.json()["audio_transcription"] == "hello world"
    # Modal path → not persisted, no DB id.
    assert resp.json()["audio_transcription_id"] is None
    _, kwargs = fake_facade.transcribe.call_args
    assert kwargs["platform"] == "modal"


async def test_runpod_upload_returns_200(
    authenticated_client: AsyncClient, fake_facade, test_user: Dict
):
    resp = await authenticated_client.post(
        "/tasks/audio/transcriptions",
        data={"language": "lug", "platform": "runpod"},
        files=audio_part(),
    )
    assert resp.status_code == 200
    _, kwargs = fake_facade.transcribe.call_args
    assert kwargs["platform"] == "runpod"
    assert kwargs["whisper"] is True
    assert kwargs["recognise_speakers"] is True


async def test_runpod_gcs_returns_200(
    authenticated_client: AsyncClient, fake_facade, test_user: Dict
):
    resp = await authenticated_client.post(
        "/tasks/audio/transcriptions",
        data={
            "language": "lug",
            "platform": "runpod",
            "gcs_blob_name": "audio/file.wav",
        },
    )
    assert resp.status_code == 200
    _, kwargs = fake_facade.transcribe.call_args
    assert kwargs["gcs_blob_name"] == "audio/file.wav"


async def test_invalid_combo_returns_400(
    authenticated_client: AsyncClient, test_user: Dict
):
    """A real facade should reject modal+gcs with 400 (no override here)."""
    resp = await authenticated_client.post(
        "/tasks/audio/transcriptions",
        data={
            "language": "lug",
            "platform": "modal",
            "gcs_blob_name": "audio/file.wav",
        },
    )
    assert resp.status_code == 400


async def test_requires_authentication(async_client: AsyncClient):
    resp = await async_client.post(
        "/tasks/audio/transcriptions",
        data={"language": "lug", "platform": "modal"},
        files=audio_part(),
    )
    assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest app/tests/test_audio_transcriptions.py -v`
Expected: FAIL — endpoint returns 404 (route not mounted) / ImportError on `get_transcription_service` if Task 4 incomplete.

- [ ] **Step 3: Create the router**

Create `app/routers/audio.py`:

```python
"""Unified audio router (OpenAI-style).

Hosts the consolidated Speech-to-Text endpoint ``POST /tasks/audio/transcriptions``
that supersedes the legacy /stt, /stt_from_gcs, /org/stt, and /modal/stt routes.
The text-to-speech endpoint (/tasks/audio/speech) will be added in Phase 2.
"""

import logging
import os
import tempfile
import time
from typing import Optional

import aiofiles
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Request,
    UploadFile,
)
from fastapi import Response as FastAPIResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BadRequestError,
    ExternalServiceError,
    ServiceUnavailableError,
    ValidationError,
)
from app.crud.audio_transcription import create_audio_transcription
from app.deps import (
    QuotaServiceDep,
    TranscriptionServiceDep,
    get_current_user,
    get_db,
)
from app.routers.stt import _schedule_stt_feedback
from app.schemas.stt import CHUNK_SIZE, STTTranscript, SttbLanguage, TranscriptionPlatform
from app.services.stt_service import (
    AudioProcessingError,
    AudioValidationError,
    TranscriptionError,
)
from app.utils.audio import get_audio_extension
from app.utils.quota_guard import check_quota
from app.utils.rate_limit import get_account_type_limit, limiter

logging.basicConfig(level=logging.INFO)

router = APIRouter()


@router.post(
    "/audio/transcriptions",
    response_model=STTTranscript,
    summary="Transcribe audio (unified STT endpoint)",
    description=(
        "Unified Speech-to-Text endpoint. Accepts an uploaded audio file or a "
        "GCS blob, routes to Modal or RunPod, and supports the RunPod "
        "organization workflow. Replaces /stt, /stt_from_gcs, /org/stt, and "
        "/modal/stt."
    ),
)
@limiter.limit(get_account_type_limit)
async def create_transcription(
    request: Request,
    background_tasks: BackgroundTasks,
    quota: QuotaServiceDep,
    transcription_service: TranscriptionServiceDep,
    language: SttbLanguage = Form(..., description="Target language code."),
    audio: Optional[UploadFile] = File(
        default=None, description="Audio file to transcribe."
    ),
    gcs_blob_name: Optional[str] = Form(
        default=None, description="GCS blob name (RunPod only)."
    ),
    platform: TranscriptionPlatform = Form(
        default=TranscriptionPlatform.modal,
        description="Transcription platform: 'modal' (default) or 'runpod'.",
    ),
    adapter: Optional[SttbLanguage] = Form(
        default=None, description="Language adapter (RunPod only). Defaults to language."
    ),
    whisper: Optional[bool] = Form(
        default=None, description="Use Whisper (RunPod only). Defaults to true."
    ),
    recognise_speakers: Optional[bool] = Form(
        default=None,
        description="Speaker diarization (RunPod only). Defaults to true.",
    ),
    org: bool = Form(
        default=False, description="Use the RunPod organization workflow."
    ),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> STTTranscript:
    """Transcribe audio via the selected platform and workflow."""
    await check_quota(quota, db, current_user)
    start_time = time.time()

    has_audio = audio is not None and bool(audio.filename)
    # Raises BadRequestError (400) on unsupported combinations.
    resolved_whisper, resolved_speakers = transcription_service.validate_and_normalize(
        platform=platform.value,
        has_audio=has_audio,
        gcs_blob_name=gcs_blob_name,
        org=org,
        whisper=whisper,
        recognise_speakers=recognise_speakers,
    )
    adapter_value = (adapter or language).value

    file_path: Optional[str] = None
    try:
        if platform == TranscriptionPlatform.modal:
            audio_bytes = await audio.read()
            result = await transcription_service.transcribe(
                platform="modal",
                language=language.value,
                adapter=adapter_value,
                audio_bytes=audio_bytes,
            )
        elif gcs_blob_name:
            result = await transcription_service.transcribe(
                platform="runpod",
                language=language.value,
                adapter=adapter_value,
                gcs_blob_name=gcs_blob_name,
                whisper=resolved_whisper,
                recognise_speakers=resolved_speakers,
            )
        else:
            # RunPod uploaded file (org or standard). Stream to a temp file.
            content_type = audio.content_type
            file_extension = get_audio_extension(audio.filename)
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=file_extension
            ) as temp_file:
                file_path = temp_file.name
                async with aiofiles.open(file_path, "wb") as out_file:
                    while content := await audio.read(CHUNK_SIZE):
                        await out_file.write(content)
            result = await transcription_service.transcribe(
                platform="runpod",
                language=language.value,
                adapter=adapter_value,
                org=org,
                whisper=resolved_whisper,
                recognise_speakers=resolved_speakers,
                file_path=file_path,
                file_extension=file_extension,
                content_type=content_type,
            )

        elapsed_time = time.time() - start_time

        # Persist only for RunPod non-org paths (parity with legacy /stt,
        # /stt_from_gcs). Org and Modal paths are not persisted.
        audio_transcription_id = None
        should_persist = platform == TranscriptionPlatform.runpod and not org
        if should_persist and result.transcription:
            try:
                db_obj = await create_audio_transcription(
                    db,
                    current_user,
                    result.audio_url,
                    result.blob_name,
                    result.transcription,
                    language.value,
                )
                audio_transcription_id = db_obj.id
            except Exception as e:
                logging.error(f"Database error: {str(e)}")

        response = STTTranscript(
            audio_transcription=result.transcription,
            diarization_output=result.diarization_output,
            formatted_diarization_output=result.formatted_diarization_output,
            audio_transcription_id=audio_transcription_id,
            audio_url=result.audio_url,
            language=language.value,
            was_audio_trimmed=result.was_trimmed,
            original_duration_minutes=result.original_duration
            if result.was_trimmed
            else None,
        )

        _schedule_stt_feedback(
            background_tasks=background_tasks,
            user=current_user,
            source=gcs_blob_name or (audio.filename if audio else "uploaded_audio"),
            transcription=result.transcription,
            audio_url=result.audio_url,
            blob_name=result.blob_name,
            language=language.value,
            adapter=adapter_value,
            whisper=resolved_whisper if platform == TranscriptionPlatform.runpod else True,
            processing_time=elapsed_time,
            model_type="whisper-modal"
            if platform == TranscriptionPlatform.modal
            else None,
            org=org,
        )

        return response

    except AudioValidationError as e:
        raise ValidationError(
            message=str(e), errors=[{"field": "audio", "value": None}]
        )
    except AudioProcessingError as e:
        raise BadRequestError(message=str(e))
    except TranscriptionError as e:
        raise ExternalServiceError(
            service_name="STT Transcription Service", message=str(e)
        )
    except (BadRequestError, ValidationError, ExternalServiceError, ServiceUnavailableError):
        raise
    except Exception as e:
        logging.error(f"Unexpected error in create_transcription: {str(e)}")
        raise ExternalServiceError(
            service_name="STT Service",
            message="An unexpected error occurred while processing your request",
            original_error=str(e),
        )
    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass
```

- [ ] **Step 4: Mount the router in `app/api.py`**

1. Add the import next to the other router imports (after the `stt` import ~line 36):

```python
from app.routers.audio import router as audio_router
```

2. Add the include next to the `stt_router` include (after ~line 169):

```python
app.include_router(
    audio_router, prefix="/tasks", tags=["Speech-to-Text (Unified)"]
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest app/tests/test_audio_transcriptions.py -v`
Expected: PASS (all tests)

- [ ] **Step 6: Commit**

```bash
git add app/routers/audio.py app/api.py app/tests/test_audio_transcriptions.py
git commit -m "feat(stt): add unified POST /tasks/audio/transcriptions endpoint"
```

---

## Task 6: Deprecate the 4 legacy STT endpoints

**Files:**
- Modify: `app/routers/stt.py`
- Test: `app/tests/test_audio_transcriptions.py`

- [ ] **Step 1: Write the failing tests**

Append to `app/tests/test_audio_transcriptions.py`:

```python
async def test_openapi_marks_legacy_stt_deprecated(async_client: AsyncClient):
    resp = await async_client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    for path in ["/tasks/stt", "/tasks/stt_from_gcs", "/tasks/org/stt", "/tasks/modal/stt"]:
        assert paths[path]["post"].get("deprecated") is True, path


async def test_legacy_modal_stt_returns_deprecation_headers(
    authenticated_client: AsyncClient, test_user: Dict, monkeypatch
):
    """The legacy /modal/stt route should carry RFC-8594 headers."""
    from app.deps import get_modal_stt_service

    fake = MagicMock()
    fake.transcribe = AsyncMock(return_value="legacy text")
    app.dependency_overrides[get_modal_stt_service] = lambda: fake
    try:
        resp = await authenticated_client.post(
            "/tasks/modal/stt",
            data={"language": "lug"},
            files=audio_part(),
        )
    finally:
        app.dependency_overrides.pop(get_modal_stt_service, None)

    assert resp.status_code == 200
    assert resp.headers.get("Deprecation") == "true"
    assert "Sunset" in resp.headers
    assert 'rel="successor-version"' in resp.headers.get("Link", "")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest app/tests/test_audio_transcriptions.py::test_openapi_marks_legacy_stt_deprecated app/tests/test_audio_transcriptions.py::test_legacy_modal_stt_returns_deprecation_headers -v`
Expected: FAIL — `deprecated` is absent and `Deprecation` header is missing.

- [ ] **Step 3: Add markers to `app/routers/stt.py`**

3a. Add the import near the top (after the existing `app.utils` imports):

```python
from app.utils.deprecation import (
    SUCCESSOR_TRANSCRIPTIONS,
    add_deprecation_headers,
    deprecation_headers,
)
```

3b. **`/stt_from_gcs`** — set `deprecated=True`, inject `http_response`, add a warning log, set headers on both return paths.

Change the decorator and signature:

```python
@router.post("/stt_from_gcs", deprecated=True)
async def speech_to_text_from_gcs(
    request: Request,
    background_tasks: BackgroundTasks,
    http_response: Response,
    gcs_blob_name: str = Form(...),
    language: SttbLanguage = Form(SttbLanguage.luganda),
    adapter: SttbLanguage = Form(SttbLanguage.luganda),
    recognise_speakers: bool = Form(False),
    whisper: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    service: STTService = Depends(get_service),
) -> STTTranscript:
```

Immediately after `start_time = time.time()`, add:

```python
    logging.warning(
        "Deprecated endpoint /tasks/stt_from_gcs called; "
        "use POST /tasks/audio/transcriptions"
    )
    add_deprecation_headers(http_response, SUCCESSOR_TRANSCRIPTIONS)
```

In the trimmed-audio branch, change the raw `Response` return to include headers:

```python
        if result.was_trimmed:
            return Response(
                content=response.model_dump_json(),
                media_type="application/json",
                headers=deprecation_headers(SUCCESSOR_TRANSCRIPTIONS),
            )
```

3c. **`/stt`** — same pattern. Decorator becomes `@router.post("/stt", deprecated=True)`. Add `http_response: Response` to the signature (e.g. right after `quota: QuotaServiceDep,`). After `start_time = time.time()` (just below `await check_quota(...)`), add the warning log + `add_deprecation_headers(http_response, SUCCESSOR_TRANSCRIPTIONS)`. Update the trimmed branch's raw `Response(...)` to pass `headers=deprecation_headers(SUCCESSOR_TRANSCRIPTIONS)`.

3d. **`/org/stt`** — decorator becomes `@router.post("/org/stt", deprecated=True)`. Add `http_response: Response` after `quota: QuotaServiceDep,`. After `start_time = time.time()`, add:

```python
    logging.warning(
        "Deprecated endpoint /tasks/org/stt called; "
        "use POST /tasks/audio/transcriptions"
    )
    add_deprecation_headers(http_response, SUCCESSOR_TRANSCRIPTIONS)
```

(This handler returns the `STTTranscript` model directly, so the injected `http_response` headers are merged automatically — no raw `Response` branch to change.)

3e. **`/modal/stt`** — add `deprecated=True` to the existing decorator kwargs:

```python
@router.post(
    "/modal/stt",
    response_model=STTTranscript,
    deprecated=True,
    summary="Transcribe Audio via Modal Whisper ASR",
    description=(
        "Upload an audio file and get transcription using the Modal-hosted "
        "Whisper model. Optionally specify a language to improve accuracy."
    ),
)
```

Add `http_response: Response` after `quota: QuotaServiceDep,`. After `start_time = time.time()`, add:

```python
    logging.warning(
        "Deprecated endpoint /tasks/modal/stt called; "
        "use POST /tasks/audio/transcriptions"
    )
    add_deprecation_headers(http_response, SUCCESSOR_TRANSCRIPTIONS)
```

> Note: `Response` is already imported in `app/routers/stt.py` (from `fastapi`). No new fastapi import needed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest app/tests/test_audio_transcriptions.py -v`
Expected: PASS (including the two new deprecation tests)

- [ ] **Step 5: Commit**

```bash
git add app/routers/stt.py app/tests/test_audio_transcriptions.py
git commit -m "feat(stt): deprecate legacy STT endpoints (OpenAPI flag + RFC-8594 headers + log)"
```

---

## Task 7: Full verification (Definition of Done)

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `pytest app/tests/ -v`
Expected: PASS (no failures, no errors). Investigate and fix any regression before continuing.

- [ ] **Step 2: Run lint check**

Run: `make lint-check`
Expected: black, isort, and flake8 all report clean. If not, run `make lint-apply` and re-run `make lint-check`.

- [ ] **Step 3: Commit any lint fixes**

```bash
git add -A
git commit -m "style(stt): lint fixes for unified transcription endpoint"
```

(Skip if there is nothing to commit.)

---

## Self-Review Notes

- **Spec coverage:** unified endpoint (Task 5), `TranscriptionService` facade (Task 3), `TranscriptionPlatform` enum (Task 1), validation → 400 (Task 3 + Task 5 test), RunPod `true` defaults (Task 3 + Task 5 test), quota/RL on all paths (Task 5 `check_quota` + `@limiter.limit`), DB-save parity (Task 5 `should_persist`), deprecation flag + headers + log (Task 6), tests + lint (Task 7). Legacy bodies otherwise unchanged ✅.
- **Out of scope (unchanged):** `tts.py`, `runpod_tts.py`, `orpheus_tts.py`, `tasks.py`. No legacy endpoint removal.
- **Type consistency:** facade methods `validate_and_normalize(...) -> (bool, bool)` and `transcribe(...) -> TranscriptionResult` are used identically in the router and tests; `TranscriptionPlatform.value` strings (`"modal"`/`"runpod"`) are what the facade compares against.
- **Known risk (from spec):** `Optional[bool] = Form(None)` must parse an omitted field as `None` (not `False`) for the modal-flag rejection rule. Covered indirectly by `test_runpod_upload_returns_200` (omitted → defaults to `True`) and `test_validate_rejects_modal_with_runpod_only_flags`. If the endpoint test shows omitted booleans arriving as `False`, switch those form params to a sentinel string or document the limitation.
