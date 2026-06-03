# TTS Unified Speech Endpoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single OpenAI-style `POST /tasks/audio/speech` endpoint that consolidates spark-tts (Modal + RunPod) and orpheus-3b-tts (Modal) single-utterance synthesis behind a `SpeechService` facade, and mark the legacy synthesis endpoints deprecated.

**Architecture:** A thin handler on the existing `app/routers/audio.py` parses a JSON `SpeechRequest`, enforces quota/rate-limit, and delegates to a new `SpeechService` facade. The facade validates (model/platform/param/voice/text-length → 400) and dispatches to `OrpheusTTSService`, `TTSService` (Modal spark), or a new `RunpodSparkTTSService` (extracted from the inline RunPod call), normalizing each provider's result into a `SpeechResult`. Streaming modes reuse the existing `app/routers/tts.py` helpers.

**Tech Stack:** FastAPI, async SQLAlchemy, pytest (`asyncio_mode=auto`, in-memory SQLite), Modal + RunPod + GCS (all mocked in tests).

**Spec:** [docs/superpowers/specs/2026-06-02-tts-unified-speech-endpoint-design.md](../specs/2026-06-02-tts-unified-speech-endpoint-design.md)

---

## File Structure

| File | Responsibility |
|---|---|
| `app/utils/deprecation.py` (modify) | Add neutral `SUNSET_DATE` (keep `STT_SUNSET_DATE` alias) + `SUCCESSOR_SPEECH` |
| `app/schemas/speech.py` (create) | `TTSModel`, `TTSPlatform`, `SpeechRequest`, `SpeechResponse` |
| `app/services/runpod_tts_service.py` (create) | `RunpodSparkTTSService` (extracted RunPod call + retry + error mapping) + singleton |
| `app/services/speech_service.py` (create) | `SpeechService` facade + `SpeechResult` + singleton |
| `app/deps.py` (modify) | `SpeechServiceDep`, `RunpodSparkTTSServiceDep` |
| `app/routers/audio.py` (modify) | `POST /audio/speech` (url + stream/both) |
| `app/routers/runpod_tts.py` (modify) | Delegate the endpoint body to `RunpodSparkTTSService` |
| `app/routers/tts.py`, `orpheus_tts.py`, `tasks.py` (modify) | Deprecation markers on synthesis endpoints |
| `app/tests/test_speech_service.py` (create) | Facade + RunpodSparkTTSService unit tests |
| `app/tests/test_audio_speech.py` (create) | Endpoint + deprecation tests |

**Reference signatures (already in the codebase — do not change):**

```python
# app/models/enums.py
class TTSResponseMode(str, Enum): URL="url"; STREAM="stream"; BOTH="both"
class SpeakerID(int, Enum):  # ACHOLI_FEMALE=241, ATESO_FEMALE=242, RUNYANKORE_FEMALE=243,
                             # LUGBARA_FEMALE=245, SWAHILI_MALE=246, LUGANDA_FEMALE=248
    @property
    def display_name(self) -> str: ...

# app/services/tts_service.py — Modal spark
class TTSService:
    async def generate_audio(self, text: str, speaker_id: int | SpeakerID) -> bytes
    async def generate_audio_stream(self, text, speaker_id, chunk_size=8192) -> AsyncGenerator[bytes, None]
    @staticmethod
    def estimate_duration(text: str, words_per_minute: int = 150) -> float
def get_tts_service() -> TTSService

# app/services/orpheus_tts_service.py — Orpheus
@dataclass
class SynthesizeResult:
    audio_url: str; audio_url_expires_at: datetime; speaker_id: str; language: Optional[str]
    sample_rate: int; duration_seconds: float; chunks: Optional[int]; audio_size_bytes: int
    gcs_object: str; inference_ms: float; upload_ms: float; signed_url_ms: float; total_ms: float
class OrpheusTTSService:
    async def synthesize(self, *, text, speaker_id, language=None, seed=None,
        temperature=0.6, top_p=0.95, repetition_penalty=1.1, max_tokens=1200) -> SynthesizeResult
def get_orpheus_tts_service() -> OrpheusTTSService

# app/utils/storage.py — legacy GCS (Modal spark)
class GCPStorageService:
    def generate_file_name(self, text, speaker_id) -> str
    async def upload_audio_async(self, audio_data, file_name) -> blob
    def generate_signed_url(self, blob) -> tuple[str, datetime]
def get_storage_service() -> GCPStorageService   # imported in deps as get_legacy_storage_service

# app/routers/tts.py — streaming helpers (reused by the unified router)
async def _stream_audio(request: TTSRequest, tts_service) -> StreamingResponse
async def _stream_audio_with_url(request: TTSRequest, storage_service, tts_service) -> StreamingResponse
# app/schemas/tts.py
class TTSRequest(BaseModel): text: str; speaker_id: SpeakerID = 248; response_mode: TTSResponseMode = "url"

# app/utils/feedback.py
INFERENCE_TYPES = {"tts": "tts", ...}
async def save_api_inference(source, results, user, *, model_type=None, processing_time=None, inference_type=None, job_details=None)

# app/core/exceptions.py — BadRequestError -> 400, ServiceUnavailableError -> 503, ExternalServiceError -> 502
```

> **Test note:** `conftest.py`'s autouse `stub_quota_service` makes `check_quota` always allow unless a test is `@pytest.mark.real_quota`. Feedback uses `app.utils.feedback.save_api_inference`; stub it in endpoint tests (pattern shown in Task 6). TTS endpoints do **not** write to the DB.

---

## Task 1: Generalize the deprecation helper

**Files:**
- Modify: `app/utils/deprecation.py`
- Test: `app/tests/test_speech_service.py`

- [ ] **Step 1: Write the failing test**

Create `app/tests/test_speech_service.py`:

