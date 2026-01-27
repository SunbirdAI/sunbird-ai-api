"""
Monitoring Middleware Module.

This module provides middleware for logging and monitoring API endpoint usage.
It tracks authenticated requests to task endpoints, recording user information,
endpoint paths, and request duration for analytics and usage monitoring.

Architecture:
    Request -> Monitoring Middleware -> Route Handler -> Response
    Middleware logs: username, endpoint, organization, execution time

Usage:
    from app.middleware.monitoring_middleware import MonitoringMiddleware

    # In FastAPI app setup
    app.add_middleware(MonitoringMiddleware)

    # Or as a function-based middleware
    from app.middleware.monitoring_middleware import log_request
    app.middleware("http")(log_request)

Monitoring Features:
    - Automatic request/response timing
    - User authentication extraction from JWT tokens
    - Organization tracking for enterprise analytics
    - Selective monitoring (only /tasks/* endpoints)
    - Graceful error handling (logs but doesn't break requests)
    - Async database logging for performance

Security:
    - Token validation happens at the route level
    - This middleware only logs authenticated requests
    - Failed authentication is logged but doesn't block the request
    - Middleware doesn't enforce authentication (handled by route dependencies)
"""

import logging
import time
from typing import Callable, Optional

from fastapi import Request, Response
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.exceptions import AuthenticationError
from app.crud.monitoring import log_endpoint
from app.crud.users import get_user_by_username
from app.database.db import async_session_maker
from app.utils.auth import ALGORITHM, SECRET_KEY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MonitoringMiddleware(BaseHTTPMiddleware):
    """
    Middleware for monitoring and logging API endpoint usage.

    This middleware intercepts requests to task endpoints (/tasks/*) and logs
    usage information including the authenticated user, endpoint path, organization,
    and request duration. Monitoring data is stored asynchronously in the database.

    The middleware only monitors authenticated requests to /tasks/* endpoints.
    Other endpoints are passed through without monitoring. If authentication
    extraction fails, the request continues normally (authentication is enforced
    at the route level via dependencies).

    Attributes:
        monitor_path_prefix: URL path prefix to monitor (default: "/tasks")

    Example:
        >>> app = FastAPI()
        >>> app.add_middleware(MonitoringMiddleware)
        >>> # All /tasks/* endpoints will now be monitored
    """

    def __init__(self, app, monitor_path_prefix: str = "/tasks"):
        """
        Initialize the monitoring middleware.

        Args:
            app: The FastAPI application instance.
            monitor_path_prefix: URL path prefix to monitor (default: "/tasks").
        """
        super().__init__(app)
        self.monitor_path_prefix = monitor_path_prefix

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process the request and log monitoring data.

        This method intercepts requests to monitored endpoints, extracts user
        information from JWT tokens, times the request, and logs the data
        asynchronously to the database.

        Args:
            request: The incoming HTTP request.
            call_next: The next middleware or route handler in the chain.

        Returns:
            Response: The HTTP response from the route handler.

        Notes:
            - Only monitors requests starting with the configured path prefix
            - Extracts user info from Authorization header (Bearer token)
            - Logs errors but allows requests to proceed even if monitoring fails
            - Uses async database sessions for non-blocking logging
        """
        # Only monitor specified endpoints (e.g., /tasks/*)
        if not request.url.path.startswith(self.monitor_path_prefix):
            return await call_next(request)

        # Extract user information from token
        user_info = await self._extract_user_info(request)

        # Time the request
        start_time = time.time()
        response = await call_next(request)
        end_time = time.time()

        # Log monitoring data if user was successfully extracted
        if user_info:
            await self._log_request_data(
                username=user_info["username"],
                organization=user_info["organization"],
                endpoint=request.url.path,
                start_time=start_time,
                end_time=end_time,
            )

        return response

    async def _extract_user_info(self, request: Request) -> Optional[dict]:
        """
        Extract user information from the request's JWT token.

        Parses the Authorization header, validates the JWT token, and retrieves
        the user's information from the database.

        Args:
            request: The incoming HTTP request.

        Returns:
            Optional[dict]: Dictionary with 'username' and 'organization' keys,
                          or None if extraction fails.

        Notes:
            - Logs errors but returns None instead of raising exceptions
            - This allows the request to continue even if monitoring fails
            - Actual authentication is enforced at the route level
        """
        try:
            # Extract token from Authorization header
            auth_header = request.headers.get("Authorization")
            if not auth_header:
                logger.debug("No Authorization header found for monitoring")
                return None

            # Parse Bearer token
            parts = auth_header.split()
            if len(parts) != 2 or parts[0].lower() != "bearer":
                logger.warning(f"Invalid Authorization header format: {auth_header}")
                return None

            token = parts[1]

            # Decode JWT token
            try:
                payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            except JWTError as e:
                logger.debug(f"JWT decode error (expected for invalid tokens): {e}")
                return None

            username = payload.get("sub")
            if not username:
                logger.warning("JWT token missing 'sub' claim")
                return None

            # Fetch user from database
            async with async_session_maker() as db:
                user = await get_user_by_username(db, username)
                if not user:
                    logger.warning(f"User not found in database: {username}")
                    return None

                return {
                    "username": user.username,
                    "organization": user.organization,
                }

        except Exception as e:
            logger.error(f"Unexpected error extracting user info: {e}", exc_info=True)
            return None

    async def _log_request_data(
        self,
        username: str,
        organization: Optional[str],
        endpoint: str,
        start_time: float,
        end_time: float,
    ) -> None:
        """
        Log request monitoring data to the database.

        Creates an endpoint log entry with user information, endpoint path,
        organization, and request duration.

        Args:
            username: The authenticated username.
            organization: The user's organization (optional).
            endpoint: The API endpoint path.
            start_time: Request start timestamp.
            end_time: Request end timestamp.

        Notes:
            - Uses async database session for non-blocking operation
            - Logs errors but doesn't raise exceptions to avoid breaking requests
            - Session is automatically committed and closed via context manager
        """
        try:
            async with async_session_maker() as db:
                # Use the CRUD helper to create the log entry
                from app.models.users import User

                # Create a minimal user object for logging
                user = User(username=username, organization=organization)

                await log_endpoint(
                    db=db,
                    user=user,
                    request=None,  # Not used by log_endpoint
                    start_time=start_time,
                    end_time=end_time,
                )

                logger.info(
                    f"Logged request: user={username}, endpoint={endpoint}, "
                    f"duration={end_time - start_time:.3f}s"
                )

        except Exception as e:
            logger.error(f"Failed to log endpoint usage: {e}", exc_info=True)


async def log_request(request: Request, call_next: Callable) -> Response:
    """
    Function-based monitoring middleware for logging API endpoint usage.

    This is an alternative to the class-based MonitoringMiddleware. It provides
    the same functionality but can be used as a function-based middleware.

    The middleware monitors requests to /tasks/* endpoints, extracting user
    information from JWT tokens and logging request duration and metadata
    to the database for analytics.

    Args:
        request: The incoming HTTP request.
        call_next: The next middleware or route handler in the chain.

    Returns:
        Response: The HTTP response from the route handler.

    Example:
        >>> from functools import partial
        >>> app = FastAPI()
        >>> logging_middleware = partial(log_request)
        >>> app.middleware("http")(logging_middleware)

    Notes:
        - Only monitors requests starting with "/tasks"
        - Extracts user from Authorization Bearer token
        - Gracefully handles errors (logs but doesn't block requests)
        - Uses async database sessions for non-blocking logging
        - Authentication is enforced at route level, not here
    """
    # Only monitor task endpoints
    if not request.url.path.startswith("/tasks"):
        return await call_next(request)

    username: Optional[str] = None
    organization: Optional[str] = None

    try:
        # Extract user information from Authorization header
        auth_header = request.headers.get("Authorization")
        if auth_header:
            parts = auth_header.split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                token = parts[1]

                try:
                    # Decode JWT token
                    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
                    username = payload.get("sub")

                    if username:
                        # Fetch user from database
                        async with async_session_maker() as db:
                            user = await get_user_by_username(db, username)
                            if user:
                                organization = user.organization
                            else:
                                logger.debug(f"User not found: {username}")
                                username = None

                except JWTError as e:
                    logger.debug(f"JWT decode error: {e}")
                except Exception as e:
                    logger.error(f"Error fetching user: {e}")

    except Exception as e:
        logger.error(f"Error extracting authentication info: {e}")

    # Time the request
    start_time = time.time()
    response = await call_next(request)
    end_time = time.time()

    # Log endpoint usage if user was successfully authenticated
    if username:
        try:
            async with async_session_maker() as db:
                from app.models.users import User

                # Create minimal user object for logging
                user = User(username=username, organization=organization)

                await log_endpoint(
                    db=db,
                    user=user,
                    request=request,
                    start_time=start_time,
                    end_time=end_time,
                )

                logger.info(
                    f"Logged request: user={username}, endpoint={request.url.path}, "
                    f"duration={end_time - start_time:.3f}s"
                )

        except Exception as e:
            logger.error(f"Failed to log endpoint usage: {e}")

    return response


__all__ = [
    "MonitoringMiddleware",
    "log_request",
]
