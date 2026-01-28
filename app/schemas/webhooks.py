"""
Webhooks Schema Definitions.

This module defines Pydantic models for webhook operations,
primarily for WhatsApp Business API webhook handling.

Models:
    - WebhookResponse: Response model for webhook handling
    - WebhookVerificationParams: Query parameters for webhook verification
"""

from typing import Dict, Optional

from pydantic import BaseModel, Field


class WebhookResponse(BaseModel):
    """
    Response model for webhook handling.

    Attributes:
        status: Status of the webhook processing.
        processing_time: Time taken to process the webhook (optional).
        message: Additional information about the processing (optional).

    Example:
        {
            "status": "success",
            "processing_time": 2.5
        }
    """

    status: str = Field(
        ...,
        description="Status of the webhook processing",
        json_schema_extra={"example": "success"},
    )
    processing_time: Optional[float] = Field(
        None,
        description="Time taken to process the webhook in seconds",
    )
    message: Optional[str] = Field(
        None,
        description="Additional information about the processing",
    )


class WebhookVerificationParams(BaseModel):
    """
    Query parameters for webhook verification.

    WhatsApp sends these parameters to verify webhook endpoint ownership.

    Attributes:
        hub_mode: Should be "subscribe" for verification.
        hub_challenge: Random string to echo back.
        hub_verify_token: Verification token to validate.

    Example:
        ?hub.mode=subscribe&hub.challenge=12345&hub.verify_token=mytoken
    """

    hub_mode: Optional[str] = Field(
        None,
        alias="hub.mode",
        description="Verification mode (should be 'subscribe')",
    )
    hub_challenge: Optional[str] = Field(
        None,
        alias="hub.challenge",
        description="Challenge string to echo back",
    )
    hub_verify_token: Optional[str] = Field(
        None,
        alias="hub.verify_token",
        description="Token to verify webhook ownership",
    )

    class Config:
        populate_by_name = True


__all__ = [
    "WebhookResponse",
    "WebhookVerificationParams",
]
