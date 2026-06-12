"""
Tests for the OpenAI-compatible /tasks/chat/completions endpoint.

Covers schema validation, the non-streaming and streaming (SSE) paths,
error mapping, and deprecation of the legacy Sunflower endpoints.
"""

from typing import Any, Dict
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient
from pydantic import ValidationError as PydanticValidationError

from app.schemas.chat import (
    SUPPORTED_MODELS,
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
)
from app.services.inference_service import (
    InferenceService,
    InferenceTimeoutError,
    ModelLoadingError,
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


@pytest.fixture
def mock_service() -> MagicMock:
    """A MagicMock standing in for InferenceService."""
    return MagicMock(spec=InferenceService)


@pytest.fixture
def override_service(mock_service: MagicMock):
    """Route the inference service dependency to the mock for one test."""
    from app.api import app
    from app.services.inference_service import get_inference_service

    app.dependency_overrides[get_inference_service] = lambda: mock_service
    yield mock_service
    app.dependency_overrides.pop(get_inference_service, None)


SAMPLE_RESULT: Dict[str, Any] = {
    "content": "In Luganda, 'How are you?' is 'Oli otya?'.",
    "model_type": "qwen",
    "usage": {"completion_tokens": 15, "prompt_tokens": 50, "total_tokens": 65},
    "processing_time": 2.0,
}


class TestChatCompletionsEndpoint:
    """Tests for POST /tasks/chat/completions (non-streaming)."""

    async def test_successful_completion_openai_shape(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        override_service: MagicMock,
    ) -> None:
        override_service.run_inference.return_value = SAMPLE_RESULT
        response = await async_client.post(
            "/tasks/chat/completions",
            json={
                "messages": [
                    {"role": "user", "content": "Translate 'How are you?' to Luganda."}
                ]
            },
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["object"] == "chat.completion"
        assert data["id"].startswith("chatcmpl-")
        assert isinstance(data["created"], int)
        assert data["model"] == "Sunbird/Sunflower-14B"
        assert data["choices"][0]["index"] == 0
        assert data["choices"][0]["message"]["role"] == "assistant"
        assert (
            data["choices"][0]["message"]["content"]
            == "In Luganda, 'How are you?' is 'Oli otya?'."
        )
        assert data["choices"][0]["finish_reason"] == "stop"
        assert data["usage"]["total_tokens"] == 65

    async def test_default_system_message_injected(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        override_service: MagicMock,
    ) -> None:
        override_service.run_inference.return_value = SAMPLE_RESULT
        await async_client.post(
            "/tasks/chat/completions",
            json={"messages": [{"role": "user", "content": "Hello"}]},
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        sent = override_service.run_inference.call_args.kwargs["messages"]
        assert sent[0]["role"] == "system"
        assert "Sunflower" in sent[0]["content"]

    async def test_client_system_message_preserved(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        override_service: MagicMock,
    ) -> None:
        override_service.run_inference.return_value = SAMPLE_RESULT
        await async_client.post(
            "/tasks/chat/completions",
            json={
                "messages": [
                    {"role": "system", "content": "You are terse."},
                    {"role": "user", "content": "Hello"},
                ]
            },
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        sent = override_service.run_inference.call_args.kwargs["messages"]
        assert sent[0] == {"role": "system", "content": "You are terse."}
        assert sum(1 for m in sent if m["role"] == "system") == 1

    async def test_multi_turn_history_passed_through(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        override_service: MagicMock,
    ) -> None:
        override_service.run_inference.return_value = SAMPLE_RESULT
        await async_client.post(
            "/tasks/chat/completions",
            json={
                "messages": [
                    {"role": "user", "content": "Translate 'hello' to Luganda."},
                    {"role": "assistant", "content": "'Hello' is 'Gyebaleko'."},
                    {"role": "user", "content": "And to Acholi?"},
                ]
            },
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        sent = override_service.run_inference.call_args.kwargs["messages"]
        # default system + 3 conversation messages
        assert len(sent) == 4
        assert [m["role"] for m in sent[1:]] == ["user", "assistant", "user"]

    async def test_requires_auth(self, async_client: AsyncClient) -> None:
        response = await async_client.post(
            "/tasks/chat/completions",
            json={"messages": [{"role": "user", "content": "Hello"}]},
        )
        assert response.status_code == 401

    async def test_unknown_model_rejected_with_400(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        override_service: MagicMock,
    ) -> None:
        response = await async_client.post(
            "/tasks/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "Hello"}],
            },
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        assert response.status_code == 400
        assert "Sunbird/Sunflower-14B" in response.json()["message"]
        override_service.run_inference.assert_not_called()

    async def test_empty_messages_rejected_with_422(
        self,
        async_client: AsyncClient,
        test_user: Dict,
    ) -> None:
        response = await async_client.post(
            "/tasks/chat/completions",
            json={"messages": []},
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        assert response.status_code == 422

    async def test_invalid_role_rejected_with_422(
        self,
        async_client: AsyncClient,
        test_user: Dict,
    ) -> None:
        response = await async_client.post(
            "/tasks/chat/completions",
            json={"messages": [{"role": "tool", "content": "Hello"}]},
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        assert response.status_code == 422

    async def test_blank_content_rejected_with_422(
        self,
        async_client: AsyncClient,
        test_user: Dict,
    ) -> None:
        response = await async_client.post(
            "/tasks/chat/completions",
            json={"messages": [{"role": "user", "content": "   "}]},
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        assert response.status_code == 422

    async def test_model_loading_maps_to_503(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        override_service: MagicMock,
    ) -> None:
        override_service.run_inference.side_effect = ModelLoadingError("loading")
        response = await async_client.post(
            "/tasks/chat/completions",
            json={"messages": [{"role": "user", "content": "Hello"}]},
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        assert response.status_code == 503

    async def test_timeout_maps_to_503(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        override_service: MagicMock,
    ) -> None:
        override_service.run_inference.side_effect = InferenceTimeoutError("slow")
        response = await async_client.post(
            "/tasks/chat/completions",
            json={"messages": [{"role": "user", "content": "Hello"}]},
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        assert response.status_code == 503

    async def test_empty_model_response_maps_to_502(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        override_service: MagicMock,
    ) -> None:
        override_service.run_inference.return_value = {
            "content": "",
            "usage": {},
        }
        response = await async_client.post(
            "/tasks/chat/completions",
            json={"messages": [{"role": "user", "content": "Hello"}]},
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        assert response.status_code == 502

    async def test_params_forwarded_to_service(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        override_service: MagicMock,
    ) -> None:
        override_service.run_inference.return_value = SAMPLE_RESULT
        await async_client.post(
            "/tasks/chat/completions",
            json={
                "messages": [{"role": "user", "content": "Hello"}],
                "temperature": 0.9,
                "max_tokens": 256,
                "top_p": 0.8,
                "stop": ["###"],
            },
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        kwargs = override_service.run_inference.call_args.kwargs
        assert kwargs["temperature"] == 0.9
        assert kwargs["max_tokens"] == 256
        assert kwargs["top_p"] == 0.8
        assert kwargs["stop"] == ["###"]
