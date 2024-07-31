import logging
import os
import ssl
from typing import Any, Dict

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

# Load environment variables and configure logging
load_dotenv()
logging.basicConfig(level=logging.INFO)

# Constants
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
DATABASE_URL = os.getenv("DATABASE_URL")


def create_ssl_context() -> ssl.SSLContext:
    """
    Create a default SSL context with hostname checking and verification disabled.

    Returns:
        ssl.SSLContext: A configured SSL context.
    """
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def get_database_url() -> str:
    """
    Get and potentially modify the database URL.

    This function checks if the DATABASE_URL starts with 'postgres://' and
    replaces it with 'postgresql+asyncpg://' if so.

    Returns:
        str: The potentially modified database URL.
    """
    if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
        return DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
    return DATABASE_URL


def get_engine_args(url: str) -> Dict[str, Any]:
    """
    Get the appropriate engine arguments based on the database type and environment.

    Args:
        url (str): The database URL.

    Returns:
        Dict[str, Any]: A dictionary of engine arguments.
    """
    args = {"echo": ENVIRONMENT != "production"}

    if url.startswith("sqlite"):
        args["connect_args"] = {"check_same_thread": False}
    else:
        args.update(
            {
                "pool_recycle": 600,
                "pool_size": 20 if ENVIRONMENT == "production" else 50,
                "max_overflow": 10 if ENVIRONMENT == "production" else 0,
            }
        )
        if ENVIRONMENT == "production":
            args["connect_args"] = {"ssl": create_ssl_context()}

    return args


# Create the database engine
url = get_database_url()
engine_args = get_engine_args(url)
engine = create_async_engine(url, **engine_args)

# Create async session maker
async_session_maker = async_sessionmaker(
    bind=engine, expire_on_commit=False, class_=AsyncSession
)

# Create declarative base
Base = declarative_base()
