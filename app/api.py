from fastapi import FastAPI, Request
from functools import partial
from app.routers.tasks import router as tasks_router
from app.routers.auth import router as auth_router
from app.routers.frontend import router as frontend_router
from app.middleware.monitoring_middleware import log_request
from app.docs import description, tags_metadata
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles


app = FastAPI(
    title="Sunbird AI API",
    description=description,
    openapi_tags=tags_metadata
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

logging_middleware = partial(log_request)
app.middleware("http")(logging_middleware)

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


app.include_router(tasks_router, prefix="/tasks", tags=["AI Tasks"])
app.include_router(auth_router, prefix="/auth", tags=["Authentication Endpoints"])
app.include_router(frontend_router, prefix="", tags=["Frontend Routes"])
