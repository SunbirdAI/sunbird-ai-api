from logging.config import fileConfig
import os

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Alembic Config object
config = context.config

# Update DATABASE_URL if needed and set it in Alembic config
DATABASE_URL = os.getenv('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql+asyncpg://', 1)

config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Set up Python logging based on alembic.ini configuration
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import and set up metadata from models
from app.database import db
from app.models.users import User
from app.models.monitoring import EndpointLog
from app.models.audio_transcription import AudioTranscription
target_metadata = db.Base.metadata

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

async def run_migrations_online() -> None:
    """Run migrations in 'online' mode using AsyncEngine."""
    connectable = create_async_engine(
        DATABASE_URL,
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

def do_run_migrations(connection):
    """Helper function to run migrations with a connection."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    # Use asyncio to run the async migrations
    import asyncio
    asyncio.run(run_migrations_online())
