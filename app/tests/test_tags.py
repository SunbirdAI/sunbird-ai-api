"""OpenAPI tag-consolidation tests.

Every deprecated endpoint (and the non-deprecated legacy `/tasks/summarise`)
must be grouped under the single ``legacy/deprecated`` tag, and that tag must
not leak onto any live endpoint.
"""

from app.api import app

LEGACY_TAG = "legacy/deprecated"

# Non-deprecated endpoints that are legacy by convention (backward-compat
# tasks_router) and should still carry the shared legacy tag.
EXTRA_LEGACY_PATHS = {"/tasks/summarise"}

_HTTP_METHODS = {"get", "post", "put", "delete", "patch"}


def _operations():
    """Yield (path, method, operation) for every real HTTP operation."""
    for path, methods in app.openapi()["paths"].items():
        for method, op in methods.items():
            if method in _HTTP_METHODS:
                yield path, method, op


def test_deprecated_endpoints_only_carry_legacy_tag():
    """Each deprecated op (and EXTRA_LEGACY_PATHS) has exactly [legacy/deprecated]."""
    offenders = [
        (method.upper(), path, op.get("tags"))
        for path, method, op in _operations()
        if (op.get("deprecated") or path in EXTRA_LEGACY_PATHS)
        and op.get("tags") != [LEGACY_TAG]
    ]
    assert not offenders, f"legacy/deprecated endpoints with wrong tags: {offenders}"


def test_legacy_tag_does_not_leak_onto_live_endpoints():
    """No live (non-deprecated, non-legacy) endpoint carries the legacy tag."""
    leaks = [
        (method.upper(), path)
        for path, method, op in _operations()
        if LEGACY_TAG in op.get("tags", [])
        and not op.get("deprecated")
        and path not in EXTRA_LEGACY_PATHS
    ]
    assert not leaks, f"live endpoints incorrectly tagged legacy/deprecated: {leaks}"


def test_all_deprecated_endpoints_are_grouped():
    """Sanity check: the unified endpoints stay under their own live tags."""
    by_path = {(path, method): op.get("tags", []) for path, method, op in _operations()}
    assert by_path[("/tasks/audio/speech", "post")] == ["Text-to-Speech (Unified)"]
    assert by_path[("/tasks/audio/speech/batch", "post")] == [
        "Text-to-Speech (Unified)"
    ]
    assert by_path[("/tasks/voice/speakers", "get")] == ["Text-to-Speech (Unified)"]
    assert by_path[("/tasks/audio/transcriptions", "post")] == [
        "Speech-to-Text (Unified)"
    ]
    # The two surviving live Modal utility endpoints keep their tag.
    assert by_path[("/tasks/modal/health", "get")] == ["TTS (Modal)"]
    assert by_path[("/tasks/modal/tts/refresh-url", "get")] == ["TTS (Modal)"]
