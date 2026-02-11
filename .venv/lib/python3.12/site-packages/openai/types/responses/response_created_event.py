# File generated from our OpenAPI spec by Stainless. See CONTRIBUTING.md for details.

from typing_extensions import Literal

from ..._models import BaseModel
from .response import Response

__all__ = ["ResponseCreatedEvent"]


class ResponseCreatedEvent(BaseModel):
    response: Response
    """The response that was created."""

    sequence_number: int
    """The sequence number for this event."""

    type: Literal["response.created"]
    """The type of the event. Always `response.created`."""
