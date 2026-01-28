"""
Middleware Module.

This module provides middleware components for the Sunbird AI API,
including request monitoring, logging, and analytics tracking.

Available Middleware:
    - MonitoringMiddleware: Class-based middleware for endpoint monitoring
    - log_request: Function-based middleware for endpoint monitoring

Usage:
    from app.middleware import MonitoringMiddleware, log_request

    # Class-based usage
    app.add_middleware(MonitoringMiddleware)

    # Function-based usage
    app.middleware("http")(log_request)
"""

from app.middleware.monitoring_middleware import MonitoringMiddleware, log_request

__all__ = [
    "MonitoringMiddleware",
    "log_request",
]
