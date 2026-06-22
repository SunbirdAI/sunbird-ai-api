---
paths:
  - "app/models/**"
  - "app/database/**"
  - "app/alembic/**"
  - "app/crud/**"
---

# Database

## Stack

- **Engine**: Async SQLAlchemy (`asyncpg` for PostgreSQL, `aiosqlite` for SQLite in tests)
- **ORM**: Declarative base from `app/database/db.py`
- **Migrations**: Alembic (`app/alembic/versions/`)
- **Sessions**: `async_session_maker` from `app/database/db.py`; injected via `get_db` dependency

## Model Pattern

```python
from app.database.db import Base
from sqlalchemy import Column, String, Integer
from sqlalchemy.orm import relationship

class MyModel(Base):
    __tablename__ = "my_table"
    id = Column(Integer, primary_key=True, index=True)
    ...
```

After changing a model, always generate and review a migration before applying:

```bash
alembic revision --autogenerate -m "describe change"
# Review app/alembic/versions/<new_file>.py
alembic upgrade head
```

## CRUD Pattern

CRUD functions in `app/crud/` accept an `AsyncSession` and return ORM objects or `None`. They do not commit — callers own the transaction.

```python
async def get_user_by_username(db: AsyncSession, username: str):
    result = await db.execute(select(User).where(User.username == username))
    return result.scalars().first()
```

## Connection Pooling

Configured in `app/core/config.py` with environment-aware defaults:
- Production: `pool_size=20`, `max_overflow=10`, SSL enabled if `DB_SSL_ENABLED=true`
- Development: `pool_size=50`, `max_overflow=0`

`DATABASE_URL` starting with `postgres://` is automatically rewritten to `postgresql+asyncpg://` by `settings.database_url_async`.
