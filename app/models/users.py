from sqlalchemy import Column, Integer, String

from app.database.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String, default=None)
    organization = Column(String, nullable=False, default="Unknown")
    account_type = Column(String, nullable=False, default="Free")
    password_reset_token = Column(String, nullable=True)
    oauth_type = Column(String, nullable=True, default="Credentials")
