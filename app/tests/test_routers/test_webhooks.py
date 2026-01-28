"""
Tests for Webhooks Router Module.

This module contains tests for the WhatsApp webhook endpoints defined in
app/routers/webhooks.py. Tests verify webhook handling, verification,
and integration with WhatsApp services.
"""

import os
from typing import Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.services.message_processor import ProcessingResult, ResponseType


class TestWebhookHandler:
    """Tests for POST /tasks/webhook endpoint."""

    @pytest.fixture
    def valid_webhook_payload(self) -> Dict:
        """Create a valid WhatsApp webhook payload for testing."""
        return {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "1234567890",
                                        "text": {"body": "Hello"},
                                    }
                                ],
                                "contacts": [{"profile": {"name": "John Doe"}}],
                                "metadata": {"phone_number_id": "9876543210"},
                            }
                        }
                    ]
                }
            ]
        }

    @pytest.mark.asyncio
    async def test_successful_webhook_processing(
        self,
        async_client: AsyncClient,
        valid_webhook_payload: Dict,
    ) -> None:
        """Test successful webhook processing."""
        with patch("app.routers.webhooks.whatsapp_service") as mock_whatsapp, patch(
            "app.routers.webhooks.processor"
        ) as mock_processor, patch(
            "app.routers.webhooks.get_user_preference"
        ) as mock_preference:
            # Setup mocks
            mock_whatsapp.valid_payload.return_value = True
            mock_whatsapp.get_messages_from_payload.return_value = [
                {"from": "1234567890"}
            ]
            mock_preference.return_value = "eng"

            # Mock processor result
            mock_result = ProcessingResult(
                message="Test response",
                response_type=ResponseType.TEXT,
                processing_time=1.0,
            )
            mock_processor.process_message = AsyncMock(return_value=mock_result)

            response = await async_client.post(
                "/tasks/webhook",
                json=valid_webhook_payload,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert "processing_time" in data

    @pytest.mark.asyncio
    async def test_webhook_invalid_payload(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test webhook with invalid payload."""
        with patch("app.routers.webhooks.whatsapp_service") as mock_whatsapp:
            mock_whatsapp.valid_payload.return_value = False

            response = await async_client.post(
                "/tasks/webhook",
                json={"invalid": "payload"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ignored"
            assert "processing_time" in data

    @pytest.mark.asyncio
    async def test_webhook_no_messages(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test webhook with no messages."""
        with patch("app.routers.webhooks.whatsapp_service") as mock_whatsapp:
            mock_whatsapp.valid_payload.return_value = True
            mock_whatsapp.get_messages_from_payload.return_value = []

            response = await async_client.post(
                "/tasks/webhook",
                json={"entry": []},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "no_messages"

    @pytest.mark.asyncio
    async def test_webhook_invalid_message_format(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test webhook with invalid message format."""
        with patch("app.routers.webhooks.whatsapp_service") as mock_whatsapp:
            mock_whatsapp.valid_payload.return_value = True
            mock_whatsapp.get_messages_from_payload.return_value = [{"test": "message"}]

            response = await async_client.post(
                "/tasks/webhook",
                json={"entry": [{"changes": []}]},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "invalid_message_format"

    @pytest.mark.asyncio
    async def test_webhook_with_button_response(
        self,
        async_client: AsyncClient,
        valid_webhook_payload: Dict,
    ) -> None:
        """Test webhook with button response."""
        with patch("app.routers.webhooks.whatsapp_service") as mock_whatsapp, patch(
            "app.routers.webhooks.processor"
        ) as mock_processor, patch(
            "app.routers.webhooks.get_user_preference"
        ) as mock_preference:
            # Setup mocks
            mock_whatsapp.valid_payload.return_value = True
            mock_whatsapp.get_messages_from_payload.return_value = [
                {"from": "1234567890"}
            ]
            mock_preference.return_value = "eng"

            # Mock processor result with button
            mock_result = ProcessingResult(
                message="",
                response_type=ResponseType.BUTTON,
                button_data={"type": "button", "body": "Test"},
                processing_time=1.0,
            )
            mock_processor.process_message = AsyncMock(return_value=mock_result)

            response = await async_client.post(
                "/tasks/webhook",
                json=valid_webhook_payload,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            mock_whatsapp.send_button.assert_called_once()

    @pytest.mark.asyncio
    async def test_webhook_with_template_response(
        self,
        async_client: AsyncClient,
        valid_webhook_payload: Dict,
    ) -> None:
        """Test webhook with template response."""
        with patch("app.routers.webhooks.whatsapp_service") as mock_whatsapp, patch(
            "app.routers.webhooks.processor"
        ) as mock_processor, patch(
            "app.routers.webhooks.get_user_preference"
        ) as mock_preference:
            # Setup mocks
            mock_whatsapp.valid_payload.return_value = True
            mock_whatsapp.get_messages_from_payload.return_value = [
                {"from": "1234567890"}
            ]
            mock_preference.return_value = "eng"

            # Mock processor result with template
            mock_result = ProcessingResult(
                message="",
                response_type=ResponseType.TEMPLATE,
                template_name="welcome_message",
                processing_time=1.0,
            )
            mock_processor.process_message = AsyncMock(return_value=mock_result)

            response = await async_client.post(
                "/tasks/webhook",
                json=valid_webhook_payload,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"

    @pytest.mark.asyncio
    async def test_webhook_error_handling(
        self,
        async_client: AsyncClient,
        valid_webhook_payload: Dict,
    ) -> None:
        """Test webhook error handling."""
        with patch("app.routers.webhooks.whatsapp_service") as mock_whatsapp, patch(
            "app.routers.webhooks.processor"
        ) as mock_processor, patch(
            "app.routers.webhooks.get_user_preference"
        ) as mock_preference:
            # Setup mocks
            mock_whatsapp.valid_payload.return_value = True
            mock_whatsapp.get_messages_from_payload.return_value = [
                {"from": "1234567890"}
            ]
            mock_preference.return_value = "eng"

            # Mock processor to raise exception
            mock_processor.process_message = AsyncMock(
                side_effect=Exception("Test error")
            )

            response = await async_client.post(
                "/tasks/webhook",
                json=valid_webhook_payload,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "error"
            assert "processing_time" in data


class TestWebhookVerification:
    """Tests for GET /tasks/webhook endpoint."""

    @pytest.mark.asyncio
    async def test_successful_webhook_verification(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test successful webhook verification."""
        verify_token = os.getenv("VERIFY_TOKEN", "test_token")

        with patch.dict(os.environ, {"VERIFY_TOKEN": "test_token"}):
            response = await async_client.get(
                "/tasks/webhook",
                params={
                    "hub.mode": "subscribe",
                    "hub.challenge": "test_challenge_123",
                    "hub.verify_token": "test_token",
                },
            )

            assert response.status_code == 200
            assert response.text == "test_challenge_123"
            assert response.headers["content-type"] == "text/plain; charset=utf-8"

    @pytest.mark.asyncio
    async def test_webhook_verification_wrong_mode(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test webhook verification with wrong mode."""
        with patch.dict(os.environ, {"VERIFY_TOKEN": "test_token"}):
            response = await async_client.get(
                "/tasks/webhook",
                params={
                    "hub.mode": "unsubscribe",
                    "hub.challenge": "test_challenge_123",
                    "hub.verify_token": "test_token",
                },
            )

            assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_webhook_verification_wrong_token(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test webhook verification with wrong token."""
        with patch.dict(os.environ, {"VERIFY_TOKEN": "test_token"}):
            response = await async_client.get(
                "/tasks/webhook",
                params={
                    "hub.mode": "subscribe",
                    "hub.challenge": "test_challenge_123",
                    "hub.verify_token": "wrong_token",
                },
            )

            assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_webhook_verification_missing_params(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test webhook verification with missing parameters."""
        response = await async_client.get(
            "/tasks/webhook",
            params={"hub.mode": "subscribe"},
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_webhook_verification_no_params(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test webhook verification with no parameters."""
        response = await async_client.get("/tasks/webhook")

        assert response.status_code == 400


class TestWebhookIntegration:
    """Integration tests for webhook functionality."""

    @pytest.mark.asyncio
    async def test_webhook_and_verification_endpoints_exist(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test that both webhook endpoints are accessible."""
        # Test POST endpoint exists (will fail validation, but endpoint exists)
        with patch("app.routers.webhooks.whatsapp_service") as mock_whatsapp:
            mock_whatsapp.valid_payload.return_value = False

            response = await async_client.post(
                "/tasks/webhook",
                json={},
            )
            # Should get a response (not 404)
            assert response.status_code == 200

        # Test GET endpoint exists (will fail validation, but endpoint exists)
        response = await async_client.get("/tasks/webhook")
        # Should get 400 (missing params) not 404
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_webhook_trailing_slash(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test that webhook endpoints work with trailing slash."""
        with patch("app.routers.webhooks.whatsapp_service") as mock_whatsapp:
            mock_whatsapp.valid_payload.return_value = False

            response = await async_client.post(
                "/tasks/webhook/",
                json={},
            )
            assert response.status_code == 200

        response = await async_client.get("/tasks/webhook/")
        assert response.status_code == 400
