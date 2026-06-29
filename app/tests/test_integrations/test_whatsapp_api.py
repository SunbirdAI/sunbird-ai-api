"""
Tests for WhatsApp API Integration Module.

This module contains unit tests for the WhatsAppAPIClient class
defined in app/integrations/whatsapp_api.py.
"""

from unittest.mock import MagicMock, patch

import requests

from app.core.config import settings
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


class TestWhatsAppAPIClientTimeouts:
    """Tests for outbound request timeout behavior (Phase 1)."""

    def test_default_timeouts_from_settings(self) -> None:
        """Client defaults its timeouts from settings."""
        client = WhatsAppAPIClient(token="t", phone_number_id="123")

        assert client.request_timeout == settings.whatsapp_request_timeout_seconds
        assert client.upload_timeout == settings.whatsapp_upload_timeout_seconds

    def test_custom_timeouts_override_defaults(self) -> None:
        """Constructor timeout overrides are respected."""
        client = WhatsAppAPIClient(
            token="t",
            phone_number_id="123",
            request_timeout=7.5,
            upload_timeout=11.0,
        )

        assert client.request_timeout == 7.5
        assert client.upload_timeout == 11.0

    def test_send_message_passes_timeout(self) -> None:
        """send_message must pass the configured request timeout to requests."""
        client = WhatsAppAPIClient(
            token="t", phone_number_id="123", request_timeout=12.0
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"messages": [{"id": "wamid.X"}]}

        with patch("requests.post", return_value=mock_response) as mock_post:
            client.send_message("1234567890", "hi")

            assert mock_post.call_args.kwargs["timeout"] == 12.0

    def test_upload_media_passes_upload_timeout(self, tmp_path) -> None:
        """upload_media must use the (larger) upload timeout."""
        media_file = tmp_path / "audio.mp3"
        media_file.write_bytes(b"fake-audio-bytes")
        client = WhatsAppAPIClient(
            token="t", phone_number_id="123", upload_timeout=45.0
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "media-123"}

        with patch("requests.post", return_value=mock_response) as mock_post:
            result = client.upload_media(str(media_file))

            assert result == {"id": "media-123"}
            assert mock_post.call_args.kwargs["timeout"] == 45.0

    def test_send_message_timeout_returns_none(self) -> None:
        """A timeout during send_message degrades to None (no exception)."""
        client = WhatsAppAPIClient(token="t", phone_number_id="123")

        with patch("requests.post", side_effect=requests.Timeout("timed out")):
            result = client.send_message("1234567890", "hi")

        assert result is None

    def test_send_button_timeout_returns_error_dict(self) -> None:
        """A timeout during a dict-returning call returns an error shape, not a raise."""
        client = WhatsAppAPIClient(token="t", phone_number_id="123")
        button = {"action": {"button": "Go", "sections": []}}

        with patch("requests.post", side_effect=requests.ConnectionError("boom")):
            result = client.send_button("1234567890", button)

        assert isinstance(result, dict)
        assert result.get("error") is not None

    def test_upload_media_timeout_returns_none(self, tmp_path) -> None:
        """A timeout during upload_media degrades to None (no exception)."""
        media_file = tmp_path / "audio.mp3"
        media_file.write_bytes(b"fake-audio-bytes")
        client = WhatsAppAPIClient(token="t", phone_number_id="123")

        with patch("requests.post", side_effect=requests.Timeout("slow upload")):
            result = client.upload_media(str(media_file))

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
            client.send_audio("1234567890", "media-id-123", link=False)

            call_data = mock_post.call_args.kwargs["json"]
            assert "id" in call_data["audio"]

    def test_send_image_with_caption(self) -> None:
        """Test sending image with caption."""
        client = WhatsAppAPIClient(token="test-token", phone_number_id="123456")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"messages": [{"id": "wamid.image123"}]}

        with patch("requests.post", return_value=mock_response) as mock_post:
            client.send_image(
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


class TestWhatsAppReplyContext:
    """2C: optional reply context (Meta context.message_id)."""

    def test_send_message_includes_context_when_provided(self) -> None:
        client = WhatsAppAPIClient(token="t", phone_number_id="123")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"messages": [{"id": "wamid.X"}]}
        with patch("requests.post", return_value=mock_response) as mock_post:
            client.send_message("123", "hi", context_message_id="wamid.IN")
            body = mock_post.call_args.kwargs["json"]
            assert body["context"] == {"message_id": "wamid.IN"}

    def test_send_message_omits_context_when_not_provided(self) -> None:
        client = WhatsAppAPIClient(token="t", phone_number_id="123")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"messages": [{"id": "wamid.X"}]}
        with patch("requests.post", return_value=mock_response) as mock_post:
            client.send_message("123", "hi")
            assert "context" not in mock_post.call_args.kwargs["json"]

    def test_send_audio_includes_context_when_provided(self) -> None:
        client = WhatsAppAPIClient(token="t", phone_number_id="123")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"messages": [{"id": "wamid.A"}]}
        with patch("requests.post", return_value=mock_response) as mock_post:
            client.send_audio("123", "MID", link=False, context_message_id="wamid.IN")
            body = mock_post.call_args.kwargs["json"]
            assert body["context"] == {"message_id": "wamid.IN"}
            assert body["audio"] == {"id": "MID"}

    def test_contextual_send_message_falls_back_to_plain(self) -> None:
        """A failed contextual send retries once without context."""
        client = WhatsAppAPIClient(token="t", phone_number_id="123")
        fail = MagicMock()
        fail.status_code = 400
        fail.text = "bad context"
        ok = MagicMock()
        ok.status_code = 200
        ok.json.return_value = {"messages": [{"id": "wamid.OK"}]}
        with patch("requests.post", side_effect=[fail, ok]) as mock_post:
            result = client.send_message("123", "hi", context_message_id="stale")
            assert result == "wamid.OK"
            assert mock_post.call_count == 2
            # First attempt had context, retry dropped it.
            assert "context" in mock_post.call_args_list[0].kwargs["json"]
            assert "context" not in mock_post.call_args_list[1].kwargs["json"]

    def test_contextual_send_audio_falls_back_to_plain(self) -> None:
        client = WhatsAppAPIClient(token="t", phone_number_id="123")
        fail = MagicMock()
        fail.status_code = 400
        fail.text = "bad context"
        ok = MagicMock()
        ok.status_code = 200
        ok.json.return_value = {"messages": [{"id": "wamid.OK"}]}
        with patch("requests.post", side_effect=[fail, ok]) as mock_post:
            client.send_audio("123", "MID", link=False, context_message_id="stale")
            assert mock_post.call_count == 2
            assert "context" in mock_post.call_args_list[0].kwargs["json"]
            assert "context" not in mock_post.call_args_list[1].kwargs["json"]
