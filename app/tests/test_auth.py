import json
import os
import sys
import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from httpx import AsyncClient

current_directory = os.path.dirname(os.path.realpath(__file__))
app_base_directory = os.path.abspath(os.path.join(current_directory, "../../"))
sys.path.append(app_base_directory)

from app.api import app
from app.database.db import Base
from app.deps import get_db


SQL_ALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///./test.db"

engine = create_async_engine(
    SQL_ALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

TestingSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop()
    yield loop
    loop.close()


@pytest.fixture()
async def test_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def override_get_db() -> AsyncSession: # type: ignore
    async with TestingSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db

def run_async(func, *args, **kwargs):
    return asyncio.run(func(*args, **kwargs))

client = TestClient(app)

@pytest.fixture()
async def async_client() -> AsyncClient: # type: ignore
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


# def test_register(test_db):
#     user_data = {
#         "username": "test_user",
#         "email": "test_user@email.com",
#         "password": "test_password",
#         "organization": "test_organization",
#         "account_type": "Free",
#     }
#     response = client.post("/auth/register", content=json.dumps(user_data))
#     assert response.status_code == 201
#     expected_dict = {key: user_data[key] for key in user_data if key != "password"}
#     expected_dict["id"] = 1
#     assert response.json() == expected_dict

# @pytest.mark.asyncio
async def test_register(test_db):
    user_data = {
        "username": "test_user",
        "email": "test_user@email.com",
        "password": "test_password",
        "organization": "test_organization",
        "account_type": "Free",
    }
    response = await client.post("/auth/register", content=json.dumps(user_data))
    assert response.status_code == 201
    expected_dict = {key: user_data[key] for key in user_data if key != "password"}
    expected_dict["id"] = 1
    assert response.json() == expected_dict
