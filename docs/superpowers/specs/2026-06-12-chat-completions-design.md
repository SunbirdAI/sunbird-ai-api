# Design: OpenAI-Compatible `/tasks/chat/completions` Endpoint

**Date:** 2026-06-12
**Status:** Approved (pending spec review)

## Goal

Decompose `/tasks/sunflower_inference` and `/tasks/sunflower_simple` into a single
OpenAI-compatible endpoint, `POST /tasks/chat/completions`, so clients can move
between the OpenAI API and the Sunbird API with minimal changes (ideally by only
changing the base URL and API key). The two legacy endpoints are deprecated but
keep working unchanged.

## Decisions (resolved with stakeholder)

1. **Response shape:** Full OpenAI `chat.completion` object (`id`, `object`,
   `created`, `model`, `choices[].message`, `finish_reason`, `usage`). No custom
   top-level fields.
2. **Legacy endpoints:** Keep working with current contracts. Mark
   `deprecated=True` in OpenAPI and add `Deprecation` + `Link` (successor)
   response headers.
3. **`model` parameter:** Replaces `model_type`. Strict validation — only
   `Sunbird/Sunflower-14B` is accepted; it is also the default when omitted.
   Anything else returns 400 listing supported models. Legacy `"qwen"`/`"gemma"`
   values remain accepted only on the deprecated endpoints.
4. **Streaming:** Fully implemented. `stream: true` returns Server-Sent Events
   of `chat.completion.chunk` deltas, terminated by `data: [DONE]`.

## Request Contract

`POST /tasks/chat/completions` — JSON only (no Form fields), Bearer auth required.

```json
{
  "model": "Sunbird/Sunflower-14B",
  "messages": [
    {"role": "system", "content": "optional custom system message"},
    {"role": "user", "content": "Translate 'hello' to Luganda"}
  ],
  "temperature": 0.3,
  "max_tokens": 1024,
  "top_p": 1.0,
  "stop": null,
  "stream": false
}
```

Supported fields:

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `model` | str | `Sunbird/Sunflower-14B` | Strict: any other value → 400 |
| `messages` | list | required | roles: `system`/`user`/`assistant`; non-empty content |
| `temperature` | float | 0.3 | 0.0–2.0 |
| `max_tokens` | int \| null | null | passed through to RunPod |
| `top_p` | float \| null | null | passed through |
| `stop` | str \| list \| null | null | passed through |
| `stream` | bool | false | SSE when true |

Mapping from legacy endpoints:

| Legacy | New |
|--------|-----|
| `sunflower_simple` `instruction` (Form) | single `user` message in `messages` |
| `sunflower_simple` / `sunflower_inference` `system_message` | a `system` role message in `messages` |
| `model_type` (`qwen`) | `model` (`Sunbird/Sunflower-14B`) |
| `temperature` | `temperature` |

A default Sunflower system message is injected when the client provides no
`system` message (same behavior as legacy endpoints).

## Response Contract

Non-streaming (200):

```json
{
  "id": "chatcmpl-<uuid>",
  "object": "chat.completion",
  "created": 1718000000,
  "model": "Sunbird/Sunflower-14B",
  "choices": [
    {
      "index": 0,
      "message": {"role": "assistant", "content": "..."},
      "finish_reason": "stop"
    }
  ],
  "usage": {"prompt_tokens": 50, "completion_tokens": 15, "total_tokens": 65}
}
```

Streaming (200, `text/event-stream`): a sequence of

```
data: {"id": "chatcmpl-...", "object": "chat.completion.chunk", "created": ..., "model": "Sunbird/Sunflower-14B", "choices": [{"index": 0, "delta": {"content": "..."}, "finish_reason": null}]}
```

First chunk carries `delta: {"role": "assistant", "content": ""}`; the last
content chunk is followed by a chunk with `finish_reason: "stop"`, an optional
usage chunk (when RunPod returns usage via `stream_options: {"include_usage": true}`),
and finally `data: [DONE]`.

## Architecture

```
POST /tasks/chat/completions
  → app/routers/chat.py (new router, mounted under /tasks)
    → InferenceService (extended)
      → RunPod OpenAI-compatible API (vLLM)
```

### Components

1. **`app/schemas/chat.py` (new)** — OpenAI-compatible Pydantic models:
   `ChatMessage` (role as `Literal["system", "user", "assistant"]`, non-empty
   content validation), `ChatCompletionRequest`, `ChatCompletionResponseMessage`,
   `ChatCompletionChoice`, `ChatCompletionUsage`, `ChatCompletionResponse`,
   `ChatCompletionChunkDelta`, `ChatCompletionChunkChoice`, `ChatCompletionChunk`.

