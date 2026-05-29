"""Rate Limiting Utility Module.

Single source of truth for per-tier rate-limit quotas plus the helpers
SlowAPI uses on each request. Routers import the ``limiter`` instance
defined here so every endpoint shares one Redis-backed storage and one
key function.

Per-minute limits are enforced by SlowAPI inline. Per-day and per-month
limits are enforced by ``QuotaService`` (Phase 2).

Tiers:
    - free / anonymous / unknown: 50/min, 500/day, 5000/month
    - premium: 100/min, 5000/day, 100000/month
    - admin: 1000/min, unlimited day/month
"""

from __future__ import annotations

from typing import Optional

from fastapi import Request
from jose import jwt
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings
from app.utils.auth import ALGORITHM, SECRET_KEY

TIER_QUOTAS: dict[str, dict[str, object]] = {
    "free": {
        "per_minute": "50/minute",
        "per_day": 500,
        "per_month": 5_000,
    },
    "premium": {
        "per_minute": "100/minute",
        "per_day": 5_000,
        "per_month": 100_000,
    },
    "admin": {
        "per_minute": "1000/minute",
        "per_day": None,  # unlimited
        "per_month": None,
    },
}


def _decode_token(request: Request) -> tuple[str, Optional[str]]:
    """Return ``(account_type, subject)`` from the request JWT.

    Defaults: ``("", None)`` when no/invalid token. ``account_type`` is
    lowercased; ``subject`` is the ``sub`` claim if present.
    """
    header = request.headers.get("Authorization")
    if not header:
        return "anonymous", None
    _, _, token = header.partition(" ")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        account_type = (payload.get("account_type") or "").lower()
        subject = payload.get("sub")
        return account_type, subject
    except Exception:
        return "", None


def custom_key_func(request: Request) -> str:
    """Return a SlowAPI key of the form ``"<tier>:<identity>"``.

    Identity is the JWT ``sub`` when present, otherwise the remote IP. This
    ensures each user's bucket is separate from every other user's bucket,
    so a single noisy free user does not starve the others.
    """
    tier, subject = _decode_token(request)
    identity = subject or get_remote_address(request)
    if not tier:
        tier = "free"
    return f"{tier}:{identity}"


def _resolve_tier(key: str) -> str:
    """Pull the tier portion out of the composite SlowAPI key."""
    tier = key.split(":", 1)[0] if ":" in key else key
    tier = tier.lower()
    if tier in ("admin", "premium", "free"):
        return tier
    return "free"


def get_account_type_limit(key: str) -> str:
    """Map a SlowAPI key to the per-minute limit string for its tier."""
    return TIER_QUOTAS[_resolve_tier(key)]["per_minute"]  # type: ignore[return-value]


def _build_limiter() -> Limiter:
    """Construct the shared SlowAPI limiter.

    Uses ``settings.redis_url`` for storage when set; falls back to in-memory
    storage on init failure. Also configures ``in_memory_fallback`` so
    transient Redis errors during request handling do not 500 the API.
    """
    fallback_limits = [
        TIER_QUOTAS["free"]["per_minute"],
        TIER_QUOTAS["premium"]["per_minute"],
        TIER_QUOTAS["admin"]["per_minute"],
    ]

    if not settings.redis_url:
        return Limiter(
            key_func=custom_key_func,
            in_memory_fallback=fallback_limits,
        )

    try:
        return Limiter(
            key_func=custom_key_func,
            storage_uri=settings.redis_url,
            in_memory_fallback=fallback_limits,
        )
    except Exception:  # noqa: BLE001 — startup must not crash
        return Limiter(
            key_func=custom_key_func,
            in_memory_fallback=fallback_limits,
        )


# Shared SlowAPI Limiter — all routers must import this instance, not their own.
limiter = _build_limiter()
