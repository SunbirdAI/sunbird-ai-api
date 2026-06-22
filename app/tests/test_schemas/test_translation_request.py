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
