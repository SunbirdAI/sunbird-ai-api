# File generated from our OpenAPI spec by Stainless. See CONTRIBUTING.md for details.

from typing_extensions import Literal

from ...._models import BaseModel
from .text import Text

__all__ = ["TextContentBlock"]


class TextContentBlock(BaseModel):
    text: Text

    type: Literal["text"]
    """Always `text`."""
