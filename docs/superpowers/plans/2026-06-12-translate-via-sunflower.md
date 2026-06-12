# Route `/tasks/translate` through Sunflower — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route `POST /tasks/translate` through the Sunflower model (the same `InferenceService.run_inference` engine behind `/tasks/chat/completions`) instead of the NLLB RunPod worker, keeping the endpoint URL, payload, and response shape backward compatible while expanding to 32 languages with optional `source_language`.

**Architecture:** Router (`app/routers/translation.py`) resolves languages via a new `app/utils/languages.py` module, then calls a new `TranslationService.translate_via_sunflower()` method which builds a `Translate from X to Y: {text}` instruction and runs it through `InferenceService.run_inference()` with fixed parameters (temperature 0.3, max_tokens 1024, top_p 0.95, model_type "qwen"). The old NLLB path stays in the codebase, unused by the endpoint.

**Tech Stack:** FastAPI, Pydantic, pytest (in-memory SQLite, `asyncio_mode=auto`), starlette `run_in_threadpool`.

**Spec:** `docs/superpowers/specs/2026-06-12-translate-via-sunflower-design.md` (approved)
**Branch:** `route-translate-through-sunflower` (baseline commit `6847e6d4`)

**Lint rules that bite here:** flake8 `max-line-length=119`, `E203` is NOT ignored (avoid spaces before `:` in slices), run `make lint-check` (black + isort + flake8) before each commit, or `make lint-apply` to autofix formatting.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `app/utils/languages.py` | Create | SALT code→name map, 32-language Sunflower allowlist, alias handling, `resolve_language()` |
| `app/tests/test_utils/test_languages.py` | Create | Unit tests for language resolution |
| `app/schemas/translation.py` | Modify | Add `SunflowerTranslationRequest` (old classes untouched) |
| `app/tests/test_schemas/test_translation_request.py` | Create | Schema validation tests |
| `app/services/translation_service.py` | Modify | `TranslationResult.source_language` → Optional; add constants + `translate_via_sunflower()` |
| `app/tests/test_services/test_translation_service.py` | Modify | Add `TestTranslateViaSunflower` class |
| `app/routers/translation.py` | Modify | Rewrite `/translate` handler: Sunflower path, deps.py aliases, new error mapping |
| `app/tests/test_routers/test_translation.py` | Rewrite | Endpoint tests against the new behavior |
| `app/tests/test_quota_endpoint.py` | Modify | Fixture patches `translate_via_sunflower` instead of `translate` |
| `app/tests/test_rate_limit_endpoint.py` | Modify | Same fixture fix |
| `app/docs.py` | Modify | Translation bullet + tags_metadata no longer say "NLLB" |
| `docs/tutorial.md` | Modify | Part 2 rewritten for Sunflower (32 languages, optional source) |

---

### Task 1: Language resolution module

**Files:**
- Create: `app/utils/languages.py`
- Test: `app/tests/test_utils/test_languages.py`

- [ ] **Step 1: Write the failing tests**

Create `app/tests/test_utils/test_languages.py`:

```python
"""Tests for app/utils/languages.py — Sunflower language resolution."""

import pytest

from app.utils.languages import (
    SALT_LANGUAGE_NAMES,
    SUNFLOWER_LANGUAGES,
    ResolvedLanguage,
    UnsupportedLanguageError,
    resolve_language,
)


class TestResolveByCode:
    def test_resolves_iso_code(self):
        assert resolve_language("lug") == ResolvedLanguage(code="lug", name="Luganda")

    def test_resolves_uppercase_code(self):
        assert resolve_language("LUG") == ResolvedLanguage(code="lug", name="Luganda")

    def test_resolves_code_with_whitespace(self):
        assert resolve_language("  eng ") == ResolvedLanguage(
            code="eng", name="English"
        )

    def test_resolves_swahili(self):
        assert resolve_language("swa") == ResolvedLanguage(code="swa", name="Swahili")


class TestResolveByName:
    def test_resolves_full_name(self):
        assert resolve_language("Luganda") == ResolvedLanguage(
            code="lug", name="Luganda"
        )

    def test_resolves_lowercase_name(self):
        assert resolve_language("luganda") == ResolvedLanguage(
            code="lug", name="Luganda"
        )

    def test_resolves_name_with_apostrophe(self):
        assert resolve_language("Ma'di") == ResolvedLanguage(code="mhi", name="Ma'di")

    @pytest.mark.parametrize("name", SUNFLOWER_LANGUAGES)
    def test_every_sunflower_language_resolves(self, name):
        resolved = resolve_language(name)
        assert resolved.name == name
        assert SALT_LANGUAGE_NAMES[resolved.code] == name


class TestAliases:
    def test_runyankore_resolves_to_runyankole(self):
        assert resolve_language("Runyankore") == ResolvedLanguage(
            code="nyn", name="Runyankole"
        )

    def test_dhopadhola_resolves_to_jopadhola(self):
        assert resolve_language("Dhopadhola") == ResolvedLanguage(
            code="adh", name="Jopadhola"
        )


class TestUnsupportedLanguages:
    @pytest.mark.parametrize(
        "value",
        ["fra", "French", "zul", "Zulu", "ibo", "xx", "", "   ", "klingon"],
    )
    def test_rejects_unsupported(self, value):
        with pytest.raises(UnsupportedLanguageError) as exc_info:
            resolve_language(value)
        assert "Supported languages" in str(exc_info.value)

    def test_error_names_the_invalid_value(self):
        with pytest.raises(UnsupportedLanguageError, match="fra"):
            resolve_language("fra")

    def test_sunflower_set_has_32_languages(self):
        assert len(SUNFLOWER_LANGUAGES) == 32
```

Note: `fra` (French), `zul` (Zulu), and `ibo` (Igbo) exist in the SALT map but are **not** Sunflower-supported — they must be rejected.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest app/tests/test_utils/test_languages.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.utils.languages'`

- [ ] **Step 3: Implement the module**

Create `app/utils/languages.py`:

