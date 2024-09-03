from typing import List, Optional

from pydantic import BaseModel


# Custom error response models
class ValidationErrorDetail(BaseModel):
    loc: List[str]
    msg: str
    input: Optional[str] = None


class ValidationErrorResponse(BaseModel):
    errors: List[ValidationErrorDetail]
