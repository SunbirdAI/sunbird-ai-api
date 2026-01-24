# FastAPI Application Refactoring Plan

## Overview

This document outlines a step-by-step refactoring plan for the `app` folder of the Sunbird AI API. The goal is to improve code organization, modularity, and maintainability while following FastAPI best practices.

**Key Principles:**
- Incremental refactoring with tests at each step
- No functionality changes during refactoring
- Proper documentation with docstrings
- Maintain backward compatibility for API endpoints

---

## Current State Analysis

### Current Folder Structure
```
app/
├── alembic/                          # Database migrations
├── core/
│   └── config.py                     # Configuration (well-structured)
├── crud/                             # CRUD operations (good)
│   ├── users.py
│   ├── audio_transcription.py
│   └── monitoring.py
├── database/
│   └── db.py                         # Database setup (good)
├── inference_services/               # ML services (needs reorganization)
│   ├── tts.py
│   ├── ug40_inference.py
│   ├── runpod_helpers.py
│   ├── whatsapp_service.py
│   ├── whats_app_services.py         # Duplicate naming
│   ├── openai_script.py
│   ├── OptimizedMessageProcessor.py  # Non-pythonic naming
│   └── user_preference.py
├── middleware/
│   └── monitoring_middleware.py
├── models/                           # ORM models (good)
├── routers/                          # API routes (needs splitting)
│   ├── auth.py                       # ~400 lines - reasonable
│   ├── tasks.py                      # ~1850 lines - TOO LARGE
│   ├── tts.py                        # ~300 lines - reasonable
│   └── frontend.py                   # ~400 lines - reasonable
├── schemas/                          # Pydantic schemas (good)
├── tests/                            # Tests (minimal coverage)
├── utils/                            # Utilities (needs reorganization)
│   ├── auth_utils.py
│   ├── email_utils.py
│   ├── exception_utils.py
│   ├── helper_utils.py
│   ├── monitoring_utils.py
│   ├── storage.py
│   └── upload_audio_file_gcp.py
├── static/
├── templates/
├── api.py                            # Main app entry point
├── deps.py                           # Dependencies
└── docs.py                           # API documentation
```

### Key Issues Identified

1. **`routers/tasks.py` is 1850+ lines** - Contains STT, TTS, translation, language ID, summarization, and webhooks all in one file
2. **Duplicate/inconsistent naming** - `whatsapp_service.py` vs `whats_app_services.py`, `OptimizedMessageProcessor.py` (PascalCase file)
3. **Business logic in routers** - Heavy processing logic mixed with endpoint definitions
4. **No service layer abstraction** - Direct calls to inference services from routers
5. **Scattered utilities** - `utils/` folder has mixed responsibilities
6. **Minimal test coverage** - Only `test_auth.py` with 1 test

---

## Target Folder Structure

