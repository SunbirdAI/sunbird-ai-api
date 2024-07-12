import logging
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()
logging.basicConfig(level=logging.INFO)
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Modify the DATABASE_URL if it starts with 'postgres://'
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
logging.info(f"DATABASE_URL: {DATABASE_URL}")

if ENVIRONMENT == "production":
    engine = create_engine(
        DATABASE_URL,
        echo=True,
        echo_pool=True,
        pool_size=20,
        max_overflow=10,
        pool_recycle=1800,
        connect_args={"sslmode": "require"},
    )
else:
    engine = create_engine(DATABASE_URL, echo=True, pool_size=20, max_overflow=0)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
