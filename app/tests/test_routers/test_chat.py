"""
Tests for the OpenAI-compatible /tasks/chat/completions endpoint.

Covers schema validation, the non-streaming and streaming (SSE) paths,
error mapping, and deprecation of the legacy Sunflower endpoints.
"""

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.schemas.chat import (
    SUPPORTED_MODELS,
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
)


class TestChatSchemas:
    """Unit tests for OpenAI-compatible request/response models."""

    def test_request_defaults(self) -> None:
        req = ChatCompletionRequest(
            messages=[{"role": "user", "content": "Hello"}]
        )
        assert req.model == "Sunbird/Sunflower-14B"
        assert req.temperature == 0.3
        assert req.stream is False
        assert req.max_tokens is None
        assert req.top_p is None
        assert req.stop is None

    def test_supported_models_constant(self) -> None:
        assert SUPPORTED_MODELS == ("Sunbird/Sunflower-14B",)

    def test_request_rejects_empty_messages(self) -> None:
        with pytest.raises(PydanticValidationError):
            ChatCompletionRequest(messages=[])

    def test_message_rejects_invalid_role(self) -> None:
        with pytest.raises(PydanticValidationError):
            ChatMessage(role="tool", content="hi")

    def test_message_rejects_blank_content(self) -> None:
        with pytest.raises(PydanticValidationError):
            ChatMessage(role="user", content="   ")

    def test_request_rejects_out_of_range_temperature(self) -> None:
        with pytest.raises(PydanticValidationError):
            ChatCompletionRequest(
                messages=[{"role": "user", "content": "Hello"}],
                temperature=3.0,
            )

    def test_stop_accepts_string_and_list(self) -> None:
        req = ChatCompletionRequest(
            messages=[{"role": "user", "content": "Hello"}], stop="\n"
        )
        assert req.stop == "\n"
        req = ChatCompletionRequest(
            messages=[{"role": "user", "content": "Hello"}], stop=["a", "b"]
        )
        assert req.stop == ["a", "b"]

    def test_response_serializes_openai_shape(self) -> None:
        resp = ChatCompletionResponse(
            id="chatcmpl-abc",
            created=1718000000,
            model="Sunbird/Sunflower-14B",
            choices=[
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Oli otya?"},
                    "finish_reason": "stop",
                }
            ],
            usage={
                "prompt_tokens": 5,
                "completion_tokens": 3,
                "total_tokens": 8,
            },
        )
        data = resp.model_dump()
        assert data["object"] == "chat.completion"
        assert data["choices"][0]["message"]["content"] == "Oli otya?"
        assert data["usage"]["total_tokens"] == 8

    def test_chunk_serializes_openai_shape(self) -> None:
        chunk = ChatCompletionChunk(
            id="chatcmpl-abc",
            created=1718000000,
            model="Sunbird/Sunflower-14B",
            choices=[{"index": 0, "delta": {"content": "Oli"}}],
        )
        data = chunk.model_dump()
        assert data["object"] == "chat.completion.chunk"
        assert data["choices"][0]["delta"]["content"] == "Oli"
        assert data["choices"][0]["finish_reason"] is None
