import os

from app.schemas.users import UserInDB, User
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

engine = create_engine(os.getenv('DATABASE_URL'))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

db = {
    "users": {}
}

def insert_user(user: UserInDB) -> User:
    id_ = len(db["users"]) + 1
    user_dict = user.dict()
    user_dict['id'] = id_
    db["users"][user.username] = user_dict
    return User(**user_dict)

def get_user(username: str) -> UserInDB:
    if username not in db["users"]:
        return None
    return UserInDB(**db["users"][username])
