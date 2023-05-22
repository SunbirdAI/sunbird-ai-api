from pydantic import BaseModel

class EndpointLog(BaseModel):
    username: str
    endpoint: str
    organization: str
    time_taken: float
