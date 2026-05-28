"""Verify Redis-related settings are exposed via the Settings model."""

from app.core.config import Settings


def test_redis_settings_defaults(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    s = Settings(_env_file=None)
    assert s.redis_url is None
    assert s.redis_socket_timeout == 2.0
    assert s.redis_socket_connect_timeout == 2.0
    assert s.redis_health_check_interval == 30
    assert s.redis_max_connections == 10


def test_redis_url_read_from_env(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "rediss://default:abc@example.upstash.io:6379")
    s = Settings(_env_file=None)
    assert s.redis_url == "rediss://default:abc@example.upstash.io:6379"
