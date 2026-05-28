"""Per-minute rate limiting for Free-tier and empty-account-type JWTs.

The shared Limiter is in-memory in tests (REDIS_URL is unset). We exercise
``/tasks/translate`` because it carries the @limiter.limit(get_account_type_limit)
decorator and its upstream service can be stubbed to a static return so the
loop runs fast.

NOTE: The plan referenced ``/tasks/language_id``, but that endpoint does NOT
carry the @limiter.limit decorator (only ``/tasks/auto_detect_audio_language``
does in the language router). ``/tasks/translate`` is the simplest JSON-body
endpoint that IS rate-limited, so it is used here instead.

The anonymous test is DROPPED: SlowAPI's @limiter.limit decorator wraps the
route handler, which means auth runs first (FastAPI dependency resolution).
Unauthenticated requests receive a 401 from the auth dependency before the
rate-limit counter can fire, so 429 never surfaces on unauthenticated calls.
"""

from typing import Dict

import pytest
from httpx import AsyncClient

from app.utils.rate_limit import TIER_QUOTAS, limiter


@pytest.fixture(autouse=True)
def reset_limiter_storage():
    """SlowAPI keeps per-process counters; reset between tests."""
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture(autouse=True)
def stub_translation_service(monkeypatch):
    """Make /tasks/translate resolve instantly to a static value.

    Also stubs out ``save_api_inference`` so the background-task feedback
    call does not attempt real network connections (FEEDBACK_URL may be
    configured in .env, causing DNS failures and multi-second retries that
    make a 51-iteration loop take many minutes).
    """
    from app.services.translation_service import TranslationResult, TranslationService

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

    async def fake_save_api_inference(*args, **kwargs):
        pass

    monkeypatch.setattr(TranslationService, "translate", fake_translate)
    monkeypatch.setattr(
        "app.utils.feedback.save_api_inference", fake_save_api_inference
    )
    monkeypatch.setattr(
        "app.routers.translation.save_api_inference", fake_save_api_inference
    )
    yield


def _free_per_minute() -> int:
    """Extract the numeric portion of e.g. ``'50/minute'``."""
    return int(TIER_QUOTAS["free"]["per_minute"].split("/")[0])


_TRANSLATE_PAYLOAD = {
    "source_language": "eng",
    "target_language": "lug",
    "text": "Hello world",
}


async def _hammer(client: AsyncClient, attempts: int):
    statuses = []
    for _ in range(attempts):
        r = await client.post("/tasks/translate", json=_TRANSLATE_PAYLOAD)
        statuses.append(r.status_code)
    return statuses


async def test_free_user_hits_429_after_quota(
    authenticated_client: AsyncClient, test_user: Dict
):
    """test_user has account_type=free; JWT has no ``account_type`` claim
    (sub-only token), so custom_key_func resolves the tier to 'free'."""
    per_min = _free_per_minute()
    statuses = await _hammer(authenticated_client, per_min + 1)

    # First `per_min` succeed (200), the (per_min+1)-th is rejected (429).
    assert statuses[:per_min].count(200) == per_min, statuses
    assert statuses[-1] == 429, statuses


async def test_empty_account_type_jwt_uses_free_tier(
    async_client: AsyncClient, test_user: Dict
):
    """A JWT with no ``account_type`` claim must be treated as free tier."""
    async_client.headers["Authorization"] = f"Bearer {test_user['token']}"
    per_min = _free_per_minute()
    statuses = await _hammer(async_client, per_min + 1)
    assert statuses[-1] == 429
