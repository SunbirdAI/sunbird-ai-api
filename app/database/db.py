"""
Database Configuration Module.

This module configures the async SQLAlchemy engine and session factory
using settings from the centralized configuration system.

Architecture:
    - Uses async SQLAlchemy with asyncpg driver for PostgreSQL
    - Supports SQLite for development/testing
    - Connection pooling with environment-specific settings
    - SSL support for production databases

Usage:
    from app.database.db import engine, async_session_maker, Base

    # Get a database session
    async with async_session_maker() as session:
        result = await session.execute(query)

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
"""

import logging
import ssl
from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_ssl_context() -> ssl.SSLContext:
    """
    Create an SSL context for database connections.

    Creates a default SSL context with hostname checking and certificate
    verification disabled. This is commonly required for cloud database
    providers like Heroku Postgres.

    Returns:
        ssl.SSLContext: A configured SSL context.

    Security Note:
        This disables SSL verification for compatibility with cloud providers.
        Consider enabling proper certificate verification in high-security environments.
    """
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def get_engine_args(url: str) -> Dict[str, Any]:
    """
    Build SQLAlchemy engine arguments based on database type and environment.

    Configures connection pooling, SSL, and other database-specific settings
    using values from the centralized configuration system.

    Args:
        url: The database connection URL.

    Returns:
        Dictionary of engine configuration arguments.

    Configuration:
        - SQLite: Disables same-thread check for async compatibility
        - PostgreSQL/Other:
            * Connection pooling with configurable pool size and overflow
            * Pool recycling to prevent stale connections
            * SSL in production (if enabled)
            * Query logging based on environment

    Examples:
        >>> args = get_engine_args("postgresql+asyncpg://user:pass@host/db")
        >>> engine = create_async_engine(url, **args)
    """
    # Base configuration
    args = {
        "echo": settings.effective_db_echo,
    }

    # SQLite-specific configuration
    if url.startswith("sqlite"):
        args["connect_args"] = {"check_same_thread": False}
        logger.info("Configured SQLite database engine")
        return args

    # PostgreSQL/MySQL configuration with connection pooling
    args.update(
        {
            "pool_recycle": settings.db_pool_recycle,
            "pool_size": settings.effective_db_pool_size,
            "max_overflow": settings.effective_db_max_overflow,
            "pool_pre_ping": True,  # Enable connection health checks
        }
    )

    # SSL configuration for production
    if settings.is_production and settings.db_ssl_enabled:
        args["connect_args"] = {"ssl": create_ssl_context()}
        logger.info("Configured database engine with SSL enabled")
    else:
        logger.info(
            f"Configured database engine without SSL "
            f"(production={settings.is_production}, ssl_enabled={settings.db_ssl_enabled})"
        )

    return args


# Get database URL from centralized settings
database_url = settings.database_url_async

# Build engine configuration
engine_args = get_engine_args(database_url)

# Create async engine
engine = create_async_engine(database_url, **engine_args)

logger.info(
    f"Database engine created: "
    f"environment={settings.environment}, "
    f"pool_size={settings.effective_db_pool_size}, "
    f"max_overflow={settings.effective_db_max_overflow}"
)

# Create async session factory
async_session_maker = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)

# Create declarative base for ORM models
Base = declarative_base()

# Module exports
__all__ = [
    "engine",
    "async_session_maker",
    "Base",
]
