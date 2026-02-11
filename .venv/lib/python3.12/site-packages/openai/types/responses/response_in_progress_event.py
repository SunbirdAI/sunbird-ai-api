# File generated from our OpenAPI spec by Stainless. See CONTRIBUTING.md for details.

from typing_extensions import Literal

from ..._models import BaseModel
from .response import Response

__all__ = ["ResponseInProgressEvent"]


class ResponseInProgressEvent(BaseModel):
    response: Response
    """The response that is in progress."""

    sequence_number: int
    """The sequence number of this event."""

    type: Literal["response.in_progress"]
    """The type of the event. Always `response.in_progress`."""