```python
"""
Language code/name resolution for Sunflower translation.

Maps SALT ISO 639-3 codes to full language names and validates that a
requested language is supported by the Sunflower model. The Sunflower
instruction format requires full language names, so API clients may send
either an ISO code (e.g. ``lug``) or a full name (e.g. ``Luganda``),
case-insensitively.
"""

from typing import Dict, NamedTuple

# Full SALT language map (code -> canonical full name). Includes languages
# beyond what Sunflower supports; only names in SUNFLOWER_LANGUAGES are
# accepted by resolve_language().
SALT_LANGUAGE_NAMES: Dict[str, str] = {
    "ach": "Acholi",
    "eng": "English",
    "ibo": "Igbo",
    "lgg": "Lugbara",
    "lug": "Luganda",
    "nyn": "Runyankole",
    "swa": "Swahili",
    "teo": "Ateso",
    "xog": "Lusoga",
    "ttj": "Rutooro",
    "kin": "Kinyarwanda",
    "myx": "Lumasaba",
    "adh": "Jopadhola",
    "alz": "Alur",
    "bfa": "Bari",
    "cgg": "Rukiga",
    "gwr": "Lugwere",
    "ikx": "Ik",
    "kdi": "Kumam",
    "kdj": "Karamojong",
    "keo": "Kakwa",
    "koo": "Rukonjo",
    "kpz": "Kupsabiny",
    "laj": "Lango",
    "led": "Lendu",
    "lsm": "Samia",
    "lth": "Thur",
    "luc": "Aringa",
    "luo": "Luo",
    "lzm": "Lulubo",
    "mhi": "Ma'di",
    "ndp": "Kebu",  # replacing Ndo with Kebu
    "pok": "Pokot",
    "rub": "Lugungu",
    "ruc": "Ruruuli",
    "rwm": "Kwamba",
    "sbx": "Sebei",
    "soc": "So",
    "tlj": "Lubwisi",  # Bwisi-Talinga
    "nuj": "Lunyole",
    "nyo": "Runyoro",
    # Rest of Africa
    "afr": "Afrikaans",
    "aka": "Akan",
    "amh": "Amharic",
    "bam": "Bambara",
    "bem": "Bemba",
    "ber": "Berber",
    "nya": "Chichewa",
    "dga": "Dagaare",
    "dag": "Dagbani",
    "din": "Dinka",
    "ewe": "Ewe",
    "fra": "French",
    "ful": "Fulani",
    "kik": "Kikuyu",
    "hau": "Hausa",
    "kpo": "Ikposo",
    "kab": "Kabyle",
    "kln": "Kalenjin",
    "kau": "Kanuri",
    "run": "Kirundi",
    "lin": "Lingala",
    "luy": "Luhya",
    "mlg": "Malagasy",
    "nbl": "Ndebele",
    "pcm": "Nigerian Pidgin",
    "orm": "Oromo",
    "sot": "Sotho",
    "sna": "Shona",
    "som": "Somali",
    "tsn": "Tswana",
    "wol": "Wolof",
    "xho": "Xhosa",
    "yor": "Yoruba",
    "zul": "Zulu",
}

# The 32 languages the Sunflower model supports for translation.
SUNFLOWER_LANGUAGES = (
    "Acholi",
    "Alur",
    "Aringa",
    "Ateso",
    "Bari",
    "English",
    "Jopadhola",
    "Kakwa",
    "Karamojong",
    "Kinyarwanda",
    "Kumam",
    "Kupsabiny",
    "Kwamba",
    "Lango",
    "Lubwisi",
    "Luganda",
    "Lugbara",
    "Lugungu",
    "Lugwere",
    "Lumasaba",
    "Lunyole",
    "Lusoga",
    "Ma'di",
    "Pokot",
    "Rukiga",
    "Rukonjo",
    "Runyankole",
    "Runyoro",
    "Ruruuli",
    "Rutooro",
    "Samia",
    "Swahili",
)

# Input spelling variants -> canonical SALT name.
LANGUAGE_ALIASES: Dict[str, str] = {
    "runyankore": "Runyankole",
    "dhopadhola": "Jopadhola",
}


class UnsupportedLanguageError(ValueError):
    """Raised when a language is not supported by Sunflower translation."""


class ResolvedLanguage(NamedTuple):
    """A validated language: canonical ISO code and full name."""

    code: str
    name: str


_SUNFLOWER_NAME_SET = set(SUNFLOWER_LANGUAGES)
_CODE_TO_NAME: Dict[str, str] = {
    code: name
    for code, name in SALT_LANGUAGE_NAMES.items()
    if name in _SUNFLOWER_NAME_SET
}
_NAME_TO_CODE: Dict[str, str] = {
    name.lower(): code for code, name in _CODE_TO_NAME.items()
}


def resolve_language(value: str) -> ResolvedLanguage:
    """Resolve an ISO code or full language name to a ResolvedLanguage.

    Accepts ISO 639-3 codes ("lug"), full names ("Luganda"), and known
    spelling variants ("Runyankore"), case-insensitively and ignoring
    surrounding whitespace.

    Raises:
        UnsupportedLanguageError: If the value does not resolve to one of
            the 32 Sunflower-supported languages.
    """
    cleaned = (value or "").strip()
    key = cleaned.lower()

    if key in _CODE_TO_NAME:
        return ResolvedLanguage(code=key, name=_CODE_TO_NAME[key])

    name = LANGUAGE_ALIASES.get(key)
    if name is None and key in _NAME_TO_CODE:
        name = _CODE_TO_NAME[_NAME_TO_CODE[key]]

    if name is not None:
        return ResolvedLanguage(code=_NAME_TO_CODE[name.lower()], name=name)

    raise UnsupportedLanguageError(
        f"Unsupported language: '{cleaned}'. "
        f"Supported languages: {', '.join(sorted(SUNFLOWER_LANGUAGES))} "
        f"(full name or ISO code)."
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest app/tests/test_utils/test_languages.py -v`
Expected: PASS (all ~50 including the 32 parametrized name cases)

- [ ] **Step 5: Lint and commit**

```bash
make lint-check   # if formatting issues: make lint-apply, re-check
git add app/utils/languages.py app/tests/test_utils/test_languages.py
git commit -m "feat: add Sunflower language resolution module"
```

---

### Task 2: `SunflowerTranslationRequest` schema

**Files:**
- Modify: `app/schemas/translation.py` (append; existing classes untouched)
- Test: `app/tests/test_schemas/test_translation_request.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `app/tests/test_schemas/test_translation_request.py`:

```python
"""Tests for the SunflowerTranslationRequest schema."""

