from typing import Optional

from pydantic import BaseModel, ConfigDict


class EndpointLog(BaseModel):
    username: str
    endpoint: str
    organization: Optional[str] = None
    time_taken: float

    model_config = ConfigDict(from_attributes=True)
