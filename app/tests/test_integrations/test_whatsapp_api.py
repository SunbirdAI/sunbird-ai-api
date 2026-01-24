"""
Tests for WhatsApp API Integration Module.

This module contains unit tests for the WhatsAppAPIClient class
defined in app/integrations/whatsapp_api.py.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.integrations.whatsapp_api import (
    DEFAULT_API_VERSION,
    LEGACY_API_VERSION,
    WhatsAppAPIClient,
    get_whatsapp_api_client,
    reset_whatsapp_api_client,
)


class TestWhatsAppAPIClientInitialization:
    """Tests for WhatsAppAPIClient initialization."""

    def test_default_initialization_from_env(self) -> None:
        """Test that client initializes with environment variables."""
        with patch.dict(
            "os.environ",
            {"WHATSAPP_TOKEN": "test-token", "PHONE_NUMBER_ID": "123456789"},
        ):
            client = WhatsAppAPIClient()

            assert client.token == "test-token"
            assert client.phone_number_id == "123456789"
            assert client.api_version == DEFAULT_API_VERSION

    def test_custom_initialization(self) -> None:
        """Test that client accepts custom configuration."""
        client = WhatsAppAPIClient(
            token="custom-token",
            phone_number_id="987654321",
            api_version="v18.0",
        )

        assert client.token == "custom-token"
        assert client.phone_number_id == "987654321"
        assert client.api_version == "v18.0"

    def test_missing_token_logs_warning(self) -> None:
        """Test that missing token logs a warning."""
        with patch.dict("os.environ", {}, clear=True):
            with patch("app.integrations.whatsapp_api.logger") as mock_logger:
                client = WhatsAppAPIClient()

                mock_logger.warning.assert_called()
                assert client.token is None

    def test_base_url_uses_api_version(self) -> None:
        """Test that base URL includes correct API version."""
        client = WhatsAppAPIClient(
            token="test", phone_number_id="123", api_version="v19.0"
        )

        assert "v19.0" in client.base_url
        assert client.base_url == "https://graph.facebook.com/v19.0"


class TestWhatsAppAPIClientHeaders:
    """Tests for header generation."""

    def test_headers_include_authorization(self) -> None:
        """Test that headers include Bearer token."""
        client = WhatsAppAPIClient(token="test-token", phone_number_id="123")

        headers = client.headers

        assert headers["Authorization"] == "Bearer test-token"
        assert headers["Content-Type"] == "application/json"


class TestWhatsAppAPIClientSendMessage:
    """Tests for send_message method."""

    def test_send_message_success(self) -> None:
        """Test successful message sending."""
        client = WhatsAppAPIClient(token="test-token", phone_number_id="123456")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"messages": [{"id": "wamid.HBgL1234567890"}]}

        with patch("requests.post", return_value=mock_response):
            result = client.send_message("1234567890", "Hello, World!")

            assert result == "wamid.HBgL1234567890"

    def test_send_message_failure(self) -> None:
        """Test message sending failure."""
        client = WhatsAppAPIClient(token="test-token", phone_number_id="123456")

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"error": "Bad request"}

        with patch("requests.post", return_value=mock_response):
            result = client.send_message("1234567890", "Hello!")

            assert result is None


class TestWhatsAppAPIClientSendTemplate:
    """Tests for send_template method."""

    def test_send_template_success(self) -> None:
        """Test successful template sending."""
        client = WhatsAppAPIClient(token="test-token", phone_number_id="123456")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"messages": [{"id": "wamid.template123"}]}

        with patch("requests.post", return_value=mock_response) as mock_post:
            result = client.send_template("1234567890", "welcome_template")

            assert result["messages"][0]["id"] == "wamid.template123"
            call_args = mock_post.call_args
            assert "template" in call_args.kwargs["json"]["type"]


class TestWhatsAppAPIClientSendMedia:
    """Tests for media sending methods."""

    def test_send_audio_with_link(self) -> None:
        """Test sending audio via URL link."""
        client = WhatsAppAPIClient(token="test-token", phone_number_id="123456")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"messages": [{"id": "wamid.audio123"}]}

        with patch("requests.post", return_value=mock_response) as mock_post:
            result = client.send_audio(
                "1234567890", "https://example.com/audio.mp3", link=True
            )

            assert "messages" in result
            call_data = mock_post.call_args.kwargs["json"]
            assert "link" in call_data["audio"]

    def test_send_audio_with_media_id(self) -> None:
        """Test sending audio via media ID."""
        client = WhatsAppAPIClient(token="test-token", phone_number_id="123456")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"messages": [{"id": "wamid.audio456"}]}

        with patch("requests.post", return_value=mock_response) as mock_post:
            result = client.send_audio("1234567890", "media-id-123", link=False)

            call_data = mock_post.call_args.kwargs["json"]
            assert "id" in call_data["audio"]

    def test_send_image_with_caption(self) -> None:
        """Test sending image with caption."""
        client = WhatsAppAPIClient(token="test-token", phone_number_id="123456")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"messages": [{"id": "wamid.image123"}]}

        with patch("requests.post", return_value=mock_response) as mock_post:
            result = client.send_image(
                "1234567890",
                "https://example.com/image.jpg",
                caption="Check this out!",
            )

            call_data = mock_post.call_args.kwargs["json"]
            assert call_data["image"]["caption"] == "Check this out!"


class TestWhatsAppAPIClientInteractive:
    """Tests for interactive message methods."""

    def test_send_button(self) -> None:
        """Test sending interactive list button."""
        client = WhatsAppAPIClient(token="test-token", phone_number_id="123456")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"messages": [{"id": "wamid.btn123"}]}

        button = {
            "header": "Test Header",
            "body": "Test Body",
            "footer": "Test Footer",
            "action": {"button": "Options", "sections": []},
        }

        with patch("requests.post", return_value=mock_response) as mock_post:
            result = client.send_button("1234567890", button)

            assert "messages" in result
            call_data = mock_post.call_args.kwargs["json"]
            assert call_data["type"] == "interactive"

    def test_send_reply_button(self) -> None:
        """Test sending reply button."""
        client = WhatsAppAPIClient(token="test-token", phone_number_id="123456")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"messages": [{"id": "wamid.reply123"}]}

        button = {
            "type": "button",
            "body": {"text": "Choose"},
            "action": {"buttons": []},
        }

        with patch("requests.post", return_value=mock_response):
            result = client.send_reply_button("1234567890", button)

            assert "messages" in result


class TestWhatsAppAPIClientMedia:
    """Tests for media query and download methods."""

    def test_query_media_url_success(self) -> None:
        """Test successful media URL query."""
        client = WhatsAppAPIClient(token="test-token", phone_number_id="123456")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "url": "https://media.whatsapp.net/download/123"
        }

        with patch("requests.get", return_value=mock_response):
            result = client.query_media_url("media-id-123")

            assert result == "https://media.whatsapp.net/download/123"

    def test_query_media_url_failure(self) -> None:
        """Test media URL query failure."""
        client = WhatsAppAPIClient(token="test-token", phone_number_id="123456")

        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("requests.get", return_value=mock_response):
            result = client.query_media_url("invalid-media-id")

            assert result is None

    def test_mark_as_read_success(self) -> None:
        """Test marking message as read."""
        client = WhatsAppAPIClient(token="test-token", phone_number_id="123456")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True}

        with patch("requests.post", return_value=mock_response):
            result = client.mark_as_read("wamid.123")

            assert result is True


class TestWhatsAppAPIClientSingleton:
    """Tests for singleton pattern."""

    def test_get_whatsapp_api_client_creates_singleton(self) -> None:
        """Test that get_whatsapp_api_client returns the same instance."""
        reset_whatsapp_api_client()

        with patch.dict(
            "os.environ",
            {"WHATSAPP_TOKEN": "test-token", "PHONE_NUMBER_ID": "123456"},
        ):
            client1 = get_whatsapp_api_client()
            client2 = get_whatsapp_api_client()

            assert client1 is client2

    def test_reset_whatsapp_api_client_clears_singleton(self) -> None:
        """Test that reset_whatsapp_api_client clears the singleton."""
        reset_whatsapp_api_client()

        with patch.dict(
            "os.environ",
            {"WHATSAPP_TOKEN": "test-token", "PHONE_NUMBER_ID": "123456"},
        ):
            client1 = get_whatsapp_api_client()
            reset_whatsapp_api_client()
            client2 = get_whatsapp_api_client()

            assert client1 is not client2


class TestAPIVersionConstants:
    """Tests for API version constants."""

    def test_default_api_version(self) -> None:
        """Test default API version constant."""
        assert DEFAULT_API_VERSION == "v20.0"

    def test_legacy_api_version(self) -> None:
        """Test legacy API version constant."""
        assert LEGACY_API_VERSION == "v12.0"
