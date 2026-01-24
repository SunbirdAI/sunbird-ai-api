"""
WhatsApp Business Service Module.

This module provides the business logic layer for WhatsApp messaging operations.
It handles message processing, webhook payload parsing, and conversation management
for the Sunbird AI translation and transcription bot.

The service supports:
    - Message processing (text, audio, reactions, interactive)
    - Webhook payload parsing and validation
    - Interactive button creation (welcome, language selection, feedback)
    - Conversation context management
    - User preference handling

Architecture:
    Routers -> WhatsAppBusinessService -> WhatsAppAPIClient -> Meta Graph API
                                       -> UserPreference (Firebase)
                                       -> RunPod (ML inference)

Usage:
    from app.services.whatsapp_service import (
        WhatsAppBusinessService,
        get_whatsapp_service,
    )

    # Using the singleton
    service = get_whatsapp_service()
    result = await service.process_message(payload, from_number, sender_name, ...)

    # Or create a custom instance
    service = WhatsAppBusinessService()
    result = await service.process_message(...)

Example:
    >>> service = get_whatsapp_service()
    >>> result = await service.process_message(
    ...     payload=webhook_payload,
    ...     from_number="256123456789",
    ...     sender_name="John",
    ...     target_language="lug",
    ...     phone_number_id="123456789"
    ... )
    >>> print(result.message)
    "Hello John! How can I help you today?"
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from app.integrations.whatsapp_api import WhatsAppAPIClient, get_whatsapp_api_client
from app.services.base import BaseService

# Module-level logger
logger = logging.getLogger(__name__)

# Message tracking to prevent duplicates
_processed_messages: Set[str] = set()


class MessageType(Enum):
    """Types of WhatsApp messages that can be received."""

    TEXT = "text"
    AUDIO = "audio"
    UNSUPPORTED = "unsupported"
    REACTION = "reaction"
    INTERACTIVE = "interactive"


class ResponseType(Enum):
    """Types of responses that can be sent back."""

    TEXT = "text"
    TEMPLATE = "template"
    BUTTON = "button"
    SKIP = "skip"


@dataclass
class ProcessingResult:
    """Result of processing a WhatsApp message.

    Attributes:
        message: The response message to send.
        response_type: Type of response (text, template, button, skip).
        template_name: Name of template if response_type is TEMPLATE.
        should_save: Whether to save this interaction to database.
        processing_time: Time taken to process in seconds.
    """

    message: str
    response_type: ResponseType
    template_name: str = ""
    should_save: bool = True
    processing_time: float = 0.0


class WebhookParser:
    """Static helper class for parsing WhatsApp webhook payloads.

    This class provides methods to extract various fields from
    WhatsApp webhook payloads without making any API calls.

    Example:
        >>> payload = {"entry": [{"changes": [...]}]}
        >>> mobile = WebhookParser.get_mobile(payload)
        >>> message = WebhookParser.get_message_text(payload)
    """

    @staticmethod
    def preprocess(data: Dict) -> Dict:
        """Extract the value object from webhook data.

        Args:
            data: Raw webhook payload.

        Returns:
            The nested 'value' dictionary.
        """
        return data["entry"][0]["changes"][0]["value"]

    @staticmethod
    def is_valid_payload(payload: Dict) -> bool:
        """Check if a webhook payload is valid and contains messages.

        Args:
            payload: The webhook payload to validate.

        Returns:
            True if valid, False otherwise.
        """
        if "object" in payload and "entry" in payload:
            for entry in payload["entry"]:
                if "changes" in entry:
                    for change in entry["changes"]:
                        if "value" in change:
                            if (
                                "messages" in change["value"]
                                or "statuses" in change["value"]
                            ):
                                return True
        return False

    @staticmethod
    def get_mobile(data: Dict) -> Optional[str]:
        """Extract the sender's mobile number.

        Args:
            data: Webhook payload.

        Returns:
            Mobile number (wa_id) or None.
        """
        try:
            value = WebhookParser.preprocess(data)
            if "contacts" in value:
                return value["contacts"][0]["wa_id"]
        except (KeyError, IndexError):
            pass
        return None

    @staticmethod
    def get_name(data: Dict) -> Optional[str]:
        """Extract the sender's name.

        Args:
            data: Webhook payload.

        Returns:
            Sender's name or None.
        """
        try:
            value = WebhookParser.preprocess(data)
            if value:
                return value["contacts"][0]["profile"]["name"]
        except (KeyError, IndexError):
            pass
        return None

    @staticmethod
    def get_message_text(data: Dict) -> Optional[str]:
        """Extract the text message content.

        Args:
            data: Webhook payload.

        Returns:
            Text message body or None.
        """
        try:
            value = WebhookParser.preprocess(data)
            if "messages" in value:
                return value["messages"][0]["text"]["body"]
        except (KeyError, IndexError):
            pass
        return None

    @staticmethod
    def get_message_id(data: Dict) -> Optional[str]:
        """Extract the message ID.

        Args:
            data: Webhook payload.

        Returns:
            Message ID or None.
        """
        try:
            value = WebhookParser.preprocess(data)
            if "messages" in value:
                return value["messages"][0]["id"]
        except (KeyError, IndexError):
            pass
        return None

    @staticmethod
    def get_phone_number_id(data: Dict) -> Optional[str]:
        """Extract the phone number ID from metadata.

        Args:
            data: Webhook payload.

        Returns:
            Phone number ID or None.
        """
        try:
            return data["entry"][0]["changes"][0]["value"]["metadata"][
                "phone_number_id"
            ]
        except (KeyError, IndexError):
            return None

    @staticmethod
    def get_message_type(data: Dict) -> MessageType:
        """Determine the type of message received.

        Args:
            data: Webhook payload.

        Returns:
            MessageType enum value.
        """
        try:
            messages = data["entry"][0]["changes"][0]["value"]["messages"]
            message = messages[0]

            if "reaction" in message:
                return MessageType.REACTION
            elif "interactive" in message:
                return MessageType.INTERACTIVE
            elif "audio" in message:
                return MessageType.AUDIO
            elif any(
                key in message for key in ["image", "video", "document", "location"]
            ):
                return MessageType.UNSUPPORTED
            else:
                return MessageType.TEXT
        except (KeyError, IndexError):
            return MessageType.TEXT

    @staticmethod
    def get_reaction(data: Dict) -> Optional[Dict]:
        """Extract reaction data from the message.

        Args:
            data: Webhook payload.

        Returns:
            Reaction dict with 'message_id' and 'emoji', or None.
        """
        try:
            message = data["entry"][0]["changes"][0]["value"]["messages"][0]
            return message.get("reaction")
        except (KeyError, IndexError):
            return None

    @staticmethod
    def get_interactive_response(data: Dict) -> Optional[Dict]:
        """Extract interactive response data.

        Args:
            data: Webhook payload.

        Returns:
            Interactive response dict or None.
        """
        try:
            message = data["entry"][0]["changes"][0]["value"]["messages"][0]
            return message.get("interactive")
        except (KeyError, IndexError):
            return None

    @staticmethod
    def get_audio_info(data: Dict) -> Optional[Dict]:
        """Extract audio message information.

        Args:
            data: Webhook payload.

        Returns:
            Dict with 'id' and 'mime_type', or None.
        """
        try:
            message = data["entry"][0]["changes"][0]["value"]["messages"][0]
            if "audio" in message:
                return {
                    "id": message["audio"]["id"],
                    "mime_type": message["audio"]["mime_type"],
                }
        except (KeyError, IndexError):
            pass
        return None

    @staticmethod
    def get_image(data: Dict) -> Optional[Dict]:
        """Extract image data from the message.

        Args:
            data: Webhook payload.

        Returns:
            Image dict or None.
        """
        try:
            value = WebhookParser.preprocess(data)
            if "messages" in value and "image" in value["messages"][0]:
                return value["messages"][0]["image"]
        except (KeyError, IndexError):
            pass
        return None

    @staticmethod
    def get_video(data: Dict) -> Optional[Dict]:
        """Extract video data from the message.

        Args:
            data: Webhook payload.

        Returns:
            Video dict or None.
        """
        try:
            value = WebhookParser.preprocess(data)
            if "messages" in value and "video" in value["messages"][0]:
                return value["messages"][0]["video"]
        except (KeyError, IndexError):
            pass
        return None

    @staticmethod
    def get_document(data: Dict) -> Optional[Dict]:
        """Extract document data from the message.

        Args:
            data: Webhook payload.

        Returns:
            Document dict or None.
        """
        try:
            value = WebhookParser.preprocess(data)
            if "messages" in value and "document" in value["messages"][0]:
                return value["messages"][0]["document"]
        except (KeyError, IndexError):
            pass
        return None

    @staticmethod
    def get_location(data: Dict) -> Optional[Dict]:
        """Extract location data from the message.

        Args:
            data: Webhook payload.

        Returns:
            Location dict or None.
        """
        try:
            value = WebhookParser.preprocess(data)
            if "messages" in value and "location" in value["messages"][0]:
                return value["messages"][0]["location"]
        except (KeyError, IndexError):
            pass
        return None

    @staticmethod
    def get_timestamp(data: Dict) -> Optional[str]:
        """Extract the message timestamp.

        Args:
            data: Webhook payload.

        Returns:
            Timestamp string or None.
        """
        try:
            value = WebhookParser.preprocess(data)
            if "messages" in value:
                return value["messages"][0]["timestamp"]
        except (KeyError, IndexError):
            pass
        return None

    @staticmethod
    def get_delivery_status(data: Dict) -> Optional[str]:
        """Extract delivery status from the message.

        Args:
            data: Webhook payload.

        Returns:
            Status string or None.
        """
        try:
            value = WebhookParser.preprocess(data)
            if "statuses" in value:
                return value["statuses"][0]["status"]
        except (KeyError, IndexError):
            pass
        return None

    @staticmethod
    def get_changed_field(data: Dict) -> Optional[str]:
        """Get the changed field from webhook data.

        Args:
            data: Webhook payload.

        Returns:
            Changed field name or None.
        """
        try:
            return data["entry"][0]["changes"][0]["field"]
        except (KeyError, IndexError):
            return None


class InteractiveButtonBuilder:
    """Builder class for creating WhatsApp interactive buttons.

    This class provides methods to create various interactive button
    configurations for WhatsApp messages.

    Example:
        >>> builder = InteractiveButtonBuilder()
        >>> welcome_btn = builder.create_welcome_button()
        >>> api_client.send_button(recipient_id, welcome_btn)
    """

    LANGUAGE_MAPPING = {
        "lug": "Luganda",
        "ach": "Acholi",
        "teo": "Ateso",
        "lgg": "Lugbara",
        "nyn": "Runyankole",
        "eng": "English",
    }

    @classmethod
    def create_welcome_button(cls) -> Dict[str, Any]:
        """Create a welcome button for new users.

        Returns:
            Button configuration dict.
        """
        return {
            "header": "🌻 Welcome to Sunflower!",
            "body": "I'm your multilingual assistant for Ugandan languages. What would you like to do first?",
            "footer": "Made with ❤️ by Sunbird AI",
            "action": {
                "button": "Get Started",
                "sections": [
                    {
                        "title": "Quick Actions",
                        "rows": [
                            {
                                "id": "row 1",
                                "title": "Get Help",
                                "description": "📚 Learn what I can do for you",
                            },
                            {
                                "id": "row 2",
                                "title": "Set Language",
                                "description": "🌐 Choose language for your audio commands",
                            },
                            {
                                "id": "row 3",
                                "title": "Start Chatting",
                                "description": "💬 Begin our conversation",
                            },
                        ],
                    }
                ],
            },
        }

    @classmethod
    def create_language_selection_button(cls) -> Dict[str, Any]:
        """Create a language selection button.

        Returns:
            Button configuration dict.
        """
        language_rows = []
        for i, (code, name) in enumerate(cls.LANGUAGE_MAPPING.items(), 1):
            language_rows.append(
                {
                    "id": f"row {i}",
                    "title": name,
                    "description": f"Set your preferred language to {name}",
                }
            )

        return {
            "header": "🌐 Language Selection",
            "body": "Please select your preferred language for your audio commands:",
            "footer": "Powered by Sunbird AI 🌻",
            "action": {
                "button": "Select Language",
                "sections": [{"title": "Available Languages", "rows": language_rows}],
            },
        }

    @classmethod
    def create_feedback_button(cls) -> Dict[str, Any]:
        """Create a feedback collection button.

        Returns:
            Button configuration dict.
        """
        return {
            "header": "📝 Feedback",
            "body": "How was my response? Your feedback helps me improve!",
            "footer": "Thank you for helping Sunflower grow 🌻",
            "action": {
                "button": "Rate Response",
                "sections": [
                    {
                        "title": "Response Quality",
                        "rows": [
                            {
                                "id": "row 1",
                                "title": "Excellent",
                                "description": "🌟 Very helpful response!",
                            },
                            {
                                "id": "row 2",
                                "title": "Good",
                                "description": "😊 Helpful response",
                            },
                            {
                                "id": "row 3",
                                "title": "Fair",
                                "description": "👌 Somewhat helpful",
                            },
                            {
                                "id": "row 4",
                                "title": "Poor",
                                "description": "👎 Not helpful",
                            },
                        ],
                    }
                ],
            },
        }


class WhatsAppBusinessService(BaseService):
    """Business service for WhatsApp messaging operations.

    This service handles the business logic for processing WhatsApp messages,
    including text, audio, reactions, and interactive responses.

    Attributes:
        api_client: The WhatsApp API client for sending messages.
        language_mapping: Mapping of language codes to names.
        system_message: Default system message for AI responses.

    Example:
        >>> service = WhatsAppBusinessService()
        >>> result = await service.process_message(
        ...     payload=webhook_data,
        ...     from_number="256123456789",
        ...     sender_name="John",
        ...     target_language="lug",
        ...     phone_number_id="123456789"
        ... )
    """

    LANGUAGE_MAPPING = {
        "lug": "Luganda",
        "ach": "Acholi",
        "teo": "Ateso",
        "lgg": "Lugbara",
        "nyn": "Runyankole",
        "eng": "English",
    }

    DEFAULT_SYSTEM_MESSAGE = (
        "You are Sunflower, a multilingual assistant for Ugandan languages "
        "made by Sunbird AI. You specialise in accurate translations, "
        "explanations, summaries and other cross-lingual tasks."
    )

    def __init__(
        self,
        api_client: Optional[WhatsAppAPIClient] = None,
        system_message: Optional[str] = None,
    ) -> None:
        """Initialize the WhatsApp business service.

        Args:
            api_client: WhatsApp API client. Defaults to singleton.
            system_message: Custom system message for AI. Defaults to standard.

        Example:
            >>> # Use defaults
            >>> service = WhatsAppBusinessService()

            >>> # Use custom client
            >>> custom_client = WhatsAppAPIClient(token="...", phone_number_id="...")
            >>> service = WhatsAppBusinessService(api_client=custom_client)
        """
        super().__init__()
        self.api_client = api_client or get_whatsapp_api_client()
        self.system_message = system_message or self.DEFAULT_SYSTEM_MESSAGE

    async def process_message(
        self,
        payload: Dict,
        from_number: str,
        sender_name: str,
        target_language: str,
        phone_number_id: str,
    ) -> ProcessingResult:
        """Process an incoming WhatsApp message.

        This is the main entry point for message processing. It determines
        the message type and routes to the appropriate handler.

        Args:
            payload: The webhook payload from WhatsApp.
            from_number: Sender's phone number.
            sender_name: Sender's name.
            target_language: User's preferred language code.
            phone_number_id: WhatsApp phone number ID.

        Returns:
            ProcessingResult with the response details.

        Example:
            >>> result = await service.process_message(
            ...     payload=webhook_data,
            ...     from_number="256123456789",
            ...     sender_name="John",
            ...     target_language="lug",
            ...     phone_number_id="123456789"
            ... )
            >>> if result.response_type == ResponseType.TEXT:
            ...     print(result.message)
        """
        start_time = time.time()

        try:
            message_id = WebhookParser.get_message_id(payload)
            if not message_id:
                message_id = f"unknown_{int(time.time())}"

            # Check for duplicates
            if message_id in _processed_messages:
                self.log_info(f"Duplicate message {message_id}, skipping")
                return ProcessingResult(
                    "", ResponseType.SKIP, processing_time=time.time() - start_time
                )

            _processed_messages.add(message_id)

            # Determine message type and route
            message_type = WebhookParser.get_message_type(payload)
            self.log_info(f"Processing {message_type.value} message from {from_number}")

            if message_type == MessageType.REACTION:
                result = await self._handle_reaction(payload)
            elif message_type == MessageType.INTERACTIVE:
                result = await self._handle_interactive(
                    payload, sender_name, from_number
                )
            elif message_type == MessageType.UNSUPPORTED:
                result = self._handle_unsupported(sender_name)
            elif message_type == MessageType.AUDIO:
                result = await self._handle_audio(
                    payload, target_language, from_number, sender_name, phone_number_id
                )
            else:  # TEXT
                result = await self._handle_text(
                    payload, target_language, from_number, sender_name
                )

            result.processing_time = time.time() - start_time
            self.log_info(f"Message processed in {result.processing_time:.2f}s")
            return result

        except Exception as e:
            self.log_error(f"Error processing message: {str(e)}", exc_info=True)
            return ProcessingResult(
                f"Sorry {sender_name}, I encountered an error. Please try again.",
                ResponseType.TEXT,
                processing_time=time.time() - start_time,
            )

    async def _handle_reaction(self, payload: Dict) -> ProcessingResult:
        """Handle emoji reaction messages.

        Args:
            payload: Webhook payload.

        Returns:
            ProcessingResult for reaction handling.
        """
        try:
            reaction = WebhookParser.get_reaction(payload)
            if reaction:
                message_id = reaction["message_id"]
                emoji = reaction["emoji"]

                # Save feedback asynchronously
                asyncio.create_task(
                    self._save_reaction_feedback_async(message_id, emoji)
                )

                return ProcessingResult(
                    "",
                    ResponseType.TEMPLATE,
                    template_name="custom_feedback",
                    should_save=False,
                )
        except Exception as e:
            self.log_error(f"Error handling reaction: {e}")

        return ProcessingResult("", ResponseType.SKIP)

    async def _handle_interactive(
        self,
        payload: Dict,
        sender_name: str,
        from_number: str,
    ) -> ProcessingResult:
        """Handle interactive button responses.

        Args:
            payload: Webhook payload.
            sender_name: User's name.
            from_number: User's phone number.

        Returns:
            ProcessingResult for interactive response.
        """
        try:
            interactive_response = WebhookParser.get_interactive_response(payload)
            if interactive_response:
                if "list_reply" in interactive_response:
                    return await self._handle_list_reply(
                        interactive_response["list_reply"], from_number, sender_name
                    )
                elif "button_reply" in interactive_response:
                    return await self._handle_button_reply(
                        interactive_response["button_reply"], from_number, sender_name
                    )
        except Exception as e:
            self.log_error(f"Error handling interactive response: {e}")

        return ProcessingResult(
            f"Dear {sender_name}, Thanks for that response.",
            ResponseType.TEXT,
            should_save=False,
        )

    def _handle_unsupported(self, sender_name: str) -> ProcessingResult:
        """Handle unsupported message types.

        Args:
            sender_name: User's name.

        Returns:
            ProcessingResult with unsupported message response.
        """
        return ProcessingResult(
            f"Dear {sender_name}, I currently only support text and audio messages. "
            f"\n\nPlease try again with text or voice.",
            ResponseType.TEXT,
            should_save=False,
        )

    async def _handle_audio(
        self,
        payload: Dict,
        target_language: str,
        from_number: str,
        sender_name: str,
        phone_number_id: str,
    ) -> ProcessingResult:
        """Handle audio message - return immediate acknowledgment.

        Note: Actual audio processing happens in background via
        the OptimizedMessageProcessor.

        Args:
            payload: Webhook payload.
            target_language: User's preferred language.
            from_number: User's phone number.
            sender_name: User's name.
            phone_number_id: WhatsApp phone number ID.

        Returns:
            ProcessingResult acknowledging audio receipt.
        """
        # Audio processing is handled by OptimizedMessageProcessor in background
        # This just returns an immediate acknowledgment
        return ProcessingResult(
            "Audio message received. Processing...",
            ResponseType.TEXT,
            should_save=False,
        )

    async def _handle_text(
        self,
        payload: Dict,
        target_language: str,
        from_number: str,
        sender_name: str,
    ) -> ProcessingResult:
        """Handle text message processing.

        Args:
            payload: Webhook payload.
            target_language: User's preferred language.
            from_number: User's phone number.
            sender_name: User's name.

        Returns:
            ProcessingResult with text response.
        """
        try:
            input_text = WebhookParser.get_message_text(payload) or ""

            # Check for quick commands first
            command_result = self._handle_quick_commands(
                input_text, target_language, sender_name
            )
            if command_result:
                return command_result

            # For complex processing, return template to trigger
            # OptimizedMessageProcessor handling
            return ProcessingResult(
                "",
                ResponseType.TEMPLATE,
                template_name="process_with_llm",
                should_save=True,
            )

        except Exception as e:
            self.log_error(f"Error in text processing: {str(e)}")
            return ProcessingResult(
                "I'm experiencing issues. Please try again.",
                ResponseType.TEXT,
            )

    def _handle_quick_commands(
        self,
        input_text: str,
        target_language: str,
        sender_name: str,
    ) -> Optional[ProcessingResult]:
        """Handle common commands without AI processing.

        Args:
            input_text: User's message text.
            target_language: User's preferred language.
            sender_name: User's name.

        Returns:
            ProcessingResult if command matched, None otherwise.
        """
        text_lower = input_text.lower().strip()

        # Greeting messages
        if text_lower in ["hello", "hi", "hey", "hola", "greetings"]:
            return ProcessingResult(
                "",
                ResponseType.TEMPLATE,
                template_name="welcome_message",
                should_save=False,
            )

        # Help command
        if text_lower in ["help", "commands"]:
            return ProcessingResult(self._get_help_text(), ResponseType.TEXT)

        # Status command
        if text_lower == "status":
            return ProcessingResult(
                self._get_status_text(target_language, sender_name),
                ResponseType.TEXT,
            )

        # Languages command
        if text_lower in ["languages", "language"]:
            return ProcessingResult(self._get_languages_text(), ResponseType.TEXT)

        # Set language command
        if text_lower.startswith("set language"):
            return ProcessingResult(
                "", ResponseType.TEMPLATE, template_name="choose_language"
            )

        return None

    async def _handle_list_reply(
        self,
        list_reply: Dict,
        from_number: str,
        sender_name: str,
    ) -> ProcessingResult:
        """Handle list selection responses.

        Args:
            list_reply: List reply data.
            from_number: User's phone number.
            sender_name: User's name.

        Returns:
            ProcessingResult based on selection.
        """
        selected_id = list_reply.get("id", "")
        selected_title = list_reply.get("title", "")

        # Welcome button responses
        if selected_id == "row 1" and selected_title == "Get Help":
            return ProcessingResult(self._get_help_text(), ResponseType.TEXT)

        if selected_id == "row 2" and selected_title == "Set Language":
            return ProcessingResult(
                "", ResponseType.TEMPLATE, template_name="choose_language"
            )

        if selected_id == "row 3" and selected_title == "Start Chatting":
            return ProcessingResult(
                f"Perfect {sender_name}! 🌻 I'm ready to help you with:\n\n"
                f"• Translations between Ugandan languages and English\n"
                f"• Audio transcription in local languages\n"
                f"• Language learning support\n\n"
                f"Just send me a message or audio to get started!",
                ResponseType.TEXT,
            )

        # Language selection
        if selected_title in self.LANGUAGE_MAPPING.values():
            return await self._handle_language_selection(
                selected_title, from_number, sender_name
            )

        # Feedback responses
        if selected_title in ["Excellent", "Good", "Fair", "Poor"]:
            return await self._handle_feedback(selected_title, from_number, sender_name)

        # Unknown selection
        return ProcessingResult(
            f"Thanks {sender_name}! How can I help you further?",
            ResponseType.TEXT,
        )

    async def _handle_button_reply(
        self,
        button_reply: Dict,
        from_number: str,
        sender_name: str,
    ) -> ProcessingResult:
        """Handle button reply responses.

        Args:
            button_reply: Button reply data.
            from_number: User's phone number.
            sender_name: User's name.

        Returns:
            ProcessingResult based on button clicked.
        """
        # Handle based on button ID or title
        button_id = button_reply.get("id", "")
        button_title = button_reply.get("title", "")

        self.log_info(f"Button reply: {button_id} - {button_title}")

        return ProcessingResult(
            f"Thanks {sender_name}! How can I help you further?",
            ResponseType.TEXT,
        )

    async def _handle_language_selection(
        self,
        language_name: str,
        from_number: str,
        sender_name: str,
    ) -> ProcessingResult:
        """Handle language selection from interactive button.

        Args:
            language_name: Selected language name.
            from_number: User's phone number.
            sender_name: User's name.

        Returns:
            ProcessingResult confirming language selection.
        """
        # Find language code
        language_code = None
        for code, name in self.LANGUAGE_MAPPING.items():
            if name == language_name:
                language_code = code
                break

        if not language_code:
            return ProcessingResult(
                f"Sorry {sender_name}, I couldn't find that language. Please try again.",
                ResponseType.TEXT,
            )

        # Save preference asynchronously
        asyncio.create_task(
            self._save_language_preference_async(from_number, language_code)
        )

        return ProcessingResult(
            f"✅ Perfect! Language set to {language_name}!\n\n"
            f"You can now:\n"
            f"• Send messages in {language_name} or English\n"
            f"• Ask me to translate to {language_name}\n"
            f"• Send audio in {language_name} for transcription\n\n"
            f"Just start typing or send an audio message! 🎤📝",
            ResponseType.TEXT,
        )

    async def _handle_feedback(
        self,
        feedback_title: str,
        from_number: str,
        sender_name: str,
    ) -> ProcessingResult:
        """Handle feedback selection.

        Args:
            feedback_title: Selected feedback option.
            from_number: User's phone number.
            sender_name: User's name.

        Returns:
            ProcessingResult thanking user for feedback.
        """
        feedback_responses = {
            "Excellent": (
                f"🌟 *Wonderful* {sender_name}!\n\n"
                f"Thank you for the *excellent* rating!\n"
                f"*Feel free to ask me anything else!*"
            ),
            "Good": (
                f"😊 Thank you {sender_name}!\n\n"
                f"I'm glad the response was *helpful*."
            ),
            "Fair": (
                f"👍 Thanks {sender_name} for the *honest feedback*!\n\n"
                f"I'm always *learning* and *improving*."
            ),
            "Poor": (
                f"🤔 Thank you {sender_name} for the feedback.\n\n"
                f"Please try *rephrasing your question* - I'll do my best!"
            ),
        }

        response = feedback_responses.get(
            feedback_title,
            f"Thank you {sender_name} for your feedback!",
        )

        # Save feedback asynchronously
        asyncio.create_task(
            self._save_feedback_async(from_number, feedback_title, sender_name)
        )

        return ProcessingResult(response, ResponseType.TEXT)

    # =========================================================================
    # Async Helper Methods
    # =========================================================================

    async def _save_reaction_feedback_async(self, message_id: str, emoji: str) -> None:
        """Save reaction feedback asynchronously.

        Args:
            message_id: Message being reacted to.
            emoji: Reaction emoji.
        """
        try:
            # Import here to avoid circular imports
            from app.inference_services.user_preference import update_feedback

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, update_feedback, message_id, emoji)
            self.log_info(f"Reaction feedback saved: {message_id} - {emoji}")
        except Exception as e:
            self.log_error(f"Error saving reaction feedback: {e}")

    async def _save_language_preference_async(
        self, from_number: str, language_code: str
    ) -> None:
        """Save language preference asynchronously.

        Args:
            from_number: User's phone number.
            language_code: Selected language code.
        """
        try:
            from app.inference_services.user_preference import save_user_preference

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, save_user_preference, from_number, "English", language_code
            )
            self.log_info(f"Language preference saved: {from_number} - {language_code}")
        except Exception as e:
            self.log_error(f"Error saving language preference: {e}")

    async def _save_feedback_async(
        self, from_number: str, feedback: str, sender_name: str
    ) -> None:
        """Save detailed feedback asynchronously.

        Args:
            from_number: User's phone number.
            feedback: Feedback text.
            sender_name: User's name.
        """
        try:
            from app.inference_services.user_preference import (
                save_feedback_with_context,
            )

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                save_feedback_with_context,
                from_number,
                feedback,
                sender_name,
                "button",
            )
            self.log_info(f"Feedback saved: {from_number} - {feedback}")
        except Exception as e:
            self.log_error(f"Error saving feedback: {e}")

    # =========================================================================
    # Response Text Generators
    # =========================================================================

    def _get_help_text(self) -> str:
        """Generate help text response.

        Returns:
            Formatted help text.
        """
        return (
            "*🌻 Sunflower Assistant Commands*\n\n"
            "*Basic Commands:*\n"
            "• *help* – Show this help message\n"
            "• *status* – Show your current settings\n"
            "• *languages* – Show supported languages\n\n"
            "*Language Commands:*\n"
            "• *set language* – Set your preferred language\n\n"
            "*Natural Questions:*\n"
            "You can also ask naturally:\n"
            "• *What can you do?*\n"
            "• *What languages do you support?*\n\n"
            "Just type your message normally – *I'm here to help!*"
        )

    def _get_status_text(self, target_language: str, sender_name: str) -> str:
        """Generate status text response.

        Args:
            target_language: Current language code.
            sender_name: User's name.

        Returns:
            Formatted status text.
        """
        language_name = self.LANGUAGE_MAPPING.get(target_language, target_language)
        return (
            f"*🌻 Status for {sender_name}*\n\n"
            f"*Current Language:* *{language_name}* ({target_language})\n"
            "*Assistant:* Sunflower by Sunbird AI\n"
            "*Platform:* WhatsApp\n\n"
            "Type *help* for available commands or just *chat naturally!*"
        )

    def _get_languages_text(self) -> str:
        """Generate supported languages text.

        Returns:
            Formatted languages text.
        """
        languages_list = [
            f"• *{name}* ({code})"
            for code, name in sorted(self.LANGUAGE_MAPPING.items())
        ]
        return (
            "*🌐 Supported Languages*\n\n"
            f"{chr(10).join(languages_list)}\n\n"
            "To set your language, type:\n"
            "*set language [name]* or *set language [code]*\n\n"
            "Example: *set language english*"
        )

    # =========================================================================
    # Convenience Methods for API Client
    # =========================================================================

    def send_message(
        self,
        recipient_id: str,
        message: str,
        phone_number_id: Optional[str] = None,
    ) -> Optional[str]:
        """Send a text message (convenience wrapper).

        Args:
            recipient_id: Recipient's phone number.
            message: Message text.
            phone_number_id: Override phone number ID.

        Returns:
            Message ID if successful.
        """
        return self.api_client.send_message(
            recipient_id, message, phone_number_id=phone_number_id
        )

    def send_button(
        self,
        recipient_id: str,
        button: Dict[str, Any],
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send an interactive button (convenience wrapper).

        Args:
            recipient_id: Recipient's phone number.
            button: Button configuration.
            phone_number_id: Override phone number ID.

        Returns:
            API response.
        """
        return self.api_client.send_button(
            recipient_id, button, phone_number_id=phone_number_id
        )

    def send_template(
        self,
        recipient_id: str,
        template: str,
        components: Optional[List[Dict]] = None,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a template message (convenience wrapper).

        Args:
            recipient_id: Recipient's phone number.
            template: Template name.
            components: Template components.
            phone_number_id: Override phone number ID.

        Returns:
            API response.
        """
        return self.api_client.send_template(
            recipient_id,
            template,
            components=components,
            phone_number_id=phone_number_id,
        )


# =============================================================================
# Singleton and Dependency Injection
# =============================================================================

_whatsapp_service: Optional[WhatsAppBusinessService] = None


def get_whatsapp_service() -> WhatsAppBusinessService:
    """Get or create the WhatsApp service singleton.

    Returns:
        WhatsAppBusinessService instance.

    Example:
        >>> service = get_whatsapp_service()
        >>> result = await service.process_message(...)
    """
    global _whatsapp_service
    if _whatsapp_service is None:
        _whatsapp_service = WhatsAppBusinessService()
    return _whatsapp_service


def reset_whatsapp_service() -> None:
    """Reset the WhatsApp service singleton.

    Primarily used for testing to ensure a fresh instance.
    """
    global _whatsapp_service
    _whatsapp_service = None


def clear_processed_messages() -> None:
    """Clear the processed messages set.

    Primarily used for testing.
    """
    global _processed_messages
    _processed_messages.clear()


__all__ = [
    # Main service
    "WhatsAppBusinessService",
    "get_whatsapp_service",
    "reset_whatsapp_service",
    # Helper classes
    "WebhookParser",
    "InteractiveButtonBuilder",
    # Data classes and enums
    "MessageType",
    "ResponseType",
    "ProcessingResult",
    # Utilities
    "clear_processed_messages",
]
