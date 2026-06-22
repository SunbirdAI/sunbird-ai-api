"""Tier quotas are sourced from a single TIER_QUOTAS dict."""

from app.utils.rate_limit import TIER_QUOTAS, get_account_type_limit


def test_tier_quotas_shape():
    for tier in ("free", "premium", "admin"):
        q = TIER_QUOTAS[tier]
        assert "per_minute" in q
        assert "per_day" in q
        assert "per_month" in q


def test_free_per_minute_string():
    assert get_account_type_limit("free:alice") == "50/minute"


def test_empty_key_defaults_to_free():
    assert get_account_type_limit("") == "50/minute"


def test_anonymous_defaults_to_free():
    assert get_account_type_limit("anonymous:1.2.3.4") == "50/minute"


def test_premium_limit():
    assert get_account_type_limit("premium:bob") == "100/minute"


def test_admin_limit():
    assert get_account_type_limit("admin:root") == "1000/minute"


def test_unknown_tier_defaults_to_free():
    assert get_account_type_limit("ghost:x") == "50/minute"