```
app/
├── alembic/                          # Database migrations (unchanged)
├── core/                             # Core application configuration
│   ├── __init__.py
│   ├── config.py                     # Settings (unchanged)
│   ├── exceptions.py                 # Custom exception classes (NEW)
│   └── logging.py                    # Logging configuration (NEW)
├── crud/                             # Database CRUD operations (unchanged)
│   ├── __init__.py
│   ├── users.py
│   ├── audio_transcription.py
│   └── monitoring.py
├── database/                         # Database setup (unchanged)
│   ├── __init__.py
│   └── db.py
├── middleware/                       # Middleware (unchanged)
│   ├── __init__.py
│   └── monitoring_middleware.py
├── models/                           # ORM models (unchanged)
│   ├── __init__.py
│   ├── users.py
│   ├── audio_transcription.py
│   ├── enums.py
│   └── monitoring.py
├── routers/                          # API routers (REFACTORED)
│   ├── __init__.py
│   ├── auth.py                       # Authentication endpoints
│   ├── stt.py                        # Speech-to-text endpoints (NEW - from tasks.py)
│   ├── translation.py                # Translation endpoints (NEW - from tasks.py)
│   ├── language.py                   # Language ID/classification (NEW - from tasks.py)
│   ├── summarization.py              # Summarization endpoints (NEW - from tasks.py)
│   ├── inference.py                  # Sunflower AI endpoints (NEW - from tasks.py)
│   ├── tts.py                        # TTS endpoints (existing + merged)
│   ├── webhooks.py                   # WhatsApp webhooks (NEW - from tasks.py)
│   ├── upload.py                     # File upload endpoints (NEW - from tasks.py)
│   └── frontend.py                   # Frontend routes (unchanged)
├── schemas/                          # Pydantic schemas (ENHANCED)
│   ├── __init__.py
│   ├── base.py                       # Common base schemas (NEW)
│   ├── users.py
│   ├── tasks.py                      # Will be split
│   ├── stt.py                        # STT-specific schemas (NEW)
│   ├── translation.py                # Translation schemas (NEW)
│   ├── language.py                   # Language schemas (NEW)
│   ├── summarization.py              # Summarization schemas (NEW)
│   ├── tts.py
│   ├── audio_transcription.py
│   ├── monitoring.py
│   └── errors.py
├── services/                         # Business logic layer (NEW)
│   ├── __init__.py
│   ├── base.py                       # Base service class (NEW)
│   ├── stt_service.py                # STT business logic (NEW)
│   ├── tts_service.py                # TTS business logic (MOVED from inference_services)
│   ├── translation_service.py        # Translation logic (NEW)
│   ├── language_service.py           # Language ID logic (NEW)
│   ├── summarization_service.py      # Summarization logic (NEW)
│   ├── inference_service.py          # Sunflower inference (MOVED)
│   ├── whatsapp_service.py           # WhatsApp logic (CONSOLIDATED)
│   └── storage_service.py            # GCP storage (MOVED from utils)
├── integrations/                     # External API integrations (NEW)
│   ├── __init__.py
│   ├── runpod.py                     # RunPod API client (MOVED)
│   ├── openai_client.py              # OpenAI integration (MOVED)
│   └── whatsapp_api.py               # WhatsApp API client (NEW)
├── utils/                            # Pure utility functions (SIMPLIFIED)
│   ├── __init__.py
│   ├── auth.py                       # Auth utilities (RENAMED)
│   ├── email.py                      # Email utilities (RENAMED)
│   ├── helpers.py                    # Generic helpers (RENAMED)
│   └── audio.py                      # Audio processing helpers (NEW)
├── tests/                            # Tests (EXPANDED)
│   ├── __init__.py
│   ├── conftest.py                   # Shared fixtures (NEW)
│   ├── test_auth.py
│   ├── test_stt.py                   # STT tests (NEW)
│   ├── test_tts.py                   # TTS tests (NEW)
│   ├── test_translation.py           # Translation tests (NEW)
│   ├── test_services/                # Service unit tests (NEW)
│   │   ├── __init__.py
│   │   └── ...
│   └── test_utils/                   # Utility tests (NEW)
│       ├── __init__.py
│       └── ...
├── static/
├── templates/
├── api.py                            # Main app entry point
├── deps.py                           # Dependencies (ENHANCED)
└── docs.py                           # API documentation
```

---

## Refactoring Steps

Each step is designed to be atomic and testable. Complete one step fully before moving to the next.

---

### Phase 1: Foundation Setup (Steps 1-3)

#### Step 1: Set Up Test Infrastructure
**Goal:** Create robust testing foundation before any refactoring

**Files to create:**
- `app/tests/conftest.py` - Shared pytest fixtures
- Update `app/tests/__init__.py`

**Tasks:**
1. Create `conftest.py` with:
   - Async test database fixture (SQLite in-memory)
   - Async client fixture
   - User creation fixture
   - Authentication fixture (get valid token)
   - Database session override
2. Move existing fixture code from `test_auth.py` to `conftest.py`
3. Update `test_auth.py` to use shared fixtures
4. Add basic smoke tests for app startup

**Tests to run:**
```bash
pytest app/tests/ -v
```

**Acceptance criteria:**
- All existing tests pass
- New fixtures work correctly
- App starts without errors

---

#### Step 2: Create Base Schemas and Exceptions
**Goal:** Establish common patterns for schemas and error handling

**Files to create:**
- `app/schemas/base.py` - Common response models
- `app/core/exceptions.py` - Custom exception classes

**Tasks:**
1. Create `base.py` with:
   - `BaseResponse` model with `success`, `message` fields
   - `PaginatedResponse` generic model
   - `ErrorResponse` model