```python
"""Unit tests for the TTS unified speech facade and helpers."""

from app.utils.deprecation import (
    SUCCESSOR_SPEECH,
    SUNSET_DATE,
    STT_SUNSET_DATE,
    deprecation_headers,
)


def test_speech_successor_and_sunset_constants():
    assert SUCCESSOR_SPEECH == "/tasks/audio/speech"
    # STT alias preserved for Phase 1.
    assert STT_SUNSET_DATE == SUNSET_DATE


def test_deprecation_headers_for_speech():
    headers = deprecation_headers(SUCCESSOR_SPEECH)
    assert headers["Deprecation"] == "true"
    assert headers["Sunset"] == SUNSET_DATE
    assert headers["Link"] == '</tasks/audio/speech>; rel="successor-version"'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest app/tests/test_speech_service.py -v`
Expected: FAIL with `ImportError: cannot import name 'SUCCESSOR_SPEECH'`

- [ ] **Step 3: Edit `app/utils/deprecation.py`**

Replace the two constant lines:

```python
STT_SUNSET_DATE = "Tue, 01 Dec 2026 00:00:00 GMT"

# Successor endpoint for the legacy STT routes.
SUCCESSOR_TRANSCRIPTIONS = "/tasks/audio/transcriptions"
```

with:

```python
# RFC 7231 HTTP-date. 2026-12-01 is a Tuesday. Shared sunset horizon for all
# deprecated /tasks endpoints.
SUNSET_DATE = "Tue, 01 Dec 2026 00:00:00 GMT"

# Backwards-compatible alias (Phase 1 STT).
STT_SUNSET_DATE = SUNSET_DATE

# Successor endpoints.
SUCCESSOR_TRANSCRIPTIONS = "/tasks/audio/transcriptions"
SUCCESSOR_SPEECH = "/tasks/audio/speech"
```

Then change both function default args from `sunset: str = STT_SUNSET_DATE` to `sunset: str = SUNSET_DATE` (in `deprecation_headers` and `add_deprecation_headers`).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest app/tests/test_speech_service.py -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add app/utils/deprecation.py app/tests/test_speech_service.py
git commit -m "feat(tts): add SUCCESSOR_SPEECH + neutral SUNSET_DATE to deprecation helper"
```

---

## Task 2: `SpeechRequest` / `SpeechResponse` schemas

**Files:**
- Create: `app/schemas/speech.py`
- Test: `app/tests/test_speech_service.py`

- [ ] **Step 1: Write the failing test**

Append to `app/tests/test_speech_service.py`:

```python
from app.schemas.speech import SpeechRequest, SpeechResponse, TTSModel, TTSPlatform


def test_speech_request_defaults():
    req = SpeechRequest(text="hello")
    assert req.model is TTSModel.orpheus_3b_tts
    assert req.platform is TTSPlatform.modal
    assert req.response_mode.value == "url"
    assert req.voice is None
    assert req.temperature is None


def test_tts_enum_values():
    assert TTSModel.orpheus_3b_tts.value == "orpheus-3b-tts"
    assert TTSModel.spark_tts.value == "spark-tts"
    assert TTSPlatform.modal.value == "modal"
    assert TTSPlatform.runpod.value == "runpod"


def test_speech_response_minimal():
    resp = SpeechResponse(audio_url="https://x/y.wav", model="spark-tts", platform="runpod", voice="luganda_female")
    assert resp.audio_url == "https://x/y.wav"
    assert resp.sample_rate is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest app/tests/test_speech_service.py -k speech_request -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.schemas.speech'`

- [ ] **Step 3: Create `app/schemas/speech.py`**

```python
"""Schemas for the unified Text-to-Speech endpoint (/tasks/audio/speech)."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator

from app.models.enums import TTSResponseMode  # reused: url | stream | both


class TTSModel(str, Enum):
    """Supported TTS models for the unified endpoint."""

    orpheus_3b_tts = "orpheus-3b-tts"
    spark_tts = "spark-tts"


class TTSPlatform(str, Enum):
    """Supported TTS platforms for the unified endpoint."""

    modal = "modal"
    runpod = "runpod"


class SpeechRequest(BaseModel):
    """Unified text-to-speech request.

    Some fields apply only to specific model/platform combinations; the
    SpeechService validates combinations and returns 400 on a mismatch.
    """

    text: str = Field(..., min_length=1, max_length=10000, description="Text to synthesize.")
    model: TTSModel = Field(
        default=TTSModel.orpheus_3b_tts, description="TTS model."
    )
    platform: TTSPlatform = Field(
        default=TTSPlatform.modal, description="Inference platform."
    )
    voice: Optional[str] = Field(
        default=None,
        description="Voice/speaker. spark-tts: SpeakerID name (e.g. 'luganda_female') "
        "or id (e.g. '248'); orpheus-3b-tts: catalog tag (e.g. 'salt_lug_0001').",
    )
    response_mode: TTSResponseMode = Field(
        default=TTSResponseMode.URL,
        description="url (signed URL), stream (raw audio), or both (SSE). "
        "stream/both require model='spark-tts' on platform='modal'.",
    )
    language: Optional[str] = Field(default=None, description="orpheus only (ISO 639-3).")
    temperature: Optional[float] = Field(default=None, description="orpheus + runpod-spark.")
    top_p: Optional[float] = Field(default=None, description="orpheus only.")
    repetition_penalty: Optional[float] = Field(default=None, description="orpheus only.")
    max_tokens: Optional[int] = Field(default=None, description="orpheus only.")
    seed: Optional[int] = Field(default=None, description="orpheus only.")
    max_new_audio_tokens: Optional[int] = Field(default=None, description="runpod-spark only.")

    @field_validator("text")
    @classmethod
    def _strip_text(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("text must not be empty")
        return v


class SpeechResponse(BaseModel):
    """Normalized response for response_mode='url' across all providers."""

    audio_url: str = Field(description="Signed URL to the generated audio.")
    model: str = Field(description="Model used.")
    platform: str = Field(description="Platform used.")
    voice: str = Field(description="Resolved voice/speaker.")
    audio_url_expires_at: Optional[datetime] = Field(default=None)
    language: Optional[str] = Field(default=None)
    sample_rate: Optional[int] = Field(default=None)
    duration_seconds: Optional[float] = Field(default=None)
    gcs_object: Optional[str] = Field(default=None)
    request_id: Optional[str] = Field(default=None)
    timings_ms: Optional[Dict[str, Any]] = Field(default=None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest app/tests/test_speech_service.py -k "speech_request or tts_enum or speech_response" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/schemas/speech.py app/tests/test_speech_service.py
git commit -m "feat(tts): add SpeechRequest/SpeechResponse schemas and TTS enums"
```

