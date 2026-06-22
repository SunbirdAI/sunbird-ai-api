# Design Spec: Route `/tasks/translate` through Sunflower

**Date:** 2026-06-12
**Status:** Approved
**Author:** Brainstormed with Claude

## Goal

Route the `/tasks/translate` endpoint through the Sunflower chat-completions
inference logic (`InferenceService.run_inference`, the same engine behind
`POST /tasks/chat/completions`) instead of the finetuned NLLB RunPod worker,
while keeping the endpoint URL, request payload, and response shape fully
backward compatible.

## Requirements

1. **Same endpoint, same payload.** `POST /tasks/translate` keeps accepting:

   ```json
   {
     "source_language": "eng",
     "target_language": "lug",
     "text": "Hello, how are you?"
   }
   ```

2. **`source_language` becomes optional.** When omitted, Sunflower infers the
   source language from the text.

3. **Languages accepted as ISO code or full name**, case-insensitively:
   `"lug"`, `"LUG"`, `"Luganda"`, `"luganda"` are all valid. Codes resolve to
   full names via the SALT language map because the Sunflower instruction must
   contain full language names.

4. **Only the 32 Sunflower-supported languages are accepted.** Languages in
   the SALT map but outside the Sunflower set (e.g. `fra`/French, `zul`/Zulu)
   are rejected with a 400 listing supported languages.

5. **Instruction format** sent to Sunflower:
   - Both languages given: `Translate from {source_name} to {target_name}: {text}`
   - Target only: `Translate to {target_name}: {text}`

6. **Inference parameters** (fixed, matching the chat/completions contract):

   ```json
   {
     "model": "Sunbird/Sunflower-14B",
     "temperature": 0.3,
     "max_tokens": 1024,
     "top_p": 0.95,
     "stream": false
   }
   ```

   Internally this is `InferenceService.run_inference(messages=...,
   model_type="qwen", temperature=0.3, max_tokens=1024, top_p=0.95)` — `"qwen"`
   is the RunPod endpoint key that serves `Sunbird/Sunflower-14B` (same as
   `app/routers/chat.py::INTERNAL_MODEL_TYPE`).

7. **Response shape unchanged** (`WorkerTranslationResponse`):

   ```json
   {
     "id": "<generated uuid>",
     "status": "COMPLETED",
     "output": {
       "translated_text": "Oli otya?",
       "source_language": "eng",
       "target_language": "lug"
     }
   }
   ```

   `output.source_language` / `output.target_language` echo **canonical ISO
   codes** even when full names were provided. `output.source_language` is
   `null` when the request omitted it.

8. **NLLB path retired but retained.** The router stops calling
   `TranslationService.translate()` (NLLB). The NLLB code stays in the
   codebase untouched for rollback; removal is a separate future change. The
   WhatsApp translate flow (`message_processor.py`) is out of scope — it
   already has its own Sunflower path.

## Architecture

```
POST /tasks/translate
  → app/routers/translation.py            (URL, auth, quota, rate limit unchanged)
    → TranslationService.translate_via_sunflower()      ← NEW method
      → InferenceService.run_inference()                ← shared with /tasks/chat/completions
        → RunPod OpenAI-compatible API (Sunflower-14B)
```

## Components

### 1. Language resolution — NEW `app/utils/languages.py`

- `SALT_LANGUAGE_NAMES: Dict[str, str]` — the full SALT map (code → name),
  exactly as provided (Ugandan languages + rest-of-Africa block).
- `SUNFLOWER_LANGUAGES: tuple[str, ...]` — the 32 names Sunflower supports:
  Acholi, Alur, Aringa, Ateso, Bari, English, Jopadhola, Kakwa, Karamojong,
  Kinyarwanda, Kumam, Kupsabiny, Kwamba, Lango, Lubwisi, Luganda, Lugbara,
  Lugungu, Lugwere, Lumasaba, Lunyole, Lusoga, Ma'di, Pokot, Rukiga, Rukonjo,
  Runyankole, Runyoro, Ruruuli, Rutooro, Samia, Swahili.
- `LANGUAGE_ALIASES: Dict[str, str]` — input spelling variants → canonical
  name. SALT names are canonical (they go into the prompt):
  - `"runyankore"` → `"Runyankole"` (`nyn`)
  - `"dhopadhola"` → `"Jopadhola"` (`adh`)
- `class UnsupportedLanguageError(ValueError)` — message names the invalid
  value and lists supported languages.
- `resolve_language(value: str) -> ResolvedLanguage` — `ResolvedLanguage` is a
  NamedTuple `(code: str, name: str)`. Accepts ISO code or full name (or
  alias), case-insensitive, surrounding whitespace stripped. Raises
  `UnsupportedLanguageError` for anything not resolving to a Sunflower
  language — including SALT-only languages like French.

### 2. Request schema — `app/schemas/translation.py`

New `SunflowerTranslationRequest` (replaces `NllbTranslationRequest` on the
endpoint; the old class stays for the retained NLLB code):

```python
class SunflowerTranslationRequest(BaseModel):
    source_language: Optional[str] = None   # ISO code or full name
    target_language: str                    # ISO code or full name
    text: constr(min_length=1, strip_whitespace=True)
```

Pydantic does **not** validate language membership (so the error is a friendly
400, not a 422); membership is validated in the router via
`resolve_language`. Old enum-style payloads (`"eng"`, `"lug"`, …) remain valid
— the new schema is a strict superset.

### 3. Service — `app/services/translation_service.py`

`TranslationResult.source_language` becomes `Optional[str]`.

New method:

```python
async def translate_via_sunflower(
    self,
    text: str,
    target_language: ResolvedLanguage,
    source_language: Optional[ResolvedLanguage] = None,
) -> TranslationResult
```

