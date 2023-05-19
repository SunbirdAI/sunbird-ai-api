from fastapi import FastAPI, Request
from functools import partial
from app.routers.tasks import router as tasks_router
from app.routers.auth import router as auth_router
from app.middleware.monitoring_middleware import log_request
from app.docs import description, tags_metadata


app = FastAPI(
    title="Sunbird AI API",
    description=description,
    openapi_tags=tags_metadata
)

logging_middleware = partial(log_request)
app.middleware("http")(logging_middleware)

app.include_router(tasks_router, prefix="/tasks", tags=["AI Tasks"])
app.include_router(auth_router, prefix="/auth", tags=["Authentication Endpoints"])