---

## Task 3: `RunpodSparkTTSService` + refactor the RunPod endpoint

**Files:**
- Create: `app/services/runpod_tts_service.py`
- Modify: `app/routers/runpod_tts.py`
- Test: `app/tests/test_speech_service.py`

- [ ] **Step 1: Write the failing test**

Append to `app/tests/test_speech_service.py`:

```python
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import ExternalServiceError, ServiceUnavailableError


async def test_runpod_spark_service_builds_payload_and_returns_output(monkeypatch):
    from app.services import runpod_tts_service as mod

    captured = {}

    def fake_run_sync(data, timeout):
        captured["data"] = data
        captured["timeout"] = timeout
        return {"audio_url": "https://x/y.mp3", "blob": "tts/y.mp3", "sample_rate": 16000}

    fake_endpoint = MagicMock()
    fake_endpoint.run_sync = fake_run_sync
    monkeypatch.setattr(mod.runpod, "Endpoint", lambda _id: fake_endpoint)

    svc = mod.RunpodSparkTTSService(endpoint_id="ep123")
    out = await svc.synthesize(
        text="  hello  ", speaker_id=248, temperature=0.7, max_new_audio_tokens=2000
    )
    assert out["audio_url"] == "https://x/y.mp3"
    assert captured["data"]["input"] == {
        "task": "tts",
        "text": "hello",
        "speaker_id": 248,
        "temperature": 0.7,
        "max_new_audio_tokens": 2000,
    }
    assert captured["timeout"] == 600


async def test_runpod_spark_service_maps_timeout(monkeypatch):
    from app.services import runpod_tts_service as mod

    def boom(data, timeout):
        raise TimeoutError("slow")

    fake_endpoint = MagicMock()
    fake_endpoint.run_sync = boom
    monkeypatch.setattr(mod.runpod, "Endpoint", lambda _id: fake_endpoint)

    svc = mod.RunpodSparkTTSService(endpoint_id="ep123")
    with pytest.raises(ServiceUnavailableError):
        await svc.synthesize(text="hi", speaker_id=248, temperature=0.7, max_new_audio_tokens=2000)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest app/tests/test_speech_service.py -k runpod_spark -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.runpod_tts_service'`

- [ ] **Step 3: Create `app/services/runpod_tts_service.py`**

```python
"""RunPod spark-tts service.

Extracts the inline RunPod TTS call (payload build + tenacity retry + error
mapping) out of the router so the unified SpeechService and the legacy
/tasks/runpod/tts endpoint share one implementation.
"""

import logging
import os
from typing import Optional

import runpod
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.exceptions import (
    BadRequestError,
    ExternalServiceError,
    ServiceUnavailableError,
)

logger = logging.getLogger(__name__)

runpod.api_key = os.getenv("RUNPOD_API_KEY")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=1, max=60),
    retry=retry_if_exception_type((TimeoutError, ConnectionError)),
    reraise=True,
)
async def _run_sync_with_retry(endpoint, data):
    return endpoint.run_sync(data, timeout=600)


class RunpodSparkTTSService:
    """Calls the RunPod spark-tts worker."""

    def __init__(self, endpoint_id: Optional[str] = None) -> None:
        self.endpoint_id = endpoint_id or os.getenv("RUNPOD_ENDPOINT_ID")

    async def synthesize(
        self,
        *,
        text: str,
        speaker_id: int,
        temperature: float,
        max_new_audio_tokens: int,
    ) -> dict:
        """Run RunPod spark-tts and return the raw worker output.

        Raises:
            ServiceUnavailableError, ExternalServiceError, BadRequestError.
        """
        data = {
            "input": {
                "task": "tts",
                "text": text.strip(),
                "speaker_id": speaker_id,
                "temperature": temperature,
                "max_new_audio_tokens": max_new_audio_tokens,
            }
        }
        endpoint = runpod.Endpoint(self.endpoint_id)
        try:
            return await _run_sync_with_retry(endpoint, data)
        except TimeoutError as e:
            logger.error(f"RunPod TTS timed out: {e}")
            raise ServiceUnavailableError(message="Service unavailable due to timeout")
        except ConnectionError as e:
            logger.error(f"RunPod TTS connection error: {e}")
            raise ExternalServiceError(
                service_name="RunPod TTS Service",
                message="Service unavailable due to connection error",
                original_error=str(e),
            )
        except ValueError as e:
            logger.error(f"RunPod TTS worker bad request: {e}")
            raise BadRequestError(message=f"Invalid request to TTS worker: {e}")
        except Exception as e:
            logger.exception("Unexpected error calling RunPod TTS worker")
            raise ExternalServiceError(
                service_name="RunPod TTS Worker",
                message="TTS worker error",
                original_error=str(e),
            )


_runpod_spark_tts_service: Optional[RunpodSparkTTSService] = None


def get_runpod_spark_tts_service() -> RunpodSparkTTSService:
    global _runpod_spark_tts_service
    if _runpod_spark_tts_service is None:
        _runpod_spark_tts_service = RunpodSparkTTSService()
    return _runpod_spark_tts_service


def reset_runpod_spark_tts_service() -> None:
    global _runpod_spark_tts_service
    _runpod_spark_tts_service = None
```

