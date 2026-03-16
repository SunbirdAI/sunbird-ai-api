---
paths:
  - "app/tests/**"
---

# Testing

Tests use in-memory SQLite (`sqlite+aiosqlite:///:memory:`). `asyncio_mode = auto` is set in `pytest.ini` — no need to mark individual tests `@pytest.mark.asyncio`.

## Key Fixtures (from `conftest.py`)

| Fixture | Type | Purpose |
|---------|------|---------|
| `test_db` | async | Creates/drops all tables around each test |
| `db_session` | `AsyncSession` | Direct DB access |
| `async_client` | `AsyncClient` | Unauthenticated HTTP client |
| `authenticated_client` | `AsyncClient` | Client with Bearer token header |
| `test_user` | dict | Free-tier user + JWT token |
| `admin_user` | dict | Admin user + JWT token |
| `premium_user` | dict | Premium user + JWT token |
| `mock_storage_service` | `MagicMock` | GCP storage mock |
| `mock_tts_service` | `MagicMock` | TTS service mock |
| `mock_runpod_client` | `MagicMock` | RunPod inference mock |

## Test Markers

- `@pytest.mark.integration` — tests requiring external services
- `@pytest.mark.slow` — slow-running tests
- `@pytest.mark.unit` — pure unit tests

Run by marker: `pytest app/tests/ -m "not integration" -v`

## Pattern for New Tests

```python
async def test_example(authenticated_client, test_db):
    response = await authenticated_client.post("/tasks/endpoint", json={...})
    assert response.status_code == 200
```

For endpoints that call external services, mock at the service layer using `monkeypatch` or fixture overrides rather than patching HTTP calls directly.
