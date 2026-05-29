"""Free-tier daily cap is enforced through the HTTP layer."""

import datetime as dt
from typing import Dict

import fakeredis.aioredis
import pytest
from httpx import AsyncClient

from app.services.redis_client import SafeRedis

# Opt out of the conftest stub_quota_service autouse fixture for the whole
# module so we exercise the real QuotaService end-to-end.
pytestmark = pytest.mark.real_quota


@pytest.fixture(autouse=True)
def install_quota_with_fakeredis(monkeypatch):
    """Install a QuotaService backed by fakeredis and a fixed 'today'."""
    from app.services import quota_service as qs_module
    from app.services.quota_service import QuotaService

    safe = SafeRedis(fakeredis.aioredis.FakeRedis(decode_responses=True))
    svc = QuotaService(redis=safe, today=lambda: dt.date(2026, 5, 28))
    monkeypatch.setattr(qs_module, "_quota_service", svc)
    yield
    monkeypatch.setattr(qs_module, "_quota_service", None)


@pytest.fixture(autouse=True)
def stub_translation_service(monkeypatch):
    """Make /tasks/translate resolve instantly to a static value, and prevent
    the FEEDBACK_URL background task from hanging the loop on DNS failures.
    """
    from app.services.translation_service import TranslationResult, TranslationService

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

    # FEEDBACK_URL kicks off a background HTTP call; stub it.
    async def noop_save(*args, **kwargs):
        return None

    try:
        import app.utils.feedback as feedback_module

        monkeypatch.setattr(
            feedback_module, "save_api_inference", noop_save, raising=False
        )
    except ImportError:
        pass
    try:
        import app.routers.translation as translation_module

        monkeypatch.setattr(
            translation_module, "save_api_inference", noop_save, raising=False
        )
    except (ImportError, AttributeError):
        pass

    yield


async def test_free_user_429_after_daily_cap(
    authenticated_client: AsyncClient, test_user: Dict
):
    """Free tier daily cap is 500; the 501st /tasks/translate request returns 429."""
    # NllbLanguage enum values are ISO codes: eng, lug, ach, teo, lgg, nyn
    payload = {
        "text": "hello",
        "source_language": "eng",
        "target_language": "lug",
    }

    # Per-minute limit is 50; reset SlowAPI's in-memory bucket every 50 calls so
    # the daily-cap test is not derailed by the per-minute cap.
    from app.utils.rate_limit import limiter

    statuses = []
    for i in range(500):
        if i % 50 == 0:
            limiter.reset()
        r = await authenticated_client.post("/tasks/translate", json=payload)
        statuses.append(r.status_code)

    assert (
        statuses.count(200) == 500
    ), f"unexpected non-200s: {dict.fromkeys(statuses, 0) | {s: statuses.count(s) for s in set(statuses)}}"

    limiter.reset()
    r = await authenticated_client.post("/tasks/translate", json=payload)
    assert r.status_code == 429
    assert "Daily quota exceeded" in r.json().get("message", "")
    assert int(r.headers.get("Retry-After", "0")) > 0