2. Create `exceptions.py` with:
   - `APIException` base class
   - `NotFoundError`
   - `ValidationError`
   - `AuthenticationError`
   - `ExternalServiceError`
3. Add docstrings to all classes
4. Write unit tests for schema validation

**Tests to write:**
- `app/tests/test_schemas/test_base.py`
- `app/tests/test_core/test_exceptions.py`

**Tests to run:**
```bash
pytest app/tests/test_schemas/ app/tests/test_core/ -v
```

**Acceptance criteria:**
- Base schemas can be imported and validated
- Exceptions inherit properly and contain expected attributes
- All tests pass

---

#### Step 3: Create Service Layer Base
**Goal:** Establish service layer pattern

**Files to create:**
- `app/services/__init__.py`
- `app/services/base.py` - Base service class

**Tasks:**
1. Create `base.py` with:
   - `BaseService` abstract class
   - Common service methods (logging, error handling)
   - Type hints and docstrings
2. Define service interface pattern to be followed
3. Document service layer conventions

**Tests to write:**
- `app/tests/test_services/__init__.py`
- `app/tests/test_services/test_base.py`

**Tests to run:**
```bash
pytest app/tests/test_services/ -v
```

**Acceptance criteria:**
- Base service can be subclassed
- Service pattern is documented
- All tests pass

---

### Phase 2: Extract Services from Inference Services (Steps 4-7)

#### Step 4: Refactor TTS Service
**Goal:** Move and enhance TTS service with proper structure

**Files to modify/create:**
- Move `app/inference_services/tts.py` → `app/services/tts_service.py`
- Update imports in `app/routers/tts.py`
- Update `app/deps.py`

**Tasks:**
1. Copy `inference_services/tts.py` to `services/tts_service.py`
2. Make `TTSService` inherit from `BaseService`
3. Add comprehensive docstrings to all methods
4. Update imports in `routers/tts.py` to use new location
5. Update `deps.py` with new import path
6. Verify all TTS endpoints still work
7. Keep old file temporarily for backward compatibility

**Tests to write:**
- `app/tests/test_services/test_tts_service.py`

**Tests to run:**
```bash
pytest app/tests/ -v
# Manual test: Call TTS endpoints
```

**Acceptance criteria:**
- TTS endpoints return same responses as before
- Service has proper docstrings
- All tests pass

---

#### Step 5: Create Integrations Module
**Goal:** Separate external API clients from business logic

**Files to create:**
- `app/integrations/__init__.py`
- `app/integrations/runpod.py` - RunPod client
- `app/integrations/openai_client.py` - OpenAI client

**Tasks:**
1. Create `integrations/runpod.py`:
   - Move `runpod_helpers.py` content
   - Add docstrings
   - Rename file to follow convention
2. Create `integrations/openai_client.py`:
   - Extract OpenAI logic from `openai_script.py`
   - Add proper error handling
   - Add docstrings
3. Update imports in inference services
4. Write integration tests (mocked)

**Tests to write:**
- `app/tests/test_integrations/test_runpod.py`
- `app/tests/test_integrations/test_openai_client.py`

**Tests to run:**
```bash
pytest app/tests/test_integrations/ -v
pytest tests/test_runpod_helpers.py -v  # Existing tests should still pass
```

**Acceptance criteria:**
- RunPod functions work as before
- OpenAI client properly abstracted
- All existing tests pass

---

#### Step 6: Consolidate WhatsApp Services
**Goal:** Merge duplicate WhatsApp files into single service

**Files to modify/create:**
- Create `app/services/whatsapp_service.py`
- Create `app/integrations/whatsapp_api.py`
- Deprecate `app/inference_services/whatsapp_service.py`
- Deprecate `app/inference_services/whats_app_services.py`
- Rename `app/inference_services/OptimizedMessageProcessor.py` → integrate into service

**Tasks:**
1. Analyze both WhatsApp files to understand differences
2. Create `integrations/whatsapp_api.py` for API calls
3. Create `services/whatsapp_service.py` for business logic
4. Consolidate `OptimizedMessageProcessor` logic
5. Update all imports
6. Add docstrings
7. Remove deprecated files after verification

**Tests to write:**
- `app/tests/test_services/test_whatsapp_service.py`
- `app/tests/test_integrations/test_whatsapp_api.py`

