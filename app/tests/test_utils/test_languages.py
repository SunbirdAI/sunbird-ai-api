"""Tests for app/utils/languages.py — Sunflower language resolution."""

import pytest

from app.utils.languages import (
    _CODE_TO_NAME,
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

    @pytest.mark.parametrize("code", list(_CODE_TO_NAME.keys()))
    def test_every_supported_code_resolves(self, code):
        resolved = resolve_language(code)
        assert resolved.code == code
        assert resolved.name == _CODE_TO_NAME[code]


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
