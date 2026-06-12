"""
OpenAI-Compatible Chat Completion Schemas.

Pydantic models for the /tasks/chat/completions endpoint. The request and
response shapes mirror the OpenAI Chat Completions API so clients can switch
between the OpenAI API and the Sunbird API by changing only the base URL and
API key.

Spec: docs/superpowers/specs/2026-06-12-chat-completions-design.md
"""

from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator

# The only model served today. The legacy "qwen" alias is accepted solely by
# the deprecated /tasks/sunflower_* endpoints.
SUPPORTED_MODELS = ("Sunbird/Sunflower-14B",)

DEFAULT_MODEL = SUPPORTED_MODELS[0]


class ChatMessage(BaseModel):
    """A single message in the conversation, OpenAI format."""

    role: Literal["system", "user", "assistant"] = Field(
        ..., description="Message role"
    )
    content: str = Field(..., description="Message content")

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("content cannot be empty")
        return value


class ChatCompletionRequest(BaseModel):
    """Request body for POST /tasks/chat/completions (OpenAI format)."""

    model: str = Field(
        DEFAULT_MODEL,
        description=f"Model to use. Supported: {', '.join(SUPPORTED_MODELS)}",
    )
    messages: List[ChatMessage] = Field(
        ..., min_length=1, description="Conversation messages"
    )
    temperature: float = Field(0.3, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: Optional[int] = Field(
        None, ge=1, description="Maximum tokens to generate"
    )
    top_p: Optional[float] = Field(
        None, gt=0.0, le=1.0, description="Nucleus sampling probability"
    )
    stop: Optional[Union[str, List[str]]] = Field(None, description="Stop sequence(s)")
    stream: bool = Field(False, description="Stream the response as Server-Sent Events")


class ChatCompletionResponseMessage(BaseModel):
    """The assistant message inside a completion choice."""

    role: Literal["assistant"] = "assistant"
    content: str


class ChatCompletionChoice(BaseModel):
    """A single completion choice."""

    index: int = 0
    message: ChatCompletionResponseMessage
    finish_reason: Optional[str] = "stop"


class ChatCompletionUsage(BaseModel):
    """Token usage statistics, OpenAI field names."""

    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


class ChatCompletionResponse(BaseModel):
    """Non-streaming response body, OpenAI `chat.completion` object."""

    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: ChatCompletionUsage = Field(default_factory=ChatCompletionUsage)


class ChatCompletionChunkDelta(BaseModel):
    """Incremental content for a streamed choice."""

    role: Optional[str] = None
    content: Optional[str] = None


class ChatCompletionChunkChoice(BaseModel):
    """A single streamed choice."""

    index: int = 0
    delta: ChatCompletionChunkDelta
    finish_reason: Optional[str] = None


class ChatCompletionChunk(BaseModel):
    """Streaming response chunk, OpenAI `chat.completion.chunk` object."""

    id: str
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int
    model: str
    choices: List[ChatCompletionChunkChoice]
    usage: Optional[ChatCompletionUsage] = None


__all__ = [
    "SUPPORTED_MODELS",
    "DEFAULT_MODEL",
    "ChatMessage",
    "ChatCompletionRequest",
    "ChatCompletionResponseMessage",
    "ChatCompletionChoice",
    "ChatCompletionUsage",
    "ChatCompletionResponse",
    "ChatCompletionChunkDelta",
    "ChatCompletionChunkChoice",
    "ChatCompletionChunk",
]
