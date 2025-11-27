import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database.db import async_session_maker
from app.models import monitoring as models
from app.models.users import User
from app.schemas import monitoring as schemas
from app.schemas.monitoring import EndpointLog

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def auto_session() -> AsyncSession:  # type: ignore
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            logging.error(str(e))
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_endpoint_log(log: schemas.EndpointLog, db: AsyncSession):
    logging.info(f"log: {log}")
    db_log = models.EndpointLog(
        username=log.username,
        endpoint=log.endpoint,
        time_taken=log.time_taken,
        organization=log.organization,
    )
    db.add(db_log)
    await db.commit()


async def log_endpoint(
    db: AsyncSession, user: User, request: Request, start_time: float, end_time: float
):
    try:
        endpoint_log = EndpointLog(
            username=user.username,
            endpoint=request.url.path,
            organization=user.organization,
            time_taken=(end_time - start_time),
        )
        await create_endpoint_log(endpoint_log, db)
    except Exception as e:
        logging.error(f"Error: {str(e)}")


async def get_logs_by_username(db: AsyncSession, username: str) -> List[EndpointLog]:
    result = await db.execute(
        select(models.EndpointLog).filter(models.EndpointLog.username == username)
    )
    return result.scalars().all()


async def get_recent_logs_by_username(
    db: AsyncSession, username: str, limit: int = 10
) -> List[EndpointLog]:
    result = await db.execute(
        select(models.EndpointLog)
        .filter(models.EndpointLog.username == username)
        .order_by(models.EndpointLog.date.desc())
        .limit(limit)
    )
    return result.scalars().all()


async def get_logs_by_username_since(
    db: AsyncSession, username: str, since: datetime
) -> List[EndpointLog]:
    result = await db.execute(
        select(models.EndpointLog)
        .filter(models.EndpointLog.username == username)
        .filter(models.EndpointLog.date >= since)
    )
    return result.scalars().all()
