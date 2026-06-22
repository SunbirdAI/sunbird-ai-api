---
paths:
  - "app/routers/**"
  - "app/services/**"
  - "app/integrations/**"
---

# API Router & Service Patterns

## Router Pattern

```python
from fastapi import APIRouter
from app.deps import STTServiceDep, DbDep, CurrentUserDep

router = APIRouter()

@router.post("/transcribe")
async def transcribe(
    stt_service: STTServiceDep,
    db: DbDep,
    current_user: CurrentUserDep,
):
    ...
```

- Import all service/auth dependencies from `app/deps.py`, not directly from service files.
- Use the `Annotated` type aliases (`STTServiceDep`, `TranslationServiceDep`, etc.) defined in `app/deps.py`.
- Use custom exception classes from `app/core/exceptions.py` (`AuthenticationError`, `BadRequestError`, `NotFoundError`, `ConflictError`, `ExternalServiceError`) — not bare `HTTPException`.

## Adding a New Service

1. Create `app/services/my_service.py` with the service class and a `get_my_service()` singleton factory.
2. Register a `Depends()` binding and `Annotated` alias in `app/deps.py`.
3. Create `app/routers/my_router.py` and include it in `app/api.py`.

## Service Singleton Pattern

```python
_service_instance = None

def get_my_service() -> MyService:
    global _service_instance
    if _service_instance is None:
        _service_instance = MyService()
    return _service_instance
```

## WhatsApp Webhook

The webhook flow in `webhooks.py` uses `OptimizedMessageProcessor` from `app/services/message_processor.py`. User preferences (language, voice settings) are stored via `app/integrations/whatsapp_store.py`. First-time users always receive the onboarding template.

## Rate Limiting

Two rate-limiting systems coexist:
- **SlowAPI** (`slowapi`) — IP-based, applied at middleware level
- **FastAPILimiter** (Redis-backed) — token-bucket, applied per-endpoint with `@limiter.limit()`

Use `FastAPILimiter` decorators for per-user/per-endpoint limits on `/tasks/*` endpoints.
