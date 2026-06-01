"""Helpers for marking legacy endpoints deprecated via RFC 8594 headers.

Adds standard ``Deprecation`` / ``Sunset`` / ``Link`` response headers so that
programmatic clients can detect a deprecated endpoint and discover its
successor. Pair with ``deprecated=True`` on the route decorator for the
OpenAPI/Swagger signal.
"""

from typing import Dict

from fastapi import Response

# RFC 7231 HTTP-date. 2026-12-01 is a Tuesday.
STT_SUNSET_DATE = "Tue, 01 Dec 2026 00:00:00 GMT"

# Successor endpoint for the legacy STT routes.
SUCCESSOR_TRANSCRIPTIONS = "/tasks/audio/transcriptions"


def deprecation_headers(
    successor: str, sunset: str = STT_SUNSET_DATE
) -> Dict[str, str]:
    """Build RFC-8594 deprecation headers pointing at a successor endpoint.

    Args:
        successor: Path of the replacement endpoint.
        sunset: HTTP-date string for the planned removal date.

    Returns:
        A dict of header name -> value.
    """
    return {
        "Deprecation": "true",
        "Sunset": sunset,
        "Link": f'<{successor}>; rel="successor-version"',
    }


def add_deprecation_headers(
    response: Response, successor: str, sunset: str = STT_SUNSET_DATE
) -> None:
    """Set RFC-8594 deprecation headers on an injected FastAPI ``Response``.

    Use this when the handler returns a Pydantic model (FastAPI merges the
    injected response's headers into the final response). For handlers that
    return a raw ``Response`` object, pass ``deprecation_headers(...)`` to that
    object's ``headers=`` argument instead.
    """
    for key, value in deprecation_headers(successor, sunset).items():
        response.headers[key] = value
