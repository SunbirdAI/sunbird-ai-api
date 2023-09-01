from pydantic import BaseModel

class EndpointLog(BaseModel):
    username: str
    endpoint: str
    organization: str | None
    time_taken: float

    class Config:
        orm_mode = True