**Tests to run:**
```bash
pytest app/tests/test_services/test_whatsapp_service.py -v
pytest app/tests/test_integrations/test_whatsapp_api.py -v
```

**Acceptance criteria:**
- WhatsApp functionality works as before
- Single source of truth for WhatsApp logic
- All tests pass

---

#### Step 7: Create Inference Service
**Goal:** Properly structure Sunflower/UG40 inference

**Files to modify/create:**
- Create `app/services/inference_service.py`
- Move logic from `app/inference_services/ug40_inference.py`

**Tasks:**
1. Create `services/inference_service.py`:
   - Inherit from `BaseService`
   - Move `UG40Inference` logic
   - Add docstrings
2. Update imports in routers
3. Deprecate old file

**Tests to write:**
- `app/tests/test_services/test_inference_service.py`

**Tests to run:**
```bash
pytest app/tests/test_services/test_inference_service.py -v
```

**Acceptance criteria:**
- Sunflower endpoints work as before
- Service has proper documentation
- All tests pass

---

### Phase 3: Split Tasks Router (Steps 8-14)

This is the most critical phase - the `tasks.py` router is 1850+ lines and needs to be split into focused modules.

#### Step 8: Create STT Router
**Goal:** Extract Speech-to-Text endpoints from tasks.py

**Files to create:**
- `app/routers/stt.py`
- `app/schemas/stt.py`
- `app/services/stt_service.py`

**Endpoints to move:**
- `POST /tasks/stt` - Audio file transcription
- `POST /tasks/stt_from_gcs` - GCS blob transcription
- `POST /tasks/org/stt` - Organization transcription

**Tasks:**
1. Create `schemas/stt.py` with STT-specific schemas
2. Create `services/stt_service.py` with STT business logic
3. Create `routers/stt.py` with endpoints
4. Add router to `api.py` with prefix `/tasks`
5. Remove endpoints from `tasks.py`
6. Add docstrings to all functions
7. Ensure backward compatibility (same URL paths)

**Tests to write:**
- `app/tests/test_routers/test_stt.py`
- `app/tests/test_services/test_stt_service.py`

**Tests to run:**
```bash
pytest app/tests/test_routers/test_stt.py -v
# Manual test: Call STT endpoints
```

**Acceptance criteria:**
- STT endpoints respond at same URLs
- Response format unchanged
- All tests pass

---

#### Step 9: Create Translation Router
**Goal:** Extract translation endpoints from tasks.py

**Files to create:**
- `app/routers/translation.py`
- `app/schemas/translation.py`
- `app/services/translation_service.py`

**Endpoints to move:**
- `POST /tasks/nllb_translate` - Text translation

**Tasks:**
1. Create `schemas/translation.py` with translation schemas (move from `tasks.py`)
2. Create `services/translation_service.py` with translation logic
3. Create `routers/translation.py` with endpoints
4. Add router to `api.py`
5. Remove endpoints from `tasks.py`
6. Add docstrings

**Tests to write:**
- `app/tests/test_routers/test_translation.py`
- `app/tests/test_services/test_translation_service.py`

**Tests to run:**
```bash
pytest app/tests/test_routers/test_translation.py -v
```

**Acceptance criteria:**
- Translation endpoint responds at same URL
- Response format unchanged
- All tests pass

---

#### Step 10: Create Language Router
**Goal:** Extract language identification endpoints from tasks.py

**Files to create:**
- `app/routers/language.py`
- `app/schemas/language.py`
- `app/services/language_service.py`

**Endpoints to move:**
- `POST /tasks/language_id` - Language identification
- `POST /tasks/classify_language` - Language classification
- `POST /tasks/auto_detect_audio_language` - Audio language detection

**Tasks:**
1. Create `schemas/language.py` with language schemas
2. Create `services/language_service.py` with language logic
3. Create `routers/language.py` with endpoints
4. Add router to `api.py`
5. Remove endpoints from `tasks.py`
6. Add docstrings

**Tests to write:**
- `app/tests/test_routers/test_language.py`
- `app/tests/test_services/test_language_service.py`

**Tests to run:**
```bash
pytest app/tests/test_routers/test_language.py -v
```