- [ ] **Step 4: Refactor `app/routers/runpod_tts.py` to use the service**

In `text_to_speech`, after the validation block computes `temperature` and `max_new_audio_tokens`, replace the inline endpoint creation + `call_endpoint_with_retry` + error-handling block (the `endpoint = runpod.Endpoint(...)` line near the top and the `data = {...}` + `try: request_response = await call_endpoint_with_retry(...)` block) with:

```python
    from app.services.runpod_tts_service import get_runpod_spark_tts_service

    service = get_runpod_spark_tts_service()
    start_time = time.time()
    request_response = await service.synthesize(
        text=text,
        speaker_id=speaker_id_val,
        temperature=temperature,
        max_new_audio_tokens=max_new_audio_tokens,
    )
    end_time = time.time()
```

Leave the rest of the handler (validation above, `response = {}; response["output"] = request_response`, the feedback-scheduling block, and `return response`) unchanged. Remove the now-unused `endpoint = runpod.Endpoint(RUNPOD_ENDPOINT_ID)` line and the module-level `call_endpoint_with_retry` function (and its `tenacity`/`runpod` imports if they become unused — run flake8 to confirm). Keep `import runpod` only if still referenced; if not, remove it.

> The service now owns error mapping, so the router's `try/except` around the call is removed. Behavior is preserved (same payload, same exceptions, same response shape).

- [ ] **Step 5: Run tests**

Run: `pytest app/tests/test_speech_service.py -k runpod_spark -v`
Expected: PASS

Verify the RunPod router still imports cleanly:
Run: `python -c "import app.routers.runpod_tts"`
Expected: no error.

- [ ] **Step 6: Lint + commit**

```bash
isort app/services/runpod_tts_service.py app/routers/runpod_tts.py app/tests/test_speech_service.py
black app/services/runpod_tts_service.py app/routers/runpod_tts.py app/tests/test_speech_service.py
flake8 app/services/runpod_tts_service.py app/routers/runpod_tts.py
git add app/services/runpod_tts_service.py app/routers/runpod_tts.py app/tests/test_speech_service.py
git commit -m "feat(tts): extract RunpodSparkTTSService and use it in /tasks/runpod/tts"
```

---

## Task 4: `SpeechService` facade

**Files:**
- Create: `app/services/speech_service.py`
- Test: `app/tests/test_speech_service.py`

- [ ] **Step 1: Write the failing tests**

Append to `app/tests/test_speech_service.py`:

```python
from datetime import datetime
from unittest.mock import AsyncMock

from app.core.exceptions import BadRequestError
from app.models.enums import SpeakerID
from app.schemas.speech import SpeechRequest
from app.services.orpheus_tts_service import SynthesizeResult
from app.services.speech_service import SpeechService


def make_speech_facade():
    spark = MagicMock()
    spark.generate_audio = AsyncMock(return_value=b"WAVDATA")
    spark.estimate_duration = MagicMock(return_value=3.0)
    orpheus = MagicMock()
    orpheus.synthesize = AsyncMock(
        return_value=SynthesizeResult(
            audio_url="https://o/a.wav",
            audio_url_expires_at=datetime(2026, 12, 1),
            speaker_id="salt_lug_0001",
            language="lug",
            sample_rate=24000,
            duration_seconds=2.5,
            chunks=1,
            audio_size_bytes=1000,
            gcs_object="orpheus_tts/a.wav",
            inference_ms=10.0,
            upload_ms=5.0,
            signed_url_ms=1.0,
            total_ms=16.0,
        )
    )
    runpod_spark = MagicMock()
    runpod_spark.synthesize = AsyncMock(
        return_value={"audio_url": "https://r/a.mp3", "blob": "tts/a.mp3", "sample_rate": 16000}
    )
    storage = MagicMock()
    storage.generate_file_name = MagicMock(return_value="tts_audio/x.wav")
    storage.upload_audio_async = AsyncMock(return_value="blob-obj")
    storage.generate_signed_url = MagicMock(return_value=("https://s/x.wav", datetime(2026, 12, 1)))
    facade = SpeechService(
        tts_service=spark,
        orpheus_service=orpheus,
        runpod_spark_service=runpod_spark,
        storage_service=storage,
    )
    return facade, spark, orpheus, runpod_spark, storage


# --- voice resolution ---

def test_resolve_spark_speaker_default():
    assert SpeechService.resolve_spark_speaker(None) is SpeakerID.LUGANDA_FEMALE


def test_resolve_spark_speaker_by_name_and_int():
    assert SpeechService.resolve_spark_speaker("luganda_female") is SpeakerID.LUGANDA_FEMALE
    assert SpeechService.resolve_spark_speaker("248") is SpeakerID.LUGANDA_FEMALE
    assert SpeechService.resolve_spark_speaker("ACHOLI_FEMALE") is SpeakerID.ACHOLI_FEMALE


def test_resolve_spark_speaker_invalid():
    with pytest.raises(BadRequestError):
        SpeechService.resolve_spark_speaker("no_such_voice")


# --- validation ---

def test_validate_rejects_orpheus_on_runpod():
    facade, *_ = make_speech_facade()
    req = SpeechRequest(text="hi", model="orpheus-3b-tts", platform="runpod")
    with pytest.raises(BadRequestError):
        facade.validate_request(req)


def test_validate_rejects_stream_on_non_modal_spark():
    facade, *_ = make_speech_facade()
    req = SpeechRequest(text="hi", model="spark-tts", platform="runpod", response_mode="stream")
    with pytest.raises(BadRequestError):
        facade.validate_request(req)


def test_validate_rejects_orpheus_param_on_spark():
    facade, *_ = make_speech_facade()
    req = SpeechRequest(text="hi", model="spark-tts", platform="runpod", top_p=0.9)
    with pytest.raises(BadRequestError):
        facade.validate_request(req)


def test_validate_rejects_max_new_audio_tokens_off_target():
    facade, *_ = make_speech_facade()
    req = SpeechRequest(text="hi", model="spark-tts", platform="modal", max_new_audio_tokens=100)
    with pytest.raises(BadRequestError):
        facade.validate_request(req)


def test_validate_rejects_temperature_on_modal_spark():
    facade, *_ = make_speech_facade()
    req = SpeechRequest(text="hi", model="spark-tts", platform="modal", temperature=0.5)
    with pytest.raises(BadRequestError):
        facade.validate_request(req)


def test_validate_rejects_overlong_orpheus_text():
    facade, *_ = make_speech_facade()
    req = SpeechRequest(text="x" * 2001, model="orpheus-3b-tts", platform="modal")
    with pytest.raises(BadRequestError):
        facade.validate_request(req)


def test_validate_accepts_valid_runpod_spark():
    facade, *_ = make_speech_facade()
    req = SpeechRequest(text="hi", model="spark-tts", platform="runpod", temperature=0.7)
    facade.validate_request(req)  # no raise


# --- dispatch ---

async def test_synthesize_orpheus():
    facade, _, orpheus, _, _ = make_speech_facade()
    req = SpeechRequest(text="hi", model="orpheus-3b-tts", platform="modal", voice="salt_lug_0001")
    result = await facade.synthesize(req)
    orpheus.synthesize.assert_awaited_once()
    assert result.audio_url == "https://o/a.wav"
    assert result.model == "orpheus-3b-tts"
    assert result.timings_ms["total_ms"] == 16.0


async def test_synthesize_spark_modal_uploads_and_signs():
    facade, spark, _, _, storage = make_speech_facade()
    req = SpeechRequest(text="hi", model="spark-tts", platform="modal", voice="luganda_female")
    result = await facade.synthesize(req)
    spark.generate_audio.assert_awaited_once()
    storage.upload_audio_async.assert_awaited_once()
    assert result.audio_url == "https://s/x.wav"
    assert result.voice == "luganda_female"


async def test_synthesize_spark_runpod_maps_output():
    facade, _, _, runpod_spark, _ = make_speech_facade()
    req = SpeechRequest(text="hi", model="spark-tts", platform="runpod", voice="248")
    result = await facade.synthesize(req)
    runpod_spark.synthesize.assert_awaited_once()
    assert result.audio_url == "https://r/a.mp3"
    assert result.sample_rate == 16000
    assert result.gcs_object == "tts/a.mp3"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest app/tests/test_speech_service.py -k "resolve_spark or validate_ or synthesize_" -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.speech_service'`

