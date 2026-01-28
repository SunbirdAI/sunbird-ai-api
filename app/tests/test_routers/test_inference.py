"""
Tests for Inference Router Module.

This module contains tests for the Sunflower AI inference endpoints defined in
app/routers/inference.py. Tests verify request handling, authentication,
error responses, and integration with the InferenceService.
"""

from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.api import app
from app.routers.inference import get_service
from app.services.inference_service import InferenceService, ModelLoadingError


class TestSunflowerInferenceEndpoint:
    """Tests for POST /tasks/sunflower_inference endpoint."""

    @pytest.fixture
    def mock_inference_service(self) -> MagicMock:
        """Create a mock InferenceService for testing."""
        mock = MagicMock(spec=InferenceService)
        return mock

    @pytest.fixture
    def sample_inference_response(self) -> Dict[str, Any]:
        """Create a sample inference response for testing."""
        return {
            "content": "In Luganda, 'How are you?' is 'Oli otya?'.",
            "model_type": "qwen",
            "usage": {
                "completion_tokens": 15,
                "prompt_tokens": 50,
                "total_tokens": 65,
            },
            "processing_time": 2.0,
        }

    @pytest.mark.asyncio
    async def test_successful_sunflower_inference(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        sample_inference_response: Dict[str, Any],
    ) -> None:
        """Test successful Sunflower inference request."""
        with patch(
            "app.routers.inference.run_inference",
            return_value=sample_inference_response,
        ):
            response = await async_client.post(
                "/tasks/sunflower_inference",
                json={
                    "messages": [
                        {
                            "role": "user",
                            "content": "Translate 'How are you?' to Luganda.",
                        }
                    ],
                    "model_type": "qwen",
                    "temperature": 0.3,
                },
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["content"] == "In Luganda, 'How are you?' is 'Oli otya?'."
            assert data["model_type"] == "qwen"
            assert "usage" in data
            assert "processing_time" in data

    @pytest.mark.asyncio
    async def test_sunflower_inference_without_auth(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test that Sunflower inference requires authentication."""
        response = await async_client.post(
            "/tasks/sunflower_inference",
            json={
                "messages": [{"role": "user", "content": "Hello"}],
            },
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_sunflower_inference_empty_messages(
        self,
        async_client: AsyncClient,
        test_user: Dict,
    ) -> None:
        """Test that empty messages returns 400."""
        response = await async_client.post(
            "/tasks/sunflower_inference",
            json={
                "messages": [],
            },
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        assert response.status_code == 400
        assert "required" in response.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_sunflower_inference_invalid_role(
        self,
        async_client: AsyncClient,
        test_user: Dict,
    ) -> None:
        """Test that invalid message role returns 422."""
        response = await async_client.post(
            "/tasks/sunflower_inference",
            json={
                "messages": [{"role": "invalid", "content": "Hello"}],
            },
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        assert response.status_code == 422
        assert "role" in response.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_sunflower_inference_empty_content(
        self,
        async_client: AsyncClient,
        test_user: Dict,
    ) -> None:
        """Test that empty message content returns 422."""
        response = await async_client.post(
            "/tasks/sunflower_inference",
            json={
                "messages": [{"role": "user", "content": "   "}],
            },
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        assert response.status_code == 422
        assert "empty" in response.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_sunflower_inference_model_loading_error(
        self,
        async_client: AsyncClient,
        test_user: Dict,
    ) -> None:
        """Test that model loading error returns 503."""
        with patch(
            "app.routers.inference.run_inference",
            side_effect=ModelLoadingError("Model is loading"),
        ):
            response = await async_client.post(
                "/tasks/sunflower_inference",
                json={
                    "messages": [{"role": "user", "content": "Hello"}],
                },
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 503
            assert "loading" in response.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_sunflower_inference_timeout_error(
        self,
        async_client: AsyncClient,
        test_user: Dict,
    ) -> None:
        """Test that timeout error returns 504."""
        with patch(
            "app.routers.inference.run_inference",
            side_effect=TimeoutError("Request timed out"),
        ):
            response = await async_client.post(
                "/tasks/sunflower_inference",
                json={
                    "messages": [{"role": "user", "content": "Hello"}],
                },
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 503
            assert "timed out" in response.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_sunflower_inference_empty_response(
        self,
        async_client: AsyncClient,
        test_user: Dict,
    ) -> None:
        """Test that empty model response returns 502."""
        with patch(
            "app.routers.inference.run_inference",
            return_value={"content": ""},
        ):
            response = await async_client.post(
                "/tasks/sunflower_inference",
                json={
                    "messages": [{"role": "user", "content": "Hello"}],
                },
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 502
            assert "empty" in response.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_sunflower_inference_with_system_message(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        sample_inference_response: Dict[str, Any],
    ) -> None:
        """Test Sunflower inference with custom system message."""
        with patch(
            "app.routers.inference.run_inference",
            return_value=sample_inference_response,
        ):
            response = await async_client.post(
                "/tasks/sunflower_inference",
                json={
                    "messages": [
                        {"role": "system", "content": "You are a helpful translator."},
                        {"role": "user", "content": "Translate 'hello' to Luganda."},
                    ],
                    "model_type": "qwen",
                },
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_sunflower_inference_with_conversation_history(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        sample_inference_response: Dict[str, Any],
    ) -> None:
        """Test Sunflower inference with conversation history."""
        with patch(
            "app.routers.inference.run_inference",
            return_value=sample_inference_response,
        ):
            response = await async_client.post(
                "/tasks/sunflower_inference",
                json={
                    "messages": [
                        {"role": "user", "content": "What is hello in Luganda?"},
                        {
                            "role": "assistant",
                            "content": "Hello in Luganda is 'Gyebaleko'.",
                        },
                        {"role": "user", "content": "And in Acholi?"},
                    ],
                    "model_type": "qwen",
                },
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 200


class TestSunflowerSimpleEndpoint:
    """Tests for POST /tasks/sunflower_simple endpoint."""

    @pytest.fixture
    def sample_simple_response(self) -> Dict[str, Any]:
        """Create a sample simple inference response for testing."""
        return {
            "content": "In Luganda, 'hello' is 'Gyebaleko'.",
            "model_type": "qwen",
            "usage": {
                "completion_tokens": 10,
                "prompt_tokens": 20,
                "total_tokens": 30,
            },
            "processing_time": 1.5,
        }

    @pytest.mark.asyncio
    async def test_successful_simple_inference(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        sample_simple_response: Dict[str, Any],
    ) -> None:
        """Test successful simple Sunflower inference request."""
        with patch(
            "app.routers.inference.run_inference",
            return_value=sample_simple_response,
        ):
            response = await async_client.post(
                "/tasks/sunflower_simple",
                data={
                    "instruction": "Translate 'hello' to Luganda",
                    "model_type": "qwen",
                    "temperature": "0.3",
                },
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["response"] == "In Luganda, 'hello' is 'Gyebaleko'."
            assert data["model_type"] == "qwen"
            assert data["success"] is True

    @pytest.mark.asyncio
    async def test_simple_inference_without_auth(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test that simple inference requires authentication."""
        response = await async_client.post(
            "/tasks/sunflower_simple",
            data={"instruction": "Hello"},
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_simple_inference_empty_instruction(
        self,
        async_client: AsyncClient,
        test_user: Dict,
    ) -> None:
        """Test that empty instruction returns 400."""
        response = await async_client.post(
            "/tasks/sunflower_simple",
            data={"instruction": "   "},
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        assert response.status_code == 400
        assert "empty" in response.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_simple_inference_instruction_too_long(
        self,
        async_client: AsyncClient,
        test_user: Dict,
    ) -> None:
        """Test that instruction longer than 4000 chars returns 400."""
        response = await async_client.post(
            "/tasks/sunflower_simple",
            data={"instruction": "a" * 4001},
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        assert response.status_code == 400
        assert "long" in response.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_simple_inference_invalid_model_type(
        self,
        async_client: AsyncClient,
        test_user: Dict,
    ) -> None:
        """Test that invalid model type returns 422."""
        response = await async_client.post(
            "/tasks/sunflower_simple",
            data={
                "instruction": "Hello",
                "model_type": "invalid",
            },
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        assert response.status_code == 422
        assert "model type" in response.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_simple_inference_model_loading_error(
        self,
        async_client: AsyncClient,
        test_user: Dict,
    ) -> None:
        """Test that model loading error returns 503."""
        with patch(
            "app.routers.inference.run_inference",
            side_effect=ModelLoadingError("Model is loading"),
        ):
            response = await async_client.post(
                "/tasks/sunflower_simple",
                data={"instruction": "Hello"},
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 503
            assert "loading" in response.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_simple_inference_timeout_error(
        self,
        async_client: AsyncClient,
        test_user: Dict,
    ) -> None:
        """Test that timeout error returns 504."""
        with patch(
            "app.routers.inference.run_inference",
            side_effect=TimeoutError("Request timed out"),
        ):
            response = await async_client.post(
                "/tasks/sunflower_simple",
                data={"instruction": "Hello"},
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 503
            assert "timed out" in response.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_simple_inference_with_custom_system_message(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        sample_simple_response: Dict[str, Any],
    ) -> None:
        """Test simple inference with custom system message."""
        with patch(
            "app.routers.inference.run_inference",
            return_value=sample_simple_response,
        ):
            response = await async_client.post(
                "/tasks/sunflower_simple",
                data={
                    "instruction": "Translate 'hello' to Luganda",
                    "system_message": "You are a translator.",
                },
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_simple_inference_with_gemma_model(
        self,
        async_client: AsyncClient,
        test_user: Dict,
        sample_simple_response: Dict[str, Any],
    ) -> None:
        """Test simple inference with gemma model type."""
        sample_simple_response["model_type"] = "gemma"
        with patch(
            "app.routers.inference.run_inference",
            return_value=sample_simple_response,
        ):
            response = await async_client.post(
                "/tasks/sunflower_simple",
                data={
                    "instruction": "Hello",
                    "model_type": "gemma",
                },
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )

            assert response.status_code == 200
            assert response.json()["model_type"] == "gemma"


class TestInferenceSchemaValidation:
    """Tests for request schema validation."""

    @pytest.mark.asyncio
    async def test_missing_messages_field(
        self,
        async_client: AsyncClient,
        test_user: Dict,
    ) -> None:
        """Test that missing messages field returns 422."""
        response = await async_client.post(
            "/tasks/sunflower_inference",
            json={},
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_instruction_field(
        self,
        async_client: AsyncClient,
        test_user: Dict,
    ) -> None:
        """Test that missing instruction field returns 422."""
        response = await async_client.post(
            "/tasks/sunflower_simple",
            data={},
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_message_structure(
        self,
        async_client: AsyncClient,
        test_user: Dict,
    ) -> None:
        """Test that invalid message structure returns 422."""
        response = await async_client.post(
            "/tasks/sunflower_inference",
            json={
                "messages": [{"invalid": "structure"}],
            },
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        assert response.status_code == 422