**Acceptance criteria:**
- Language endpoints respond at same URLs
- Response format unchanged
- All tests pass

---

#### Step 11: Create Summarization Router
**Goal:** Extract summarization endpoints from tasks.py

**Files to create:**
- `app/routers/summarization.py`
- `app/schemas/summarization.py`
- `app/services/summarization_service.py`

**Endpoints to move:**
- `POST /tasks/summarise` - Text summarization

**Tasks:**
1. Create `schemas/summarization.py` with summarization schemas
2. Create `services/summarization_service.py` with summarization logic
3. Create `routers/summarization.py` with endpoints
4. Add router to `api.py`
5. Remove endpoints from `tasks.py`
6. Add docstrings

**Tests to write:**
- `app/tests/test_routers/test_summarization.py`
- `app/tests/test_services/test_summarization_service.py`

**Tests to run:**
```bash
pytest app/tests/test_routers/test_summarization.py -v
```

**Acceptance criteria:**
- Summarization endpoint responds at same URL
- Response format unchanged
- All tests pass

---

#### Step 12: Create Inference Router (Sunflower)
**Goal:** Extract Sunflower AI endpoints from tasks.py

**Files to create:**
- `app/routers/inference.py`
- `app/schemas/inference.py`

**Endpoints to move:**
- `POST /tasks/sunflower_inference` - Chat completions
- `POST /tasks/sunflower_simple` - Simple chat

**Tasks:**
1. Create `schemas/inference.py` with inference schemas
2. Create `routers/inference.py` with endpoints
3. Wire to existing `services/inference_service.py`
4. Add router to `api.py`
5. Remove endpoints from `tasks.py`
6. Add docstrings

**Tests to write:**
- `app/tests/test_routers/test_inference.py`

**Tests to run:**
```bash
pytest app/tests/test_routers/test_inference.py -v
```

**Acceptance criteria:**
- Inference endpoints respond at same URLs
- Response format unchanged
- All tests pass

---

#### Step 13: Create Upload Router
**Goal:** Extract file upload endpoints from tasks.py

**Files to create:**
- `app/routers/upload.py`
- `app/schemas/upload.py`
- `app/services/storage_service.py`

**Endpoints to move:**
- `POST /tasks/generate-upload-url` - GCS signed URL generation

**Tasks:**
1. Move `utils/storage.py` → `services/storage_service.py`
2. Move `utils/upload_audio_file_gcp.py` logic into service
3. Create `schemas/upload.py` with upload schemas
4. Create `routers/upload.py` with endpoints
5. Add router to `api.py`
6. Remove endpoints from `tasks.py`
7. Add docstrings

**Tests to write:**
- `app/tests/test_routers/test_upload.py`
- `app/tests/test_services/test_storage_service.py`

**Tests to run:**
```bash
pytest app/tests/test_routers/test_upload.py -v
```

**Acceptance criteria:**
- Upload endpoints respond at same URLs
- Response format unchanged
- All tests pass

---

#### Step 14: Create Webhooks Router
**Goal:** Extract webhook endpoints from tasks.py

**Files to create:**
- `app/routers/webhooks.py`
- `app/schemas/webhooks.py`

**Endpoints to move:**
- `POST /tasks/webhook` - WhatsApp webhook handler
- `GET /tasks/webhook` - WhatsApp webhook verification

**Tasks:**
1. Create `schemas/webhooks.py` with webhook schemas
2. Create `routers/webhooks.py` with endpoints
3. Wire to `services/whatsapp_service.py`
4. Add router to `api.py`
5. Remove endpoints from `tasks.py`
6. Add docstrings
7. **Delete empty `tasks.py`** after all endpoints moved

**Tests to write:**
- `app/tests/test_routers/test_webhooks.py`

**Tests to run:**
```bash
pytest app/tests/test_routers/test_webhooks.py -v
```

**Acceptance criteria:**
- Webhook endpoints respond at same URLs
- Response format unchanged
- `tasks.py` is removed
- All tests pass

---

### Phase 4: Utilities Reorganization (Steps 15-16)

#### Step 15: Reorganize Utils Module
**Goal:** Clean up and rename utility files

