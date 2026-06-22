from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class EndpointLog(BaseModel):
    id: Optional[int] = None
    username: str
    endpoint: str
    organization: Optional[str] = None
    time_taken: float
    date: Optional[datetime] = None
    organization_type: Optional[str] = None
    sector: Optional[List[str]] = None

    model_config = ConfigDict(from_attributes=True)