import pytest
from pydantic import ValidationError

from app.schemas.translation import SunflowerTranslationRequest


class TestSunflowerTranslationRequest:
    def test_legacy_payload_valid(self):
        req = SunflowerTranslationRequest(
            source_language="eng", target_language="lug", text="Hello"
        )
        assert req.source_language == "eng"
        assert req.target_language == "lug"

    def test_source_language_optional(self):
        req = SunflowerTranslationRequest(target_language="lug", text="Hello")
        assert req.source_language is None

    def test_full_names_accepted(self):
        req = SunflowerTranslationRequest(
            source_language="English", target_language="Luganda", text="Hello"
        )
        assert req.target_language == "Luganda"

    def test_unknown_languages_pass_schema(self):
        # Membership validation happens in the router (400), not the schema.
        req = SunflowerTranslationRequest(target_language="fra", text="Hello")
        assert req.target_language == "fra"

    def test_target_language_required(self):
        with pytest.raises(ValidationError):
            SunflowerTranslationRequest(text="Hello")

    def test_empty_text_rejected(self):
        with pytest.raises(ValidationError):
            SunflowerTranslationRequest(target_language="lug", text="")

    def test_whitespace_only_text_rejected(self):
        with pytest.raises(ValidationError):
            SunflowerTranslationRequest(target_language="lug", text="   ")

    def test_text_whitespace_stripped(self):
        req = SunflowerTranslationRequest(target_language="lug", text="  Hello ")
        assert req.text == "Hello"
```

If `app/tests/test_schemas/` lacks an `__init__.py`, check how the existing test files in that directory are discovered first (`ls app/tests/test_schemas/`) and mirror that.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest app/tests/test_schemas/test_translation_request.py -v`
Expected: FAIL with `ImportError: cannot import name 'SunflowerTranslationRequest'`

- [ ] **Step 3: Implement the schema**

Append to `app/schemas/translation.py` (after `NllbTranslationRequest`):

```python
class SunflowerTranslationRequest(BaseModel):
    """Request model for Sunflower-backed text translation.

    Languages are accepted as ISO 639-3 codes (e.g. ``lug``) or full names
    (e.g. ``Luganda``), case-insensitively. Membership in the supported
    language set is validated in the router (returning a 400 with the
    supported list), not here.

    Attributes:
        source_language: Optional source language; auto-detected when omitted.
        target_language: The target language (code or full name).
        text: The text to translate (min 1 character, whitespace stripped).
    """

    source_language: Optional[str] = Field(
        None,
        description="Source language ISO code or full name (optional; "
        "auto-detected when omitted)",
    )
    target_language: str = Field(
        ..., description="Target language ISO code or full name"
    )
    text: constr(min_length=1, strip_whitespace=True) = Field(  # type: ignore
        ..., description="The text to translate"
    )
```

