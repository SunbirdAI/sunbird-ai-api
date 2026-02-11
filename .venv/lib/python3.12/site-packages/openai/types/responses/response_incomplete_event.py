# File generated from our OpenAPI spec by Stainless. See CONTRIBUTING.md for details.

from typing_extensions import Literal

from ..._models import BaseModel
from .response import Response

__all__ = ["ResponseIncompleteEvent"]


class ResponseIncompleteEvent(BaseModel):
    response: Response
    """The response that was incomplete."""

    sequence_number: int
    """The sequence number of this event."""

    type: Literal["response.incomplete"]
    """The type of the event. Always `response.incomplete`."""
