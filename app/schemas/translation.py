"""
Translation Schema Definitions.

This module contains Pydantic models for translation-related request and response
validation. These schemas are used by the translation router and service layers.

Usage:
    from app.schemas.translation import (
        NllbLanguage,
        NllbTranslationRequest,
        WorkerTranslationResponse,
    )

Note:
    This module was extracted from app/schemas/tasks.py as part of the
    services layer refactoring to improve modularity.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, constr


class NllbLanguage(str, Enum):
    """Supported languages for NLLB translation.

    This enum defines the language codes supported by the NLLB translation
    service. Each value represents an ISO 639-3 language code.

    Attributes:
        acholi: Acholi language (ach).
        ateso: Ateso language (teo).
        english: English language (eng).
        luganda: Luganda language (lug).
        lugbara: Lugbara language (lgg).
        runyankole: Runyankole language (nyn).
    """

    acholi = "ach"
    ateso = "teo"
    english = "eng"
    luganda = "lug"
    lugbara = "lgg"
    runyankole = "nyn"


class NllbTranslationRequest(BaseModel):
    """Request model for NLLB text translation.

    This model validates translation requests with source and target
    languages along with the text to translate.

    Attributes:
        source_language: The source language for translation.
        target_language: The target language for translation.
        text: The text to translate (min 1 character, whitespace stripped).

    Example:
        >>> request = NllbTranslationRequest(
        ...     source_language=NllbLanguage.english,
        ...     target_language=NllbLanguage.luganda,
        ...     text="Hello world"
        ... )
    """

    source_language: NllbLanguage = Field(
        ..., description="The source language for translation"
    )
    target_language: NllbLanguage = Field(
        ..., description="The target language for translation"
    )
    text: constr(min_length=1, strip_whitespace=True) = Field(  # type: ignore
        ..., description="The text to translate"
    )


class WorkerTranslationOutput(BaseModel):
    """Output model for translation worker results.

    This model represents the output from the RunPod translation worker.
    It handles various response formats from the worker.

    Attributes:
        text: The translated text (some workers use this field).
        translated_text: The translated text (alternative field name).
        source_language: The source language code if returned.
        target_language: The target language code if returned.
        error: Error message if translation failed.
    """

    text: Optional[str] = Field(None, description="Translated text output")
    translated_text: Optional[str] = Field(
        None, description="Alternative translated text field"
    )
    source_language: Optional[str] = Field(
        None, description="Source language code if returned"
    )
    target_language: Optional[str] = Field(
        None, description="Target language code if returned"
    )
    error: Optional[str] = Field(
        None, alias="Error", description="Error message if translation failed"
    )

    class Config:
        """Pydantic model configuration."""

        populate_by_name = True
        extra = "allow"


class WorkerTranslationResponse(BaseModel):
    """Response model for translation worker API calls.

    This model wraps the translation worker output with metadata
    about the job execution.

    Attributes:
        delayTime: Time spent waiting in queue (ms).
        executionTime: Time spent executing the job (ms).
        id: Unique job identifier.
        output: The translation output data.
        status: Job status (e.g., "COMPLETED", "FAILED").
        workerId: Identifier of the worker that processed the job.
    """

    delayTime: Optional[int] = Field(
        None, description="Time spent waiting in queue (ms)"
    )
    executionTime: Optional[int] = Field(
        None, description="Time spent executing the job (ms)"
    )
    id: Optional[str] = Field(None, description="Unique job identifier")
    output: Optional[WorkerTranslationOutput] = Field(
        None, description="The translation output data"
    )
    status: Optional[str] = Field(
        None, description="Job status (e.g., COMPLETED, FAILED)"
    )
    workerId: Optional[str] = Field(
        None, description="Identifier of the worker that processed the job"
    )

    class Config:
        """Pydantic model configuration."""

        populate_by_name = True
        extra = "allow"
