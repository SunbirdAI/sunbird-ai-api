import logging
import os
import ssl

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

load_dotenv()
logging.basicConfig(level=logging.INFO)
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# Modify the DATABASE_URL if it starts with 'postgres://'
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
logging.info(f"DATABASE_URL: {DATABASE_URL}")

if ENVIRONMENT == "production":
    engine = create_async_engine(
        DATABASE_URL,
        echo=True,
        pool_size=20,
        max_overflow=10,
        pool_recycle=600,
        # connect_args={"sslmode": "require"},
        connect_args={"ssl": ssl_context},
    )
else:
    engine = create_async_engine(
        DATABASE_URL, echo=True, pool_size=50, max_overflow=0, pool_recycle=600
    )

# Using async_sessionmaker for async sessions
async_session_maker = async_sessionmaker(
    bind=engine, expire_on_commit=False, class_=AsyncSession
)

Base = declarative_base()
