# Middleware Documentation

This directory contains middleware components for the Sunbird AI API.

## Overview

Middleware components intercept and process requests/responses before they reach route handlers. They provide cross-cutting concerns like monitoring, authentication, rate limiting, and CORS handling.

## Available Middleware

### MonitoringMiddleware

**Location**: `app/middleware/monitoring_middleware.py`

**Purpose**: Automatically logs endpoint usage for analytics and monitoring.

**How It Works**:
- Intercepts all requests to `/tasks/*` endpoints
- Extracts user information from JWT tokens in the Authorization header
- Records: username, organization, endpoint path, and request duration
- Stores logs asynchronously in the database
- Gracefully handles errors without breaking requests

**Usage**:
```python
from app.middleware import MonitoringMiddleware

# In app/api.py
app.add_middleware(MonitoringMiddleware)
```

**Configuration**:
```python
# Custom path prefix (default: "/tasks")
app.add_middleware(MonitoringMiddleware, monitor_path_prefix="/api")
```

**Features**:
- ✅ Automatic monitoring - no router configuration needed
- ✅ Async database logging for performance
- ✅ Graceful error handling
- ✅ JWT token extraction and validation
- ✅ Organization tracking for enterprise analytics
- ✅ Request timing with millisecond precision

**Logged Data**:
```python
{
    "username": "john.doe",
    "organization": "Acme Corp",
    "endpoint": "/tasks/translate",
    "time_taken": 0.234  # seconds
}
```

**Integration with Routers**:

The monitoring middleware works **transparently** with all routers. No special configuration is needed in route handlers. Simply ensure routes:
1. Start with `/tasks/` prefix
2. Use authentication dependencies (`get_current_user`)
3. Include valid JWT tokens in requests

Example router endpoint (no changes needed):
```python
@router.post("/translate")
async def translate_text(
    request: TranslationRequest,
    service: TranslationServiceDep,
    current_user: User = Depends(get_current_user),  # ← Monitoring extracts user from this
):
    # Your route logic here
    return await service.translate(...)
```

The middleware automatically:
1. Detects the `/tasks/translate` path
2. Extracts the JWT token from the Authorization header
3. Validates the token and retrieves user info
4. Times the request
5. Logs all data to the database

## Middleware Execution Order

**IMPORTANT**: Middleware executes in **LIFO (Last In, First Out)** order.

The middleware added **last** executes **first** on incoming requests:

```python
# In app/api.py

# Added first, executes last (closest to route handler)
app.add_middleware(LargeUploadMiddleware)
app.add_middleware(SessionMiddleware)
app.add_middleware(MonitoringMiddleware)
app.add_middleware(CORSMiddleware)
app.add_middleware(SlowAPIMiddleware)  # Added last, executes first
```

**Request Flow** (outer → inner):
```
Incoming Request
    ↓
1. SlowAPIMiddleware (rate limiting)
    ↓
2. CORSMiddleware (CORS headers)
    ↓
3. MonitoringMiddleware (log start time)
    ↓
4. SessionMiddleware (session management)
    ↓
5. LargeUploadMiddleware (file size check)
    ↓
Route Handler (your endpoint)
```

**Response Flow** (inner → outer):
```
Route Handler (your response)
    ↓
5. LargeUploadMiddleware
    ↓
4. SessionMiddleware
    ↓
3. MonitoringMiddleware (log end time, save to DB)
    ↓
2. CORSMiddleware (add CORS headers)
    ↓
1. SlowAPIMiddleware
    ↓
Outgoing Response
```

### Why This Order?

1. **Rate Limiting First** (SlowAPIMiddleware)
   - Reject excessive requests before any processing
   - Protect the API from abuse

2. **CORS Second** (CORSMiddleware)
   - Add CORS headers to all responses
   - Handle preflight requests early

3. **Monitoring Third** (MonitoringMiddleware)
   - Log authenticated requests after rate limiting
   - Track actual usage, not rate-limited requests

4. **Session Fourth** (SessionMiddleware)
   - Manage user sessions
   - Used by authentication dependencies

5. **Upload Size Last** (LargeUploadMiddleware)
   - Closest to route handler
   - Validate file size before processing

## Monitoring Middleware Details

### Database Schema

The monitoring middleware logs to the `endpoint_logs` table:

```sql
CREATE TABLE endpoint_logs (
    id SERIAL PRIMARY KEY,
    username VARCHAR NOT NULL,
    endpoint VARCHAR NOT NULL,
    organization VARCHAR,
    time_taken FLOAT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Performance Considerations

- **Async Logging**: Database writes are asynchronous and don't block requests
- **Error Handling**: Monitoring failures don't affect route responses
- **Minimal Overhead**: Only monitors authenticated `/tasks/*` endpoints
- **Connection Pooling**: Uses SQLAlchemy async connection pool

### Security

- **No Authentication Enforcement**: Middleware only logs; authentication is enforced by route dependencies
- **Token Validation**: JWT tokens are validated but errors are logged, not raised
- **Graceful Degradation**: If monitoring fails, the request continues normally
- **Privacy**: Only logs username, organization, endpoint, and timing (no request/response data)

### Debugging

Enable debug logging to see monitoring details:

```python
import logging
logging.getLogger("app.middleware.monitoring_middleware").setLevel(logging.DEBUG)
```

Debug logs include:
- Token extraction attempts
- User lookup results
- Database logging operations
- Error tracebacks

### Testing

The monitoring middleware is tested indirectly through router tests:

```python
# All router tests automatically exercise the monitoring middleware
async def test_endpoint(async_client, test_user):
    response = await async_client.post(
        "/tasks/translate",
        json={"text": "Hello"},
        headers={"Authorization": f"Bearer {test_user['token']}"}
    )
    # ↑ This request is automatically monitored and logged
```

### Querying Logs

Use the CRUD functions to query endpoint logs:

```python
from app.crud.monitoring import get_logs_by_username

# Get all logs for a user
async with async_session_maker() as db:
    logs = await get_logs_by_username(db, "john.doe")

    for log in logs:
        print(f"{log.endpoint}: {log.time_taken}s")
```

## Adding New Middleware

To add new middleware:

1. **Create the middleware file** in `app/middleware/`
2. **Implement as class or function**:
   ```python
   # Class-based
   class MyMiddleware(BaseHTTPMiddleware):
       async def dispatch(self, request, call_next):
           # Before request
           response = await call_next(request)
           # After request
           return response

   # Function-based
   async def my_middleware(request, call_next):
       # Before request
       response = await call_next(request)
       # After request
       return response
   ```

3. **Export in `__init__.py`**:
   ```python
   from app.middleware.my_middleware import MyMiddleware

   __all__ = ["MyMiddleware", ...]
   ```

4. **Register in `app/api.py`**:
   ```python
   from app.middleware import MyMiddleware

   app.add_middleware(MyMiddleware)
   ```

5. **Document execution order** in `app/api.py` comments

## Best Practices

1. **Keep middleware lightweight** - they execute on every request
2. **Handle errors gracefully** - don't break requests due to middleware failures
3. **Use async operations** - especially for I/O (database, external APIs)
4. **Log appropriately** - debug for expected failures, error for unexpected ones
5. **Consider order carefully** - middleware order affects functionality
6. **Document behavior** - explain what the middleware does and when it executes
7. **Test thoroughly** - middleware can affect all endpoints

## Resources

- [FastAPI Middleware Documentation](https://fastapi.tiangolo.com/tutorial/middleware/)
- [Starlette Middleware](https://www.starlette.io/middleware/)
- [Custom Exception Handlers](https://fastapi.tiangolo.com/tutorial/handling-errors/)
