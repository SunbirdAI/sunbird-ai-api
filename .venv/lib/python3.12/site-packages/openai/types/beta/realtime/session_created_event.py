# File generated from our OpenAPI spec by Stainless. See CONTRIBUTING.md for details.

from typing_extensions import Literal

from ...._models import BaseModel
from .session import Session

__all__ = ["SessionCreatedEvent"]


class SessionCreatedEvent(BaseModel):
    event_id: str
    """The unique ID of the server event."""

    session: Session
    """Realtime session object configuration."""

    type: Literal["session.created"]
    """The event type, must be `session.created`."""
