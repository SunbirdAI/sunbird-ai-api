from app.services.cache import CacheBackend, get_cache_backend
from app.services.cache.in_memory import InMemoryTTLCache


def test_factory_returns_in_memory_by_default(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.cache_backend", "memory")
    import app.services.cache as cache_mod

    cache_mod._instance = None

    backend = get_cache_backend()
    assert isinstance(backend, InMemoryTTLCache)
    assert isinstance(backend, CacheBackend)


def test_factory_returns_same_instance(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.cache_backend", "memory")
    import app.services.cache as cache_mod

    cache_mod._instance = None

    first = get_cache_backend()
    second = get_cache_backend()
    assert first is second


def test_factory_unknown_backend_raises(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.cache_backend", "bogus")
    import app.services.cache as cache_mod

    cache_mod._instance = None

    import pytest

    with pytest.raises(ValueError, match="Unknown cache_backend"):
        get_cache_backend()
