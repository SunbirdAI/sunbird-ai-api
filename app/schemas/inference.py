"""
Inference Schema Definitions.

This module contains Pydantic models for Sunflower inference request and response
validation. These schemas are used by the inference router.

The main chat request/response models are re-exported from the inference service
for backward compatibility and consistency.

Usage:
    from app.schemas.inference import (
        SunflowerChatMessage,
        SunflowerChatRequest,
        SunflowerChatResponse,
        SunflowerUsageStats,
        SunflowerSimpleResponse,
    )

Note:
    This module was created as part of the services layer refactoring
    (Phase 3 Step 12: Create Inference Router).
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

# Re-export models from inference_service for backward compatibility
from app.services.inference_service import (
    SunflowerChatMessage,
    SunflowerChatRequest,
    SunflowerChatResponse,
    SunflowerUsageStats,
)


class SunflowerSimpleResponse(BaseModel):
    """Response model for simple Sunflower inference.

    This model represents the response from the simplified single-instruction
    inference endpoint.

    Attributes:
        response: The AI's response text.
        model_type: The model used for inference.
        processing_time: Total processing time in seconds.
        usage: Token usage statistics.
        success: Whether the inference was successful.

    Example:
        >>> response = SunflowerSimpleResponse(
        ...     response="In Luganda, 'hello' is 'Oli otya?'",
        ...     model_type="qwen",
        ...     processing_time=1.5,
        ...     usage={"completion_tokens": 10, "prompt_tokens": 5},
        ...     success=True
        ... )
    """

    response: str = Field(..., description="The AI's response text")
    model_type: str = Field(..., description="Model used for inference")
    processing_time: float = Field(..., description="Total processing time in seconds")
    usage: Dict[str, Any] = Field(
        default_factory=dict, description="Token usage statistics"
    )
    success: bool = Field(True, description="Whether the inference was successful")


__all__ = [
    "SunflowerChatMessage",
    "SunflowerChatRequest",
    "SunflowerChatResponse",
    "SunflowerUsageStats",
    "SunflowerSimpleResponse",
]