- [ ] **Step 3: Create `app/services/speech_service.py`**

```python
"""SpeechService facade for the unified /tasks/audio/speech endpoint.

Validates a SpeechRequest, routes by (model, platform) to the existing TTS
services, and normalizes each provider's result into a SpeechResult. No
synthesis logic lives here — it composes TTSService (Modal spark),
RunpodSparkTTSService (RunPod spark), and OrpheusTTSService.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from app.core.exceptions import BadRequestError
from app.models.enums import SpeakerID, TTSResponseMode
from app.schemas.speech import SpeechRequest
from app.services.orpheus_tts_service import OrpheusTTSService, get_orpheus_tts_service
from app.services.runpod_tts_service import (
    RunpodSparkTTSService,
    get_runpod_spark_tts_service,
)
from app.services.tts_service import TTSService, get_tts_service
from app.utils.storage import GCPStorageService
from app.utils.storage import get_storage_service as get_legacy_storage_service

logger = logging.getLogger(__name__)

# Per-model defaults.
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

        if (
            req.temperature is not None
            and model == "spark-tts"
            and platform == "modal"
        ):
            raise BadRequestError(
                message="'temperature' is not supported for model='spark-tts' on "
                "platform='modal'."
            )

        max_len = ORPHEUS_MAX_TEXT if model == "orpheus-3b-tts" else SPARK_MAX_TEXT
        if len(req.text) > max_len:
            raise BadRequestError(
                message=f"`text` is too long for {model} (max {max_len} characters)."
            )

        if model == "spark-tts":
            self.resolve_spark_speaker(req.voice)  # raises on invalid voice

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

        # spark-tts
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

        # spark-tts + runpod
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
        out = output.get("output") if isinstance(output, dict) and "output" in output else output
        out = out if isinstance(out, dict) else {}
        return SpeechResult(
            audio_url=out.get("audio_url") or out.get("url") or "",
            model=model,
            platform=platform,
            voice=speaker.name.lower(),
            sample_rate=out.get("sample_rate"),
            gcs_object=out.get("blob"),
        )


_speech_service: Optional[SpeechService] = None


def get_speech_service() -> SpeechService:
    global _speech_service
    if _speech_service is None:
        _speech_service = SpeechService()
    return _speech_service


def reset_speech_service() -> None:
    global _speech_service
    _speech_service = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest app/tests/test_speech_service.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Lint + commit**

```bash
isort app/services/speech_service.py app/tests/test_speech_service.py
black app/services/speech_service.py app/tests/test_speech_service.py
flake8 app/services/speech_service.py
git add app/services/speech_service.py app/tests/test_speech_service.py
git commit -m "feat(tts): add SpeechService facade (validation + dispatch + normalization)"
```

---

## Task 5: Register deps

**Files:**
- Modify: `app/deps.py`
- Test: `app/tests/test_speech_service.py`

- [ ] **Step 1: Write the failing test**

Append to `app/tests/test_speech_service.py`:

```python
def test_speech_deps_exported():
    import app.deps as deps

    assert hasattr(deps, "SpeechServiceDep")
    assert hasattr(deps, "RunpodSparkTTSServiceDep")
    assert "SpeechServiceDep" in deps.__all__
    assert "RunpodSparkTTSServiceDep" in deps.__all__
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest app/tests/test_speech_service.py::test_speech_deps_exported -v`
Expected: FAIL with `AssertionError`

- [ ] **Step 3: Edit `app/deps.py`**

1. Add imports near the other service imports:

```python
from app.services.runpod_tts_service import (
    RunpodSparkTTSService,
    get_runpod_spark_tts_service,
)
from app.services.speech_service import SpeechService, get_speech_service
```

2. Add aliases near the other `*ServiceDep` aliases:

```python
SpeechServiceDep = Annotated[SpeechService, Depends(get_speech_service)]
RunpodSparkTTSServiceDep = Annotated[
    RunpodSparkTTSService, Depends(get_runpod_spark_tts_service)
]
```

3. Add `"SpeechServiceDep"`, `"RunpodSparkTTSServiceDep"`, `"SpeechService"`, `"RunpodSparkTTSService"` to `__all__`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest app/tests/test_speech_service.py::test_speech_deps_exported -v`
Expected: PASS

