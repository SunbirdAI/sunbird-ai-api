from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class EndpointLog(BaseModel):
    id: Optional[int] = None
    username: str
    endpoint: str
    organization: Optional[str] = None
    time_taken: float
    date: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
