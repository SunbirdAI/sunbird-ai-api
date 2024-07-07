import json
import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

current_directory = os.path.dirname(os.path.realpath(__file__))
app_base_directory = os.path.abspath(os.path.join(current_directory, "../../"))
sys.path.append(app_base_directory)

from app.api import app
from app.database.db import Base
from app.deps import get_db

SQL_ALCHEMY_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    SQL_ALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture()
def test_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)


def test_register(test_db):
    user_data = {
        "username": "test_user",
        "email": "test_user@email.com",
        "password": "test_password",
        "organization": "test_organization",
        "account_type": "Free",
    }
    response = client.post("/auth/register", content=json.dumps(user_data))
    assert response.status_code == 201
    expected_dict = {key: user_data[key] for key in user_data if key != "password"}
    expected_dict["id"] = 1
    assert response.json() == expected_dict