- [ ] **Step 5: Lint + commit**

```bash
isort app/deps.py
black app/deps.py
flake8 app/deps.py
git add app/deps.py app/tests/test_speech_service.py
git commit -m "feat(deps): register SpeechServiceDep and RunpodSparkTTSServiceDep"
```

---

## Task 6: Unified `POST /tasks/audio/speech`

**Files:**
- Modify: `app/routers/audio.py`
- Test: `app/tests/test_audio_speech.py`

- [ ] **Step 1: Write the failing tests**

Create `app/tests/test_audio_speech.py`:

```python
"""Integration tests for POST /tasks/audio/speech."""

from datetime import datetime
from typing import Dict
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.api import app
from app.deps import get_speech_service
from app.services.speech_service import SpeechResult


@pytest.fixture(autouse=True)
def stub_feedback(monkeypatch):
    async def noop_save(*args, **kwargs):
        return None

    import app.utils.feedback as feedback_module
    monkeypatch.setattr(feedback_module, "save_api_inference", noop_save, raising=False)
    import app.routers.audio as audio_module
    monkeypatch.setattr(audio_module, "save_api_inference", noop_save, raising=False)
    yield


@pytest.fixture
def fake_speech():
    facade = MagicMock()
    facade.validate_request = MagicMock(return_value=None)
    facade.synthesize = AsyncMock(
        return_value=SpeechResult(
            audio_url="https://x/a.wav",
            model="orpheus-3b-tts",
            platform="modal",
            voice="salt_lug_0001",
            audio_url_expires_at=datetime(2026, 12, 1),
            sample_rate=24000,
            duration_seconds=2.5,
            gcs_object="orpheus_tts/a.wav",
            timings_ms={"total_ms": 16.0},
        )
    )
    app.dependency_overrides[get_speech_service] = lambda: facade
    yield facade
    app.dependency_overrides.pop(get_speech_service, None)


async def test_speech_url_mode_returns_200(
    authenticated_client: AsyncClient, fake_speech, test_user: Dict
):
    resp = await authenticated_client.post(
        "/tasks/audio/speech",
        json={"text": "hello", "model": "orpheus-3b-tts", "platform": "modal"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["audio_url"] == "https://x/a.wav"
    assert body["model"] == "orpheus-3b-tts"
    assert body["request_id"]  # router-generated trace id
    fake_speech.validate_request.assert_called_once()
    fake_speech.synthesize.assert_awaited_once()


async def test_speech_requires_auth(async_client: AsyncClient):
    resp = await async_client.post(
        "/tasks/audio/speech", json={"text": "hello"}
    )
    assert resp.status_code == 401


async def test_speech_invalid_combo_returns_400(
    authenticated_client: AsyncClient, test_user: Dict
):
    """Real facade (no override) rejects orpheus on runpod with 400."""
    resp = await authenticated_client.post(
        "/tasks/audio/speech",
        json={"text": "hello", "model": "orpheus-3b-tts", "platform": "runpod"},
    )
    assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest app/tests/test_audio_speech.py -v`
Expected: FAIL — route returns 404 (not yet added).

- [ ] **Step 3: Add the endpoint to `app/routers/audio.py`**

1. Add imports at the top (next to existing imports):

```python
import uuid

from fastapi import Body
from fastapi.responses import StreamingResponse

from app.deps import LegacyStorageServiceDep, SpeechServiceDep, TTSServiceDep
from app.models.enums import TTSResponseMode
from app.routers.tts import _stream_audio, _stream_audio_with_url
from app.schemas.speech import SpeechRequest, SpeechResponse
from app.schemas.tts import TTSRequest as ModalTTSRequest
from app.services.speech_service import SpeechService
from app.utils.feedback import INFERENCE_TYPES, save_api_inference
```

2. Append the handler at the end of the module:

