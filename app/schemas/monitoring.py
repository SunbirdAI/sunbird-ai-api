from pydantic import BaseModel

class EndpointLog(BaseModel):
    username: str
    endpoint: str
    time_taken: float