2. **`app/services/inference_service.py` (extended)** —
   - `run_inference()` gains pass-through parameters: `max_tokens`, `top_p`,
     `stop` (temperature already supported).
   - New `run_inference_stream()` generator yielding content deltas (and a final
     usage record when available). Retry/backoff applies only up to the arrival
     of the first chunk — once streaming has begun, a failure terminates the
     stream with an SSE error event; it is never retried mid-stream.
   - New stateful `ThinkTagFilter` that strips `<think>…</think>` spans across
     chunk boundaries so reasoning tokens never reach the client (streaming
     equivalent of the existing `_clean_response`). It buffers ambiguous
     partial-tag suffixes until disambiguated.

3. **`app/routers/chat.py` (new)** — `POST /chat/completions`:
   - Same guards as legacy endpoints: Bearer auth, quota check
     (`check_quota`), SlowAPI rate limit (`@limiter.limit(get_account_type_limit)`).
   - Strict model validation (400 via `BadRequestError` for unsupported model).
   - Non-stream path: call service, build `ChatCompletionResponse`.
   - Stream path: `StreamingResponse(media_type="text/event-stream")` wrapping
     the service generator; emits OpenAI-format chunk JSON lines and `[DONE]`.
   - Error mapping identical to legacy: `ModelLoadingError`/timeout →
     `ServiceUnavailableError` (503), invalid input → `BadRequestError`/
     `ValidationError`, empty model response / unexpected → `ExternalServiceError`.
   - Feedback (`save_api_inference`) recorded in both modes with a new
     `INFERENCE_TYPES["chat_completions"]` entry; for streaming it is saved after
     the stream completes using the accumulated content.

4. **`app/routers/inference.py` (modified)** — both legacy routes get
   `deprecated=True` plus `Deprecation: true` and
   `Link: </tasks/chat/completions>; rel="successor-version"` response headers.
   Handler logic otherwise untouched.

5. **`app/api.py` (modified)** — `app.include_router(chat_router, prefix="/tasks",
   tags=["Chat"])`.

6. **`app/docs.py` (modified)** — document `POST /tasks/chat/completions`; mark
   the two legacy endpoints as deprecated with pointers to the successor.

## Error Handling

| Condition | Status | Mechanism |
|-----------|--------|-----------|
| No/invalid token | 401 | existing auth dependency |
| Quota exceeded | 429 | `check_quota` |
| Rate limit | 429 | SlowAPI |
| Empty `messages`, empty content, bad role | 400/422 | Pydantic + `BadRequestError`/`ValidationError` |
| Unsupported `model` | 400 | `BadRequestError` listing supported models |
| Model loading (RunPod cold start) | 503 | `ServiceUnavailableError` |
| Inference timeout | 503 | `ServiceUnavailableError` |
| Empty model response | 502 | `ExternalServiceError` |
| Mid-stream failure | `data: {"error": {"message": "...", "type": "server_error"}}`, then `data: [DONE]` | stream terminates, no retry |

## Testing

New `app/tests/test_routers/test_chat.py` (service mocked at the
`run_inference`/`run_inference_stream` layer, per testing rules):

- Success: response is a valid OpenAI `chat.completion` object (all fields).
- Auth required (401 without token).
- Validation: empty `messages`, invalid role, empty content, unknown `model`
  (400 with supported-models message), default model when omitted.
- Single-instruction use case (one user message) and multi-turn history.
- Custom system message honored; default system message injected when absent.
- Error mapping: model loading → 503, timeout → 503, empty response → 502.
- Streaming: SSE content type; chunks parse as `chat.completion.chunk`;
  role-priming first chunk; `finish_reason: "stop"` chunk; `[DONE]` terminator;
  accumulated deltas equal full content.
- `ThinkTagFilter` unit tests: tag split across chunk boundaries, no tags,
  nested/multiple tags, unterminated tag.
- Deprecation: legacy endpoints still return 200 and carry `Deprecation` +
  `Link` headers; OpenAPI schema marks them deprecated.

Definition of Done additionally requires: `pytest app/tests/ -v` green and
`make lint-check` clean.

## Out of Scope

- Removing the legacy endpoints (future release).
- `n > 1` completions, `logprobs`, function/tool calling, `response_format`.
- Multiple models — only `Sunbird/Sunflower-14B` for now.
