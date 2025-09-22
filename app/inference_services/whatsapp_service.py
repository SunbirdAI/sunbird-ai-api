import json
import logging
import mimetypes
import os
import secrets
import tempfile
import time
from datetime import datetime
from typing import Any, Dict, List, Union

import requests
import runpod
from dotenv import load_dotenv
from fastapi import HTTPException
from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError
from requests_toolbelt import MultipartEncoder

from app.inference_services.openai_script import (
    classify_input,
    get_completion_from_messages,
    get_guide_based_on_classification,
    is_json,
)
from app.inference_services.ug40_inference import run_inference
from app.inference_services.user_preference import (
    get_user_last_five_conversation_pairs,
    get_user_last_five_messages,
    get_user_preference,
    save_message,
    save_response,
    save_user_preference,
    update_feedback,
)
from app.utils.upload_audio_file_gcp import upload_audio_file

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)


class WhatsAppService:
    def __init__(self, token: str, phone_number_id: str):
        self.base_url = "https://graph.facebook.com/v20.0"
        self.token = token
        self.phone_number_id = phone_number_id
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def download_whatsapp_audio(self, url, access_token):
        """
        Download WhatsApp audio file with improved error handling and validation
        """
        temp_file_path = None
        try:
            # Generate a secure random filename with timestamp
            random_string = secrets.token_hex(8)
            current_time = datetime.now().strftime("%Y%m%d_%H%M%S")

            # Create temporary file with proper extension
            with tempfile.NamedTemporaryFile(
                delete=False,
                suffix=".mp3",
                prefix=f"whatsapp_audio_{random_string}_{current_time}_",
            ) as temp_file:
                temp_file_path = temp_file.name

            # Download the audio file with streaming
            headers = {"Authorization": f"Bearer {access_token}"}
            response = requests.get(url, headers=headers, stream=True, timeout=60)

            if response.status_code == 200:
                # Check content type if available
                content_type = response.headers.get("content-type", "")
                if content_type and not any(
                    audio_type in content_type.lower()
                    for audio_type in ["audio", "application/octet-stream"]
                ):
                    logging.warning(
                        f"Unexpected content type for audio: {content_type}"
                    )

                # Write file in chunks to handle large files efficiently
                with open(temp_file_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:  # Filter out keep-alive chunks
                            f.write(chunk)

                # Validate the downloaded file
                file_size = os.path.getsize(temp_file_path)
                if file_size == 0:
                    raise HTTPException(
                        status_code=422, detail="Downloaded audio file is empty"
                    )

                # Try to validate it's a proper audio file using pydub
                try:
                    audio_segment = AudioSegment.from_file(temp_file_path)
                    duration_seconds = len(audio_segment) / 1000.0
                    logging.info(
                        f"WhatsApp audio downloaded successfully: {temp_file_path}, Size: {file_size} bytes, Duration: {duration_seconds:.1f}s"
                    )
                except CouldntDecodeError as e:
                    raise HTTPException(
                        status_code=422,
                        detail="Downloaded file is not a valid audio format or is corrupted",
                    ) from e

                return temp_file_path
            else:
                error_msg = (
                    f"Failed to download WhatsApp audio. Status: {response.status_code}"
                )
                if response.text:
                    error_msg += f", Response: {response.text[:200]}"
                logging.error(error_msg)
                raise HTTPException(
                    status_code=500,
                    detail="Failed to download audio file from WhatsApp",
                )

        except requests.exceptions.Timeout:
            logging.error("Timeout while downloading WhatsApp audio")
            raise HTTPException(
                status_code=408, detail="Timeout while downloading audio file"
            )
        except requests.exceptions.ConnectionError as e:
            logging.error(
                f"Connection error while downloading WhatsApp audio: {str(e)}"
            )
            raise HTTPException(
                status_code=503, detail="Connection error while downloading audio file"
            )
        except requests.exceptions.RequestException as e:
            logging.error(f"Request error while downloading WhatsApp audio: {str(e)}")
            raise HTTPException(
                status_code=500, detail="Error occurred while downloading audio file"
            )
        except Exception as e:
            logging.error(
                f"Unexpected error while downloading WhatsApp audio: {str(e)}"
            )
            # Clean up temp file if created but download failed
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except:
                    pass
            raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

    def send_message(
        self, message, token, recipient_id, phone_number_id, preview_url=True
    ):
        """
        Sends a text message to a WhatsApp user and returns the message ID

        Args:
            message[str]: Message to be sent to the user
            token[str]: Access token for WhatsApp API
            recipient_id[str]: Phone number of the user with country code without +
            phone_number_id[str]: ID of the phone number sending the message
            preview_url[bool]: Whether to send a preview url or not

        Returns:
            str: ID of the sent message
        """
        base_url = "https://graph.facebook.com/v12.0"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        url = f"{base_url}/{phone_number_id}/messages"
        data = {
            "messaging_product": "whatsapp",
            "to": recipient_id,
            "text": {"preview_url": preview_url, "body": message},
        }
        logging.info(f"Sending message to {recipient_id}")
        r = requests.post(url, headers=headers, json=data)
        if r.status_code == 200:
            response_json = r.json()
            message_id = response_json.get("messages", [{}])[0].get("id")
            logging.info(f"Message sent to {recipient_id} with ID: {message_id}")
            return message_id
        else:
            logging.error(f"Message not sent to {recipient_id}")
            logging.error(f"Status code: {r.status_code}")
            logging.error(f"Response: {r.json()}")
            return None

    def reply_to_message(
        self,
        token,
        message_id: str,
        recipient_id: str,
        phone_number_id: str,
        message: str,
        preview_url: bool = True,
    ):
        """
        Replies to a message

        Args:
            message_id[str]: Message id of the message to be replied to
            recipient_id[str]: Phone number of the user with country code wihout +
            message[str]: Message to be sent to the user
            preview_url[bool]: Whether to send a preview url or not
        """
        url = f"{self.base_url}/{phone_number_id}/messages?access_token={token}"
        data = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient_id,
            "type": "text",
            "context": {"message_id": message_id},
            "text": {"preview_url": preview_url, "body": message},
        }

        logging.info(f"Replying to {message_id}")
        r = requests.post(f"{url}", headers=self.headers, json=data)
        if r.status_code == 200:
            logging.info(f"Message sent to {recipient_id}")
            return r.json()
        logging.info(f"Message not sent to {recipient_id}")
        logging.info(f"Status code: {r.status_code}")
        logging.info(f"Response: {r.json()}")
        return r.json()

    def send_template(
        self,
        token,
        template: str,
        phone_number_id: str,
        recipient_id: str,
        recipient_type="individual",
        lang: str = "en",
        components: List = None,
    ):
        """
        Sends a template message to a WhatsApp user, Template messages can either be;
            1. Text template
            2. Media based template
            3. Interactive template
        You can customize the template message by passing a dictionary of components.
        You can find the available components in the documentation.
        https://developers.facebook.com/docs/whatsapp/cloud-api/guides/send-message-templates
        Args:
            template[str]: Template name to be sent to the user
            recipient_id[str]: Phone number of the user with country code wihout +
            lang[str]: Language of the template message
            components[list]: List of components to be sent to the user  # CHANGE

        """
        url = f"{self.base_url}/{phone_number_id}/messages?access_token={token}"
        if components is None:  # TO NOT USE LIST AS DEFAULT, BECAUSE IT IS MUTABLE
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
        logging.info(f"Sending template to {recipient_id}")
        r = requests.post(url, headers=self.headers, json=data)

        if r.status_code == 200:
            logging.info(f"Template sent to {recipient_id}")
            return r.json()
        logging.info(f"Template not sent to {recipient_id}")
        logging.info(f"Status code: {r.status_code}")
        logging.info(f"Response: {r.json()}")
        return r.json()

    def send_templatev2(
        self, token, template, recipient_id, components, phone_number_id, lang="en"
    ):
        url = f"{self.base_url}/{phone_number_id}/messages?access_token={token}"
        data = {
            "messaging_product": "whatsapp",
            "to": recipient_id,
            "type": "template",
            "template": {
                "name": template,
                "language": {"code": lang},
                "components": components,
            },
        }
        logging.info(f"Sending template to {recipient_id}")
        r = requests.post(url, headers=self.headers, json=data)
        if r.status_code == 200:
            logging.info(f"Template sent to {recipient_id}")
            return r.json()
        logging.info(f"Template not sent to {recipient_id}")
        logging.info(f"Status code: {r.status_code}")
        logging.info(f"Response: {r.json()}")
        return r.json()

    def send_location(
        self, token, lat, long, name, address, recipient_id, phone_number_id
    ):
        """
        Sends a location message to a WhatsApp user

        Args:
            lat[str]: Latitude of the location
            long[str]: Longitude of the location
            name[str]: Name of the location
            address[str]: Address of the location
            recipient_id[str]: Phone number of the user with country code wihout +

        """
        url = f"{self.base_url}/{phone_number_id}/messages?access_token={token}"
        data = {
            "messaging_product": "whatsapp",
            "to": recipient_id,
            "type": "location",
            "location": {
                "latitude": lat,
                "longitude": long,
                "name": name,
                "address": address,
            },
        }
        logging.info(f"Sending location to {recipient_id}")
        r = requests.post(url, headers=self.headers, json=data)
        if r.status_code == 200:
            logging.info(f"Location sent to {recipient_id}")
            return r.json()
        logging.info(f"Location not sent to {recipient_id}")
        logging.info(f"Status code: {r.status_code}")
        logging.error(r.json())
        return r.json()

    def send_image(
        self,
        token,
        image,
        phone_number_id,
        recipient_id,
        recipient_type="individual",
        caption=None,
        link=True,
    ):
        """
        Sends an image message to a WhatsApp user

        There are two ways to send an image message to a user, either by passing the image id or by passing the image link.
        Image id is the id of the image uploaded to the cloud api.

        Args:
            image[str]: Image id or link of the image
            recipient_id[str]: Phone number of the user with country code wihout +
            recipient_type[str]: Type of the recipient, either individual or group
            caption[str]: Caption of the image
            link[bool]: Checks if image is id or link, True means id

        """
        url = f"{self.base_url}/{phone_number_id}/messages?access_token={token}"
        if link:
            data = {
                "messaging_product": "whatsapp",
                "recipient_type": recipient_type,
                "to": recipient_id,
                "type": "image",
                "image": {"link": image, "caption": caption},
            }
        else:
            data = {
                "messaging_product": "whatsapp",
                "recipient_type": recipient_type,
                "to": recipient_id,
                "type": "image",
                "image": {"id": image, "caption": caption},
            }
        logging.info(f"Sending image to {recipient_id}")
        r = requests.post(url, headers=self.headers, json=data)
        if r.status_code == 200:
            logging.info(f"Image sent to {recipient_id}")
            return r.json()
        logging.info(f"Image not sent to {recipient_id}")
        logging.info(f"Status code: {r.status_code}")
        logging.error(r.json())
        return r.json()

    def send_sticker(self, sticker: str, recipient_id: str, link=True):
        pass

    def send_audio(self, token, audio, phone_number_id, recipient_id, link=True):
        """
        Sends an audio message to a WhatsApp user
        Audio messages can either be sent by passing the audio id or by passing the audio link.

        Args:
            audio[str]: Audio id or link of the audio
            recipient_id[str]: Phone number of the user with country code wihout +
            link[bool]: Choose audio id or audio link, True means audio is an id, False means audio is a link

        """
        url = f"{self.base_url}/{phone_number_id}/messages?access_token={token}"
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
        logging.info(f"Sending audio to {recipient_id}")
        r = requests.post(url, headers=self.headers, json=data)
        if r.status_code == 200:
            logging.info(f"Audio sent to {recipient_id}")
            return r.json()
        logging.info(f"Audio not sent to {recipient_id}")
        logging.info(f"Status code: {r.status_code}")
        logging.error(f"Response: {r.json()}")
        return r.json()

    def send_video(self, video, phone_number_id, recipient_id, caption=None, link=True):
        """ "
        Sends a video message to a WhatsApp user
        Video messages can either be sent by passing the video id or by passing the video link.

        Args:
            video[str]: Video id or link of the video
            recipient_id[str]: Phone number of the user with country code wihout +
            caption[str]: Caption of the video
            link[bool]: Choose to send video id or  video link, True means video is an id, False means video is a link

        """
        url = f"{self.base_url}/{phone_number_id}/messages"
        if link:
            data = {
                "messaging_product": "whatsapp",
                "to": recipient_id,
                "type": "video",
                "video": {"link": video, "caption": caption},
            }
        else:
            data = {
                "messaging_product": "whatsapp",
                "to": recipient_id,
                "type": "video",
                "video": {"id": video, "caption": caption},
            }
        logging.info(f"Sending video to {recipient_id}")
        r = requests.post(url, headers=self.headers, json=data)
        if r.status_code == 200:
            logging.info(f"Video sent to {recipient_id}")
            return r.json()
        logging.info(f"Video not sent to {recipient_id}")
        logging.info(f"Status code: {r.status_code}")
        logging.error(f"Response: {r.json()}")
        return r.json()

    def send_document(
        self, document, phone_number_id, recipient_id, caption=None, link=True
    ):
        """ "
        Sends a document message to a WhatsApp user
        Document messages can either be sent by passing the document id or by passing the document link.

        Args:
            document[str]: Document id or link of the document
            recipient_id[str]: Phone number of the user with country code wihout +
            caption[str]: Caption of the document
            link[bool]: Choose to send id or link for document, True means document is an id else it's a link

        """
        url = f"{self.base_url}/{phone_number_id}/messages"
        if link:
            data = {
                "messaging_product": "whatsapp",
                "to": recipient_id,
                "type": "document",
                "document": {"link": document, "caption": caption},
            }
        else:
            data = {
                "messaging_product": "whatsapp",
                "to": recipient_id,
                "type": "document",
                "document": {"id": document, "caption": caption},
            }

        logging.info(f"Sending document to {recipient_id}")
        r = requests.post(url, headers=self.headers, json=data)
        if r.status_code == 200:
            logging.info(f"Document sent to {recipient_id}")
            return r.json()
        logging.info(f"Document not sent to {recipient_id}")
        logging.info(f"Status code: {r.status_code}")
        logging.error(f"Response: {r.json()}")
        return r.json()

    def send_contacts(
        self, contacts: List[Dict[Any, Any]], phone_number_id: str, recipient_id: str
    ):
        """send_contacts

        Send a list of contacts to a user

        Args:
            contacts(List[Dict[Any, Any]]): List of contacts to send
            recipient_id(str): Phone number of the user with country code wihout +

        REFERENCE: https://developers.facebook.com/docs/whatsapp/cloud-api/reference/messages#contacts-object
        """

        url = f"{self.base_url}/{phone_number_id}/messages"
        data = {
            "messaging_product": "whatsapp",
            "to": recipient_id,
            "type": "contacts",
            "contacts": contacts,
        }
        logging.info(f"Sending contacts to {recipient_id}")
        r = requests.post(url, headers=self.headers, json=data)
        if r.status_code == 200:
            logging.info(f"Contacts sent to {recipient_id}")
            return r.json()
        logging.info(f"Contacts not sent to {recipient_id}")
        logging.info(f"Status code: {r.status_code}")
        logging.error(f"Response: {r.json()}")
        return r.json()

    def upload_media(self, headers, media: str, phone_number_id: str):
        """
        Uploads a media to the cloud api and returns the id of the media

        Args:
            media[str]: Path of the media to be uploaded

        REFERENCE: https://developers.facebook.com/docs/whatsapp/cloud-api/reference/media#
        """
        form_data = {
            "file": (
                media,
                open(os.path.realpath(media), "rb"),
                mimetypes.guess_type(media)[0],
            ),
            "messaging_product": "whatsapp",
            "type": mimetypes.guess_type(media)[0],
        }
        form_data = MultipartEncoder(fields=form_data)
        headers = headers.copy()
        headers["Content-Type"] = form_data.content_type
        logging.info(f"Content-Type: {form_data.content_type}")
        logging.info(f"Uploading media {media}")
        r = requests.post(
            f"{self.base_url}/{phone_number_id}/media",
            headers=headers,
            data=form_data,
        )
        if r.status_code == 200:
            logging.info(f"Media {media} uploaded")
            return r.json()
        logging.info(f"Error uploading media {media}")
        logging.info(f"Status code: {r.status_code}")
        logging.info(f"Response: {r.json()}")
        return None

    def delete_media(self, media_id: str):
        """
        Deletes a media from the cloud api

        Args:
            media_id[str]: Id of the media to be deleted
        """
        logging.info(f"Deleting media {media_id}")
        r = requests.delete(f"{self.base_url}/{media_id}", headers=self.headers)
        if r.status_code == 200:
            logging.info(f"Media {media_id} deleted")
            return r.json()
        logging.info(f"Error deleting media {media_id}")
        logging.info(f"Status code: {r.status_code}")
        logging.info(f"Response: {r.json()}")
        return None

    def mark_as_read(self, token, message_id: str, phone_number_id: str):
        """
        Marks a message as read

        Args:
            message_id[str]: Id of the message to be marked as read
        """
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        json_data = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }
        response = requests.post(
            f"{self.base_url}/{phone_number_id}/messages",
            headers=headers,
            json=json_data,
        ).json()
        return response["success"]

    def create_button(self, button):
        """
        Method to create a button object to be used in the send_message method.

        This is method is designed to only be used internally by the send_button method.

        Args:
            button[dict]: A dictionary containing the button data
        """
        data = {"type": "list", "action": button.get("action")}
        if button.get("header"):
            data["header"] = {"type": "text", "text": button.get("header")}
        if button.get("body"):
            data["body"] = {"text": button.get("body")}
        if button.get("footer"):
            data["footer"] = {"text": button.get("footer")}
        return data

    def send_button(self, button, phone_number_id, recipient_id):
        """
        Sends an interactive buttons message to a WhatsApp user

        Args:
            button[dict]: A dictionary containing the button data(rows-title may not exceed 20 characters)
            recipient_id[str]: Phone number of the user with country code wihout +

        check https://github.com/Neurotech-HQ/heyoo#sending-interactive-reply-buttons for an example.
        """

        url = f"{self.base_url}/{phone_number_id}/messages"
        data = {
            "messaging_product": "whatsapp",
            "to": recipient_id,
            "type": "interactive",
            "interactive": self.create_button(button),
        }
        logging.info(f"Sending buttons to {recipient_id}")
        r = requests.post(url, headers=self.headers, json=data)
        if r.status_code == 200:
            logging.info(f"Buttons sent to {recipient_id}")
            return r.json()
        logging.info(f"Buttons not sent to {recipient_id}")
        logging.info(f"Status code: {r.status_code}")
        logging.info(f"Response: {r.json()}")
        return r.json()

    def send_reply_button(self, button, recipient_id, phone_number_id):
        """
        Sends an interactive reply buttons[menu] message to a WhatsApp user

        Args:
            button[dict]: A dictionary containing the button data
            recipient_id[str]: Phone number of the user with country code wihout +

        Note:
            The maximum number of buttons is 3, more than 3 buttons will rise an error.
        """

        url = f"{self.base_url}/{phone_number_id}/messages"
        data = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient_id,
            "type": "interactive",
            "interactive": button,
        }
        r = requests.post(url, headers=self.headers, json=data)
        if r.status_code == 200:
            logging.info(f"Reply buttons sent to {recipient_id}")
            return r.json()
        logging.info(f"Reply buttons not sent to {recipient_id}")
        logging.info(f"Status code: {r.status_code}")
        logging.info(f"Response: {r.json()}")
        return r.json()

    def query_media_url(self, media_id, access_token):
        """
        Query media url from media id obtained either by manually uploading media or received media

        Args:
            media_id[str]: Media id of the media

        Returns:
            str: Media url

        """

        headers = {"Authorization": f"Bearer {access_token}"}
        logging.info(f"Querying media url for {media_id}")
        r = requests.get(f"{self.base_url}/{media_id}", headers=headers)
        if r.status_code == 200:
            logging.info(f"Media url queried for {media_id}")
            return r.json()["url"]
        logging.info(f"Media url not queried for {media_id}")
        logging.info(f"Status code: {r.status_code}")
        logging.info(f"Response: {r.json()}")
        return None

    def download_media(
        self, media_url, access_token, file_path="downloaded_media_file"
    ):
        """
        Download the media from the media URL obtained from the WhatsApp Business API.

        :param media_url: The URL of the media file to download.
        :param access_token: The access token for authenticating with the WhatsApp Business API.
        :param file_path: The local file path where the media should be saved.
        :return: The path to the downloaded media file.
        """
        logging.info(f"Media url is:: {media_url}")

        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get(media_url, headers=headers, stream=True)

        logging.info(f"The response is:: {response}")
        logging.info(f"Response Status: {response.status_code}")
        logging.info(f"Response Content: {response.content[:100]}")

        if response.status_code == 200:
            with open(file_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return file_path
        else:
            raise Exception(
                f"Failed to download media. HTTP Status: {response.status_code}"
            )

    def preprocess(self, data):
        """
        Preprocesses the data received from the webhook.

        This method is designed to only be used internally.

        Args:
            data[dict]: The data received from the webhook
        """
        return data["entry"][0]["changes"][0]["value"]

    def get_mobile(self, data) -> Union[str, None]:
        """
        Extracts the mobile number of the sender from the data received from the webhook.

        Args:
            data[dict]: The data received from the webhook
        Returns:
            str: The mobile number of the sender

        """
        data = self.preprocess(data)
        if "contacts" in data:
            return data["contacts"][0]["wa_id"]

    def get_name(self, data) -> Union[str, None]:
        """
        Extracts the name of the sender from the data received from the webhook.

        Args:
            data[dict]: The data received from the webhook
        Returns:
            str: The name of the sender

        """
        contact = self.preprocess(data)
        if contact:
            return contact["contacts"][0]["profile"]["name"]

    def get_message(self, data) -> Union[str, None]:
        """
        Extracts the text message of the sender from the data received from the webhook.

        Args:
            data[dict]: The data received from the webhook
        Returns:
            str: The text message received from the sender

        """
        data = self.preprocess(data)
        if "messages" in data:
            return data["messages"][0]["text"]["body"]

    def get_message_id(self, data) -> Union[str, None]:
        """
        Extracts the message id of the sender from the data received from the webhook.

        Args:
            data[dict]: The data received from the webhook
        Returns:
            str: The message id of the sender

        """
        data = self.preprocess(data)
        if "messages" in data:
            return data["messages"][0]["id"]

    def get_messages_from_payload(self, payload):
        try:
            # Ensure 'entry' and 'changes' are in the payload
            if "entry" in payload and isinstance(payload["entry"], list):
                for entry in payload["entry"]:
                    if "changes" in entry and isinstance(entry["changes"], list):
                        for change in entry["changes"]:
                            if "value" in change and "messages" in change["value"]:
                                # Extract messages here
                                return change["value"]["messages"]
            logging.error("No 'messages' found in the payload")
            return None
        except Exception as e:
            logging.error(f"Error parsing payload: {str(e)}")
            return None

    def get_message_timestamp(self, data) -> Union[str, None]:
        """ "
        Extracts the timestamp of the message from the data received from the webhook.

        Args:
            data[dict]: The data received from the webhook
        Returns:
            str: The timestamp of the message

        """
        data = self.preprocess(data)
        if "messages" in data:
            return data["messages"][0]["timestamp"]

    def get_interactive_response(self, data) -> Union[Dict, None]:
        """
        Extracts the response of the interactive message from the data received from the webhook.

        Args:
            data[dict]: The data received from the webhook
        Returns:
            dict: The response of the interactive message

        """
        data = self.preprocess(data)
        if "messages" in data:
            if "interactive" in data["messages"][0]:
                return data["messages"][0]["interactive"]

    def get_location(self, data) -> Union[Dict, None]:
        """
        Extracts the location of the sender from the data received from the webhook.

        Args:
            data[dict]: The data received from the webhook

        Returns:
            dict: The location of the sender

        """
        data = self.preprocess(data)
        if "messages" in data:
            if "location" in data["messages"][0]:
                return data["messages"][0]["location"]

    def get_image(self, data) -> Union[Dict, None]:
        """ "
        Extracts the image of the sender from the data received from the webhook.

        Args:
            data[dict]: The data received from the webhook
        Returns:
            dict: The image_id of an image sent by the sender

        """
        data = self.preprocess(data)
        if "messages" in data:
            if "image" in data["messages"][0]:
                return data["messages"][0]["image"]

    def get_document(self, data) -> Union[Dict, None]:
        """ "
        Extracts the document of the sender from the data received from the webhook.

        Args:
            data[dict]: The data received from the webhook
        Returns:
            dict: The document_id of an image sent by the sender

        """
        data = self.preprocess(data)
        if "messages" in data:
            if "document" in data["messages"][0]:
                return data["messages"][0]["document"]

    def get_video(self, data) -> Union[Dict, None]:
        """
        Extracts the video of the sender from the data received from the webhook.

        Args:
            data[dict]: The data received from the webhook

        Returns:
            dict: Dictionary containing the video details sent by the sender

        """
        data = self.preprocess(data)
        if "messages" in data:
            if "video" in data["messages"][0]:
                return data["messages"][0]["video"]

    def get_message_type(self, data) -> Union[str, None]:
        """
        Gets the type of the message sent by the sender from the data received from the webhook.


        Args:
            data [dict]: The data received from the webhook

        Returns:
            str: The type of the message sent by the sender

        """
        data = self.preprocess(data)
        if "messages" in data:
            return data["messages"][0]["type"]

    def get_delivery(self, data) -> Union[Dict, None]:
        """
        Extracts the delivery status of the message from the data received from the webhook.
        Args:
            data [dict]: The data received from the webhook

        Returns:
            dict: The delivery status of the message and message id of the message
        """
        data = self.preprocess(data)
        if "statuses" in data:
            return data["statuses"][0]["status"]

    def changed_field(self, data):
        """
        Helper function to check if the field changed in the data received from the webhook.

        Args:
            data [dict]: The data received from the webhook

        Returns:
            str: The field changed in the data received from the webhook

        """
        return data["entry"][0]["changes"][0]["field"]

    def extract_audio_messages(self, message_received):
        """
        Extract audio messages from the received message.

        Parameters:
        - message_received (str): JSON message containing audio information.

        Returns:
        - list: List of audio messages.
        """
        audio_message_received = json.loads(message_received)
        audio_messages = []

        for entry in audio_message_received["entry"]:
            for change in entry["changes"]:
                audio_messages.extend(change["value"]["messages"])

        return audio_messages

    def handle_request_exception(self, exception):
        """
        Handle request exceptions.

        Parameters:
        - exception (requests.RequestException): Request exception object.
        """
        print(f"Error fetching media URL: {exception}")
        # Add more specific error handling or logging if needed.

    def download_audio_file(self, url, file_path="temp_audio_file.wav"):
        """
        Download an audio file from a URL and save it to a local file.
        :param url: The URL of the audio file.
        :param file_path: Path where the audio file should be saved.
        :return: The path to the downloaded audio file.
        """
        response = requests.get(url)
        if response.status_code == 200:
            with open(file_path, "wb") as audio_file:
                audio_file.write(response.content)
            return file_path
        else:
            raise Exception(
                f"Failed to download audio file from {url}. Status code: {response.status_code}"
            )

    def process_audio_message(self, payload):
        """
        Extract the audio URL from the WhatsApp message payload.
        :param payload: The webhook payload from WhatsApp.
        :return: The URL of the audio file.
        """
        # Example path within payload to the audio URL, adjust based on actual payload structure
        audio_id = payload["entry"][0]["changes"][0]["value"]["messages"][0]["audio"][
            "id"
        ]
        return audio_id

    def fetch_media_url(self, media_id, token):
        """
        Fetch the media URL from the API using the provided media ID.

        :param api_base_url: Base URL of the API.
        :param media_id: ID of the media to fetch.
        :param auth_token: Authentication token for the API.
        :return: URL of the media file.
        """
        url = f"https://graph.facebook.com/v20.0/{media_id}"  # Adjust the endpoint as necessary
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            # Assuming the API returns a JSON response with the media URL in a field named 'media_url'
            logging.info(f"Fetch reponse: {response.json()}")
            media_url = response.json().get("url")
            return media_url
        else:
            raise Exception(
                f"Failed to fetch media URL for ID {media_id}. HTTP Status: {response.status_code}"
            )

    def get_media_url(self, media_id, token):
        """
        Retrieve the media URL for a given media ID from the WhatsApp Business API.

        :param media_id: The media ID obtained from the webhook payload.
        :param access_token: The access token for authenticating with the WhatsApp Business API.
        :return: The URL of the media file.
        """
        url = f"https://graph.facebook.com/v19.0/{media_id}/"
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            media_url = response.json().get("media_url")
            return media_url
        else:
            raise Exception(
                f"Failed to retrieve media URL. HTTP Status: {response.status_code}, Response: {response.text}"
            )

    # my new code

    def valid_payload(self, payload):
        if "object" in payload and "entry" in payload:
            for entry in payload["entry"]:
                if "changes" in entry:
                    for change in entry["changes"]:
                        if "value" in change:
                            # Check for either 'messages' or 'statuses' in the 'value'
                            if (
                                "messages" in change["value"]
                                or "statuses" in change["value"]
                            ):
                                return True
        return False

    def get_phone_number_id(self, payload):
        return payload["entry"][0]["changes"][0]["value"]["metadata"]["phone_number_id"]

    def get_from_number(self, payload):
        return payload["entry"][0]["changes"][0]["value"]["messages"][0]["from"]

    def get_reaction(self, payload):
        # Check if the payload contains a reaction
        messages = payload["entry"][0]["changes"][0]["value"]["messages"]
        for message in messages:
            logging.info(f"Message: {message}")
            if "reaction" in message:
                reaction = message["reaction"]
                logging.info(f"Reaction: {reaction}")
                return message["reaction"]
        return None

    def welcome_message(self, sender_name=""):
        return (
            f"Hello {sender_name},\n\n"
            "Welcome to our translation and audio transcription service! 🌍\n\n"
            "Here are some things you can do:\n\n"
            "1. *Translate Text*:\n"
            "   - Simply send any text message (between 3 to 200 characters) to translate it into your preferred language.\n"
            "   - Reply with 'hi' or 'start' to begin the translation process.\n\n"
            "2. *Set Preferred Language*:\n"
            "   - Please choose the language you prefer to translate to by sending the corresponding number:\n"
            "     1: Luganda (default)\n"
            "     2: Acholi\n"
            "     3: Ateso\n"
            "     4: Lugbara\n"
            "     5: Runyankole\n"
            "     6: English\n"
            "   - You can change your preferred language at any time by sending the number of your new choice.\n\n"
            "3. *Audio Transcription*:\n"
            "   - Send an audio message to transcribe it into text. Make sure to specify your preferred transcription language.\n\n"
            "4. *Feedback*:\n"
            "   - React to any message with an emoji to provide feedback. We value your input!\n\n"
            "5. *Help*:\n"
            "   - Reply with 'help' anytime to receive instructions on how to use this service.\n\n"
            "6. *Unsupported Message Types*:\n"
            "   - Note that we currently do not support image, video, or document messages.\n"
            "   - You will receive a notification if you send any unsupported message type.\n\n"
            "We hope you enjoy using our service. Feel free to reach out if you have any questions or need assistance!\n\n"
            "Best regards,\n"
            "The Translation and Transcription Service Team"
        )

    def help_message(self):
        return (
            "Help Guide:\n\n"
            "1. *Start Translation*:\n"
            "   - Reply with 'hi' or 'start' to initiate the translation service and set your preferred language.\n\n"
            "2. *Send Text for Translation*:\n"
            "   - Simply send any text message (between 3 to 200 characters) to translate it into your chosen language.\n\n"
            "3. *Change Preferred Language*:\n"
            "   - To change your preferred translation language, send the number corresponding to your new choice:\n"
            "     1: Luganda\n"
            "     2: Acholi\n"
            "     3: Ateso\n"
            "     4: Lugbara\n"
            "     5: Runyankole\n"
            "     6: English\n\n"
            "4. *Audio Transcription*:\n"
            "   - Send an audio message to transcribe it into text. Ensure you specify the language for transcription.\n\n"
            "5. *Provide Feedback*:\n"
            "   - React to any message with an emoji to give feedback. Your input helps us improve!\n\n"
            "6. *Need More Help?*:\n"
            "   - If you need further assistance, just reply with 'help' at any time.\n\n"
            "Thank you for using our service! 😊"
        )

    def set_default_target_language(self, user_id, save_user_preference):
        default_target_language = "Luganda"
        defualt_source_language = "English"
        save_user_preference(user_id, defualt_source_language, default_target_language)

    def handle_language_selection(
        self, user_id, selection, source_language, save_user_preference, languages_obj
    ):
        if int(selection) == 6:
            save_user_preference(user_id, source_language, languages_obj[selection])
            return f"Language set to {languages_obj[selection]}. You can now send texts to translate."
        else:
            save_user_preference(user_id, source_language, languages_obj[selection])
            return f"Language set to {languages_obj[selection]}. You can now send texts to translate."

    def get_audio(self, payload: dict):
        """
        Extracts audio information from the webhook payload.

        Args:
            payload (dict): The incoming webhook payload.

        Returns:
            dict: Audio information if available, otherwise None.
        """
        try:
            if "entry" in payload:
                for entry in payload["entry"]:
                    if "changes" in entry:
                        for change in entry["changes"]:
                            if "value" in change and "messages" in change["value"]:
                                for message in change["value"]["messages"]:
                                    if "audio" in message:
                                        audio_info = {
                                            "id": message["audio"]["id"],
                                            "mime_type": message["audio"]["mime_type"],
                                        }
                                        return audio_info
            return None
        except KeyError:
            logging.error("KeyError: Missing expected key in payload.")
            return None

    def handle_ug40_message(
        self,
        payload,
        target_language,
        from_number,
        sender_name,
        phone_number_id,
        processed_messages,
        call_endpoint_with_retry,
    ):
        """
        Handle WhatsApp messages using the UG40 model for classification and processing.
        This method replaces the OpenAI-based message handling with our custom UG40 model.
        """
        message_id = self.get_message_id(payload)

        if message_id in processed_messages:
            logging.info("Message ID %s already processed. Skipping.", message_id)
            return

        # Add message_id to processed messages
        processed_messages.add(message_id)
        logging.info("Message ID %s added to processed messages.", message_id)

        # Language mapping dictionary
        language_mapping = {
            "lug": "Luganda",
            "ach": "Acholi",
            "teo": "Ateso",
            "lgg": "Lugbara",
            "nyn": "Runyankole",
            "eng": "English",
        }

        # Handle different message types
        if interactive_response := self.get_interactive_response(payload):
            return f"Dear {sender_name}, Thanks for that response.", False, ""

        if location := self.get_location(payload):
            return (
                f"Dear {sender_name}, We have no support for messages of type locations.",
                False,
                "",
            )

        if image := self.get_image(payload):
            return (
                f"Dear {sender_name}, We have no support for messages of type image.",
                False,
                "",
            )

        if video := self.get_video(payload):
            return (
                f"Dear {sender_name}, We have no support for messages of type video.",
                False,
                "",
            )

        if docs := self.get_document(payload):
            return f"Dear {sender_name}, We do not support documents.", False, ""

        # Handle audio messages
        if audio_info := self.get_audio(payload):
            return (
                self._handle_audio_with_ug40(
                    audio_info,
                    target_language,
                    from_number,
                    sender_name,
                    phone_number_id,
                    call_endpoint_with_retry,
                ),
                False,
                "",
            )

        # Handle reactions
        elif reaction := self.get_reaction(payload):
            mess_id = reaction["message_id"]
            emoji = reaction["emoji"]
            update_feedback(mess_id, emoji)
            return " ", True, "custom_feedback"

        # Handle text messages with UG40 model
        else:
            return self._handle_text_with_ug40(
                payload,
                target_language,
                from_number,
                sender_name,
                phone_number_id,
                language_mapping,
            )

    def _handle_audio_with_ug40(
        self,
        audio_info,
        target_language,
        from_number,
        sender_name,
        phone_number_id,
        call_endpoint_with_retry,
    ):
        """
        Enhanced audio message handling using improved transcription logic
        Based on tasks.py STT implementation but without audio trimming
        """
        if not audio_info:
            logging.error("No audio information provided.")
            return "Failed to process audio message."

        # Language mapping for better UX
        language_mapping = {
            "lug": "Luganda",
            "ach": "Acholi",
            "teo": "Ateso",
            "lgg": "Lugbara",
            "nyn": "Runyankole",
            "eng": "English",
        }

        target_lang_name = language_mapping.get(target_language, "English")
        if not target_language:
            target_language = "eng"

        # Initialize variables for cleanup
        local_audio_path = None
        blob_name = None
        blob_url = None

        try:
            # Step 1: Notify user that audio was received
            self.send_message(
                "🎵 Audio message received. Processing...",
                os.getenv("WHATSAPP_TOKEN"),
                from_number,
                phone_number_id,
            )

            # Step 2: Fetch media URL from WhatsApp
            audio_url = self.fetch_media_url(
                audio_info["id"], os.getenv("WHATSAPP_TOKEN")
            )
            if not audio_url:
                logging.error("Failed to fetch media URL from WhatsApp API")
                return "❌ Failed to retrieve audio file. Please try sending the audio again."

            # Step 3: Download audio file with validation
            self.send_message(
                "⬇️ Downloading audio file...",
                os.getenv("WHATSAPP_TOKEN"),
                from_number,
                phone_number_id,
            )

            local_audio_path = self.download_whatsapp_audio(
                audio_url, os.getenv("WHATSAPP_TOKEN")
            )
            if not local_audio_path:
                logging.error("Failed to download audio from WhatsApp")
                return "❌ Failed to download audio file. Please check your internet connection and try again."

            # Step 4: Validate audio file (without trimming)
            try:
                audio_segment = AudioSegment.from_file(local_audio_path)
                duration_minutes = len(audio_segment) / (
                    1000 * 60
                )  # Convert to minutes
                file_size_mb = os.path.getsize(local_audio_path) / (1024 * 1024)

                logging.info(
                    f"Audio file validated - Duration: {duration_minutes:.1f} minutes, Size: {file_size_mb:.1f} MB"
                )

                # Log if audio is very long (but don't trim)
                if duration_minutes > 10:
                    logging.info(
                        f"Long audio file detected: {duration_minutes:.1f} minutes"
                    )

            except CouldntDecodeError:
                logging.error(
                    "Downloaded audio file is corrupted or in unsupported format"
                )
                return "❌ Audio file appears to be corrupted or in an unsupported format. Please try sending again."
            except Exception as e:
                logging.error(f"Audio validation error: {str(e)}")
                return "❌ Error validating audio file. Please try again."

            try:
                blob_name, blob_url = upload_audio_file(file_path=local_audio_path)
                if not blob_name or not blob_url:
                    raise Exception("Upload returned empty blob name or URL")

                logging.info(
                    f"Audio file successfully uploaded to cloud storage: {blob_url}"
                )

            except Exception as e:
                logging.error(f"Cloud storage upload error: {str(e)}")
                return "❌ Failed to upload audio to cloud storage. Please try again."

            # Step 5: Initialize transcription service
            self.send_message(
                f"🎯 Starting transcription to {target_lang_name}...",
                os.getenv("WHATSAPP_TOKEN"),
                from_number,
                phone_number_id,
            )

            endpoint = runpod.Endpoint(os.getenv("RUNPOD_ENDPOINT_ID"))
            transcription_data = {
                "input": {
                    "task": "transcribe",
                    "target_lang": target_language,
                    "adapter": target_language,
                    "audio_file": blob_name,
                    "whisper": True,  # Use Whisper for transcription
                    "recognise_speakers": False,
                }
            }

            # Step 6: Process transcription with retry logic
            start_time = time.time()
            try:
                request_response = endpoint.run_sync(transcription_data, timeout=150)

            except TimeoutError as e:
                logging.error(f"Transcription timeout: {str(e)}")
                return "⏱️ Transcription service timed out. Your audio might be too long. Please try with a shorter recording."

            except ConnectionError as e:
                logging.error(f"Connection error during transcription: {str(e)}")
                return "🌐 Connection error during transcription. Please check your internet connection and try again."

            except Exception as e:
                logging.error(f"Transcription error: {str(e)}")
                return (
                    "❌ An error occurred during transcription. Please try again later."
                )

            end_time = time.time()
            processing_time = end_time - start_time
            logging.info(f"Transcription completed in {processing_time:.2f} seconds")

            # Step 7: Validate transcription result
            transcribed_text = request_response.get("audio_transcription", "").strip()
            if not transcribed_text:
                logging.warning("Empty transcription result received")
                return "🔇 No speech detected in the audio. Please ensure you're speaking clearly and try again."

            # Step 8: Process with UG40 model for enhanced response
            self.send_message(
                "🧠 Processing with advanced language model...",
                os.getenv("WHATSAPP_TOKEN"),
                from_number,
                phone_number_id,
            )

            #             # Create specialized prompt for UG40
            ug40_system_message = f""" You are Sunflower, a multilingual assistant for Ugandan languages made by Sunbird AI. You specialise in accurate translations, explanations, summaries and other cross-lingual tasks."""

            try:
                ug40_response = run_inference(
                    transcribed_text, "qwen", custom_system_message=ug40_system_message
                )

                return ug40_response.get("content", "")

            except Exception as ug40_error:
                logging.error(f"UG40 processing error for audio: {str(ug40_error)}")
                # Fallback to basic transcription response
                return f'🎵 *Audio Transcription:*\n"{transcribed_text}"\n\n✅ Your message has been transcribed successfully!'

        except Exception as e:
            logging.error(f"Unexpected error in audio processing: {str(e)}")
            return "❌ An unexpected error occurred while processing your audio. Please try again."

        finally:
            # Step 10: Cleanup temporary files
            if local_audio_path and os.path.exists(local_audio_path):
                try:
                    os.remove(local_audio_path)
                    logging.info("Cleaned up local audio file")
                except Exception as cleanup_error:
                    logging.warning(
                        f"Could not clean up local audio file: {cleanup_error}"
                    )

    def _handle_text_with_ug40(
        self,
        payload,
        target_language,
        from_number,
        sender_name,
        phone_number_id,
        language_mapping,
    ):
        """Enhanced text message handling with improved prompting, context, and response saving"""
        try:
            input_text = self.get_message(payload)
            mess_id = self.get_message_id(payload)

            # Save current user message
            save_message(from_number, input_text)

            # Check for natural language commands
            command_response = self._handle_natural_commands(
                input_text,
                target_language,
                from_number,
                sender_name,
                phone_number_id,
                language_mapping,
                mess_id,
            )

            if command_response:
                # Save the command response
                save_response(from_number, input_text, command_response, mess_id)
                return command_response, False, ""

            # Get conversation context using conversation pairs
            conversation_pairs = get_user_last_five_conversation_pairs(from_number)
            is_new_user = len(conversation_pairs) == 0

            enhanced_system_message = "You are Sunflower, a multilingual assistant for Ugandan languages made by Sunbird AI. You specialise in accurate translations, explanations, summaries and other cross-lingual tasks. Given the users last five previous conversations, use that context to inform your response. Always respond in a concise manner suitable for WhatsApp. Never echo the user's input. Focus on being helpful and culturally sensitive."

            logging.info(
                f"Enhanced system message for UG40:\n{enhanced_system_message}"
            )

            # Create simple user instruction (only current message)
            if is_new_user:
                user_instruction = (
                    "No previous messages. Start by welcoming the user to the platform powered by Sunbird AI of Uganda.\n"
                    f'Current message: "{input_text}"'
                )
                # self.send_templatev2(
                #     token=os.getenv("WHATSAPP_TOKEN"),
                #     template="welcome_message",
                #     phone_number_id=phone_number_id,
                #     recipient_id=from_number,
                #     components=[
                #         {"type": "body", "parameters": [{"type": "text", "text": sender_name}]}
                #     ]
                # )
                return " ", True, "welcome_message"
            else:
                # Format previous conversation pairs for context
                formatted_pairs = ""
                for i, pair in enumerate(conversation_pairs, 1):
                    formatted_pairs += f"\n{i}. User: \"{pair['user_message']}\"\n   Bot: \"{pair['bot_response'][:100]}{'...' if len(pair['bot_response']) > 100 else ''}\""
                user_instruction = (
                    f"Previous conversation:{formatted_pairs}\n"
                    f'Current message: "{input_text}"'
                )

            # Call UG40 model with enhanced system message
            ug40_response = run_inference(
                user_instruction, "qwen", custom_system_message=enhanced_system_message
            )

            response_content = ug40_response.get("content", "").strip()

            # Validate and clean response
            if not response_content:
                response_content = self._get_fallback_response(input_text, is_new_user)

            # Ensure response isn't too long for WhatsApp
            if len(response_content) > 1600:  # WhatsApp message limit consideration
                response_content = (
                    response_content[:1500]
                    + "...\n\nMessage truncated. Please ask for specific parts if you need more details."
                )

            # Save the bot response with the user message it responds to
            save_response(from_number, input_text, response_content, mess_id)

            return response_content, False, ""

        except Exception as e:
            logging.error(f"Error in enhanced UG40 processing: {str(e)}")
            fallback_response = self._get_fallback_response(input_text, False)
            # Save the fallback response as well
            save_response(from_number, input_text, fallback_response, mess_id)
            return fallback_response, False, ""

    def _handle_natural_commands(
        self,
        input_text,
        target_language,
        from_number,
        sender_name,
        phone_number_id,
        language_mapping,
        mess_id,
    ):
        """
        Handle natural language commands without requiring special symbols

        Supported commands:
        - help - Show available commands
        - status - Show current language settings
        - languages - Show supported languages
        - set language [language_name/code] - Set target language
        - translate [text] - Direct translation (if starts with "translate")
        """
        # Normalize input for command detection
        normalized_input = input_text.strip().lower()

        try:
            # Split input into words for analysis
            words = normalized_input.split()

            if not words:
                return None

            first_word = words[0]

            # Handle single word commands
            if len(words) == 1:
                if first_word in ["help", "commands"]:
                    return self._show_command_help()
                elif first_word == "status":
                    return self._show_user_status(
                        target_language, language_mapping, sender_name
                    )
                elif first_word in ["languages", "language"]:
                    return self._show_supported_languages(language_mapping)

            # Handle multi-word commands
            elif len(words) >= 2:
                # "set language [language]"
                if first_word == "set" and words[1] in ["language", "lang"]:
                    if len(words) >= 3:
                        language_arg = " ".join(words[2:])
                        # return self._handle_set_language_command(
                        #     language_arg, from_number, language_mapping
                        # )
                        return (
                            "Please select your preferred language from the options above.",
                            True,
                            "choose_language",
                        )
                    else:
                        return (
                            "❌ Please specify a language. Example: `set language english` or `set language luganda`",
                            False,
                            "",
                        )

                # "change language [language]" or "switch language [language]"
                elif (
                    first_word in ["change", "switch"]
                    and len(words) >= 3
                    and words[1] in ["language", "lang"]
                ):
                    language_arg = " ".join(words[2:])
                    return self._handle_set_language_command(
                        language_arg, from_number, language_mapping
                    )

            # Check if the entire message is asking for help (various phrasings)
            help_phrases = [
                "what can you do",
                "how to use",
                "how do i use",
                "what commands",
                "show commands",
                "list commands",
                "available commands",
            ]

            if any(phrase in normalized_input for phrase in help_phrases):
                return self._show_command_help()

            # Check if asking about languages
            language_phrases = [
                "what languages",
                "supported languages",
                "available languages",
                "which languages",
                "list languages",
            ]

            if any(phrase in normalized_input for phrase in language_phrases):
                return self._show_supported_languages(language_mapping)

            # Check if asking about status
            status_phrases = [
                "my settings",
                "current settings",
                "my language",
                "current language",
            ]

            if any(phrase in normalized_input for phrase in status_phrases):
                return self._show_user_status(
                    target_language, language_mapping, sender_name
                )

            # No command detected
            return None

        except Exception as e:
            logging.error(f"Error processing natural command '{input_text}': {str(e)}")
            return None

    def _handle_set_language_command(self, language_arg, from_number, language_mapping):
        """Handle language setting command"""
        try:
            # Normalize the language argument
            language_arg = language_arg.strip().lower()

            # Check if it's a valid language code or name
            language_code = None
            language_name = None

            # Direct code match
            if language_arg in language_mapping:
                language_code = language_arg
                language_name = language_mapping[language_arg]
            else:
                # Search by language name
                for code, name in language_mapping.items():
                    if name.lower() == language_arg or name.lower().startswith(
                        language_arg
                    ):
                        language_code = code
                        language_name = name
                        break

            if language_code:
                # Update user's language preference (implement your storage logic here)
                # update_user_language_preference(from_number, language_code)

                return (
                    f"✅ Language set to {language_name} ({language_code}). All audios should be sent in {language_name}.",
                    False,
                    "",
                )
            else:
                available_languages = "\n".join(
                    [f"• {name} ({code})" for code, name in language_mapping.items()]
                )
                return (
                    f"❌ Language '{language_arg}' not found.\n\nSupported languages:\n{available_languages}",
                    False,
                    "",
                )

        except Exception as e:
            logging.error(f"Error setting language: {str(e)}")
            return "❌ Error updating language settings. Please try again.", False, ""

    def _show_command_help(self):
        """Show available commands and usage"""
        help_text = """🌻 *Sunflower Assistant Commands*

        *Basic Commands:*
        • `help` - Show this help message
        • `status` - Show your current settings
        • `languages` - Show supported languages

        *Language Commands:*
        • `set language [name]` - Set your preferred language
        Example: `set language luganda`
        • `translate [text]` - Translate text directly
        Example: `translate hello world`

        *Natural Questions:*
        You can also ask naturally:
        • "What can you do?"
        • "What languages do you support?"
        • "Change my language to English"

        Just type your message normally - I'm here to help! 🌻"""

        return help_text, False, ""

    def _show_user_status(self, target_language, language_mapping, sender_name):
        """Show current user status and settings"""
        try:
            language_name = language_mapping.get(target_language, target_language)

            status_text = f"""👤 *Status for {sender_name}*

            🌐 *Current Language:* {language_name} ({target_language})
            🤖 *Assistant:* Sunflower by Sunbird AI
            📱 *Platform:* WhatsApp

            Type `help` for available commands or just chat naturally!"""

            return status_text, False, ""

        except Exception as e:
            logging.error(f"Error showing user status: {str(e)}")
            return "❌ Error retrieving status information.", False, ""

    def _show_supported_languages(self, language_mapping):
        """Show all supported languages"""
        try:
            languages_list = []
            for code, name in sorted(language_mapping.items()):
                languages_list.append(f"• {name} ({code})")

            languages_text = f"""🌐 *Supported Languages*

                            {chr(10).join(languages_list)}

                            To set your language, type:
                            `set language [name]` or `set language [code]`

                            Example: `set language english` or `set language en`"""

            return languages_text, False, ""

        except Exception as e:
            logging.error(f"Error showing supported languages: {str(e)}")
            return "❌ Error retrieving language information.", False, ""

    def _get_fallback_response(self, input_text, is_new_user):
        """Provide contextual fallback responses"""
        if is_new_user:
            return """Hello! I'm UgandaBot, your Ugandan language assistant. I can help with:
                    • Translations between Ugandan languages and English
                    • Language learning and cultural context
                    • General questions about Uganda

                    I'm experiencing technical difficulties right now. Please try again in a moment."""
        else:
            return (
                "I'm experiencing technical difficulties processing your message. Please try rephrasing or try again later.",
                False,
                "",
            )

    def detect_language(self, text):
        endpoint = runpod.Endpoint(os.getenv("RUNPOD_ENDPOINT_ID"))
        request_response = {}

        try:
            request_response = endpoint.run_sync(
                {
                    "input": {
                        "task": "auto_detect_language",
                        "text": text,
                    }
                },
                timeout=60,
            )

            logging.info("Request response: %s", request_response)

            if request_response:
                return request_response["language"]
            else:
                raise HTTPException(
                    status_code=500,
                    detail="Language detection failed. No output from the service.",
                )

        except TimeoutError as e:
            logging.error("Job timed out.")
            raise HTTPException(
                status_code=408,
                detail="The language identification job timed out. Please try again later.",
            ) from e
