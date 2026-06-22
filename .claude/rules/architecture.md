# Architecture

## Request Flow

`app/api.py` → Router → Service → Integration/DB

**Middleware** (LIFO order — last registered executes first on requests):
1. SlowAPI rate limiting
2. CORS
3. MonitoringMiddleware (logs `/tasks/*` usage: username, org, endpoint, duration)
4. Session
5. LargeUpload (100MB max, rejects before processing)

## Routers (`app/routers/`)

All mounted under `/tasks` except auth. Add new endpoints to the matching router or create a new one following the same pattern.

| Router | Prefix | Purpose |
|--------|--------|---------|
| `auth.py` | `/auth` | JWT login, Google OAuth, password reset |
| `stt.py` | `/tasks` | Speech-to-text (RunPod) |
| `translation.py` | `/tasks` | Text translation |
| `language.py` | `/tasks` | Language identification |
| `tts.py` | `/tasks/modal` | TTS via Modal |
| `runpod_tts.py` | `/tasks/runpod` | TTS via RunPod |
| `inference.py` | `/tasks` | Sunflower model |
| `webhooks.py` | `/tasks` | WhatsApp Business webhook |
| `upload.py` | `/tasks` | Audio file upload |
| `dashboard.py` | `/api/dashboard` | Usage analytics |
| `tasks.py` | `/tasks` | Legacy endpoints (backward compat) |
| `spa.py` | `/` | Serves React SPA |

## Services (`app/services/`)

Business logic layer. Each service has a `get_<service>()` singleton factory used for dependency injection. Services are injected into routers via `Annotated` type aliases defined in `app/deps.py`.

```python
# Pattern for injecting a service in a router
async def endpoint(stt_service: STTServiceDep, db: DbDep, current_user: CurrentUserDep):
```

## Integrations (`app/integrations/`)

Thin wrappers around external HTTP clients:
- `runpod.py` — RunPod serverless inference
- `openai_client.py` — OpenAI API
- `whatsapp_api.py` — WhatsApp Business HTTP API
- `whatsapp_store.py` — user preference persistence for WhatsApp
- `firebase.py` — Firebase

## Dependency Injection (`app/deps.py`)

Central hub for all `Annotated` type aliases. When adding a new service, register it here alongside its `Depends()` binding. Routers import only from `app/deps.py`, not directly from services.

## Configuration (`app/core/config.py`)

Single `Settings` (Pydantic BaseSettings) instance loaded once via `lru_cache`. Access everywhere as `from app.core.config import settings`. Key helpers: `settings.is_production`, `settings.database_url_async`.

## Frontend

React + Vite app in `frontend/`. Built output goes to `app/static/react_build/` and served as a SPA by `spa.py`. Run Tailwind in watch mode when editing frontend:

```bash
npx tailwindcss -i ./app/static/input.css -o ./app/static/output.css --watch
```

## Deployment

Google Cloud Run + Cloud SQL (PostgreSQL). CI/CD via GitHub Actions using Workload Identity Federation (see `.github/workflows/`).
