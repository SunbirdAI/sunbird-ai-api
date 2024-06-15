from typing import Optional

from pydantic import BaseModel


class EndpointLog(BaseModel):
    username: str
    endpoint: str
    # organization: str | None
    organization: Optional[str] = None
    time_taken: float

    class Config:
        orm_mode = True