```python
@router.post(
    "/audio/speech",
    response_model=SpeechResponse,
    summary="Generate speech (unified TTS endpoint)",
    description=(
        "Unified Text-to-Speech endpoint. Routes by model (orpheus-3b-tts | "
        "spark-tts) and platform (modal | runpod). Returns a signed audio URL "
        "(response_mode='url'); spark-tts on Modal also supports 'stream'/'both'. "
        "Replaces /tasks/modal/tts, /tasks/runpod/tts, and /tasks/modal/orpheus/tts."
    ),
)
@limiter.limit(get_account_type_limit)
async def create_speech(
    request: Request,
    background_tasks: BackgroundTasks,
    quota: QuotaServiceDep,
    speech_service: SpeechServiceDep,
    tts_service: TTSServiceDep,
    storage_service: LegacyStorageServiceDep,
    body: SpeechRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Generate speech via the selected model + platform."""
    await check_quota(quota, db, current_user)
    start_time = time.time()

    # Validate combinations early (raises BadRequestError -> 400).
    speech_service.validate_request(body)

    # Streaming modes (validated above to be spark-tts + modal only).
    if body.response_mode in (TTSResponseMode.STREAM, TTSResponseMode.BOTH):
        speaker = SpeechService.resolve_spark_speaker(body.voice)
        modal_req = ModalTTSRequest(
            text=body.text, speaker_id=speaker, response_mode=body.response_mode
        )
        if body.response_mode == TTSResponseMode.STREAM:
            return await _stream_audio(modal_req, tts_service)
        return await _stream_audio_with_url(modal_req, storage_service, tts_service)

    # URL mode.
    result = await speech_service.synthesize(body)
    request_id = uuid.uuid4().hex

    response = SpeechResponse(
        audio_url=result.audio_url,
        model=result.model,
        platform=result.platform,
        voice=result.voice,
        audio_url_expires_at=result.audio_url_expires_at,
        language=result.language,
        sample_rate=result.sample_rate,
        duration_seconds=result.duration_seconds,
        gcs_object=result.gcs_object,
        request_id=request_id,
        timings_ms=result.timings_ms,
    )

    _schedule_speech_feedback(
        background_tasks=background_tasks,
        user=current_user,
        text=body.text,
        result=result,
        request_id=request_id,
        processing_time=time.time() - start_time,
    )

    return response


def _schedule_speech_feedback(
    *, background_tasks, user, text, result, request_id, processing_time
):
    """Best-effort feedback save for a unified speech request."""
    try:
        background_tasks.add_task(
            save_api_inference,
            text,
            {"audio_url": result.audio_url, "gcs_object": result.gcs_object},
            user,
            model_type=f"{result.model}:{result.voice}",
            processing_time=processing_time,
            inference_type=INFERENCE_TYPES["tts"],
            job_details={
                "model": result.model,
                "platform": result.platform,
                "voice": result.voice,
                "audio_url": result.audio_url,
                "gcs_object": result.gcs_object,
                "request_id": request_id,
            },
        )
    except Exception as e:
        logging.warning(f"Failed to schedule speech feedback save task: {e}")
```

> The router is mounted under `/tasks` already (Phase 1 added `app.include_router(audio_router, prefix="/tasks", ...)`), so `/audio/speech` resolves to `/tasks/audio/speech` with no `app/api.py` change.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest app/tests/test_audio_speech.py -v`
Expected: PASS (3 tests). If `test_speech_invalid_combo_returns_400` returns 422 instead of 400, the facade raised the wrong type — STOP and report (do not weaken the assertion).

- [ ] **Step 5: Lint + commit**

```bash
isort app/routers/audio.py app/tests/test_audio_speech.py
black app/routers/audio.py app/tests/test_audio_speech.py
flake8 app/routers/audio.py app/tests/test_audio_speech.py
git add app/routers/audio.py app/tests/test_audio_speech.py
git commit -m "feat(tts): add unified POST /tasks/audio/speech endpoint"
```

---

## Task 7: Deprecate the legacy synthesis endpoints

**Files:**
- Modify: `app/routers/tts.py`, `app/routers/runpod_tts.py`, `app/routers/orpheus_tts.py`, `app/routers/tasks.py`
- Test: `app/tests/test_audio_speech.py`

- [ ] **Step 1: Write the failing test**

Append to `app/tests/test_audio_speech.py`:

```python
async def test_openapi_marks_legacy_tts_deprecated(async_client: AsyncClient):
    resp = await async_client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    for path in [
        "/tasks/modal/tts",
        "/tasks/runpod/tts",
        "/tasks/modal/orpheus/tts",
        "/tasks/tts",
    ]:
        assert paths[path]["post"].get("deprecated") is True, path


async def test_legacy_runpod_tts_has_deprecation_headers(
    authenticated_client: AsyncClient, test_user: Dict, monkeypatch
):
    """/tasks/runpod/tts should carry RFC-8594 headers and still return 200."""
    from app.services.runpod_tts_service import RunpodSparkTTSService

    async def fake_synth(self, **kwargs):
        return {"audio_url": "https://r/a.mp3", "blob": "tts/a.mp3", "sample_rate": 16000}

    monkeypatch.setattr(RunpodSparkTTSService, "synthesize", fake_synth)

    async def noop_save(*args, **kwargs):
        return None

    import app.routers.runpod_tts as rp
    monkeypatch.setattr(rp, "save_api_inference", noop_save, raising=False)

    resp = await authenticated_client.post(
        "/tasks/runpod/tts",
        json={"text": "hello", "speaker_id": 248},
    )
    assert resp.status_code == 200
    assert resp.headers.get("Deprecation") == "true"
    assert "Sunset" in resp.headers
    assert 'rel="successor-version"' in resp.headers.get("Link", "")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest app/tests/test_audio_speech.py -k "deprecated or deprecation_headers" -v`
Expected: FAIL — `deprecated` absent / headers missing.

- [ ] **Step 3: Add markers.** For each endpoint below, add `deprecated=True` to the decorator, inject `http_response: Response` (import `Response` from `fastapi` if not present — name it `http_response` to avoid clashing with any local `response` variable), and add — right after the handler's first line / `await check_quota(...)` — a warning log + `add_deprecation_headers(http_response, SUCCESSOR_SPEECH)`. Import once per module:

```python
from app.utils.deprecation import SUCCESSOR_SPEECH, add_deprecation_headers
```

3a. **`app/routers/tts.py` → `generate_tts` (`POST /tasks/modal/tts`)**
- Decorator: this handler is registered via `@router.post("/tts", ...)` — add `deprecated=True` to those kwargs.
- Add `http_response: Response` to the signature (after `background_tasks: BackgroundTasks,`).
- At the very top of the function body (before the `if request.response_mode ==` check), add:
```python
    logging.warning(
        "Deprecated endpoint /tasks/modal/tts called; use POST /tasks/audio/speech"
    )
    add_deprecation_headers(http_response, SUCCESSOR_SPEECH)