**File renames:**
- `utils/auth_utils.py` → `utils/auth.py`
- `utils/email_utils.py` → `utils/email.py`
- `utils/helper_utils.py` → `utils/helpers.py`
- `utils/monitoring_utils.py` → Keep (used by frontend)
- `utils/exception_utils.py` → Merge into `core/exceptions.py`
- Remove `utils/storage.py` (moved to services)
- Remove `utils/upload_audio_file_gcp.py` (moved to services)

**Tasks:**
1. Rename files with updated imports
2. Merge exception utilities into `core/exceptions.py`
3. Update all imports across codebase
4. Add docstrings to all utility functions
5. Remove deprecated files

**Tests to write:**
- `app/tests/test_utils/test_auth.py`
- `app/tests/test_utils/test_email.py`
- `app/tests/test_utils/test_helpers.py`

**Tests to run:**
```bash
pytest app/tests/test_utils/ -v
pytest app/tests/ -v  # Full test suite
```

**Acceptance criteria:**
- All utilities properly renamed
- No broken imports
- All tests pass

---

#### Step 16: Create Audio Utils
**Goal:** Consolidate audio processing utilities

**Files to create:**
- `app/utils/audio.py`

**Tasks:**
1. Extract audio processing helpers from various files
2. Create centralized audio utility module
3. Add docstrings
4. Update imports

**Tests to write:**
- `app/tests/test_utils/test_audio.py`

**Tests to run:**
```bash
pytest app/tests/test_utils/test_audio.py -v
```

**Acceptance criteria:**
- Audio utilities centralized
- All tests pass

---

### Phase 5: Cleanup and Documentation (Steps 17-19)

#### Step 17: Clean Up Deprecated Files
**Goal:** Remove old inference_services folder

**Files to remove:**
- `app/inference_services/` entire folder (after all migrations complete)

**Tasks:**
1. Verify all functionality moved to `services/` and `integrations/`
2. Search for any remaining imports
3. Delete `inference_services/` folder
4. Run full test suite

**Tests to run:**
```bash
pytest -v  # Full test suite
```

**Acceptance criteria:**
- No references to `inference_services/`
- All tests pass
- App starts and runs correctly

---

#### Step 18: Update Dependencies Module
**Goal:** Enhance deps.py with new service dependencies

**Files to modify:**
- `app/deps.py`

**Tasks:**
1. Add dependency injection for all new services
2. Create type aliases for new services
3. Add docstrings
4. Ensure consistent pattern

**Tests to write:**
- `app/tests/test_deps.py`

**Tests to run:**
```bash
pytest app/tests/test_deps.py -v
```

**Acceptance criteria:**
- All services injectable via dependencies
- Consistent patterns
- All tests pass

---

#### Step 19: Final Documentation and Cleanup
**Goal:** Complete documentation and final verification

**Tasks:**
1. Verify all modules have `__init__.py` with proper exports
2. Ensure all public functions have docstrings
3. Update `docs.py` with new router documentation
4. Run linting and formatting
5. Run complete test suite
6. Manual API testing of all endpoints

**Commands to run:**
```bash
# Linting
black app/
isort app/
flake8 app/

# Tests
pytest -v --cov=app

# Manual verification
uvicorn app.api:app --reload
# Test all endpoints via Swagger UI
```

**Acceptance criteria:**
- All code formatted consistently
- All tests pass
- All endpoints functional
- Documentation complete

---

## Testing Strategy

### Test Categories

1. **Unit Tests** - Test individual functions/methods in isolation
2. **Integration Tests** - Test service interactions
3. **API Tests** - Test endpoint responses
4. **Regression Tests** - Ensure refactoring doesn't break existing functionality

### Test Structure

```
app/tests/
├── conftest.py                 # Shared fixtures
├── test_api.py                 # App startup tests
├── test_deps.py                # Dependency tests
├── test_core/
│   ├── test_config.py
│   └── test_exceptions.py
├── test_schemas/
│   ├── test_base.py
│   └── ...
├── test_services/
│   ├── test_tts_service.py
│   ├── test_stt_service.py
│   └── ...
├── test_integrations/
│   ├── test_runpod.py
│   └── ...
├── test_routers/
│   ├── test_auth.py
│   ├── test_stt.py
│   └── ...
└── test_utils/
    ├── test_auth.py
    └── ...
```

### Fixtures to Create (conftest.py)