- Builds the instruction per requirement 5 using the resolved **names**.
- Builds messages `[{"role": "system", "content": InferenceService.SYSTEM_MESSAGE},
  {"role": "user", "content": instruction}]` — matching what
  `/tasks/chat/completions` does for a single-user-message request.
- Calls `run_in_threadpool(lambda: inference_service.run_inference(...))` with
  `model_type="qwen"`, `temperature=0.3`, `max_tokens=1024`, `top_p=0.95`
  (constants `SUNFLOWER_TRANSLATION_TEMPERATURE = 0.3`,
  `SUNFLOWER_TRANSLATION_MAX_TOKENS = 1024`,
  `SUNFLOWER_TRANSLATION_TOP_P = 0.95` defined in the service module).
  The `InferenceService` singleton is obtained lazily inside the method via
  `get_inference_service()` (lazy import to avoid import cycles).
- Inference exceptions (`ModelLoadingError`, `InferenceTimeoutError`,
  `ValueError`, generic) propagate to the router — the service does not
  swallow them.
- Returns `TranslationResult` with `translated_text` = cleaned model content,
  `source_language` = canonical ISO code or `None`, `target_language` =
  canonical ISO code, `status="COMPLETED"`, `job_id` = generated
  `trans-<uuid4 hex>`, `raw_response=None` (router synthesizes the response).

### 4. Router — `app/routers/translation.py`

- Request model switches to `SunflowerTranslationRequest`; response model
  stays `WorkerTranslationResponse`.
- Resolves languages with `resolve_language`; `UnsupportedLanguageError` →
  `BadRequestError` (400). After canonicalization, `source == target` →
  `BadRequestError` (400, "Source and target languages must be different").
- Calls `service.translate_via_sunflower(...)`.
- Error mapping (mirrors `app/routers/chat.py`):
  - `ModelLoadingError` → `ServiceUnavailableError` (503, "model is loading")
  - `InferenceTimeoutError` → `ServiceUnavailableError` (503, "timed out")
  - `ValueError` → `BadRequestError` (400)
  - empty/missing model content → `ExternalServiceError` (502)
  - any other exception → `ExternalServiceError` (502)
- Synthesizes the response:

  ```python
  WorkerTranslationResponse(
      id=result.job_id,
      status="COMPLETED",
      output={
          "translated_text": result.translated_text,
          "source_language": result.source_language,  # code or None
          "target_language": result.target_language,  # code
      },
  )
  ```

- Feedback logging via `background_tasks.add_task(save_api_inference, ...)`
  keeps `inference_type=INFERENCE_TYPES["translation"]` but `model_type`
  becomes `"Sunbird/Sunflower-14B"`. `job_details` carries the canonical codes
  and generated job id.
- Quota check, SlowAPI rate limit decorator, and MonitoringMiddleware
  behavior are unchanged.

## Error handling summary

| Condition | Status | Mechanism |
|---|---|---|
| Unknown/unsupported language (code or name) | 400 | `UnsupportedLanguageError` → `BadRequestError`, message lists supported languages |
| `source == target` after canonicalization | 400 | `BadRequestError` |
| Missing `target_language` / empty `text` | 422 | Pydantic schema validation |
| Model loading (cold start) | 503 | `ModelLoadingError` → `ServiceUnavailableError` |
| Inference timeout | 503 | `InferenceTimeoutError` → `ServiceUnavailableError` |
| Empty model output | 502 | `ExternalServiceError` |
| Any other inference failure | 502 | `ExternalServiceError` |

## Documentation updates

- Endpoint docstring in `app/routers/translation.py` (currently lists the 6
  NLLB languages and English-pivot restriction — replaced by the 32-language
  Sunflower set, any-to-any, optional source).
- `app/docs.py`: Translation bullet in `description` and the `Translation`
  entry in `tags_metadata` (both currently say "NLLB model").
- `docs/tutorial.md`: translation section — new language list, optional
  `source_language`, full-name support, updated examples.

## Testing

In-memory SQLite, `asyncio_mode=auto`, service-layer mocking per project
conventions (`app/tests/`).

**Unit — `app/utils/languages.py`:**
- resolve by code, by name, by alias (Runyankore, Dhopadhola), case-insensitive,
  whitespace-tolerant
- unsupported code (`fra`), unsupported name (`French`), garbage input → raises
  with supported list in message
- every Sunflower language name resolves; every canonical name has a code

**Unit — `translate_via_sunflower`:**
- instruction format with and without source language
- passes `model_type="qwen"`, `temperature=0.3`, `max_tokens=1024`,
  `top_p=0.95` to `run_inference` (assert on mock call)
- system message injected; user message contains the instruction
- result fields (codes, status, job id prefix)
- inference exceptions propagate

**Router — `/tasks/translate` (mock `TranslationService`):**
- legacy payload (`{"source_language": "eng", "target_language": "lug",
  "text": ...}`) works unchanged, response shape backward compatible
- full-name payload (`"Luganda"`), mixed code+name payload
- omitted `source_language` → success, `output.source_language` is null
- unsupported language → 400 listing supported set
- `source == target` (incl. code-vs-name, e.g. `"lug"` + `"Luganda"`) → 400
- `ModelLoadingError` → 503, `InferenceTimeoutError` → 503
- empty model content → 502
- feedback task scheduled with `model_type="Sunbird/Sunflower-14B"`
- missing `target_language` / empty `text` → 422

**Definition of Done:** full `pytest app/tests/ -v` pass and clean
`make lint-check`.

## Out of scope

- Removing the NLLB code path (separate future change)
- WhatsApp translate flow (already Sunflower-based)
- Streaming translation responses
- The deprecated legacy `/tasks/nllb_translate`-era schemas in
  `app/schemas/tasks.py`
