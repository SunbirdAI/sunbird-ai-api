"""
WhatsApp Cloud API Integration Module.

This module provides a client for interacting with the WhatsApp Cloud API
(Meta Graph API). It handles all HTTP operations for sending and receiving
messages via WhatsApp Business.

The client supports:
    - Sending text, template, media, location, and contact messages
    - Interactive messages (buttons, lists)
    - Media upload/download and URL queries
    - Message status marking (read receipts)

Architecture:
    Services -> WhatsAppAPIClient -> Meta Graph API

Usage:
    from app.integrations.whatsapp_api import WhatsAppAPIClient, get_whatsapp_api_client

    # Using the singleton
    client = get_whatsapp_api_client()
    message_id = client.send_message(recipient_id, "Hello!")

    # Or create a custom instance
    client = WhatsAppAPIClient(token="my-token", phone_number_id="12345")
    response = client.send_template(recipient_id, "welcome_template")

Example:
    >>> client = WhatsAppAPIClient(token="...", phone_number_id="...")
    >>> result = client.send_message("1234567890", "Hello, World!")
    >>> print(result)
    {"messages": [{"id": "wamid.xxx"}]}
"""

import logging
import mimetypes
import os
import secrets
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import requests
from requests_toolbelt import MultipartEncoder

# Module-level logger
logger = logging.getLogger(__name__)

# API Version constants
DEFAULT_API_VERSION = "v20.0"
LEGACY_API_VERSION = "v12.0"