```python
# Database fixtures
@pytest.fixture
async def db_session()

@pytest.fixture
async def test_db()

# Client fixtures
@pytest.fixture
async def async_client()

@pytest.fixture
async def authenticated_client()

# User fixtures
@pytest.fixture
async def test_user()

@pytest.fixture
async def admin_user()

# Service fixtures
@pytest.fixture
def mock_runpod_client()

@pytest.fixture
def mock_storage_service()
```

---

## Docstring Standards

All code must follow Google-style docstrings:

```python
def function_name(param1: str, param2: int) -> dict:
    """Short description of function.

    Longer description if needed, explaining the function's
    purpose and any important details.

    Args:
        param1: Description of param1.
        param2: Description of param2.

    Returns:
        Description of return value.

    Raises:
        ValueError: When param1 is empty.
        HTTPException: When authentication fails.

    Example:
        >>> result = function_name("test", 42)
        >>> print(result)
        {"status": "success"}
    """
```

---

## Risk Mitigation

1. **Backward Compatibility** - All API endpoints maintain same URL paths and response formats
2. **Incremental Changes** - Each step is atomic and can be reverted
3. **Test Coverage** - Tests written before and after each change
4. **Version Control** - Commit after each successful step
5. **Feature Flags** - Can temporarily keep old code paths if needed

---

## Timeline Estimate

| Phase | Steps | Description |
|-------|-------|-------------|
| Phase 1 | 1-3 | Foundation Setup |
| Phase 2 | 4-7 | Service Extraction |
| Phase 3 | 8-14 | Router Splitting |
| Phase 4 | 15-16 | Utils Reorganization |
| Phase 5 | 17-19 | Cleanup & Documentation |

---

## Checklist for Each Step

- [ ] Read and understand existing code
- [ ] Write tests for existing functionality (if not present)
- [ ] Make changes
- [ ] Add/update docstrings
- [ ] Run tests
- [ ] Verify no broken imports
- [ ] Commit changes
- [ ] Update this document with completion status

---

## Completion Tracking

| Step | Description | Status | Date |
|------|-------------|--------|------|
| 1 | Set Up Test Infrastructure | ✅ Complete | 2026-01-23 |
| 2 | Create Base Schemas and Exceptions | ✅ Complete | 2026-01-23 |
| 3 | Create Service Layer Base | ✅ Complete | 2026-01-23 |
| 4 | Refactor TTS Service | ✅ Complete | 2026-01-23 |
| 5 | Create Integrations Module | ✅ Complete | 2026-01-24 |
| 6 | Consolidate WhatsApp Services | ⬜ Pending | |
| 7 | Create Inference Service | ⬜ Pending | |
| 8 | Create STT Router | ⬜ Pending | |
| 9 | Create Translation Router | ⬜ Pending | |
| 10 | Create Language Router | ⬜ Pending | |
| 11 | Create Summarization Router | ⬜ Pending | |
| 12 | Create Inference Router | ⬜ Pending | |
| 13 | Create Upload Router | ⬜ Pending | |
| 14 | Create Webhooks Router | ⬜ Pending | |
| 15 | Reorganize Utils Module | ⬜ Pending | |
| 16 | Create Audio Utils | ⬜ Pending | |
| 17 | Clean Up Deprecated Files | ⬜ Pending | |
| 18 | Update Dependencies Module | ⬜ Pending | |
| 19 | Final Documentation and Cleanup | ⬜ Pending | |

---

## Notes

- Always run the full test suite after completing a step
- If a step fails, revert and analyze before proceeding
- Document any deviations from this plan
- Update imports immediately after moving files
- Keep the API running and test manually during development

---

## Known Issues Discovered

### Bug: ValidationErrorDetail.input type mismatch (Found in Step 1) - ✅ RESOLVED
**Location:** `app/schemas/errors.py` and `app/utils/exception_utils.py`
**Issue:** The `ValidationErrorDetail.input` field is typed as `Optional[str]` but the actual input from Pydantic validation errors is a `dict`.
**Impact:** Custom validation error handler crashes when validation errors occur with body data.
**Fix:** Updated `ValidationErrorDetail.input` to accept `Optional[Any]` type instead of `Optional[str]`.
**Resolved:** Step 2 (2026-01-23)
