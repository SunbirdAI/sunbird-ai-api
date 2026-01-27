# Database Configuration

This directory contains the database configuration and models for the Sunbird AI API.

## Overview

The database configuration uses:
- **SQLAlchemy** with async support (asyncpg driver for PostgreSQL)
- **Centralized configuration** via `app/core/config.py`
- **Environment-aware settings** (development, staging, production)
- **Connection pooling** with configurable parameters
- **SSL support** for production databases

## Configuration

All database settings are managed through environment variables in your `.env` file:

### Required Settings

```bash
# Database connection URL
DATABASE_URL=postgresql://user:password@localhost:5432/dbname

# Application environment
ENVIRONMENT=development  # Options: development, staging, production
```

### Optional Settings

```bash
# Database query logging (disabled in production automatically)
DB_ECHO=false

# Connection pool settings
DB_POOL_SIZE=50              # Default pool size (20 in production)
DB_MAX_OVERFLOW=0            # Max overflow connections (10 in production)
DB_POOL_RECYCLE=600          # Recycle connections after 600 seconds

# SSL settings
DB_SSL_ENABLED=true          # Enable SSL in production (default: false)
```

## Database URL Formats

### PostgreSQL (Recommended for Production)
```bash
# Async PostgreSQL with asyncpg driver
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/dbname

# Standard postgres:// URL (automatically converted to asyncpg)
DATABASE_URL=postgres://user:password@localhost:5432/dbname
```

### SQLite (Development/Testing)
```bash
# Async SQLite
DATABASE_URL=sqlite+aiosqlite:///./test.db
```

### Heroku Postgres
```bash
# Heroku provides postgres:// URL - will be auto-converted
DATABASE_URL=postgres://user:password@host:5432/dbname?sslmode=require
```

## Environment-Specific Behavior

### Development
- Query logging enabled (if `DB_ECHO=true`)
- Larger connection pool (50 connections)
- No connection overflow
- SSL disabled by default

### Production
- Query logging always disabled (for performance)
- Smaller connection pool (20 connections)
- Connection overflow enabled (10 extra connections)
- SSL enabled if `DB_SSL_ENABLED=true`
- Connection health checks enabled (`pool_pre_ping`)

## Usage Examples

### Basic Session Usage

```python
from app.database.db import async_session_maker

async def get_users():
    async with async_session_maker() as session:
        result = await session.execute(select(User))
        return result.scalars().all()
```

### Dependency Injection in FastAPI

```python
from app.deps import get_db
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

@router.get("/users")
async def list_users(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User))
    return result.scalars().all()
```

### Creating Tables

```python
from app.database.db import engine, Base

async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

### Running Migrations

Use Alembic for database migrations:

```bash
# Create a new migration
alembic revision --autogenerate -m "Add new table"

# Apply migrations
alembic upgrade head

# Rollback one version
alembic downgrade -1
```

## Connection Pooling

The application uses SQLAlchemy's connection pooling:

- **Pool Size**: Number of connections kept open
- **Max Overflow**: Additional connections created when pool is exhausted
- **Pool Recycle**: Time (seconds) before recycling a connection
- **Pool Pre-Ping**: Health check before using a connection

### Monitoring Pool Usage

```python
from app.database.db import engine

# Get pool status
pool = engine.pool
print(f"Pool size: {pool.size()}")
print(f"Checked out: {pool.checkedout()}")
print(f"Overflow: {pool.overflow()}")
```

## SSL Configuration

For production databases (especially cloud providers):

```bash
# Enable SSL
DB_SSL_ENABLED=true
ENVIRONMENT=production
```

The SSL context is configured to work with cloud database providers (Heroku, AWS RDS, etc.) that may use self-signed certificates.

**Security Note**: The current SSL implementation disables certificate verification for compatibility. For high-security environments, consider implementing proper certificate verification.

## Troubleshooting

### Connection Issues

```python
# Test database connection
from app.database.db import engine

async def test_connection():
    try:
        async with engine.connect() as conn:
            print("✅ Database connection successful")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
```

### Pool Exhaustion

If you see "QueuePool limit exceeded" errors:
1. Increase `DB_POOL_SIZE`
2. Increase `DB_MAX_OVERFLOW`
3. Check for connection leaks (always close sessions)

### SSL Errors

If SSL connection fails:
1. Verify `DB_SSL_ENABLED=true` in production
2. Check database provider supports SSL
3. Ensure firewall allows SSL connections

## Best Practices

1. **Always use async sessions**: Use `async with async_session_maker()` for proper cleanup
2. **Close sessions properly**: Let context manager handle cleanup
3. **Use connection pooling**: Don't create new engines
4. **Environment variables**: Never commit `.env` files
5. **Migration discipline**: Always test migrations before production
6. **Monitor connections**: Track pool usage in production

## Migration from Old Configuration

The new configuration system is backward compatible. Your existing code should work without changes, but you gain:

- Centralized configuration management
- Environment-specific optimization
- Better connection pooling
- Improved logging and monitoring
- Configurable SSL support

To take full advantage, update your `.env` file with the new optional settings as needed.

## Related Files

- `app/core/config.py` - Centralized configuration settings
- `app/deps.py` - Dependency injection for database sessions
- `app/models/` - SQLAlchemy ORM models
- `alembic/` - Database migration files
