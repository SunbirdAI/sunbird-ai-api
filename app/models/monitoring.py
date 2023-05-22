from sqlalchemy import Column, String, Float, Integer
from app.database.db import Base


class EndpointLog(Base):
    __tablename__ = "endpoint_logs"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True)
    organization = Column(String, index=True)
    endpoint = Column(String, index=True)
    time_taken = Column(Float)
