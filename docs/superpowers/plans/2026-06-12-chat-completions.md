# OpenAI-Compatible `/tasks/chat/completions` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single OpenAI-compatible `POST /tasks/chat/completions` endpoint (non-streaming + SSE streaming) backed by the Sunflower model, and deprecate `/tasks/sunflower_inference` and `/tasks/sunflower_simple` without breaking them.

**Architecture:** New router `app/routers/chat.py` + new schemas `app/schemas/chat.py`, calling an extended `InferenceService` (new streaming generator with a stateful `<think>`-tag filter; extra OpenAI passthrough params). Legacy endpoints in `app/routers/inference.py` are only annotated as deprecated. Spec: `docs/superpowers/specs/2026-06-12-chat-completions-design.md`.

**Tech Stack:** FastAPI, Pydantic v2, OpenAI Python SDK (sync client against RunPod's OpenAI-compatible vLLM endpoint), `StreamingResponse` SSE, pytest + httpx `AsyncClient` (asyncio_mode=auto), SlowAPI rate limiting, quota guard.

**Branch:** `sunflower-openai-chat-completions` (already checked out).

**Conventions that apply to every task:**
- Tests use existing fixtures from `app/tests/conftest.py`: `async_client`, `test_user` (dict with `"token"`), `test_db`. Quota is stubbed by an autouse fixture; Redis is fakeredis.
- Mock at the service layer (`InferenceService`) via `app.dependency_overrides`, never patch HTTP.
- Run single test files with: `pytest app/tests/test_routers/test_chat.py -v`
- Exceptions come from `app/core/exceptions.py`: `BadRequestError`→400, `ValidationError`→422, `ExternalServiceError`→502, `ServiceUnavailableError`→503.

---

### Task 1: OpenAI-compatible chat schemas

**Files:**
- Create: `app/schemas/chat.py`
- Test: `app/tests/test_routers/test_chat.py` (new file, schema test class only for now)

- [ ] **Step 1.1: Write the failing tests**

Create `app/tests/test_routers/test_chat.py`:

```python
"""
Tests for the OpenAI-compatible /tasks/chat/completions endpoint.

Covers schema validation, the non-streaming and streaming (SSE) paths,
error mapping, and deprecation of the legacy Sunflower endpoints.
"""

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.schemas.chat import (
    SUPPORTED_MODELS,
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
)


class TestChatSchemas:
    """Unit tests for OpenAI-compatible request/response models."""

    def test_request_defaults(self) -> None:
        req = ChatCompletionRequest(
            messages=[{"role": "user", "content": "Hello"}]
        )
        assert req.model == "Sunbird/Sunflower-14B"
        assert req.temperature == 0.3
        assert req.stream is False
        assert req.max_tokens is None
        assert req.top_p is None
        assert req.stop is None

    def test_supported_models_constant(self) -> None:
        assert SUPPORTED_MODELS == ("Sunbird/Sunflower-14B",)

    def test_request_rejects_empty_messages(self) -> None:
        with pytest.raises(PydanticValidationError):
            ChatCompletionRequest(messages=[])

    def test_message_rejects_invalid_role(self) -> None:
        with pytest.raises(PydanticValidationError):
            ChatMessage(role="tool", content="hi")

    def test_message_rejects_blank_content(self) -> None:
        with pytest.raises(PydanticValidationError):
            ChatMessage(role="user", content="   ")

    def test_request_rejects_out_of_range_temperature(self) -> None:
        with pytest.raises(PydanticValidationError):
            ChatCompletionRequest(
                messages=[{"role": "user", "content": "Hello"}],
                temperature=3.0,
            )

    def test_stop_accepts_string_and_list(self) -> None:
        req = ChatCompletionRequest(
            messages=[{"role": "user", "content": "Hello"}], stop="\n"
        )
        assert req.stop == "\n"
        req = ChatCompletionRequest(
            messages=[{"role": "user", "content": "Hello"}], stop=["a", "b"]
        )
        assert req.stop == ["a", "b"]

    def test_response_serializes_openai_shape(self) -> None:
        resp = ChatCompletionResponse(
            id="chatcmpl-abc",
            created=1718000000,
            model="Sunbird/Sunflower-14B",
            choices=[
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Oli otya?"},
                    "finish_reason": "stop",
                }
            ],
            usage={
                "prompt_tokens": 5,
                "completion_tokens": 3,
                "total_tokens": 8,
            },
        )
        data = resp.model_dump()
        assert data["object"] == "chat.completion"
        assert data["choices"][0]["message"]["content"] == "Oli otya?"
        assert data["usage"]["total_tokens"] == 8

    def test_chunk_serializes_openai_shape(self) -> None:
        chunk = ChatCompletionChunk(
            id="chatcmpl-abc",
            created=1718000000,
            model="Sunbird/Sunflower-14B",
            choices=[{"index": 0, "delta": {"content": "Oli"}}],
        )
        data = chunk.model_dump()
        assert data["object"] == "chat.completion.chunk"
        assert data["choices"][0]["delta"]["content"] == "Oli"
        assert data["choices"][0]["finish_reason"] is None
```

- [ ] **Step 1.2: Run tests to verify they fail**

Run: `pytest app/tests/test_routers/test_chat.py -v`
Expected: FAIL at import — `ModuleNotFoundError: No module named 'app.schemas.chat'`

- [ ] **Step 1.3: Write the schemas**

Create `app/schemas/chat.py`:

```python
"""
OpenAI-Compatible Chat Completion Schemas.

Pydantic models for the /tasks/chat/completions endpoint. The request and
response shapes mirror the OpenAI Chat Completions API so clients can switch
between the OpenAI API and the Sunbird API by changing only the base URL and
API key.

Spec: docs/superpowers/specs/2026-06-12-chat-completions-design.md
"""

from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator

# The only model served today. The legacy "qwen" alias is accepted solely by
# the deprecated /tasks/sunflower_* endpoints.
SUPPORTED_MODELS = ("Sunbird/Sunflower-14B",)

DEFAULT_MODEL = SUPPORTED_MODELS[0]


class ChatMessage(BaseModel):
    """A single message in the conversation, OpenAI format."""

    role: Literal["system", "user", "assistant"] = Field(
        ..., description="Message role"
    )
    content: str = Field(..., description="Message content")

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("content cannot be empty")
        return value


class ChatCompletionRequest(BaseModel):
    """Request body for POST /tasks/chat/completions (OpenAI format)."""

    model: str = Field(
        DEFAULT_MODEL,
        description=f"Model to use. Supported: {', '.join(SUPPORTED_MODELS)}",
    )
    messages: List[ChatMessage] = Field(
        ..., min_length=1, description="Conversation messages"
    )
    temperature: float = Field(
        0.3, ge=0.0, le=2.0, description="Sampling temperature"
    )
    max_tokens: Optional[int] = Field(
        None, ge=1, description="Maximum tokens to generate"
    )
    top_p: Optional[float] = Field(
        None, gt=0.0, le=1.0, description="Nucleus sampling probability"
    )
    stop: Optional[Union[str, List[str]]] = Field(
        None, description="Stop sequence(s)"
    )
    stream: bool = Field(
        False, description="Stream the response as Server-Sent Events"
    )


class ChatCompletionResponseMessage(BaseModel):
    """The assistant message inside a completion choice."""

    role: Literal["assistant"] = "assistant"
    content: str


class ChatCompletionChoice(BaseModel):
    """A single completion choice."""

    index: int = 0
    message: ChatCompletionResponseMessage
    finish_reason: Optional[str] = "stop"


class ChatCompletionUsage(BaseModel):
    """Token usage statistics, OpenAI field names."""

    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


class ChatCompletionResponse(BaseModel):
    """Non-streaming response body, OpenAI `chat.completion` object."""

    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: ChatCompletionUsage = Field(default_factory=ChatCompletionUsage)


class ChatCompletionChunkDelta(BaseModel):
    """Incremental content for a streamed choice."""

    role: Optional[str] = None
    content: Optional[str] = None


class ChatCompletionChunkChoice(BaseModel):
    """A single streamed choice."""

    index: int = 0
    delta: ChatCompletionChunkDelta
    finish_reason: Optional[str] = None


class ChatCompletionChunk(BaseModel):
    """Streaming response chunk, OpenAI `chat.completion.chunk` object."""

    id: str
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int
    model: str
    choices: List[ChatCompletionChunkChoice]
    usage: Optional[ChatCompletionUsage] = None


__all__ = [
    "SUPPORTED_MODELS",
    "DEFAULT_MODEL",
    "ChatMessage",
    "ChatCompletionRequest",
    "ChatCompletionResponseMessage",
    "ChatCompletionChoice",
    "ChatCompletionUsage",
    "ChatCompletionResponse",
    "ChatCompletionChunkDelta",
    "ChatCompletionChunkChoice",
    "ChatCompletionChunk",
]
```

- [ ] **Step 1.4: Run tests to verify they pass**

Run: `pytest app/tests/test_routers/test_chat.py -v`
Expected: all `TestChatSchemas` tests PASS

- [ ] **Step 1.5: Commit**

```bash
git add app/schemas/chat.py app/tests/test_routers/test_chat.py
git commit -m "feat: add OpenAI-compatible chat completion schemas"
```

---

### Task 2: `ThinkTagFilter` (streaming `<think>` stripper)

**Files:**
- Modify: `app/services/inference_service.py` (add class after `classify_error`, before the retry decorator section)
- Test: `app/tests/test_services/test_inference_streaming.py` (new file)

- [ ] **Step 2.1: Write the failing tests**

Create `app/tests/test_services/test_inference_streaming.py`:

```python
"""
Tests for InferenceService streaming support: the ThinkTagFilter, the
run_inference_stream generator, and OpenAI passthrough params on
run_inference.
"""

from types import SimpleNamespace
from typing import Any, Dict, Iterator, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from app.services.inference_service import InferenceService, ThinkTagFilter


class TestThinkTagFilter:
    """Unit tests for the stateful <think> tag stripper."""

    def _run(self, chunks: List[str]) -> str:
        f = ThinkTagFilter()
        out = "".join(f.feed(c) for c in chunks)
        return out + f.flush()

    def test_passthrough_without_tags(self) -> None:
        assert self._run(["Hello ", "world"]) == "Hello world"

    def test_strips_complete_tag_in_one_chunk(self) -> None:
        assert self._run(["<think>reasoning</think>Answer"]) == "Answer"

    def test_strips_tag_split_across_chunks(self) -> None:
        assert (
            self._run(["<thi", "nk>secret", " stuff</th", "ink>Visible"])
            == "Visible"
        )

    def test_strips_multiple_tags(self) -> None:
        assert (
            self._run(["a<think>x</think>b<think>y</think>c"]) == "abc"
        )

    def test_unterminated_think_is_discarded(self) -> None:
        assert self._run(["before<think>never closed"]) == "before"

    def test_partial_open_tag_that_never_completes_is_emitted(self) -> None:
        # "<thi" looks like a tag prefix but the stream ends; flush must
        # release it because it never became a real tag.
        assert self._run(["text <thi"]) == "text <thi"

    def test_lone_angle_bracket_passes_through(self) -> None:
        assert self._run(["a < b and a <t", "ag> done"]) == "a < b and a <tag> done"
```

- [ ] **Step 2.2: Run tests to verify they fail**

Run: `pytest app/tests/test_services/test_inference_streaming.py -v`
Expected: FAIL at import — `ImportError: cannot import name 'ThinkTagFilter'`

- [ ] **Step 2.3: Implement `ThinkTagFilter`**

In `app/services/inference_service.py`, add after the `classify_error` function (i.e., right before the `# Retry Decorator` section banner):

```python
# =============================================================================
# Streaming Think-Tag Filter
# =============================================================================


class ThinkTagFilter:
    """Strips ``<think>...</think>`` spans from streamed text.

    The streaming equivalent of ``InferenceService._clean_response``: because
    streamed deltas can split a tag across chunk boundaries (e.g. ``"<thi"``
    then ``"nk>"``), this filter holds back any trailing text that could still
    turn into a tag and only emits text once it is provably outside a think
    span. Content inside an unterminated ``<think>`` block is discarded.

    Usage:
        f = ThinkTagFilter()
        visible = f.feed(chunk_text)   # call per streamed delta
        visible += f.flush()           # call once after the stream ends
    """

    OPEN_TAG = "<think>"
    CLOSE_TAG = "</think>"

    def __init__(self) -> None:
        self._buffer = ""
        self._in_think = False

    @staticmethod
    def _partial_suffix_len(text: str, tag: str) -> int:
        """Length of the longest strict tag prefix that ``text`` ends with."""
        max_len = min(len(text), len(tag) - 1)
        for length in range(max_len, 0, -1):
            if text.endswith(tag[:length]):
                return length
        return 0

    def feed(self, text: str) -> str:
        """Consume a streamed delta and return the text safe to emit."""
        self._buffer += text
        emitted: List[str] = []

        while True:
            if self._in_think:
                idx = self._buffer.find(self.CLOSE_TAG)
                if idx == -1:
                    # Drop think content, but keep a possible partial close
                    # tag so it can complete on the next chunk.
                    keep = self._partial_suffix_len(self._buffer, self.CLOSE_TAG)
                    self._buffer = self._buffer[len(self._buffer) - keep :] if keep else ""
                    return "".join(emitted)
                self._buffer = self._buffer[idx + len(self.CLOSE_TAG) :]
                self._in_think = False
            else:
                idx = self._buffer.find(self.OPEN_TAG)
                if idx == -1:
                    keep = self._partial_suffix_len(self._buffer, self.OPEN_TAG)
                    emit_until = len(self._buffer) - keep
                    emitted.append(self._buffer[:emit_until])
                    self._buffer = self._buffer[emit_until:]
                    return "".join(emitted)
                emitted.append(self._buffer[:idx])
                self._buffer = self._buffer[idx + len(self.OPEN_TAG) :]
                self._in_think = True

    def flush(self) -> str:
        """Release held-back text after the stream ends.

        Text held as a potential tag prefix is emitted (it never became a
        tag); anything inside an unterminated think block stays dropped.
        """
        leftover = "" if self._in_think else self._buffer
        self._buffer = ""
        return leftover
```

Note: `List` is already imported in this module's `typing` import.

- [ ] **Step 2.4: Run tests to verify they pass**

Run: `pytest app/tests/test_services/test_inference_streaming.py -v`
Expected: all `TestThinkTagFilter` tests PASS.

Watch `test_lone_angle_bracket_passes_through`: `"a <t"` holds back `"<t"` (prefix of `<think>`), then `"ag> done"` disambiguates — output must be byte-identical to input.

- [ ] **Step 2.5: Commit**

```bash
git add app/services/inference_service.py app/tests/test_services/test_inference_streaming.py
git commit -m "feat: add ThinkTagFilter for streamed think-tag stripping"
```

---

### Task 3: OpenAI passthrough params on `run_inference`

**Files:**
- Modify: `app/services/inference_service.py` (`InferenceService.run_inference` signature + payload)
- Test: `app/tests/test_services/test_inference_streaming.py` (append class)

- [ ] **Step 3.1: Write the failing tests**

Append to `app/tests/test_services/test_inference_streaming.py`:

```python
def _make_chunk(
    content: Optional[str] = None,
    usage: Optional[Dict[str, int]] = None,
    role: Optional[str] = None,
) -> SimpleNamespace:
    """Build a fake OpenAI streaming chunk object."""
    choices = []
    if content is not None or role is not None:
        choices = [
            SimpleNamespace(
                delta=SimpleNamespace(role=role, content=content),
                index=0,
                finish_reason=None,
            )
        ]
    usage_ns = SimpleNamespace(**usage) if usage else None
    return SimpleNamespace(choices=choices, usage=usage_ns)


def _make_completion(content: str) -> SimpleNamespace:
    """Build a fake non-streaming OpenAI completion response."""
    return SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content=content))
        ],
        usage=SimpleNamespace(
            completion_tokens=3, prompt_tokens=5, total_tokens=8
        ),
    )


class TestRunInferencePassthroughParams:
    """run_inference must forward max_tokens/top_p/stop to the API payload."""

    def _service_with_mock_client(self) -> tuple:
        service = InferenceService(
            runpod_api_key="test-key", qwen_endpoint_id="test-endpoint"
        )
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_completion(
            "Oli otya?"
        )
        return service, mock_client

    def test_passthrough_params_in_payload(self) -> None:
        service, mock_client = self._service_with_mock_client()
        with patch.object(service, "_get_client", return_value=mock_client):
            service.run_inference(
                messages=[{"role": "user", "content": "Hello"}],
                temperature=0.7,
                max_tokens=128,
                top_p=0.9,
                stop=["\n"],
            )
        kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert kwargs["temperature"] == 0.7
        assert kwargs["max_tokens"] == 128
        assert kwargs["top_p"] == 0.9
        assert kwargs["stop"] == ["\n"]

    def test_omitted_params_not_in_payload(self) -> None:
        service, mock_client = self._service_with_mock_client()
        with patch.object(service, "_get_client", return_value=mock_client):
            service.run_inference(
                messages=[{"role": "user", "content": "Hello"}]
            )
        kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert "max_tokens" not in kwargs
        assert "top_p" not in kwargs
        assert "stop" not in kwargs
```

- [ ] **Step 3.2: Run tests to verify they fail**

Run: `pytest app/tests/test_services/test_inference_streaming.py::TestRunInferencePassthroughParams -v`
Expected: FAIL — `TypeError: run_inference() got an unexpected keyword argument 'max_tokens'`

- [ ] **Step 3.3: Implement**

In `InferenceService.run_inference`, change the signature:

```python
    def run_inference(  # noqa: C901
        self,
        instruction: Optional[str] = None,
        model_type: str = "qwen",
        stream: bool = False,
        custom_system_message: Optional[str] = None,
        messages: Optional[List[Dict[str, str]]] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        stop: Optional[Any] = None,
    ) -> Dict[str, Any]:
```

and immediately after the existing `payload = {...}` assignment add:

```python
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if top_p is not None:
            payload["top_p"] = top_p
        if stop is not None:
            payload["stop"] = stop
```

Also update the docstring Args list with the three new params (one line each).

- [ ] **Step 3.4: Run tests to verify they pass**

Run: `pytest app/tests/test_services/test_inference_streaming.py -v`
Expected: PASS (both new tests; ThinkTagFilter tests still green)

- [ ] **Step 3.5: Regression check + commit**

Run: `pytest app/tests/test_services/test_inference_service.py app/tests/test_routers/test_inference.py -v`
Expected: PASS (signature change is backward compatible)

```bash
git add app/services/inference_service.py app/tests/test_services/test_inference_streaming.py
git commit -m "feat: forward max_tokens/top_p/stop through run_inference"
```

---

### Task 4: `run_inference_stream` generator

**Files:**
- Modify: `app/services/inference_service.py` (new method on `InferenceService`, after `run_inference`)
- Test: `app/tests/test_services/test_inference_streaming.py` (append class)

- [ ] **Step 4.1: Write the failing tests**

Append to `app/tests/test_services/test_inference_streaming.py`:

```python
class TestRunInferenceStream:
    """Tests for the run_inference_stream generator."""

    def _service_with_chunks(self, chunks: List[Any]) -> InferenceService:
        service = InferenceService(
            runpod_api_key="test-key", qwen_endpoint_id="test-endpoint"
        )
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = iter(chunks)
        self._mock_client = mock_client
        patcher = patch.object(service, "_get_client", return_value=mock_client)
        patcher.start()
        self._patcher = patcher
        return service

    def teardown_method(self) -> None:
        if getattr(self, "_patcher", None):
            self._patcher.stop()
            self._patcher = None

    def _collect(self, gen: Iterator[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return list(gen)

    def test_yields_deltas_and_usage(self) -> None:
        service = self._service_with_chunks(
            [
                _make_chunk(role="assistant", content=""),
                _make_chunk(content="Oli "),
                _make_chunk(content="otya?"),
                _make_chunk(
                    usage={
                        "completion_tokens": 3,
                        "prompt_tokens": 5,
                        "total_tokens": 8,
                    }
                ),
            ]
        )
        items = self._collect(
            service.run_inference_stream(
                messages=[{"role": "user", "content": "Greet me"}]
            )
        )
        deltas = [i for i in items if i["type"] == "delta"]
        usage = [i for i in items if i["type"] == "usage"]
        assert "".join(d["content"] for d in deltas) == "Oli otya?"
        assert usage == [
            {
                "type": "usage",
                "usage": {
                    "completion_tokens": 3,
                    "prompt_tokens": 5,
                    "total_tokens": 8,
                },
            }
        ]

    def test_filters_think_tags_across_chunks(self) -> None:
        service = self._service_with_chunks(
            [
                _make_chunk(content="<thi"),
                _make_chunk(content="nk>internal</th"),
                _make_chunk(content="ink>Visible"),
            ]
        )
        items = self._collect(
            service.run_inference_stream(
                messages=[{"role": "user", "content": "Hi"}]
            )
        )
        assert "".join(
            i["content"] for i in items if i["type"] == "delta"
        ) == "Visible"

    def test_requests_stream_with_usage(self) -> None:
        service = self._service_with_chunks([_make_chunk(content="x")])
        self._collect(
            service.run_inference_stream(
                messages=[{"role": "user", "content": "Hi"}],
                temperature=0.5,
                max_tokens=64,
            )
        )
        kwargs = self._mock_client.chat.completions.create.call_args.kwargs
        assert kwargs["stream"] is True
        assert kwargs["stream_options"] == {"include_usage": True}
        assert kwargs["temperature"] == 0.5
        assert kwargs["max_tokens"] == 64

    def test_unsupported_model_type_raises_value_error(self) -> None:
        service = InferenceService(
            runpod_api_key="test-key", qwen_endpoint_id="test-endpoint"
        )
        with pytest.raises(ValueError):
            list(
                service.run_inference_stream(
                    messages=[{"role": "user", "content": "Hi"}],
                    model_type="nonexistent",
                )
            )
```

- [ ] **Step 4.2: Run tests to verify they fail**

Run: `pytest app/tests/test_services/test_inference_streaming.py::TestRunInferenceStream -v`
Expected: FAIL — `AttributeError: ... has no attribute 'run_inference_stream'`

- [ ] **Step 4.3: Implement `run_inference_stream`**

Add to `InferenceService` directly after `run_inference` (uses the module's existing `exponential_backoff_retry`, `classify_error`, `ModelLoadingError`, `InferenceTimeoutError`; add `Iterator` to the `typing` import):

```python
    def run_inference_stream(
        self,
        instruction: Optional[str] = None,
        model_type: str = "qwen",
        custom_system_message: Optional[str] = None,
        messages: Optional[List[Dict[str, str]]] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        stop: Optional[Any] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Stream inference results as they are generated.

        Yields dictionaries of two shapes:
            {"type": "delta", "content": str}   — cleaned content increments
            {"type": "usage", "usage": dict}    — final token usage, if the
                                                  upstream API reports it

        ``<think>`` spans are stripped via ThinkTagFilter before content is
        yielded. Retry with exponential backoff applies only to creating the
        stream (i.e., before the first token); once streaming has begun,
        failures propagate to the caller and are never retried.

        Raises:
            ValueError: If the model type is not supported.
            ModelLoadingError: If the model is still loading after retries.
            InferenceTimeoutError: If stream creation times out after retries.
        """
        config = self.endpoints.get(model_type.lower())
        if not config:
            self.log_error(f"Unsupported model type: {model_type}")
            raise ValueError(f"Unsupported model type: {model_type}")

        client = self._get_client(model_type)
        final_messages = self._build_messages(
            instruction=instruction,
            messages=messages,
            custom_system_message=custom_system_message,
        )

        payload: Dict[str, Any] = {
            "model": config["model_name"],
            "messages": final_messages,
            "temperature": temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if top_p is not None:
            payload["top_p"] = top_p
        if stop is not None:
            payload["stop"] = stop

        @exponential_backoff_retry(
            max_retries=4,
            base_delay=3.0,
            max_delay=180.0,
            exponential_base=2.0,
            jitter=True,
            retryable_exceptions=(ModelLoadingError, InferenceTimeoutError),
        )
        def _create_stream() -> Any:
            try:
                return client.chat.completions.create(**payload)
            except (ModelLoadingError, InferenceTimeoutError):
                raise
            except Exception as e:
                raise classify_error(e, str(e))

        self.log_info("Opening streaming request to RunPod API...")
        stream = _create_stream()

        think_filter = ThinkTagFilter()
        usage_dict: Optional[Dict[str, Any]] = None

        for chunk in stream:
            usage = getattr(chunk, "usage", None)
            if usage is not None:
                usage_dict = {
                    "completion_tokens": getattr(usage, "completion_tokens", None),
                    "prompt_tokens": getattr(usage, "prompt_tokens", None),
                    "total_tokens": getattr(usage, "total_tokens", None),
                }

            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue
            delta = getattr(choices[0], "delta", None)
            content = getattr(delta, "content", None) if delta else None
            if content:
                cleaned = think_filter.feed(content)
                if cleaned:
                    yield {"type": "delta", "content": cleaned}

        tail = think_filter.flush()
        if tail:
            yield {"type": "delta", "content": tail}

        if usage_dict is not None:
            yield {"type": "usage", "usage": usage_dict}

        self.log_info("Streaming request completed")
```

- [ ] **Step 4.4: Run tests to verify they pass**

Run: `pytest app/tests/test_services/test_inference_streaming.py -v`
Expected: PASS (all classes)

- [ ] **Step 4.5: Commit**

```bash
git add app/services/inference_service.py app/tests/test_services/test_inference_streaming.py
git commit -m "feat: add run_inference_stream generator to InferenceService"
```

---

### Task 5: Router — non-streaming `/tasks/chat/completions`

**Files:**
- Create: `app/routers/chat.py`
- Modify: `app/api.py` (import + include router)
- Modify: `app/utils/feedback.py` (add `INFERENCE_TYPES["chat_completions"]`)
- Test: `app/tests/test_routers/test_chat.py` (append fixtures + class)

- [ ] **Step 5.1: Write the failing tests**

Append to `app/tests/test_routers/test_chat.py` (add the new imports to the top of the file):

```python
# --- add to imports at top of file ---
from typing import Any, Dict
from unittest.mock import MagicMock

from httpx import AsyncClient

from app.services.inference_service import (
    InferenceService,
    InferenceTimeoutError,
    ModelLoadingError,
)
# --- end imports ---


@pytest.fixture
def mock_service() -> MagicMock:
    """A MagicMock standing in for InferenceService."""
    return MagicMock(spec=InferenceService)


@pytest.fixture
def override_service(mock_service: MagicMock):
    """Route get_service to the mock for the duration of a test."""
    from app.api import app
    from app.routers.chat import get_service

    app.dependency_overrides[get_service] = lambda: mock_service
    yield mock_service
    app.dependency_overrides.pop(get_service, None)


SAMPLE_RESULT: Dict[str, Any] = {
    "content": "In Luganda, 'How are you?' is 'Oli otya?'.",
    "model_type": "qwen",
    "usage": {"completion_tokens": 15, "prompt_tokens": 50, "total_tokens": 65},
    "processing_time": 2.0,
}


class TestChatCompletionsEndpoint:
    """Tests for POST /tasks/chat/completions (non-streaming)."""

    async def test_successful_completion_openai_shape(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        override_service: MagicMock,
    ) -> None:
        override_service.run_inference.return_value = SAMPLE_RESULT
        response = await async_client.post(
            "/tasks/chat/completions",
            json={
                "messages": [
                    {"role": "user", "content": "Translate 'How are you?' to Luganda."}
                ]
            },
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["object"] == "chat.completion"
        assert data["id"].startswith("chatcmpl-")
        assert isinstance(data["created"], int)
        assert data["model"] == "Sunbird/Sunflower-14B"
        assert data["choices"][0]["index"] == 0
        assert data["choices"][0]["message"]["role"] == "assistant"
        assert (
            data["choices"][0]["message"]["content"]
            == "In Luganda, 'How are you?' is 'Oli otya?'."
        )
        assert data["choices"][0]["finish_reason"] == "stop"
        assert data["usage"]["total_tokens"] == 65

    async def test_default_system_message_injected(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        override_service: MagicMock,
    ) -> None:
        override_service.run_inference.return_value = SAMPLE_RESULT
        await async_client.post(
            "/tasks/chat/completions",
            json={"messages": [{"role": "user", "content": "Hello"}]},
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        sent = override_service.run_inference.call_args.kwargs["messages"]
        assert sent[0]["role"] == "system"
        assert "Sunflower" in sent[0]["content"]

    async def test_client_system_message_preserved(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        override_service: MagicMock,
    ) -> None:
        override_service.run_inference.return_value = SAMPLE_RESULT
        await async_client.post(
            "/tasks/chat/completions",
            json={
                "messages": [
                    {"role": "system", "content": "You are terse."},
                    {"role": "user", "content": "Hello"},
                ]
            },
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        sent = override_service.run_inference.call_args.kwargs["messages"]
        assert sent[0] == {"role": "system", "content": "You are terse."}
        assert sum(1 for m in sent if m["role"] == "system") == 1

    async def test_multi_turn_history_passed_through(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        override_service: MagicMock,
    ) -> None:
        override_service.run_inference.return_value = SAMPLE_RESULT
        await async_client.post(
            "/tasks/chat/completions",
            json={
                "messages": [
                    {"role": "user", "content": "Translate 'hello' to Luganda."},
                    {"role": "assistant", "content": "'Hello' is 'Gyebaleko'."},
                    {"role": "user", "content": "And to Acholi?"},
                ]
            },
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        sent = override_service.run_inference.call_args.kwargs["messages"]
        # default system + 3 conversation messages
        assert len(sent) == 4
        assert [m["role"] for m in sent[1:]] == ["user", "assistant", "user"]

    async def test_requires_auth(self, async_client: AsyncClient) -> None:
        response = await async_client.post(
            "/tasks/chat/completions",
            json={"messages": [{"role": "user", "content": "Hello"}]},
        )
        assert response.status_code == 401

    async def test_unknown_model_rejected_with_400(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        override_service: MagicMock,
    ) -> None:
        response = await async_client.post(
            "/tasks/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "Hello"}],
            },
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        assert response.status_code == 400
        assert "Sunbird/Sunflower-14B" in response.json()["message"]
        override_service.run_inference.assert_not_called()

    async def test_empty_messages_rejected_with_422(
        self,
        async_client: AsyncClient,
        test_user: Dict,
    ) -> None:
        response = await async_client.post(
            "/tasks/chat/completions",
            json={"messages": []},
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        assert response.status_code == 422

    async def test_invalid_role_rejected_with_422(
        self,
        async_client: AsyncClient,
        test_user: Dict,
    ) -> None:
        response = await async_client.post(
            "/tasks/chat/completions",
            json={"messages": [{"role": "tool", "content": "Hello"}]},
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        assert response.status_code == 422

    async def test_blank_content_rejected_with_422(
        self,
        async_client: AsyncClient,
        test_user: Dict,
    ) -> None:
        response = await async_client.post(
            "/tasks/chat/completions",
            json={"messages": [{"role": "user", "content": "   "}]},
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        assert response.status_code == 422

    async def test_model_loading_maps_to_503(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        override_service: MagicMock,
    ) -> None:
        override_service.run_inference.side_effect = ModelLoadingError("loading")
        response = await async_client.post(
            "/tasks/chat/completions",
            json={"messages": [{"role": "user", "content": "Hello"}]},
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        assert response.status_code == 503

    async def test_timeout_maps_to_503(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        override_service: MagicMock,
    ) -> None:
        override_service.run_inference.side_effect = InferenceTimeoutError("slow")
        response = await async_client.post(
            "/tasks/chat/completions",
            json={"messages": [{"role": "user", "content": "Hello"}]},
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        assert response.status_code == 503

    async def test_empty_model_response_maps_to_502(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        override_service: MagicMock,
    ) -> None:
        override_service.run_inference.return_value = {
            "content": "",
            "usage": {},
        }
        response = await async_client.post(
            "/tasks/chat/completions",
            json={"messages": [{"role": "user", "content": "Hello"}]},
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        assert response.status_code == 502

    async def test_params_forwarded_to_service(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        override_service: MagicMock,
    ) -> None:
        override_service.run_inference.return_value = SAMPLE_RESULT
        await async_client.post(
            "/tasks/chat/completions",
            json={
                "messages": [{"role": "user", "content": "Hello"}],
                "temperature": 0.9,
                "max_tokens": 256,
                "top_p": 0.8,
                "stop": ["###"],
            },
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        kwargs = override_service.run_inference.call_args.kwargs
        assert kwargs["temperature"] == 0.9
        assert kwargs["max_tokens"] == 256
        assert kwargs["top_p"] == 0.8
        assert kwargs["stop"] == ["###"]
```

- [ ] **Step 5.2: Run tests to verify they fail**

Run: `pytest app/tests/test_routers/test_chat.py -v`
Expected: FAIL at fixture/import — `ModuleNotFoundError: No module named 'app.routers.chat'` (schema tests still pass)

- [ ] **Step 5.3: Add the feedback inference type**

In `app/utils/feedback.py`, inside `INFERENCE_TYPES`, add after the `"sunflower_simple"` entry:

```python
    "chat_completions": "chat_completions",
```

- [ ] **Step 5.4: Create the router (non-streaming path; streaming raises for now)**

Create `app/routers/chat.py`:

```python
"""
Chat Completions Router Module.

OpenAI-compatible chat completions for the Sunflower model. This endpoint
supersedes the deprecated /tasks/sunflower_inference and
/tasks/sunflower_simple endpoints: a single instruction is simply a request
with one user message, and conversational context is the messages array.

Endpoints:
    - POST /chat/completions: OpenAI-format chat completion (JSON or SSE)

Architecture:
    Routes -> InferenceService -> RunPod OpenAI-compatible API

Spec:
    docs/superpowers/specs/2026-06-12-chat-completions-design.md
"""

import json
import logging
import time
import uuid
from typing import Any, Dict, Generator, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.exceptions import (
    BadRequestError,
    ExternalServiceError,
    ServiceUnavailableError,
)
from app.deps import QuotaServiceDep, get_current_user, get_db
from app.schemas.chat import (
    SUPPORTED_MODELS,
    ChatCompletionChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionResponseMessage,
    ChatCompletionUsage,
)
from app.services.inference_service import (
    InferenceService,
    InferenceTimeoutError,
    ModelLoadingError,
    get_inference_service,
)
from app.utils.feedback import INFERENCE_TYPES, save_api_inference
from app.utils.quota_guard import check_quota
from app.utils.rate_limit import get_account_type_limit, limiter

logger = logging.getLogger(__name__)

router = APIRouter()

# RunPod endpoint key that serves Sunbird/Sunflower-14B (see
# InferenceService.endpoints).
INTERNAL_MODEL_TYPE = "qwen"


def get_service() -> InferenceService:
    """Dependency for getting the Inference service instance."""
    return get_inference_service()


def _completion_id() -> str:
    """Generate an OpenAI-style completion id."""
    return f"chatcmpl-{uuid.uuid4().hex}"


def _prepare_messages(chat_request: ChatCompletionRequest) -> List[Dict[str, str]]:
    """Convert request messages to dicts, injecting the default system message
    when the client did not provide one (mirrors the legacy endpoints)."""
    messages = [
        {"role": m.role, "content": m.content.strip()}
        for m in chat_request.messages
    ]
    if not any(m["role"] == "system" for m in messages):
        messages.insert(
            0, {"role": "system", "content": InferenceService.SYSTEM_MESSAGE}
        )
    return messages


def _validate_model(chat_request: ChatCompletionRequest) -> None:
    """Strict model validation: only models in SUPPORTED_MODELS are accepted."""
    if chat_request.model not in SUPPORTED_MODELS:
        raise BadRequestError(
            message=(
                f"Model '{chat_request.model}' is not supported. "
                f"Supported models: {', '.join(SUPPORTED_MODELS)}"
            )
        )


@router.post(
    "/chat/completions",
    response_model=ChatCompletionResponse,
    summary="OpenAI-compatible chat completion (Sunflower)",
)
@limiter.limit(get_account_type_limit)
async def chat_completions(
    request: Request,
    chat_request: ChatCompletionRequest,
    quota: QuotaServiceDep,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    service: InferenceService = Depends(get_service),
):
    """OpenAI-compatible chat completion powered by Sunbird's Sunflower model.

    Single-instruction usage is a request with one user message; conversational
    usage passes the running message history. Set ``stream: true`` for
    Server-Sent Events in OpenAI ``chat.completion.chunk`` format, terminated
    by ``data: [DONE]``.
    """
    await check_quota(quota, db, current_user)
    _validate_model(chat_request)
    messages = _prepare_messages(chat_request)

    logger.info(
        f"Chat completion requested by user {current_user.id} "
        f"({len(messages)} messages, stream={chat_request.stream})"
    )

    if chat_request.stream:
        return await _stream_chat_completion(
            chat_request, messages, service, background_tasks, current_user
        )
    return await _create_chat_completion(
        chat_request, messages, service, background_tasks, current_user
    )


async def _create_chat_completion(
    chat_request: ChatCompletionRequest,
    messages: List[Dict[str, str]],
    service: InferenceService,
    background_tasks: BackgroundTasks,
    user: Any,
) -> ChatCompletionResponse:
    """Non-streaming path: run inference and build a chat.completion object."""
    start_time = time.time()

    try:
        result = await run_in_threadpool(
            lambda: service.run_inference(
                messages=messages,
                model_type=INTERNAL_MODEL_TYPE,
                temperature=chat_request.temperature,
                max_tokens=chat_request.max_tokens,
                top_p=chat_request.top_p,
                stop=chat_request.stop,
            )
        )
    except ModelLoadingError as e:
        logger.error(f"Model loading error: {e}")
        raise ServiceUnavailableError(
            message=(
                "The AI model is currently loading. This usually takes "
                "2-3 minutes. Please try again shortly."
            )
        )
    except InferenceTimeoutError as e:
        logger.error(f"Inference timeout: {e}")
        raise ServiceUnavailableError(
            message="The request timed out. Please try again with a shorter prompt."
        )
    except ValueError as e:
        logger.error(f"Invalid request: {e}")
        raise BadRequestError(message=f"Invalid request: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected inference error: {e}")
        raise ExternalServiceError(
            service_name="Sunflower Inference Service",
            message="An unexpected error occurred during inference. Please try again.",
            original_error=str(e),
        )

    content = (result or {}).get("content")
    if not content:
        raise ExternalServiceError(
            service_name="Sunflower Model",
            message=(
                "The model returned an empty response. "
                "Please try rephrasing your request."
            ),
        )

    total_time = time.time() - start_time
    usage = (result or {}).get("usage") or {}

    background_tasks.add_task(
        save_api_inference,
        messages,
        content,
        user,
        model_type=chat_request.model,
        processing_time=total_time,
        inference_type=INFERENCE_TYPES["chat_completions"],
    )

    logger.info(f"Chat completion finished in {total_time:.2f}s")

    return ChatCompletionResponse(
        id=_completion_id(),
        created=int(time.time()),
        model=chat_request.model,
        choices=[
            ChatCompletionChoice(
                index=0,
                message=ChatCompletionResponseMessage(content=content),
                finish_reason="stop",
            )
        ],
        usage=ChatCompletionUsage(
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
        ),
    )


async def _stream_chat_completion(
    chat_request: ChatCompletionRequest,
    messages: List[Dict[str, str]],
    service: InferenceService,
    background_tasks: BackgroundTasks,
    user: Any,
) -> StreamingResponse:
    """Streaming path — implemented in Task 6."""
    raise BadRequestError(message="Streaming is not implemented yet")
```

- [ ] **Step 5.5: Mount the router in `app/api.py`**

After the existing line `from app.routers.inference import router as inference_router` add:

```python
from app.routers.chat import router as chat_router
```

After the existing line `app.include_router(inference_router, prefix="/tasks", tags=["Sunflower"])` add:

```python
app.include_router(chat_router, prefix="/tasks", tags=["Chat"])
```

- [ ] **Step 5.6: Run tests to verify they pass**

Run: `pytest app/tests/test_routers/test_chat.py -v`
Expected: all `TestChatSchemas` + `TestChatCompletionsEndpoint` tests PASS

- [ ] **Step 5.7: Commit**

```bash
git add app/routers/chat.py app/api.py app/utils/feedback.py app/tests/test_routers/test_chat.py
git commit -m "feat: add OpenAI-compatible /tasks/chat/completions endpoint (non-streaming)"
```

---

### Task 6: Router — SSE streaming path

**Files:**
- Modify: `app/routers/chat.py` (replace the `_stream_chat_completion` stub; add chunk imports)
- Test: `app/tests/test_routers/test_chat.py` (append class + SSE helper)

- [ ] **Step 6.1: Write the failing tests**

Append to `app/tests/test_routers/test_chat.py`:

```python
import json as jsonlib


async def _read_sse_events(response) -> list:
    """Collect SSE `data:` payloads from a streaming httpx response."""
    events = []
    buffer = ""
    async for text in response.aiter_text():
        buffer += text
    for line in buffer.split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            events.append(line[len("data: ") :])
    return events


class TestChatCompletionsStreaming:
    """Tests for POST /tasks/chat/completions with stream=true."""

    def _stream_items(self):
        return iter(
            [
                {"type": "delta", "content": "Oli "},
                {"type": "delta", "content": "otya?"},
                {
                    "type": "usage",
                    "usage": {
                        "completion_tokens": 3,
                        "prompt_tokens": 5,
                        "total_tokens": 8,
                    },
                },
            ]
        )

    async def test_streaming_sse_chunks(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        override_service: MagicMock,
    ) -> None:
        override_service.run_inference_stream.return_value = self._stream_items()
        async with async_client.stream(
            "POST",
            "/tasks/chat/completions",
            json={
                "messages": [{"role": "user", "content": "Greet me"}],
                "stream": True,
            },
            headers={"Authorization": f"Bearer {test_user['token']}"},
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith(
                "text/event-stream"
            )
            events = await _read_sse_events(response)

        assert events[-1] == "[DONE]"
        chunks = [jsonlib.loads(e) for e in events[:-1]]

        # Every chunk is a chat.completion.chunk with a stable id
        ids = {c["id"] for c in chunks}
        assert len(ids) == 1
        assert ids.pop().startswith("chatcmpl-")
        assert all(c["object"] == "chat.completion.chunk" for c in chunks)
        assert all(c["model"] == "Sunbird/Sunflower-14B" for c in chunks)

        # First chunk primes the assistant role
        assert chunks[0]["choices"][0]["delta"]["role"] == "assistant"

        # Accumulated content equals the full text
        content = "".join(
            c["choices"][0]["delta"].get("content") or ""
            for c in chunks
            if c["choices"]
        )
        assert content == "Oli otya?"

        # A finish chunk with finish_reason == "stop" exists
        assert any(
            c["choices"] and c["choices"][0]["finish_reason"] == "stop"
            for c in chunks
        )

        # The usage chunk carries usage and no choices
        usage_chunks = [c for c in chunks if c.get("usage")]
        assert len(usage_chunks) == 1
        assert usage_chunks[0]["usage"]["total_tokens"] == 8
        assert usage_chunks[0]["choices"] == []

    async def test_streaming_model_loading_maps_to_503(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        override_service: MagicMock,
    ) -> None:
        def _raise(*args, **kwargs):
            raise ModelLoadingError("cold start")
            yield  # pragma: no cover - makes this a generator function

        override_service.run_inference_stream.side_effect = (
            lambda *a, **k: _raise()
        )
        response = await async_client.post(
            "/tasks/chat/completions",
            json={
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": True,
            },
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        assert response.status_code == 503

    async def test_streaming_empty_stream_maps_to_502(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        override_service: MagicMock,
    ) -> None:
        override_service.run_inference_stream.return_value = iter([])
        response = await async_client.post(
            "/tasks/chat/completions",
            json={
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": True,
            },
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        assert response.status_code == 502

    async def test_streaming_midstream_error_emits_error_event(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        override_service: MagicMock,
    ) -> None:
        def _explodes():
            yield {"type": "delta", "content": "partial"}
            raise RuntimeError("connection lost")

        override_service.run_inference_stream.return_value = _explodes()
        async with async_client.stream(
            "POST",
            "/tasks/chat/completions",
            json={
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": True,
            },
            headers={"Authorization": f"Bearer {test_user['token']}"},
        ) as response:
            assert response.status_code == 200
            events = await _read_sse_events(response)

        assert events[-1] == "[DONE]"
        error_events = [
            jsonlib.loads(e) for e in events[:-1] if '"error"' in e
        ]
        assert len(error_events) == 1
        assert error_events[0]["error"]["type"] == "server_error"
```

- [ ] **Step 6.2: Run tests to verify they fail**

Run: `pytest app/tests/test_routers/test_chat.py::TestChatCompletionsStreaming -v`
Expected: FAIL — streaming requests currently return 400 ("Streaming is not implemented yet")

- [ ] **Step 6.3: Implement the streaming path**

In `app/routers/chat.py`, extend the schemas import to include the chunk models:

```python
from app.schemas.chat import (
    SUPPORTED_MODELS,
    ChatCompletionChoice,
    ChatCompletionChunk,
    ChatCompletionChunkChoice,
    ChatCompletionChunkDelta,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionResponseMessage,
    ChatCompletionUsage,
)
```

Replace the `_stream_chat_completion` stub entirely with:

```python
async def _stream_chat_completion(
    chat_request: ChatCompletionRequest,
    messages: List[Dict[str, str]],
    service: InferenceService,
    background_tasks: BackgroundTasks,
    user: Any,
) -> StreamingResponse:
    """Streaming path: emit OpenAI chat.completion.chunk SSE events.

    The first item is fetched eagerly (in a worker thread) so that failures
    occurring before any token has been produced surface as proper HTTP
    errors instead of a 200 SSE stream. After streaming begins, failures
    terminate the stream with an SSE error event and are never retried.
    """
    completion_id = _completion_id()
    created = int(time.time())
    start_time = time.time()

    stream_gen = service.run_inference_stream(
        messages=messages,
        model_type=INTERNAL_MODEL_TYPE,
        temperature=chat_request.temperature,
        max_tokens=chat_request.max_tokens,
        top_p=chat_request.top_p,
        stop=chat_request.stop,
    )

    try:
        first_item = await run_in_threadpool(lambda: next(stream_gen, None))
    except ModelLoadingError as e:
        logger.error(f"Model loading error before stream start: {e}")
        raise ServiceUnavailableError(
            message=(
                "The AI model is currently loading. This usually takes "
                "2-3 minutes. Please try again shortly."
            )
        )
    except InferenceTimeoutError as e:
        logger.error(f"Timeout before stream start: {e}")
        raise ServiceUnavailableError(
            message="The request timed out. Please try again with a shorter prompt."
        )
    except ValueError as e:
        logger.error(f"Invalid streaming request: {e}")
        raise BadRequestError(message=f"Invalid request: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error before stream start: {e}")
        raise ExternalServiceError(
            service_name="Sunflower Inference Service",
            message="An unexpected error occurred during inference. Please try again.",
            original_error=str(e),
        )

    if first_item is None:
        raise ExternalServiceError(
            service_name="Sunflower Model",
            message=(
                "The model returned an empty response. "
                "Please try rephrasing your request."
            ),
        )

    accumulated: List[str] = []

    def _sse_chunk(
        delta: ChatCompletionChunkDelta,
        finish_reason: Optional[str] = None,
    ) -> str:
        chunk = ChatCompletionChunk(
            id=completion_id,
            created=created,
            model=chat_request.model,
            choices=[
                ChatCompletionChunkChoice(
                    index=0, delta=delta, finish_reason=finish_reason
                )
            ],
        )
        return f"data: {chunk.model_dump_json()}\n\n"

    def _sse_usage_chunk(usage: Dict[str, Any]) -> str:
        chunk = ChatCompletionChunk(
            id=completion_id,
            created=created,
            model=chat_request.model,
            choices=[],
            usage=ChatCompletionUsage(
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
            ),
        )
        return f"data: {chunk.model_dump_json()}\n\n"

    def event_stream() -> Generator[str, None, None]:
        usage_stats: Optional[Dict[str, Any]] = None
        try:
            yield _sse_chunk(
                ChatCompletionChunkDelta(role="assistant", content="")
            )
            item = first_item
            while item is not None:
                if item.get("type") == "delta":
                    text = item.get("content") or ""
                    if text:
                        accumulated.append(text)
                        yield _sse_chunk(ChatCompletionChunkDelta(content=text))
                elif item.get("type") == "usage":
                    usage_stats = item.get("usage")
                item = next(stream_gen, None)

            yield _sse_chunk(ChatCompletionChunkDelta(), finish_reason="stop")
            if usage_stats:
                yield _sse_usage_chunk(usage_stats)
        except Exception as e:
            logger.error(f"Error during chat completion stream: {e}")
            error_payload = {
                "error": {
                    "message": (
                        "The stream was interrupted by an unexpected error. "
                        "Please retry the request."
                    ),
                    "type": "server_error",
                }
            }
            yield f"data: {json.dumps(error_payload)}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    async def _save_stream_feedback() -> None:
        if accumulated:
            await save_api_inference(
                messages,
                "".join(accumulated),
                user,
                model_type=chat_request.model,
                processing_time=time.time() - start_time,
                inference_type=INFERENCE_TYPES["chat_completions"],
            )

    background_tasks.add_task(_save_stream_feedback)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

Implementation notes (for the engineer):
- `event_stream` is a **sync** generator; Starlette iterates it in a threadpool, so the blocking `next(stream_gen)` calls do not block the event loop.
- FastAPI attaches the injected `BackgroundTasks` to a directly returned `Response` when `response.background` is unset, so the feedback task runs after the stream finishes.
- `first_item` is consumed before the response is created — that is what makes cold-start failures a real 503 instead of a 200 with an error event.

- [ ] **Step 6.4: Run tests to verify they pass**

Run: `pytest app/tests/test_routers/test_chat.py -v`
Expected: all tests PASS (schemas, non-streaming, streaming)

- [ ] **Step 6.5: Commit**

```bash
git add app/routers/chat.py app/tests/test_routers/test_chat.py
git commit -m "feat: add SSE streaming to /tasks/chat/completions"
```

---

### Task 7: Deprecate the legacy Sunflower endpoints

**Files:**
- Modify: `app/routers/inference.py` (both route decorators + handler signatures)
- Test: `app/tests/test_routers/test_chat.py` (append class)

- [ ] **Step 7.1: Write the failing tests**

Append to `app/tests/test_routers/test_chat.py`:

```python
class TestLegacyEndpointDeprecation:
    """The legacy Sunflower endpoints must still work but be deprecated."""

    SUCCESSOR_LINK = '</tasks/chat/completions>; rel="successor-version"'

    async def test_sunflower_inference_has_deprecation_headers(
        self,
        async_client: AsyncClient,
        test_user: Dict,
    ) -> None:
        from unittest.mock import patch

        with patch(
            "app.routers.inference.run_inference",
            return_value=SAMPLE_RESULT,
        ):
            response = await async_client.post(
                "/tasks/sunflower_inference",
                json={"messages": [{"role": "user", "content": "Hello"}]},
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )
        assert response.status_code == 200
        assert response.headers["deprecation"] == "true"
        assert response.headers["link"] == self.SUCCESSOR_LINK

    async def test_sunflower_simple_has_deprecation_headers(
        self,
        async_client: AsyncClient,
        test_user: Dict,
    ) -> None:
        from unittest.mock import patch

        with patch(
            "app.routers.inference.run_inference",
            return_value=SAMPLE_RESULT,
        ):
            response = await async_client.post(
                "/tasks/sunflower_simple",
                data={"instruction": "Translate 'hello' to Luganda"},
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )
        assert response.status_code == 200
        assert response.headers["deprecation"] == "true"
        assert response.headers["link"] == self.SUCCESSOR_LINK

    async def test_openapi_marks_legacy_endpoints_deprecated(self) -> None:
        from app.api import app

        schema = app.openapi()
        assert (
            schema["paths"]["/tasks/sunflower_inference"]["post"].get("deprecated")
            is True
        )
        assert (
            schema["paths"]["/tasks/sunflower_simple"]["post"].get("deprecated")
            is True
        )
        assert (
            schema["paths"]["/tasks/chat/completions"]["post"].get("deprecated")
            is not True
        )
```

- [ ] **Step 7.2: Run tests to verify they fail**

Run: `pytest app/tests/test_routers/test_chat.py::TestLegacyEndpointDeprecation -v`
Expected: FAIL — `KeyError: 'deprecation'` (header missing) and the openapi assertion fails

- [ ] **Step 7.3: Implement deprecation in `app/routers/inference.py`**

1. Extend the fastapi import line to include `Response`:

```python
from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request, Response
```

2. Add a module-level helper after `get_service()`:

```python
def _add_deprecation_headers(response: Response) -> None:
    """RFC 8594 deprecation headers pointing at the successor endpoint."""
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = '</tasks/chat/completions>; rel="successor-version"'
```

3. Change the `sunflower_inference` decorator and signature:

```python
@router.post(
    "/sunflower_inference",
    response_model=SunflowerChatResponse,
    deprecated=True,
)
@limiter.limit(get_account_type_limit)
async def sunflower_inference(  # noqa: C901
    request: Request,
    response: Response,
    chat_request: SunflowerChatRequest,
    quota: QuotaServiceDep,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    service: InferenceService = Depends(get_service),
) -> SunflowerChatResponse:
```

and as the first statement of the function body (before `await check_quota(...)`):

```python
    _add_deprecation_headers(response)
```

Also add one line to the docstring under the summary: `**Deprecated**: use POST /tasks/chat/completions instead.`

4. Change the `sunflower_simple_inference` decorator and signature the same way:

```python
@router.post(
    "/sunflower_simple",
    response_model=Dict[str, Any],
    deprecated=True,
)
@limiter.limit(get_account_type_limit)
async def sunflower_simple_inference(  # noqa: C901
    request: Request,
    response: Response,
    quota: QuotaServiceDep,
    background_tasks: BackgroundTasks,
    instruction: str = Form(..., description="The instruction or question for the AI"),
    model_type: str = Form("qwen", description="Model type (qwen or gemma)"),
    temperature: float = Form(0.3, ge=0.0, le=2.0, description="Sampling temperature"),
    system_message: str = Form(None, description="Custom system message"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> Dict[str, Any]:
```

with `_add_deprecation_headers(response)` as the first statement of its body, and the same docstring deprecation line.

No other handler logic changes.

- [ ] **Step 7.4: Run tests to verify they pass**

Run: `pytest app/tests/test_routers/test_chat.py app/tests/test_routers/test_inference.py -v`
Expected: PASS — new deprecation tests green, all legacy inference tests still green

- [ ] **Step 7.5: Commit**

```bash
git add app/routers/inference.py app/tests/test_routers/test_chat.py
git commit -m "feat: deprecate sunflower_inference and sunflower_simple endpoints"
```

---

### Task 8: API docs update

**Files:**
- Modify: `app/docs.py` (the `### Inference (Sunflower Chat)` section, currently lines 68-70)

- [ ] **Step 8.1: Update the docs text**

Replace:

```markdown
### Inference (Sunflower Chat)
- **`POST /tasks/sunflower_inference`** - Conversational AI powered by Sunflower model with chat history
- **`POST /tasks/sunflower_simple`** - Simple text generation without chat history
```

with:

```markdown
### Inference (Sunflower Chat)
- **`POST /tasks/chat/completions`** - OpenAI-compatible chat completions (Sunflower model). Supports single instructions, multi-turn conversations, and SSE streaming (`stream: true`). Use model `Sunbird/Sunflower-14B`.
  - **Deprecated** → superseded by the unified endpoint above:
    - `POST /tasks/sunflower_inference` → `POST /tasks/chat/completions`
    - `POST /tasks/sunflower_simple` → `POST /tasks/chat/completions` (send the instruction as a single user message)
```

- [ ] **Step 8.2: Sanity check the app still imports**

Run: `python -c "from app.api import app; print('ok')"`
Expected: `ok`

- [ ] **Step 8.3: Commit**

```bash
git add app/docs.py
git commit -m "docs: document /tasks/chat/completions, mark legacy endpoints deprecated"
```

---

### Task 9: Full verification (Definition of Done)

**Files:** none (verification only)

- [ ] **Step 9.1: Run the full backend test suite**

Run: `pytest app/tests/ -v`
Expected: all tests pass, no new failures vs. the branch baseline

- [ ] **Step 9.2: Run lint check**

Run: `make lint-check`
Expected: black, isort, flake8 all clean. If black/isort complain, run `make lint-apply` and re-run `make lint-check`.

- [ ] **Step 9.3: Commit any lint fixes**

```bash
git add -A
git commit -m "style: lint fixes for chat completions feature"
```

(Skip if the working tree is clean.)

---

## Self-Review Notes

- **Spec coverage:** request contract (Task 1), think-tag filtering + streaming service (Tasks 2/4), passthrough params (Task 3), non-streaming endpoint + error mapping + feedback (Task 5), SSE + mid-stream error + pre-stream HTTP errors + empty-stream 502 (Task 6), deprecation flags/headers (Task 7), docs (Task 8), DoD tests+lint (Task 9). Rate limiting and quota are applied in Task 5's router code; quota is exercised implicitly by every endpoint test (autouse stub).
- **Types:** `run_inference_stream` yields `{"type": "delta"|"usage", ...}` dicts — consumed with the same keys in Task 6's router and mocked with the same shape in tests.
- **Known judgment calls:** non-streaming inference runs via `run_in_threadpool` (legacy endpoints call it directly on the event loop; not changed there). `stop` is typed `Optional[Any]` at the service layer to avoid duplicating the schema union.
