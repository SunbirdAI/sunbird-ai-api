from sqlalchemy import Column, Integer, String

from app.database.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    organization = Column(String, nullable=False, default="Unknown")
    account_type = Column(String, nullable=False, default="Free")
