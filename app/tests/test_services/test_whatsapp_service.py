"""
Tests for WhatsApp Business Service Module.

This module contains unit tests for the WhatsAppBusinessService class
and helper classes defined in app/services/whatsapp_service.py.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.whatsapp_service import (
    InteractiveButtonBuilder,
    MessageType,
    ProcessingResult,
    ResponseType,
    WebhookParser,
    WhatsAppBusinessService,
    clear_processed_messages,
    get_whatsapp_service,
    reset_whatsapp_service,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def sample_text_payload() -> dict:
    """Create a sample text message webhook payload."""
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "123456789",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "256123456789",
                                "phone_number_id": "123456789",
                            },
                            "contacts": [
                                {
                                    "profile": {"name": "John Doe"},
                                    "wa_id": "256987654321",
                                }
                            ],
                            "messages": [
                                {
                                    "from": "256987654321",
                                    "id": "wamid.HBgL1234567890",
                                    "timestamp": "1234567890",
                                    "text": {"body": "Hello, World!"},
                                    "type": "text",
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }


@pytest.fixture
def sample_audio_payload() -> dict:
    """Create a sample audio message webhook payload."""
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "123456789"},
                            "contacts": [
                                {"profile": {"name": "John"}, "wa_id": "256987654321"}
                            ],
                            "messages": [
                                {
                                    "from": "256987654321",
                                    "id": "wamid.audio123",
                                    "timestamp": "1234567890",
                                    "audio": {
                                        "id": "media-id-123",
                                        "mime_type": "audio/ogg",
                                    },
                                    "type": "audio",
                                }
                            ],
                        }
                    }
                ]
            }
        ],
    }


@pytest.fixture
def sample_reaction_payload() -> dict:
    """Create a sample reaction webhook payload."""
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [{"wa_id": "256987654321"}],
                            "messages": [
                                {
                                    "id": "wamid.reaction123",
                                    "reaction": {
                                        "message_id": "wamid.orig123",
                                        "emoji": "👍",
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }


@pytest.fixture
def sample_interactive_payload() -> dict:
    """Create a sample interactive response webhook payload."""
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [
                                {"profile": {"name": "John"}, "wa_id": "256987654321"}
                            ],
                            "messages": [
                                {
                                    "id": "wamid.interactive123",
                                    "interactive": {
                                        "list_reply": {
                                            "id": "row 1",
                                            "title": "Get Help",
                                        }
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }


# =============================================================================
# WebhookParser Tests
# =============================================================================


class TestWebhookParser:
    """Tests for WebhookParser helper class."""

    def test_get_mobile(self, sample_text_payload: dict) -> None:
        """Test extracting mobile number from payload."""
        result = WebhookParser.get_mobile(sample_text_payload)

        assert result == "256987654321"

    def test_get_mobile_invalid_payload(self) -> None:
        """Test get_mobile with invalid payload."""
        result = WebhookParser.get_mobile({})

        assert result is None

    def test_get_name(self, sample_text_payload: dict) -> None:
        """Test extracting sender name from payload."""
        result = WebhookParser.get_name(sample_text_payload)

        assert result == "John Doe"

    def test_get_message_text(self, sample_text_payload: dict) -> None:
        """Test extracting message text from payload."""
        result = WebhookParser.get_message_text(sample_text_payload)

        assert result == "Hello, World!"

    def test_get_message_id(self, sample_text_payload: dict) -> None:
        """Test extracting message ID from payload."""
        result = WebhookParser.get_message_id(sample_text_payload)

        assert result == "wamid.HBgL1234567890"

    def test_get_phone_number_id(self, sample_text_payload: dict) -> None:
        """Test extracting phone number ID from metadata."""
        result = WebhookParser.get_phone_number_id(sample_text_payload)

        assert result == "123456789"

    def test_get_message_type_text(self, sample_text_payload: dict) -> None:
        """Test detecting text message type."""
        result = WebhookParser.get_message_type(sample_text_payload)

        assert result == MessageType.TEXT

    def test_get_message_type_audio(self, sample_audio_payload: dict) -> None:
        """Test detecting audio message type."""
        result = WebhookParser.get_message_type(sample_audio_payload)

        assert result == MessageType.AUDIO

    def test_get_message_type_reaction(self, sample_reaction_payload: dict) -> None:
        """Test detecting reaction message type."""
        result = WebhookParser.get_message_type(sample_reaction_payload)

        assert result == MessageType.REACTION

    def test_get_message_type_interactive(
        self, sample_interactive_payload: dict
    ) -> None:
        """Test detecting interactive message type."""
        result = WebhookParser.get_message_type(sample_interactive_payload)

        assert result == MessageType.INTERACTIVE

    def test_get_reaction(self, sample_reaction_payload: dict) -> None:
        """Test extracting reaction data."""
        result = WebhookParser.get_reaction(sample_reaction_payload)

        assert result is not None
        assert result["emoji"] == "👍"
        assert result["message_id"] == "wamid.orig123"

    def test_get_interactive_response(self, sample_interactive_payload: dict) -> None:
        """Test extracting interactive response data."""
        result = WebhookParser.get_interactive_response(sample_interactive_payload)

        assert result is not None
        assert "list_reply" in result

    def test_get_audio_info(self, sample_audio_payload: dict) -> None:
        """Test extracting audio information."""
        result = WebhookParser.get_audio_info(sample_audio_payload)

        assert result is not None
        assert result["id"] == "media-id-123"
        assert result["mime_type"] == "audio/ogg"

    def test_is_valid_payload_with_messages(self, sample_text_payload: dict) -> None:
        """Test validating payload with messages."""
        result = WebhookParser.is_valid_payload(sample_text_payload)

        assert result is True

    def test_is_valid_payload_empty(self) -> None:
        """Test validating empty payload."""
        result = WebhookParser.is_valid_payload({})

        assert result is False


# =============================================================================
# InteractiveButtonBuilder Tests
# =============================================================================


class TestInteractiveButtonBuilder:
    """Tests for InteractiveButtonBuilder class."""

    def test_create_welcome_button(self) -> None:
        """Test creating welcome button configuration."""
        button = InteractiveButtonBuilder.create_welcome_button()

        assert "header" in button
        assert "Sunflower" in button["header"]
        assert "body" in button
        assert "action" in button
        assert len(button["action"]["sections"]) > 0

    def test_create_language_selection_button(self) -> None:
        """Test creating language selection button."""
        button = InteractiveButtonBuilder.create_language_selection_button()

        assert "Language" in button["header"]
        rows = button["action"]["sections"][0]["rows"]
        assert len(rows) == len(InteractiveButtonBuilder.LANGUAGE_MAPPING)

    def test_create_feedback_button(self) -> None:
        """Test creating feedback button."""
        button = InteractiveButtonBuilder.create_feedback_button()

        assert "Feedback" in button["header"]
        rows = button["action"]["sections"][0]["rows"]
        titles = [r["title"] for r in rows]
        assert "Excellent" in titles
        assert "Good" in titles
        assert "Fair" in titles
        assert "Poor" in titles

    def test_language_mapping_contains_expected_languages(self) -> None:
        """Test that language mapping has expected languages."""
        mapping = InteractiveButtonBuilder.LANGUAGE_MAPPING

        assert "lug" in mapping  # Luganda
        assert "eng" in mapping  # English
        assert "ach" in mapping  # Acholi
        assert mapping["lug"] == "Luganda"


# =============================================================================
# ProcessingResult Tests
# =============================================================================


class TestProcessingResult:
    """Tests for ProcessingResult dataclass."""

    def test_default_values(self) -> None:
        """Test ProcessingResult default values."""
        result = ProcessingResult(message="Test", response_type=ResponseType.TEXT)

        assert result.message == "Test"
        assert result.response_type == ResponseType.TEXT
        assert result.template_name == ""
        assert result.should_save is True
        assert result.processing_time == 0.0

    def test_custom_values(self) -> None:
        """Test ProcessingResult with custom values."""
        result = ProcessingResult(
            message="",
            response_type=ResponseType.TEMPLATE,
            template_name="welcome",
            should_save=False,
            processing_time=1.5,
        )

        assert result.template_name == "welcome"
        assert result.should_save is False
        assert result.processing_time == 1.5


# =============================================================================
# WhatsAppBusinessService Tests
# =============================================================================


class TestWhatsAppBusinessServiceInitialization:
    """Tests for WhatsAppBusinessService initialization."""

    def test_default_initialization(self) -> None:
        """Test service initialization with defaults."""
        with patch.dict(
            "os.environ",
            {"WHATSAPP_TOKEN": "test-token", "PHONE_NUMBER_ID": "123456"},
        ):
            service = WhatsAppBusinessService()

            assert service.api_client is not None
            assert (
                service.system_message == WhatsAppBusinessService.DEFAULT_SYSTEM_MESSAGE
            )

    def test_custom_api_client(self) -> None:
        """Test service with custom API client."""
        mock_client = MagicMock()
        service = WhatsAppBusinessService(api_client=mock_client)

        assert service.api_client is mock_client

    def test_custom_system_message(self) -> None:
        """Test service with custom system message."""
        service = WhatsAppBusinessService(
            api_client=MagicMock(), system_message="Custom message"
        )

        assert service.system_message == "Custom message"


class TestWhatsAppBusinessServiceProcessMessage:
    """Tests for process_message method."""

    @pytest.mark.asyncio
    async def test_process_text_message_help(self, sample_text_payload: dict) -> None:
        """Test processing help command."""
        clear_processed_messages()
        sample_text_payload["entry"][0]["changes"][0]["value"]["messages"][0]["text"][
            "body"
        ] = "help"

        mock_client = MagicMock()
        service = WhatsAppBusinessService(api_client=mock_client)

        result = await service.process_message(
            payload=sample_text_payload,
            from_number="256987654321",
            sender_name="John",
            target_language="eng",
            phone_number_id="123456",
        )

        assert result.response_type == ResponseType.TEXT
        assert "Commands" in result.message

    @pytest.mark.asyncio
    async def test_process_text_message_greeting(
        self, sample_text_payload: dict
    ) -> None:
        """Test processing greeting message."""
        clear_processed_messages()
        sample_text_payload["entry"][0]["changes"][0]["value"]["messages"][0]["text"][
            "body"
        ] = "hello"

        mock_client = MagicMock()
        service = WhatsAppBusinessService(api_client=mock_client)

        result = await service.process_message(
            payload=sample_text_payload,
            from_number="256987654321",
            sender_name="John",
            target_language="eng",
            phone_number_id="123456",
        )

        assert result.response_type == ResponseType.TEMPLATE
        assert result.template_name == "welcome_message"

    @pytest.mark.asyncio
    async def test_process_unsupported_message(self) -> None:
        """Test processing unsupported message type."""
        clear_processed_messages()
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "contacts": [
                                    {"wa_id": "123", "profile": {"name": "John"}}
                                ],
                                "messages": [
                                    {
                                        "id": "wamid.image123",
                                        "image": {"id": "media-123"},
                                    }
                                ],
                            }
                        }
                    ]
                }
            ]
        }

        mock_client = MagicMock()
        service = WhatsAppBusinessService(api_client=mock_client)

        result = await service.process_message(
            payload=payload,
            from_number="256123456789",
            sender_name="John",
            target_language="eng",
            phone_number_id="123456",
        )

        assert result.response_type == ResponseType.TEXT
        assert "only support text and audio" in result.message

    @pytest.mark.asyncio
    async def test_duplicate_message_skipped(self, sample_text_payload: dict) -> None:
        """Test that duplicate messages are skipped."""
        clear_processed_messages()
        mock_client = MagicMock()
        service = WhatsAppBusinessService(api_client=mock_client)

        # Process first time
        result1 = await service.process_message(
            payload=sample_text_payload,
            from_number="256987654321",
            sender_name="John",
            target_language="eng",
            phone_number_id="123456",
        )

        # Process same message again
        result2 = await service.process_message(
            payload=sample_text_payload,
            from_number="256987654321",
            sender_name="John",
            target_language="eng",
            phone_number_id="123456",
        )

        assert result2.response_type == ResponseType.SKIP

    @pytest.mark.asyncio
    async def test_process_reaction(self, sample_reaction_payload: dict) -> None:
        """Test processing reaction message."""
        clear_processed_messages()
        mock_client = MagicMock()
        service = WhatsAppBusinessService(api_client=mock_client)

        with patch.object(
            service, "_save_reaction_feedback_async", new_callable=AsyncMock
        ):
            result = await service.process_message(
                payload=sample_reaction_payload,
                from_number="256987654321",
                sender_name="John",
                target_language="eng",
                phone_number_id="123456",
            )

            assert result.response_type == ResponseType.TEMPLATE
            assert result.template_name == "custom_feedback"

    @pytest.mark.asyncio
    async def test_process_interactive_help(
        self, sample_interactive_payload: dict
    ) -> None:
        """Test processing interactive help selection."""
        clear_processed_messages()
        mock_client = MagicMock()
        service = WhatsAppBusinessService(api_client=mock_client)

        result = await service.process_message(
            payload=sample_interactive_payload,
            from_number="256987654321",
            sender_name="John",
            target_language="eng",
            phone_number_id="123456",
        )

        assert result.response_type == ResponseType.TEXT
        # Help command should return help text
        assert "Commands" in result.message


class TestWhatsAppBusinessServiceQuickCommands:
    """Tests for quick command handling."""

    def test_handle_help_command(self) -> None:
        """Test help command recognition."""
        service = WhatsAppBusinessService(api_client=MagicMock())

        result = service._handle_quick_commands("help", "eng", "John")

        assert result is not None
        assert result.response_type == ResponseType.TEXT
        assert "Commands" in result.message

    def test_handle_status_command(self) -> None:
        """Test status command recognition."""
        service = WhatsAppBusinessService(api_client=MagicMock())

        result = service._handle_quick_commands("status", "lug", "John")

        assert result is not None
        assert "Status" in result.message
        assert "Luganda" in result.message

    def test_handle_languages_command(self) -> None:
        """Test languages command recognition."""
        service = WhatsAppBusinessService(api_client=MagicMock())

        result = service._handle_quick_commands("languages", "eng", "John")

        assert result is not None
        assert "Supported Languages" in result.message

    def test_handle_set_language_command(self) -> None:
        """Test set language command recognition."""
        service = WhatsAppBusinessService(api_client=MagicMock())

        result = service._handle_quick_commands("set language", "eng", "John")

        assert result is not None
        assert result.response_type == ResponseType.TEMPLATE
        assert result.template_name == "choose_language"

    def test_non_command_returns_none(self) -> None:
        """Test that non-commands return None."""
        service = WhatsAppBusinessService(api_client=MagicMock())

        result = service._handle_quick_commands("translate this text", "eng", "John")

        assert result is None


class TestWhatsAppBusinessServiceTextGenerators:
    """Tests for text response generators."""

    def test_get_help_text(self) -> None:
        """Test help text generation."""
        service = WhatsAppBusinessService(api_client=MagicMock())

        text = service._get_help_text()

        assert "Sunflower" in text
        assert "Commands" in text
        assert "help" in text.lower()

    def test_get_status_text(self) -> None:
        """Test status text generation."""
        service = WhatsAppBusinessService(api_client=MagicMock())

        text = service._get_status_text("lug", "John")

        assert "John" in text
        assert "Luganda" in text

    def test_get_languages_text(self) -> None:
        """Test languages text generation."""
        service = WhatsAppBusinessService(api_client=MagicMock())

        text = service._get_languages_text()

        assert "Supported Languages" in text
        assert "Luganda" in text
        assert "English" in text


class TestWhatsAppBusinessServiceConvenience:
    """Tests for convenience wrapper methods."""

    def test_send_message_calls_api_client(self) -> None:
        """Test that send_message calls API client."""
        mock_client = MagicMock()
        mock_client.send_message.return_value = "wamid.123"
        service = WhatsAppBusinessService(api_client=mock_client)

        result = service.send_message("256123456789", "Hello!")

        mock_client.send_message.assert_called_once()
        assert result == "wamid.123"

    def test_send_button_calls_api_client(self) -> None:
        """Test that send_button calls API client."""
        mock_client = MagicMock()
        mock_client.send_button.return_value = {"messages": []}
        service = WhatsAppBusinessService(api_client=mock_client)

        button = {"header": "Test", "body": "Test"}
        service.send_button("256123456789", button)

        mock_client.send_button.assert_called_once()

    def test_send_template_calls_api_client(self) -> None:
        """Test that send_template calls API client."""
        mock_client = MagicMock()
        mock_client.send_template.return_value = {"messages": []}
        service = WhatsAppBusinessService(api_client=mock_client)

        service.send_template("256123456789", "welcome")

        mock_client.send_template.assert_called_once()


class TestWhatsAppBusinessServiceSingleton:
    """Tests for singleton pattern."""

    def test_get_whatsapp_service_creates_singleton(self) -> None:
        """Test that get_whatsapp_service returns the same instance."""
        reset_whatsapp_service()

        with patch.dict(
            "os.environ",
            {"WHATSAPP_TOKEN": "test-token", "PHONE_NUMBER_ID": "123456"},
        ):
            service1 = get_whatsapp_service()
            service2 = get_whatsapp_service()

            assert service1 is service2

    def test_reset_whatsapp_service_clears_singleton(self) -> None:
        """Test that reset_whatsapp_service clears the singleton."""
        reset_whatsapp_service()

        with patch.dict(
            "os.environ",
            {"WHATSAPP_TOKEN": "test-token", "PHONE_NUMBER_ID": "123456"},
        ):
            service1 = get_whatsapp_service()
            reset_whatsapp_service()
            service2 = get_whatsapp_service()

            assert service1 is not service2


class TestEnumsAndDataClasses:
    """Tests for enums and data classes."""

    def test_message_type_values(self) -> None:
        """Test MessageType enum values."""
        assert MessageType.TEXT.value == "text"
        assert MessageType.AUDIO.value == "audio"
        assert MessageType.REACTION.value == "reaction"
        assert MessageType.INTERACTIVE.value == "interactive"
        assert MessageType.UNSUPPORTED.value == "unsupported"

    def test_response_type_values(self) -> None:
        """Test ResponseType enum values."""
        assert ResponseType.TEXT.value == "text"
        assert ResponseType.TEMPLATE.value == "template"
        assert ResponseType.BUTTON.value == "button"
        assert ResponseType.SKIP.value == "skip"