(`Optional`, `BaseModel`, `Field`, `constr` are already imported in this file.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest app/tests/test_schemas/test_translation_request.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Lint and commit**

```bash
make lint-check
git add app/schemas/translation.py app/tests/test_schemas/test_translation_request.py
git commit -m "feat: add SunflowerTranslationRequest schema with optional source language"
```

---

### Task 3: `TranslationService.translate_via_sunflower()`

**Files:**
- Modify: `app/services/translation_service.py`
- Test: `app/tests/test_services/test_translation_service.py` (append a class)

- [ ] **Step 1: Write the failing tests**

Append to `app/tests/test_services/test_translation_service.py`. Add these imports at the top of the file (merge with existing imports; isort will order them):

```python
from unittest.mock import MagicMock

import pytest

from app.services.inference_service import InferenceService, ModelLoadingError
from app.services.translation_service import TranslationService
from app.utils.languages import ResolvedLanguage
```

Then append the test class:

```python
class TestTranslateViaSunflower:
    """Tests for TranslationService.translate_via_sunflower."""

    @pytest.fixture
    def mock_inference_service(self, monkeypatch):
        mock = MagicMock()
        mock.run_inference.return_value = {
            "content": "Oli otya?",
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
            "model_type": "qwen",
            "processing_time": 1.2,
        }
        monkeypatch.setattr(
            "app.services.inference_service.get_inference_service", lambda: mock
        )
        return mock

    async def test_instruction_with_source_and_target(self, mock_inference_service):
        service = TranslationService()
        result = await service.translate_via_sunflower(
            text="How are you?",
            target_language=ResolvedLanguage(code="lug", name="Luganda"),
            source_language=ResolvedLanguage(code="eng", name="English"),
        )
        messages = mock_inference_service.run_inference.call_args.kwargs["messages"]
        assert messages[1] == {
            "role": "user",
            "content": "Translate from English to Luganda: How are you?",
        }
        assert result.translated_text == "Oli otya?"

    async def test_instruction_without_source(self, mock_inference_service):
        service = TranslationService()
        result = await service.translate_via_sunflower(
            text="How are you?",
            target_language=ResolvedLanguage(code="lug", name="Luganda"),
        )
        messages = mock_inference_service.run_inference.call_args.kwargs["messages"]
        assert messages[1] == {
            "role": "user",
            "content": "Translate to Luganda: How are you?",
        }
        assert result.source_language is None

    async def test_system_message_injected(self, mock_inference_service):
        service = TranslationService()
        await service.translate_via_sunflower(
            text="Hi",
            target_language=ResolvedLanguage(code="lug", name="Luganda"),
        )
        messages = mock_inference_service.run_inference.call_args.kwargs["messages"]
        assert messages[0] == {
            "role": "system",
            "content": InferenceService.SYSTEM_MESSAGE,
        }

    async def test_inference_parameters(self, mock_inference_service):
        service = TranslationService()
        await service.translate_via_sunflower(
            text="Hi",
            target_language=ResolvedLanguage(code="lug", name="Luganda"),
            source_language=ResolvedLanguage(code="eng", name="English"),
        )
        kwargs = mock_inference_service.run_inference.call_args.kwargs
        assert kwargs["model_type"] == "qwen"
        assert kwargs["temperature"] == 0.3
        assert kwargs["max_tokens"] == 1024
        assert kwargs["top_p"] == 0.95

    async def test_result_metadata(self, mock_inference_service):
        service = TranslationService()
        result = await service.translate_via_sunflower(
            text="Hi",
            target_language=ResolvedLanguage(code="lug", name="Luganda"),
            source_language=ResolvedLanguage(code="eng", name="English"),
        )
        assert result.status == "COMPLETED"
        assert result.source_language == "eng"
        assert result.target_language == "lug"
        assert result.job_id.startswith("trans-")
        assert result.raw_response is None

    async def test_text_is_stripped_in_instruction(self, mock_inference_service):
        service = TranslationService()
        await service.translate_via_sunflower(
            text="  Hi  ",
            target_language=ResolvedLanguage(code="lug", name="Luganda"),
        )
        messages = mock_inference_service.run_inference.call_args.kwargs["messages"]
        assert messages[1]["content"] == "Translate to Luganda: Hi"

    async def test_empty_content_yields_none_translated_text(
        self, mock_inference_service
    ):
        mock_inference_service.run_inference.return_value = {
            "content": "",
            "usage": {},
        }
        service = TranslationService()
        result = await service.translate_via_sunflower(
            text="Hi",
            target_language=ResolvedLanguage(code="lug", name="Luganda"),
        )
        assert result.translated_text is None

    async def test_inference_errors_propagate(self, mock_inference_service):
        mock_inference_service.run_inference.side_effect = ModelLoadingError("loading")
        service = TranslationService()
        with pytest.raises(ModelLoadingError):
            await service.translate_via_sunflower(
                text="Hi",
                target_language=ResolvedLanguage(code="lug", name="Luganda"),
            )
```

Why patching `app.services.inference_service.get_inference_service` works: `translate_via_sunflower` does a lazy `from app.services.inference_service import get_inference_service` at call time, so the name is looked up in that module's namespace when the method runs.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest app/tests/test_services/test_translation_service.py::TestTranslateViaSunflower -v`
Expected: FAIL with `AttributeError: 'TranslationService' object has no attribute 'translate_via_sunflower'`

- [ ] **Step 3: Implement the service method**

In `app/services/translation_service.py`:

3a. Add to the imports block at the top:

```python
import uuid

from starlette.concurrency import run_in_threadpool

from app.utils.languages import ResolvedLanguage
```

3b. Add module-level constants after the imports (below `logging.basicConfig`):

```python
# Sunflower translation inference parameters (see spec
# docs/superpowers/specs/2026-06-12-translate-via-sunflower-design.md).
# "qwen" is the InferenceService endpoint key serving Sunbird/Sunflower-14B.
SUNFLOWER_MODEL_TYPE = "qwen"
SUNFLOWER_TRANSLATION_TEMPERATURE = 0.3
SUNFLOWER_TRANSLATION_MAX_TOKENS = 1024
SUNFLOWER_TRANSLATION_TOP_P = 0.95
```

3c. In the `TranslationResult` dataclass, change:

```python
    source_language: str
```

to:

```python
    source_language: Optional[str]
```

(also update its docstring line to `source_language: The source language code, or None when auto-detected.`)

3d. Add the method to `TranslationService` (after the existing `translate` method):

```python
    async def translate_via_sunflower(
        self,
        text: str,
        target_language: ResolvedLanguage,
        source_language: Optional[ResolvedLanguage] = None,
    ) -> TranslationResult:
        """Translate text using the Sunflower model via InferenceService.

        Builds a Sunflower translation instruction with full language names
        and runs it through the same inference engine as
        /tasks/chat/completions, with fixed parameters (temperature 0.3,
        max_tokens 1024, top_p 0.95).

        Args:
            text: The text to translate.
            target_language: Resolved target language (code + name).
            source_language: Resolved source language, or None to let the
                model infer it from the text.

        Returns:
            TranslationResult with translated_text (None when the model
            returned no content), canonical ISO codes, a generated
            ``trans-<hex>`` job id, and status "COMPLETED".

        Raises:
            ModelLoadingError: If the model is still loading (propagated).
            InferenceTimeoutError: If the request times out (propagated).
            ValueError: For invalid inference configuration (propagated).
        """
        from app.services.inference_service import (
            InferenceService,
            get_inference_service,
        )

        cleaned_text = text.strip()
        if source_language is not None:
            instruction = (
                f"Translate from {source_language.name} to "
                f"{target_language.name}: {cleaned_text}"
            )
        else:
            instruction = f"Translate to {target_language.name}: {cleaned_text}"

        messages = [
            {"role": "system", "content": InferenceService.SYSTEM_MESSAGE},
            {"role": "user", "content": instruction},
        ]

        source_code = source_language.code if source_language else None
        self.log_info(
            f"Starting Sunflower translation: "
            f"{source_code or 'auto'} -> {target_language.code}"
        )

        inference_service = get_inference_service()
        result = await run_in_threadpool(
            lambda: inference_service.run_inference(
                messages=messages,
                model_type=SUNFLOWER_MODEL_TYPE,
                temperature=SUNFLOWER_TRANSLATION_TEMPERATURE,
                max_tokens=SUNFLOWER_TRANSLATION_MAX_TOKENS,
                top_p=SUNFLOWER_TRANSLATION_TOP_P,
            )
        )

        content = (result or {}).get("content") or None

        return TranslationResult(
            translated_text=content,
            source_language=source_code,
            target_language=target_language.code,
            job_id=f"trans-{uuid.uuid4().hex}",
            status="COMPLETED",
            raw_response=None,
        )
```

The lazy import of `InferenceService`/`get_inference_service` inside the method avoids a module-level import cycle and keeps the singleton patchable in tests. Inference exceptions intentionally propagate — the router maps them to HTTP errors.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest app/tests/test_services/test_translation_service.py -v`
Expected: PASS (all existing tests + 9 new)

- [ ] **Step 5: Lint and commit**

```bash
make lint-check
git add app/services/translation_service.py app/tests/test_services/test_translation_service.py
git commit -m "feat: add TranslationService.translate_via_sunflower"
```

---

### Task 4: Router — route `/tasks/translate` through Sunflower

**Files:**
- Modify: `app/routers/translation.py` (full rewrite of the handler)
- Rewrite: `app/tests/test_routers/test_translation.py`
- Modify: `app/tests/test_quota_endpoint.py:37-48` (fixture)
- Modify: `app/tests/test_rate_limit_endpoint.py:46-62` (fixture)

- [ ] **Step 1: Rewrite the endpoint tests (failing first)**

Replace the entire contents of `app/tests/test_routers/test_translation.py` with:

```python
"""
Tests for Translation Router Module (Sunflower-backed).

POST /tasks/translate routes through TranslationService.translate_via_sunflower
(Sunflower model via InferenceService). These tests mock at the service layer
and verify language resolution, response shape backward compatibility, and
error mapping.
"""

from typing import Dict
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.api import app
from app.services.inference_service import InferenceTimeoutError, ModelLoadingError
from app.services.translation_service import (
    TranslationResult,
    get_translation_service,
)
from app.utils.languages import ResolvedLanguage


def _make_result(
    translated_text="Oli otya?",
    source_language="eng",
    target_language="lug",
):
    return TranslationResult(
        translated_text=translated_text,
        source_language=source_language,
        target_language=target_language,
        status="COMPLETED",
        job_id="trans-abc123",
        raw_response=None,
    )


@pytest.fixture
def mock_translation_service() -> MagicMock:
    mock = MagicMock()
    mock.translate_via_sunflower = AsyncMock(return_value=_make_result())
    return mock


@pytest.fixture
def override_service(mock_translation_service):
    app.dependency_overrides[get_translation_service] = (
        lambda: mock_translation_service
    )
    yield mock_translation_service
    app.dependency_overrides.pop(get_translation_service, None)


def _auth(test_user: Dict) -> Dict[str, str]:
    return {"Authorization": f"Bearer {test_user['token']}"}


class TestTranslateEndpoint:
    """Happy-path and language-resolution tests for POST /tasks/translate."""

    async def test_legacy_payload_with_codes(
        self, async_client: AsyncClient, test_user: Dict, override_service
    ):
        response = await async_client.post(
            "/tasks/translate",
            json={
                "source_language": "eng",
                "target_language": "lug",
                "text": "How are you?",
            },
            headers=_auth(test_user),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "COMPLETED"
        assert data["id"] == "trans-abc123"
        assert data["output"]["translated_text"] == "Oli otya?"
        assert data["output"]["source_language"] == "eng"
        assert data["output"]["target_language"] == "lug"
        override_service.translate_via_sunflower.assert_awaited_once_with(
            text="How are you?",
            target_language=ResolvedLanguage(code="lug", name="Luganda"),
            source_language=ResolvedLanguage(code="eng", name="English"),
        )

    async def test_full_name_payload(
        self, async_client: AsyncClient, test_user: Dict, override_service
    ):
        response = await async_client.post(
            "/tasks/translate",
            json={
                "source_language": "English",
                "target_language": "Luganda",
                "text": "How are you?",
            },
            headers=_auth(test_user),
        )

        assert response.status_code == 200
        override_service.translate_via_sunflower.assert_awaited_once_with(
            text="How are you?",
            target_language=ResolvedLanguage(code="lug", name="Luganda"),
            source_language=ResolvedLanguage(code="eng", name="English"),
        )

    async def test_alias_name_resolves(
        self, async_client: AsyncClient, test_user: Dict, override_service
    ):
        response = await async_client.post(
            "/tasks/translate",
            json={
                "source_language": "eng",
                "target_language": "Runyankore",
                "text": "Hello",
            },
            headers=_auth(test_user),
        )

        assert response.status_code == 200
        call_kwargs = override_service.translate_via_sunflower.await_args.kwargs
        assert call_kwargs["target_language"] == ResolvedLanguage(
            code="nyn", name="Runyankole"
        )

    async def test_omitted_source_language(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        override_service,
        mock_translation_service,
    ):
        mock_translation_service.translate_via_sunflower = AsyncMock(
            return_value=_make_result(source_language=None)
        )

        response = await async_client.post(
            "/tasks/translate",
            json={"target_language": "lug", "text": "How are you?"},
            headers=_auth(test_user),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["output"]["source_language"] is None
        call_kwargs = mock_translation_service.translate_via_sunflower.await_args.kwargs
        assert call_kwargs["source_language"] is None

    @pytest.mark.parametrize(
        "source_lang,target_lang",
        [
            ("eng", "lug"),
            ("eng", "ach"),
            ("eng", "teo"),
            ("eng", "lgg"),
            ("eng", "nyn"),
            ("lug", "eng"),
            ("ach", "eng"),
            ("teo", "eng"),
            ("lgg", "eng"),
            ("nyn", "eng"),
        ],
    )
    async def test_legacy_language_pairs_still_accepted(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        override_service,
        source_lang: str,
        target_lang: str,
    ):
        response = await async_client.post(
            "/tasks/translate",
            json={
                "source_language": source_lang,
                "target_language": target_lang,
                "text": "Hello world",
            },
            headers=_auth(test_user),
        )

        assert response.status_code == 200

    async def test_new_sunflower_pair_accepted(
        self, async_client: AsyncClient, test_user: Dict, override_service
    ):
        # Any-to-any: Swahili -> Kinyarwanda was impossible with NLLB.
        response = await async_client.post(
            "/tasks/translate",
            json={
                "source_language": "swa",
                "target_language": "kin",
                "text": "Habari",
            },
            headers=_auth(test_user),
        )

        assert response.status_code == 200

    async def test_feedback_logged_with_sunflower_model(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        override_service,
        monkeypatch,
    ):
        calls = []

        async def record_feedback(*args, **kwargs):
            calls.append(kwargs)

        monkeypatch.setattr(
            "app.routers.translation.save_api_inference", record_feedback
        )

        response = await async_client.post(
            "/tasks/translate",
            json={
                "source_language": "eng",
                "target_language": "lug",
                "text": "Hello",
            },
            headers=_auth(test_user),
        )

        assert response.status_code == 200
        assert len(calls) == 1
        assert calls[0]["model_type"] == "Sunbird/Sunflower-14B"
        assert calls[0]["inference_type"] == "translation"


class TestTranslateValidation:
    """400/422 validation tests."""

    async def test_unsupported_target_code(
        self, async_client: AsyncClient, test_user: Dict, override_service
    ):
        response = await async_client.post(
            "/tasks/translate",
            json={"target_language": "fra", "text": "Hello"},
            headers=_auth(test_user),
        )

        assert response.status_code == 400
        message = response.json()["message"]
        assert "fra" in message
        assert "Supported languages" in message
        override_service.translate_via_sunflower.assert_not_awaited()

    async def test_unsupported_source_name(
        self, async_client: AsyncClient, test_user: Dict, override_service
    ):
        response = await async_client.post(
            "/tasks/translate",
            json={
                "source_language": "French",
                "target_language": "lug",
                "text": "Bonjour",
            },
            headers=_auth(test_user),
        )

        assert response.status_code == 400
        override_service.translate_via_sunflower.assert_not_awaited()

    async def test_source_equals_target_code_vs_name(
        self, async_client: AsyncClient, test_user: Dict, override_service
    ):
        response = await async_client.post(
            "/tasks/translate",
            json={
                "source_language": "lug",
                "target_language": "Luganda",
                "text": "Hello",
            },
            headers=_auth(test_user),
        )

        assert response.status_code == 400
        assert "different" in response.json()["message"].lower()
        override_service.translate_via_sunflower.assert_not_awaited()

    async def test_without_auth(self, async_client: AsyncClient):
        response = await async_client.post(
            "/tasks/translate",
            json={"target_language": "lug", "text": "Hello"},
        )
        assert response.status_code == 401

    async def test_missing_target_language(
        self, async_client: AsyncClient, test_user: Dict
    ):
        response = await async_client.post(
            "/tasks/translate",
            json={"text": "Hello"},
            headers=_auth(test_user),
        )
        assert response.status_code == 422

    async def test_empty_text(self, async_client: AsyncClient, test_user: Dict):
        response = await async_client.post(
            "/tasks/translate",
            json={"target_language": "lug", "text": ""},
            headers=_auth(test_user),
        )
        assert response.status_code == 422

    async def test_whitespace_only_text(
        self, async_client: AsyncClient, test_user: Dict
    ):
        response = await async_client.post(
            "/tasks/translate",
            json={"target_language": "lug", "text": "   "},
            headers=_auth(test_user),
        )
        assert response.status_code == 422


class TestTranslateErrorMapping:
    """Inference error -> HTTP status mapping."""

    async def _post(self, async_client, test_user):
        return await async_client.post(
            "/tasks/translate",
            json={
                "source_language": "eng",
                "target_language": "lug",
                "text": "Hello",
            },
            headers=_auth(test_user),
        )

    async def test_model_loading_maps_to_503(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        override_service,
        mock_translation_service,
    ):
        mock_translation_service.translate_via_sunflower = AsyncMock(
            side_effect=ModelLoadingError("loading")
        )
        response = await self._post(async_client, test_user)
        assert response.status_code == 503
        assert "loading" in response.json()["message"].lower()

    async def test_timeout_maps_to_503(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        override_service,
        mock_translation_service,
    ):
        mock_translation_service.translate_via_sunflower = AsyncMock(
            side_effect=InferenceTimeoutError("timeout")
        )
        response = await self._post(async_client, test_user)
        assert response.status_code == 503
        assert "timed out" in response.json()["message"].lower()

    async def test_generic_error_maps_to_502(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        override_service,
        mock_translation_service,
    ):
        mock_translation_service.translate_via_sunflower = AsyncMock(
            side_effect=RuntimeError("boom")
        )
        response = await self._post(async_client, test_user)
        assert response.status_code == 502

    async def test_empty_translation_maps_to_502(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        override_service,
        mock_translation_service,
    ):
        mock_translation_service.translate_via_sunflower = AsyncMock(
            return_value=_make_result(translated_text=None)
        )
        response = await self._post(async_client, test_user)
        assert response.status_code == 502
        assert "empty" in response.json()["message"].lower()
```

- [ ] **Step 2: Run new tests to verify they fail**

Run: `pytest app/tests/test_routers/test_translation.py -v`
Expected: FAIL — mostly `AttributeError`/assertion errors because the router still calls `service.translate(...)` and rejects non-enum languages with 422.

- [ ] **Step 3: Rewrite the router**

Replace the entire contents of `app/routers/translation.py` with:

```python
"""
Translation Router Module.

POST /tasks/translate translates text between 32 Ugandan and East African
languages using the Sunflower model — the same inference engine that powers
/tasks/chat/completions. The legacy NLLB code path
(TranslationService.translate) remains in the codebase but is no longer used
by this endpoint.

Architecture:
    Routes -> TranslationService.translate_via_sunflower -> InferenceService
    -> RunPod OpenAI-compatible API (Sunflower-14B)

Spec:
    docs/superpowers/specs/2026-06-12-translate-via-sunflower-design.md
"""

import logging
import time

from dotenv import load_dotenv
from fastapi import APIRouter, BackgroundTasks, Request

from app.core.exceptions import (
    BadRequestError,
    ExternalServiceError,
    ServiceUnavailableError,
)
from app.deps import CurrentUserDep, DbDep, QuotaServiceDep, TranslationServiceDep
from app.schemas.chat import DEFAULT_MODEL
from app.schemas.translation import (
    SunflowerTranslationRequest,
    WorkerTranslationResponse,
)
from app.services.inference_service import InferenceTimeoutError, ModelLoadingError
from app.utils.feedback import INFERENCE_TYPES, save_api_inference
from app.utils.languages import UnsupportedLanguageError, resolve_language
from app.utils.quota_guard import check_quota
from app.utils.rate_limit import get_account_type_limit, limiter

load_dotenv()
logging.basicConfig(level=logging.INFO)

router = APIRouter()


@router.post(
    "/translate",
    response_model=WorkerTranslationResponse,
)
@limiter.limit(get_account_type_limit)
async def translate(
    request: Request,
    translation_request: SunflowerTranslationRequest,
    quota: QuotaServiceDep,
    background_tasks: BackgroundTasks,
    db: DbDep,
    current_user: CurrentUserDep,
    service: TranslationServiceDep,
) -> dict:
    """Translate text between supported languages using the Sunflower model.

    Languages are accepted as ISO 639-3 codes (e.g. ``lug``) or full names
    (e.g. ``Luganda``), case-insensitively. ``source_language`` is optional —
    when omitted, Sunflower infers the source language from the text.
    Translation works between any pair of supported languages.

    Supported languages: Acholi (ach), Alur (alz), Aringa (luc), Ateso (teo),
    Bari (bfa), English (eng), Jopadhola (adh), Kakwa (keo),
    Karamojong (kdj), Kinyarwanda (kin), Kumam (kdi), Kupsabiny (kpz),
    Kwamba (rwm), Lango (laj), Lubwisi (tlj), Luganda (lug), Lugbara (lgg),
    Lugungu (rub), Lugwere (gwr), Lumasaba (myx), Lunyole (nuj),
    Lusoga (xog), Ma'di (mhi), Pokot (pok), Rukiga (cgg), Rukonjo (koo),
    Runyankole (nyn), Runyoro (nyo), Ruruuli (ruc), Rutooro (ttj),
    Samia (lsm), Swahili (swa).

    Example:

        Request body:
        {
            "source_language": "eng",
            "target_language": "lug",
            "text": "Hello, how are you?"
        }

        Response:
        {
            "id": "trans-1a2b3c...",
            "status": "COMPLETED",
            "output": {
                "translated_text": "Oli otya?",
                "source_language": "eng",
                "target_language": "lug"
            }
        }

    Raises:

        BadRequestError: Unsupported language, or source == target.
        ServiceUnavailableError: Model loading or inference timeout.
        ExternalServiceError: Empty model output or unexpected failure.
    """
    await check_quota(quota, db, current_user)

    try:
        target = resolve_language(translation_request.target_language)
        source = (
            resolve_language(translation_request.source_language)
            if translation_request.source_language is not None
            else None
        )
    except UnsupportedLanguageError as e:
        raise BadRequestError(message=str(e))

    if source is not None and source.code == target.code:
        raise BadRequestError(message="Source and target languages must be different")

    start_time = time.time()

    try:
        result = await service.translate_via_sunflower(
            text=translation_request.text,
            target_language=target,
            source_language=source,
        )
    except ModelLoadingError as e:
        logging.error(f"Model loading error during translation: {e}")
        raise ServiceUnavailableError(
            message=(
                "The AI model is currently loading. This usually takes "
                "2-3 minutes. Please try again shortly."
            )
        )
    except InferenceTimeoutError as e:
        logging.error(f"Translation timed out: {e}")
        raise ServiceUnavailableError(
            message="The request timed out. Please try again with a shorter text."
        )
    except ValueError as e:
        logging.error(f"Invalid translation request: {e}")
        raise BadRequestError(message=f"Invalid request: {str(e)}")
    except Exception as e:
        logging.error(f"Unexpected error during translation: {e}")
        raise ExternalServiceError(
            service_name="Sunflower Translation Service",
            message=(
                "An unexpected error occurred during translation. "
                "Please try again."
            ),
            original_error=str(e),
        )

    if not result.translated_text:
        raise ExternalServiceError(
            service_name="Sunflower Model",
            message=(
                "The model returned an empty response. "
                "Please try rephrasing your request."
            ),
        )

    elapsed_time = time.time() - start_time
    logging.info(f"Translation completed in {elapsed_time:.2f} seconds")

    response_payload = WorkerTranslationResponse(
        id=result.job_id,
        status="COMPLETED",
        output={
            "translated_text": result.translated_text,
            "source_language": result.source_language,
            "target_language": result.target_language,
        },
    ).model_dump()

    try:
        job_details = {
            "source_language": result.source_language,
            "target_language": result.target_language,
            "job_id": result.job_id,
        }
        background_tasks.add_task(
            save_api_inference,
            translation_request.text,
            response_payload,
            current_user,
            model_type=DEFAULT_MODEL,
            processing_time=elapsed_time,
            inference_type=INFERENCE_TYPES["translation"],
            job_details={k: v for k, v in job_details.items() if v is not None},
        )
    except Exception as e:
        logging.warning(f"Failed to schedule translation feedback save task: {e}")

    return response_payload
```

Key points:
- `TranslationServiceDep` / `DbDep` / `CurrentUserDep` from `app/deps.py` replace the router-local `get_service()` + raw `Depends(...)` (repo convention — `.claude/rules/routers.md`). Tests override `get_translation_service`.
- `DEFAULT_MODEL` is `"Sunbird/Sunflower-14B"` from `app/schemas/chat.py` — single source of truth for the public model name.
- The empty-content 502 raise sits **outside** the `try` block so it is not swallowed by the generic `except Exception` (same pattern as `app/routers/chat.py`).
- Do not import `SUNFLOWER_LANGUAGES` — it is not referenced in code (the docstring lists languages literally) and flake8 flags unused imports (F401).

- [ ] **Step 4: Fix the two cross-cutting test fixtures**

4a. In `app/tests/test_quota_endpoint.py`, inside `stub_translation_service`, replace:

```python
    async def fake_translate(self, *args, **kwargs):
        # Return a proper TranslationResult so the router can access .raw_response.
        # raw_response=None causes the router to use its fallback branch.
        return TranslationResult(
            translated_text="hello",
            source_language="eng",
            target_language="lug",
            status="COMPLETED",
            raw_response=None,
        )

    monkeypatch.setattr(TranslationService, "translate", fake_translate, raising=False)
```

with:

```python
    async def fake_translate(self, *args, **kwargs):
        # Return a TranslationResult the router can synthesize a response from.
        return TranslationResult(
            translated_text="hello",
            source_language="eng",
            target_language="lug",
            status="COMPLETED",
            job_id="trans-test",
            raw_response=None,
        )

    monkeypatch.setattr(
        TranslationService, "translate_via_sunflower", fake_translate, raising=False
    )
```

4b. In `app/tests/test_rate_limit_endpoint.py`, inside `stub_translation_service`, replace:

```python
    async def fake_translate(
        self,
        text: str,
        source_language: str,
        target_language: str,
    ) -> TranslationResult:
        return TranslationResult(
            translated_text="Hello",
            source_language=source_language,
            target_language=target_language,
            status="COMPLETED",
        )
```

with:

```python
    async def fake_translate(self, *args, **kwargs) -> TranslationResult:
        return TranslationResult(
            translated_text="Hello",
            source_language="eng",
            target_language="lug",
            status="COMPLETED",
            job_id="trans-test",
        )
```

and replace:

```python
    monkeypatch.setattr(TranslationService, "translate", fake_translate)
```

with:

```python
    monkeypatch.setattr(TranslationService, "translate_via_sunflower", fake_translate)
```

- [ ] **Step 5: Run the affected test files**

Run: `pytest app/tests/test_routers/test_translation.py app/tests/test_quota_endpoint.py app/tests/test_rate_limit_endpoint.py -v`
Expected: PASS (quota test is slow — ~500 requests — be patient; if the environment makes it impractical, run it once here and rely on Task 6's full-suite run)

- [ ] **Step 6: Lint and commit**

```bash
make lint-check
git add app/routers/translation.py app/tests/test_routers/test_translation.py \
  app/tests/test_quota_endpoint.py app/tests/test_rate_limit_endpoint.py
git commit -m "feat: route /tasks/translate through the Sunflower model"
```

---

### Task 5: Documentation updates

**Files:**
- Modify: `app/docs.py:28-30` (Translation bullet) and `app/docs.py:106-109` (tags_metadata)
- Modify: `docs/tutorial.md:57-107` (Part 2)

- [ ] **Step 1: Update `app/docs.py`**

Replace:

```python
### Translation
- **`POST /tasks/translate`** - Translate text between English and local languages
  (Acholi, Ateso, Luganda, Lugbara, Runyankole)
```

with:

```python
### Translation
- **`POST /tasks/translate`** - Translate text between 32 Ugandan and East African
  languages using the Sunflower model. Languages are accepted as ISO codes (`lug`)
  or full names (`Luganda`); `source_language` is optional (auto-detected when
  omitted). Translation works between any pair of supported languages.
```

Replace the `Translation` entry in `tags_metadata`:

```python
    {
        "name": "Translation",
        "description": "Translate text between English and local languages using the NLLB model. Supports bidirectional translation for Acholi, Ateso, Luganda, Lugbara, and Runyankole.",  # noqa: E501
    },
```

with:

```python
    {
        "name": "Translation",
        "description": "Translate text using the Sunflower model. Supports 32 languages (e.g. Luganda, Acholi, Ateso, Lugbara, Runyankole, Swahili, Kinyarwanda) accepted as ISO codes or full names; source language is optional and translation works between any supported pair.",  # noqa: E501
    },
```

- [ ] **Step 2: Rewrite tutorial Part 2**

In `docs/tutorial.md`, replace everything from `## Part 2: Translation (NLLB Model)` (line 57) up to (not including) the `---` before `## Part 3:` (line 109) with:

````markdown
## Part 2: Translation (Sunflower Model)

Translate text between 32 Ugandan and East African languages using the
Sunflower model. Languages are accepted as ISO 639-3 codes (`lug`) or full
names (`Luganda`), case-insensitively, and translation works between **any
pair** of supported languages. `source_language` is optional — when omitted,
Sunflower infers it from the text.

```python
import os
import requests
from dotenv import load_dotenv

load_dotenv()

url = "https://api.sunbird.ai/tasks/translate"
access_token = os.getenv("AUTH_TOKEN")

headers = {
    "accept": "application/json",
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json",
}

# Example: Translate from Luganda to English
data = {
    "source_language": "lug",
    "target_language": "eng",
    "text": "Ekibiina ekiddukanya omuzannyo gw'emisinde mu ggwanga ekya Uganda Athletics Federation kivuddeyo nekitegeeza nga lawundi esooka eyemisinde egisunsulamu abaddusi abanakiika mu mpaka ezenjawulo ebweru w'eggwanga egya National Athletics Trials nga bwegisaziddwamu.",
}

response = requests.post(url, headers=headers, json=data)
print(response.json())
```

`source_language` is optional, and full language names work too:

```python
data = {
    "target_language": "Luganda",
    "text": "How are you?",
}

response = requests.post(url, headers=headers, json=data)
print(response.json())
```

**Supported languages** (ISO code → name):

```python
language_codes = {
    "ach": "Acholi",
    "adh": "Jopadhola",
    "alz": "Alur",
    "bfa": "Bari",
    "cgg": "Rukiga",
    "eng": "English",
    "gwr": "Lugwere",
    "kdi": "Kumam",
    "kdj": "Karamojong",
    "keo": "Kakwa",
    "kin": "Kinyarwanda",
    "koo": "Rukonjo",
    "kpz": "Kupsabiny",
    "laj": "Lango",
    "lgg": "Lugbara",
    "lsm": "Samia",
    "luc": "Aringa",
    "lug": "Luganda",
    "mhi": "Ma'di",
    "myx": "Lumasaba",
    "nuj": "Lunyole",
    "nyn": "Runyankole",
    "nyo": "Runyoro",
    "pok": "Pokot",
    "rub": "Lugungu",
    "ruc": "Ruruuli",
    "rwm": "Kwamba",
    "swa": "Swahili",
    "teo": "Ateso",
    "tlj": "Lubwisi",
    "ttj": "Rutooro",
    "xog": "Lusoga",
}
```

The response shape is unchanged from the previous NLLB-backed endpoint:

```json
{
    "id": "trans-1a2b3c...",
    "status": "COMPLETED",
    "output": {
        "translated_text": "Oli otya?",
        "source_language": "lug",
        "target_language": "eng"
    }
}
```

````

- [ ] **Step 3: Verify lint and unaffected tests**

Run: `make lint-check && pytest app/tests/test_api.py -v`
Expected: lint clean; test_api PASS

- [ ] **Step 4: Commit**

```bash
git add app/docs.py docs/tutorial.md
git commit -m "docs: update translation docs for Sunflower routing"
```

---

### Task 6: Full verification gate

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `pytest app/tests/ -v`
Expected: All tests pass. Known pre-existing exception on this machine: 4 `test_config.py` GA failures caused by local `.env` GA variables (verified pre-existing at baseline of PR #218 — not caused by this work; do not fix).

- [ ] **Step 2: Run lint**

Run: `make lint-check`
Expected: black, isort, flake8 all clean. If black/isort complain, run `make lint-apply` and re-check.

- [ ] **Step 3: Commit any fixes**

```bash
git add -A ':!.claude'
git commit -m "test: fix issues found in full-suite verification"   # only if fixes were needed
```

Never commit `.claude/settings.local.json`.