class WhatsAppAPIClient:
    """Client for interacting with the WhatsApp Cloud API.

    This client provides methods for all WhatsApp Cloud API operations,
    including sending messages, media handling, and webhook utilities.

    Attributes:
        token: The WhatsApp Business API access token.
        phone_number_id: The phone number ID for the WhatsApp Business account.
        api_version: The Graph API version to use.
        base_url: The base URL for API requests.

    Example:
        >>> client = WhatsAppAPIClient(token="...", phone_number_id="...")
        >>> client.send_message("1234567890", "Hello!")
        {"messages": [{"id": "wamid.xxx"}]}
    """

    def __init__(
        self,
        token: Optional[str] = None,
        phone_number_id: Optional[str] = None,
        api_version: str = DEFAULT_API_VERSION,
    ) -> None:
        """Initialize the WhatsApp API client.

        Args:
            token: WhatsApp API token. Defaults to WHATSAPP_TOKEN env var.
            phone_number_id: Phone number ID. Defaults to PHONE_NUMBER_ID env var.
            api_version: Graph API version. Defaults to v20.0.

        Example:
            >>> # Use environment variables
            >>> client = WhatsAppAPIClient()

            >>> # Use custom configuration
            >>> client = WhatsAppAPIClient(
            ...     token="EAABc...",
            ...     phone_number_id="123456789"
            ... )
        """
        self.token = token or os.getenv("WHATSAPP_TOKEN")
        self.phone_number_id = phone_number_id or os.getenv("PHONE_NUMBER_ID")
        self.api_version = api_version
        self.base_url = f"https://graph.facebook.com/{api_version}"

        if not self.token:
            logger.warning("WHATSAPP_TOKEN not set - WhatsApp API calls will fail")
        if not self.phone_number_id:
            logger.warning("PHONE_NUMBER_ID not set - WhatsApp API calls will fail")

    @property
    def headers(self) -> Dict[str, str]:
        """Get the standard headers for API requests."""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _get_messages_url(
        self, phone_number_id: Optional[str] = None, include_token: bool = False
    ) -> str:
        """Build the messages endpoint URL.

        Args:
            phone_number_id: Override phone number ID.
            include_token: Whether to include token in URL (legacy).

        Returns:
            The formatted messages endpoint URL.
        """
        pid = phone_number_id or self.phone_number_id
        url = f"{self.base_url}/{pid}/messages"
        if include_token:
            url = f"{url}?access_token={self.token}"
        return url

    # =========================================================================
    # Message Sending Methods
    # =========================================================================

    def send_message(
        self,
        recipient_id: str,
        message: str,
        preview_url: bool = True,
        phone_number_id: Optional[str] = None,
    ) -> Optional[str]:
        """Send a text message to a WhatsApp user.

        Args:
            recipient_id: Phone number with country code (no +).
            message: Text message to send.
            preview_url: Whether to show URL previews.
            phone_number_id: Override phone number ID.

        Returns:
            Message ID if successful, None otherwise.

        Example:
            >>> client.send_message("1234567890", "Hello, World!")
            "wamid.HBgL..."
        """
        # Use legacy v12.0 for send_message for consistency with original
        legacy_url = f"https://graph.facebook.com/{LEGACY_API_VERSION}/{phone_number_id or self.phone_number_id}/messages"

        data = {
            "messaging_product": "whatsapp",
            "to": recipient_id,
            "text": {"preview_url": preview_url, "body": message},
        }

        logger.info(f"Sending message to {recipient_id}")
        response = requests.post(legacy_url, headers=self.headers, json=data)

        if response.status_code == 200:
            response_json = response.json()
            message_id = response_json.get("messages", [{}])[0].get("id")
            logger.info(f"Message sent to {recipient_id} with ID: {message_id}")
            return message_id
        else:
            logger.error(f"Message not sent to {recipient_id}")
            logger.error(f"Status code: {response.status_code}")
            logger.error(f"Response: {response.json()}")
            return None

    def reply_to_message(
        self,
        message_id: str,
        recipient_id: str,
        message: str,
        preview_url: bool = True,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Reply to a specific message.

        Args:
            message_id: ID of the message to reply to.
            recipient_id: Phone number with country code (no +).
            message: Reply text.
            preview_url: Whether to show URL previews.
            phone_number_id: Override phone number ID.

        Returns:
            API response dictionary.

        Example:
            >>> client.reply_to_message("wamid.xxx", "1234567890", "Thanks!")
        """
        url = self._get_messages_url(phone_number_id, include_token=True)
        data = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient_id,
            "type": "text",
            "context": {"message_id": message_id},
            "text": {"preview_url": preview_url, "body": message},
        }

        logger.info(f"Replying to {message_id}")
        response = requests.post(url, headers=self.headers, json=data)

        if response.status_code == 200:
            logger.info(f"Reply sent to {recipient_id}")
        else:
            logger.warning(f"Reply not sent to {recipient_id}")
            logger.warning(f"Status code: {response.status_code}")

        return response.json()

    def send_template(
        self,
        recipient_id: str,
        template: str,
        lang: str = "en_US",
        components: Optional[List[Dict]] = None,
        recipient_type: str = "individual",
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a template message.

        Template messages can be text, media-based, or interactive.
        See: https://developers.facebook.com/docs/whatsapp/cloud-api/guides/send-message-templates

        Args:
            recipient_id: Phone number with country code (no +).
            template: Template name.
            lang: Template language code.
            components: Optional template components.
            recipient_type: "individual" or "group".
            phone_number_id: Override phone number ID.

        Returns:
            API response dictionary.

        Example:
            >>> client.send_template("1234567890", "welcome_message")
        """
        url = self._get_messages_url(phone_number_id, include_token=True)
        if components is None:
            components = []

        data = {
            "messaging_product": "whatsapp",
            "recipient_type": recipient_type,
            "to": recipient_id,
            "type": "template",
            "template": {
                "name": template,
                "language": {"code": lang},
                "components": components,
            },
        }

        logger.info(f"Sending template '{template}' to {recipient_id}")
        response = requests.post(url, headers=self.headers, json=data)

        if response.status_code == 200:
            logger.info(f"Template sent to {recipient_id}")
        else:
            logger.warning(f"Template not sent to {recipient_id}")
            logger.warning(f"Status code: {response.status_code}")

        return response.json()

    def send_audio(
        self,
        recipient_id: str,
        audio: str,
        link: bool = True,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send an audio message.

        Args:
            recipient_id: Phone number with country code (no +).
            audio: Audio URL (if link=True) or media ID (if link=False).
            link: True for URL, False for media ID.
            phone_number_id: Override phone number ID.

        Returns:
            API response dictionary.
        """
        url = self._get_messages_url(phone_number_id, include_token=True)

        if link:
            data = {
                "messaging_product": "whatsapp",
                "to": recipient_id,
                "type": "audio",
                "audio": {"link": audio},
            }
        else:
            data = {
                "messaging_product": "whatsapp",
                "to": recipient_id,
                "type": "audio",
                "audio": {"id": audio},
            }

        logger.info(f"Sending audio to {recipient_id}")
        response = requests.post(url, headers=self.headers, json=data)

        if response.status_code == 200:
            logger.info(f"Audio sent to {recipient_id}")
        else:
            logger.warning(f"Audio not sent to {recipient_id}")
            logger.error(f"Response: {response.json()}")

        return response.json()

    def send_image(
        self,
        recipient_id: str,
        image: str,
        caption: Optional[str] = None,
        link: bool = True,
        recipient_type: str = "individual",
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send an image message.

        Args:
            recipient_id: Phone number with country code (no +).
            image: Image URL (if link=True) or media ID (if link=False).
            caption: Optional image caption.
            link: True for URL, False for media ID.
            recipient_type: "individual" or "group".
            phone_number_id: Override phone number ID.

        Returns:
            API response dictionary.
        """
        url = self._get_messages_url(phone_number_id, include_token=True)

        image_data = {"link": image} if link else {"id": image}
        if caption:
            image_data["caption"] = caption

        data = {
            "messaging_product": "whatsapp",
            "recipient_type": recipient_type,
            "to": recipient_id,
            "type": "image",
            "image": image_data,
        }

        logger.info(f"Sending image to {recipient_id}")
        response = requests.post(url, headers=self.headers, json=data)

        if response.status_code == 200:
            logger.info(f"Image sent to {recipient_id}")
        else:
            logger.warning(f"Image not sent to {recipient_id}")
            logger.error(f"Response: {response.json()}")

        return response.json()

    def send_video(
        self,
        recipient_id: str,
        video: str,
        caption: Optional[str] = None,
        link: bool = True,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a video message.

        Args:
            recipient_id: Phone number with country code (no +).
            video: Video URL (if link=True) or media ID (if link=False).
            caption: Optional video caption.
            link: True for URL, False for media ID.
            phone_number_id: Override phone number ID.

        Returns:
            API response dictionary.
        """
        url = f"{self.base_url}/{phone_number_id or self.phone_number_id}/messages"

        video_data = {"link": video} if link else {"id": video}
        if caption:
            video_data["caption"] = caption

        data = {
            "messaging_product": "whatsapp",
            "to": recipient_id,
            "type": "video",
            "video": video_data,
        }

        logger.info(f"Sending video to {recipient_id}")
        response = requests.post(url, headers=self.headers, json=data)

        if response.status_code == 200:
            logger.info(f"Video sent to {recipient_id}")
        else:
            logger.warning(f"Video not sent to {recipient_id}")
            logger.error(f"Response: {response.json()}")

        return response.json()

    def send_document(
        self,
        recipient_id: str,
        document: str,
        caption: Optional[str] = None,
        link: bool = True,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a document message.

        Args:
            recipient_id: Phone number with country code (no +).
            document: Document URL (if link=True) or media ID (if link=False).
            caption: Optional document caption.
            link: True for URL, False for media ID.
            phone_number_id: Override phone number ID.

        Returns:
            API response dictionary.
        """
        url = f"{self.base_url}/{phone_number_id or self.phone_number_id}/messages"

        doc_data = {"link": document} if link else {"id": document}
        if caption:
            doc_data["caption"] = caption

        data = {
            "messaging_product": "whatsapp",
            "to": recipient_id,
            "type": "document",
            "document": doc_data,
        }

        logger.info(f"Sending document to {recipient_id}")
        response = requests.post(url, headers=self.headers, json=data)

        if response.status_code == 200:
            logger.info(f"Document sent to {recipient_id}")
        else:
            logger.warning(f"Document not sent to {recipient_id}")
            logger.error(f"Response: {response.json()}")

        return response.json()

    def send_location(
        self,
        recipient_id: str,
        latitude: str,
        longitude: str,
        name: str,
        address: str,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a location message.

        Args:
            recipient_id: Phone number with country code (no +).
            latitude: Location latitude.
            longitude: Location longitude.
            name: Location name.
            address: Location address.
            phone_number_id: Override phone number ID.

        Returns:
            API response dictionary.
        """
        url = self._get_messages_url(phone_number_id, include_token=True)
        data = {
            "messaging_product": "whatsapp",
            "to": recipient_id,
            "type": "location",
            "location": {
                "latitude": latitude,
                "longitude": longitude,
                "name": name,
                "address": address,
            },
        }

        logger.info(f"Sending location to {recipient_id}")
        response = requests.post(url, headers=self.headers, json=data)

        if response.status_code == 200:
            logger.info(f"Location sent to {recipient_id}")
        else:
            logger.warning(f"Location not sent to {recipient_id}")
            logger.error(f"Response: {response.json()}")

        return response.json()

    def send_contacts(
        self,
        recipient_id: str,
        contacts: List[Dict[str, Any]],
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a contacts message.

        See: https://developers.facebook.com/docs/whatsapp/cloud-api/reference/messages#contacts-object

        Args:
            recipient_id: Phone number with country code (no +).
            contacts: List of contact objects.
            phone_number_id: Override phone number ID.

        Returns:
            API response dictionary.
        """
        url = f"{self.base_url}/{phone_number_id or self.phone_number_id}/messages"
        data = {
            "messaging_product": "whatsapp",
            "to": recipient_id,
            "type": "contacts",
            "contacts": contacts,
        }

        logger.info(f"Sending contacts to {recipient_id}")
        response = requests.post(url, headers=self.headers, json=data)

        if response.status_code == 200:
            logger.info(f"Contacts sent to {recipient_id}")
        else:
            logger.warning(f"Contacts not sent to {recipient_id}")
            logger.error(f"Response: {response.json()}")

        return response.json()

    # =========================================================================
    # Interactive Message Methods
    # =========================================================================

    def send_button(
        self,
        recipient_id: str,
        button: Dict[str, Any],
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send an interactive list button message.

        Args:
            recipient_id: Phone number with country code (no +).
            button: Button configuration with header, body, footer, and action.
            phone_number_id: Override phone number ID.

        Returns:
            API response dictionary.

        Example:
            >>> button = {
            ...     "header": "Select an option",
            ...     "body": "Choose from the list below",
            ...     "footer": "Powered by Sunbird AI",
            ...     "action": {"button": "Options", "sections": [...]}
            ... }
            >>> client.send_button("1234567890", button)
        """
        url = f"{self.base_url}/{phone_number_id or self.phone_number_id}/messages"

        interactive_data = {"type": "list", "action": button.get("action")}
        if button.get("header"):
            interactive_data["header"] = {"type": "text", "text": button["header"]}
        if button.get("body"):
            interactive_data["body"] = {"text": button["body"]}
        if button.get("footer"):
            interactive_data["footer"] = {"text": button["footer"]}

        data = {
            "messaging_product": "whatsapp",
            "to": recipient_id,
            "type": "interactive",
            "interactive": interactive_data,
        }

        logger.info(f"Sending button to {recipient_id}")
        response = requests.post(url, headers=self.headers, json=data)

        if response.status_code == 200:
            logger.info(f"Button sent to {recipient_id}")
        else:
            logger.warning(f"Button not sent to {recipient_id}")
            logger.info(f"Response: {response.json()}")

        return response.json()

    def send_reply_button(
        self,
        recipient_id: str,
        button: Dict[str, Any],
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send an interactive reply button message.

        Note: Maximum of 3 buttons allowed.

        Args:
            recipient_id: Phone number with country code (no +).
            button: Interactive button configuration.
            phone_number_id: Override phone number ID.

        Returns:
            API response dictionary.
        """
        url = f"{self.base_url}/{phone_number_id or self.phone_number_id}/messages"
        data = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient_id,
            "type": "interactive",
            "interactive": button,
        }

        response = requests.post(url, headers=self.headers, json=data)

        if response.status_code == 200:
            logger.info(f"Reply buttons sent to {recipient_id}")
        else:
            logger.warning(f"Reply buttons not sent to {recipient_id}")
            logger.info(f"Response: {response.json()}")

        return response.json()

    # =========================================================================
    # Media Methods
    # =========================================================================

    def query_media_url(self, media_id: str) -> Optional[str]:
        """Get the download URL for a media file.

        Args:
            media_id: The media ID from a webhook message.

        Returns:
            Media URL if successful, None otherwise.
        """
        url = f"{self.base_url}/{media_id}"
        headers = {"Authorization": f"Bearer {self.token}"}

        logger.info(f"Querying media URL for {media_id}")
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            logger.info(f"Media URL queried for {media_id}")
            return response.json().get("url")

        logger.warning(f"Media URL not queried for {media_id}")
        logger.info(f"Status code: {response.status_code}")
        return None

    def download_media(
        self,
        media_url: str,
        file_path: str = "downloaded_media_file",
    ) -> str:
        """Download media from a WhatsApp media URL.

        Args:
            media_url: The media download URL.
            file_path: Local path to save the file.

        Returns:
            Path to the downloaded file.

        Raises:
            Exception: If download fails.
        """
        headers = {"Authorization": f"Bearer {self.token}"}

        logger.info(f"Downloading media from URL")
        response = requests.get(media_url, headers=headers, stream=True)

        if response.status_code == 200:
            with open(file_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return file_path
        else:
            raise Exception(
                f"Failed to download media. HTTP Status: {response.status_code}"
            )

    def download_whatsapp_audio(
        self,
        url: str,
        access_token: Optional[str] = None,
    ) -> str:
        """Download WhatsApp audio with validation.

        Creates a temporary file with secure naming and validates
        the downloaded content.

        Args:
            url: The audio download URL.
            access_token: Override access token.

        Returns:
            Path to the downloaded audio file.

        Raises:
            Exception: If download fails or file is invalid.
        """
        token = access_token or self.token

        # Generate secure filename
        random_string = secrets.token_hex(8)
        current_time = datetime.now().strftime("%Y%m%d_%H%M%S")

        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".mp3",
            prefix=f"whatsapp_audio_{random_string}_{current_time}_",
        ) as temp_file:
            temp_file_path = temp_file.name

        # Download with streaming
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(url, headers=headers, stream=True, timeout=60)

        if response.status_code == 200:
            with open(temp_file_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            # Validate file
            file_size = os.path.getsize(temp_file_path)
            if file_size == 0:
                os.remove(temp_file_path)
                raise Exception("Downloaded audio file is empty")

            logger.info(
                f"WhatsApp audio downloaded: {temp_file_path}, Size: {file_size} bytes"
            )
            return temp_file_path
        else:
            raise Exception(f"Failed to download audio. Status: {response.status_code}")

    def upload_media(
        self,
        media_path: str,
        phone_number_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Upload media to WhatsApp Cloud API.

        See: https://developers.facebook.com/docs/whatsapp/cloud-api/reference/media

        Args:
            media_path: Local path to the media file.
            phone_number_id: Override phone number ID.

        Returns:
            API response with media ID if successful, None otherwise.
        """
        pid = phone_number_id or self.phone_number_id
        url = f"{self.base_url}/{pid}/media"

        mime_type = mimetypes.guess_type(media_path)[0]
        form_data = MultipartEncoder(
            fields={
                "file": (
                    media_path,
                    open(os.path.realpath(media_path), "rb"),
                    mime_type,
                ),
                "messaging_product": "whatsapp",
                "type": mime_type,
            }
        )

        headers = self.headers.copy()
        headers["Content-Type"] = form_data.content_type

        logger.info(f"Uploading media {media_path}")
        response = requests.post(url, headers=headers, data=form_data)

        if response.status_code == 200:
            logger.info(f"Media {media_path} uploaded")
            return response.json()

        logger.warning(f"Error uploading media {media_path}")
        logger.info(f"Status code: {response.status_code}")
        return None

    def delete_media(self, media_id: str) -> Optional[Dict[str, Any]]:
        """Delete media from WhatsApp Cloud API.

        Args:
            media_id: The media ID to delete.

        Returns:
            API response if successful, None otherwise.
        """
        url = f"{self.base_url}/{media_id}"

        logger.info(f"Deleting media {media_id}")
        response = requests.delete(url, headers=self.headers)

        if response.status_code == 200:
            logger.info(f"Media {media_id} deleted")
            return response.json()

        logger.warning(f"Error deleting media {media_id}")
        logger.info(f"Status code: {response.status_code}")
        return None

    def fetch_media_url(self, media_id: str) -> Optional[str]:
        """Fetch media URL from media ID (alias for query_media_url).

        Args:
            media_id: The media ID from webhook.

        Returns:
            Media download URL if successful, None otherwise.
        """
        url = f"https://graph.facebook.com/{self.api_version}/{media_id}"
        headers = {"Authorization": f"Bearer {self.token}"}

        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            logger.info(f"Fetch response: {response.json()}")
            return response.json().get("url")
        else:
            logger.error(
                f"Failed to fetch media URL for ID {media_id}. "
                f"HTTP Status: {response.status_code}"
            )
            return None

    # =========================================================================
    # Status Methods
    # =========================================================================

    def mark_as_read(
        self,
        message_id: str,
        phone_number_id: Optional[str] = None,
    ) -> bool:
        """Mark a message as read.

        Args:
            message_id: The message ID to mark as read.
            phone_number_id: Override phone number ID.

        Returns:
            True if successful, False otherwise.
        """
        url = f"{self.base_url}/{phone_number_id or self.phone_number_id}/messages"
        data = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }

        response = requests.post(url, headers=self.headers, json=data)

        if response.status_code == 200:
            return response.json().get("success", False)
        return False


# =============================================================================
# Singleton and Dependency Injection
# =============================================================================

_whatsapp_api_client: Optional[WhatsAppAPIClient] = None


def get_whatsapp_api_client() -> WhatsAppAPIClient:
    """Get or create the WhatsApp API client singleton.

    Returns:
        WhatsAppAPIClient instance configured with environment settings.

    Example:
        >>> client = get_whatsapp_api_client()
        >>> client.send_message("1234567890", "Hello!")
    """
    global _whatsapp_api_client
    if _whatsapp_api_client is None:
        _whatsapp_api_client = WhatsAppAPIClient()
    return _whatsapp_api_client


def reset_whatsapp_api_client() -> None:
    """Reset the WhatsApp API client singleton.

    Primarily used for testing to ensure a fresh instance.
    """
    global _whatsapp_api_client
    _whatsapp_api_client = None


__all__ = [
    "WhatsAppAPIClient",
    "get_whatsapp_api_client",
    "reset_whatsapp_api_client",
    "DEFAULT_API_VERSION",
    "LEGACY_API_VERSION",
]
