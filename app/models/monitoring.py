from sqlalchemy import Column, DateTime, Float, Integer, JSON, String
from sqlalchemy.sql import func

from app.database.db import Base


class EndpointLog(Base):
    __tablename__ = "endpoint_logs"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True)
    organization = Column(String, index=True)
    endpoint = Column(String, index=True)
    time_taken = Column(Float)
    date = Column(DateTime(timezone=True), default=func.now())
    organization_type = Column(String, nullable=True, default=None)
    sector = Column(JSON, nullable=True, default=None)
