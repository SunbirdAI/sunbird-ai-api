"""
Language Schema Definitions.

This module contains Pydantic models for language-related request and response
validation. These schemas are used by the language router and service layers.

Usage:
    from app.schemas.language import (
        LanguageIdRequest,
        LanguageIdResponse,
        AudioDetectedLanguageResponse,
    )

Note:
    This module was extracted from app/schemas/tasks.py as part of the
    services layer refactoring to improve modularity.
"""

from typing import Dict, Optional

from pydantic import BaseModel, Field


class LanguageIdRequest(BaseModel):
    """Request model for language identification.

    This model validates language identification requests with text input.

    Attributes:
        text: The text to identify the language of (3-200 characters).

    Example:
        >>> request = LanguageIdRequest(text="Oli otya?")
    """

    text: str = Field(
        ...,
        min_length=3,
        max_length=200,
        description="The text to identify the language of",
    )


class LanguageIdResponse(BaseModel):
    """Response model for language identification.

    This model represents the response from language identification operations.

    Attributes:
        language: The identified language code (e.g., 'lug', 'eng', 'ach').

    Example:
        >>> response = LanguageIdResponse(language="lug")
    """

    language: str = Field(..., description="The identified language code")


class AudioDetectedLanguageResponse(BaseModel):
    """Response model for audio language detection.

    This model represents the response from audio language detection operations.

    Attributes:
        detected_language: The detected language code from the audio.

    Example:
        >>> response = AudioDetectedLanguageResponse(detected_language="lug")
    """

    detected_language: str = Field(
        ..., description="The detected language code from the audio"
    )


class LanguageClassificationResult(BaseModel):
    """Result model for language classification with probabilities.

    This model represents detailed language classification results
    including probability scores.

    Attributes:
        language: The detected language code or 'language not detected'.
        probability: The confidence probability (0.0-1.0).
        predictions: Full predictions dictionary from the model.

    Example:
        >>> result = LanguageClassificationResult(
        ...     language="lug",
        ...     probability=0.95,
        ...     predictions={"lug": 0.95, "eng": 0.03, "ach": 0.02}
        ... )
    """

    language: str = Field(
        ..., description="The detected language code or 'language not detected'"
    )
    probability: Optional[float] = Field(
        None, description="The confidence probability (0.0-1.0)"
    )
    predictions: Optional[Dict[str, float]] = Field(
        None, description="Full predictions dictionary from the model"
    )