```
> Note: the streaming branches return a `StreamingResponse` and will not carry the injected headers; that is acceptable (the dedicated `/tts/stream` endpoints remain the streaming path and are not deprecated). The url-mode return (the `TTSResponse` model) carries the headers.

3b. **`app/routers/runpod_tts.py` → `text_to_speech` (`POST /tasks/runpod/tts`)**
- Decorator: change `@router.post("/tts",)` to `@router.post("/tts", deprecated=True)`.
- Add `http_response: Response` after `background_tasks: BackgroundTasks,` and `from fastapi import ... Response`.
- After `await check_quota(quota, db, current_user)`, add:
```python
    logging.warning(
        "Deprecated endpoint /tasks/runpod/tts called; use POST /tasks/audio/speech"
    )
    add_deprecation_headers(http_response, SUCCESSOR_SPEECH)
```
> This handler returns a plain `dict`. Returning a `dict` lets FastAPI merge the injected `http_response` headers, so the deprecation headers are emitted.

3c. **`app/routers/orpheus_tts.py` → `synthesize_tts` (`POST /tasks/modal/orpheus/tts`)**
- Add `deprecated=True` to the `@router.post(...)` decorator kwargs.
- Add `http_response: Response` after `background_tasks: BackgroundTasks,` and import `Response` from `fastapi`.
- After `check_quota(...)` (or as the first body statement if quota is called later), add:
```python
    logging.warning(
        "Deprecated endpoint /tasks/modal/orpheus/tts called; use POST /tasks/audio/speech"
    )
    add_deprecation_headers(http_response, SUCCESSOR_SPEECH)
```
> Returns the `OrpheusTTSResponse` model → injected headers are merged.

3d. **`app/routers/tasks.py` → `text_to_speech` (`POST /tasks/tts`)**
- Already `@router.post("/tts", deprecated=True)` — leave `deprecated=True`.
- Add `http_response: Response` after `background_tasks: BackgroundTasks,` and import `Response` from `fastapi` if needed.
- After `await check_quota(...)`, add:
```python
    logging.warning(
        "Deprecated endpoint /tasks/tts called; use POST /tasks/audio/speech"
    )
    add_deprecation_headers(http_response, SUCCESSOR_SPEECH)
```

> Use `logging.warning` if the module uses `logging` directly, or the module's `logger`/`logging` convention — match each file. Do not change any synthesis/response logic.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest app/tests/test_audio_speech.py -v`
Expected: PASS (all tests).

Run the broader TTS test set to confirm no regressions:
Run: `pytest app/tests/test_routers/test_orpheus_tts.py app/tests/test_services/test_tts_service.py app/tests/test_audio_speech.py -v`
Expected: PASS (investigate any new failure).

- [ ] **Step 5: Lint + commit**

```bash
isort app/routers/tts.py app/routers/runpod_tts.py app/routers/orpheus_tts.py app/routers/tasks.py app/tests/test_audio_speech.py
black app/routers/tts.py app/routers/runpod_tts.py app/routers/orpheus_tts.py app/routers/tasks.py app/tests/test_audio_speech.py
flake8 app/routers/tts.py app/routers/runpod_tts.py app/routers/orpheus_tts.py app/routers/tasks.py app/tests/test_audio_speech.py
git add app/routers/tts.py app/routers/runpod_tts.py app/routers/orpheus_tts.py app/routers/tasks.py app/tests/test_audio_speech.py
git commit -m "feat(tts): deprecate legacy synthesis endpoints (flag + RFC-8594 headers + log)"
```

---

## Task 8: Full verification (Definition of Done)

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `pytest app/tests/ -q`
Expected: no NEW failures vs the branch base. (Pre-existing `test_config.py` GA failures are environment-dependent and unrelated — confirm the count matches the base.)

- [ ] **Step 2: Lint the touched files**

Run:
```bash
flake8 app/schemas/speech.py app/services/speech_service.py app/services/runpod_tts_service.py app/routers/audio.py app/routers/tts.py app/routers/runpod_tts.py app/routers/orpheus_tts.py app/routers/tasks.py app/deps.py app/utils/deprecation.py app/tests/test_speech_service.py app/tests/test_audio_speech.py
```
Expected: clean for all listed files. Fix any issue attributable to this work.

- [ ] **Step 3: Commit any lint fixes**

```bash
git add -A
git commit -m "style(tts): lint fixes for unified speech endpoint"
```

(Skip if nothing to commit.)

---

## Self-Review Notes

- **Spec coverage:** `SpeechRequest`/`SpeechResponse` + enums (Task 2); `SpeechService` validate + dispatch + normalization (Task 4); `RunpodSparkTTSService` extraction + RunPod endpoint delegation (Task 3); deps (Task 5); unified endpoint with url + stream/both (Task 6); deprecation of the 4 synthesis endpoints (Task 7); quota/RL on the unified endpoint (Task 6 `check_quota` + `@limiter.limit`); deprecation constants (Task 1); tests + lint (Task 8). Out-of-scope items (speaker-listing, batch, streaming helpers, health, refresh-url) are untouched ✅.
- **Type consistency:** facade methods `validate_request(req) -> None`, `resolve_spark_speaker(voice) -> SpeakerID`, `synthesize(req) -> SpeechResult` are used identically in the router and tests. `SpeechResult` fields map 1:1 to `SpeechResponse`. `TTSModel.value`/`TTSPlatform.value` strings (`"orpheus-3b-tts"`/`"spark-tts"`, `"modal"`/`"runpod"`) are what the facade compares against.
- **Known risk:** the `voice` echo for spark uses `SpeakerID.name.lower()` (e.g. `luganda_female`); orpheus echoes the catalog tag. Documented in the dispatch table. The router-generated `request_id` (uuid) is a trace id, not asserted for an exact value in tests.
- **Quota added to spark+modal path:** intentional per spec; the unified endpoint enforces quota while the legacy `/tasks/modal/tts` keeps its current no-quota behavior.
