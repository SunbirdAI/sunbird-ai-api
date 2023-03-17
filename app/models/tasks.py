from typing import List

from pydantic import BaseModel

class STTTranscript(BaseModel):
    text: str
    confidences: List[int] | None = None
