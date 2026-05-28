"""
Rate Limiting Utility Module.

Shared helpers for SlowAPI per-account-type rate limiting. Routers use
``custom_key_func`` as the SlowAPI key function and ``get_account_type_limit``
as the dynamic limit string, then apply ``@limiter.limit(get_account_type_limit)``
on individual endpoints.

Tiers (requests per minute):
    - admin: 1000
    - premium: 100
    - default (free / unknown / anonymous): 50

Usage:
    from slowapi import Limiter
    from app.utils.rate_limit import custom_key_func, get_account_type_limit

    limiter = Limiter(key_func=custom_key_func)

    @router.post("/endpoint")
    @limiter.limit(get_account_type_limit)
    async def endpoint(request: Request, ...):
        ...

Note:
    Extracted from per-router duplicates (stt, translation, language,
    inference, runpod_tts, tasks) to keep tier definitions in one place.
"""

from fastapi import Request
from jose import jwt

from app.utils.auth import ALGORITHM, SECRET_KEY


def custom_key_func(request: Request) -> str:
    """Extract account type from the JWT token in the Authorization header.

    Returns ``"anonymous"`` when no Authorization header is present, the
    raw ``account_type`` claim when the token decodes successfully, or
    ``""`` (empty string) when the token is present but invalid. Both the
    empty string and an unknown account type fall through to the default
    tier in ``get_account_type_limit``.

    Args:
        request: The FastAPI request object.

    Returns:
        The account type string, ``"anonymous"``, or ``""``.
    """
    header = request.headers.get("Authorization")
    if not header:
        return "anonymous"
    _, _, token = header.partition(" ")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        account_type: str = payload.get("account_type", "")
        return account_type or ""
    except Exception:
        return ""


def get_account_type_limit(key: str) -> str:
    """Map an account type key to its SlowAPI rate-limit string.

    Args:
        key: Account type returned by ``custom_key_func``.

    Returns:
        Rate-limit string in SlowAPI's ``"<n>/<period>"`` format.
    """
    if not key:
        return "50/minute"
    if key.lower() == "admin":
        return "1000/minute"
    if key.lower() == "premium":
        return "100/minute"
    return "50/minute"
