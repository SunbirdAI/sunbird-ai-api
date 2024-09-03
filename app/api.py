import logging
import os
from contextlib import asynccontextmanager
from functools import partial
from pathlib import Path
from urllib.parse import urlparse

import redis.asyncio as redis
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi_limiter import FastAPILimiter
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from tenacity import RetryError, retry, stop_after_attempt, wait_exponential

from app.docs import description, tags_metadata
from app.middleware.monitoring_middleware import log_request
from app.routers.auth import router as auth_router
from app.routers.frontend import router as frontend_router
from app.routers.tasks import router as tasks_router
from app.utils.exception_utils import validation_exception_handler

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=1, max=5))
async def init_redis():
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        raise ValueError("REDIS_URL environment variable not set")

    logger.info(f"Attempting to connect to Redis at {redis_url}")

    if ENVIRONMENT == "production":
        url = urlparse(os.environ.get("REDIS_URL"))
        redis_instance = redis.Redis(
            host=url.hostname,
            port=url.port,
            password=url.password,
            ssl=True,
            ssl_cert_reqs=None,
        )
    else:
        redis_instance = redis.from_url(
            os.getenv("REDIS_URL"),
            encoding="utf-8",
            decode_responses=True,
            max_connections=10,
        )
    await redis_instance.ping()
    logger.info("Connected to Redis successfully")
    return redis_instance


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        logger.info("Application startup event")
        redis_instance = await init_redis()
        await FastAPILimiter.init(redis_instance)
        logger.info("FastAPILimiter initialized successfully")
        yield
    except RetryError as e:
        logger.error(f"Failed to connect to Redis: {e}")
        yield
    except ValueError as e:
        logger.error(f"Failed to connect to Redis: {e}")
        yield
    except Exception as e:
        logger.error(f"Error during startup: {str(e)}")
        yield


app = FastAPI(
    title="Sunbird AI API",
    description=description,
    openapi_tags=tags_metadata,
    lifespan=lifespan,
)


static_files_directory = Path(__file__).parent.absolute() / "static"
app.mount("/static", StaticFiles(directory=static_files_directory), name="static")

# logging_middleware = partial(log_request)
# app.middleware("http")(logging_middleware)

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize the Limiter
limiter = Limiter(key_func=get_remote_address)

# Add middleware and exception handler for rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
# Register the custom request validation exception handler
app.add_exception_handler(RequestValidationError, validation_exception_handler)


app.include_router(tasks_router, prefix="/tasks", tags=["AI Tasks"])
app.include_router(auth_router, prefix="/auth", tags=["Authentication Endpoints"])
app.include_router(frontend_router, prefix="", tags=["Frontend Routes"])
