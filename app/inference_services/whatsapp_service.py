import json
import logging
import mimetypes
import os
import secrets
import time
from datetime import datetime
from typing import Any, Dict, List, Union

import requests
import runpod
from dotenv import load_dotenv
from fastapi import HTTPException
from requests_toolbelt import MultipartEncoder

from app.inference_services.openai_script import (
    classify_input,
    get_completion_from_messages,
    get_guide_based_on_classification,
    is_json,
)
from app.inference_services.ug40_inference import run_inference
from app.inference_services.user_preference import (
    get_user_last_five_messages,
    get_user_preference,
    save_message,
    save_translation,
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
        try:
            # Generate a random string and get the current timestamp
            random_string = secrets.token_hex(8)  # Generates a secure random hex string
            current_time = datetime.now().strftime(
                "%Y%m%d_%H%M%S"
            )  # Formats the date and time

            # Define the local path for temporary storage with the random string and time
            local_audio_path = f"audio_{random_string}_{current_time}.mp3"

            # Download the audio file
            headers = {"Authorization": f"Bearer {access_token}"}
            response = requests.get(url, headers=headers, stream=True)
            if response.status_code == 200:
                with open(local_audio_path, "wb") as f:
                    f.write(response.content)

                logging.info(
                    f"Whatsapp audio download was successfull: {local_audio_path}"
                )  # pylint: disable=logging-fstring-interpolation
                return local_audio_path
            else:
                raise HTTPException(
                    status_code=500, detail="Failed to download audio file"
                )

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

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
        lang: str = "en_US",
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
        self, token, template, recipient_id, components, phone_number_id, lang="en_US"
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

    # def get_audio(self, data) -> Union[Dict, None]:
    #     """
    #     Extracts the audio of the sender from the data received from the webhook.

    #     Args:
    #         data[dict]: The data received from the webhook

    #     Returns:
    #         dict: The audio of the sender

    #     """
    #     data = self.preprocess(data)
    #     if "messages" in data:
    #         if "audio" in data["messages"][0]:
    #             return data["messages"][0]["audio"]

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

    def handle_openai_message(
        self,
        payload,
        target_language,
        from_number,
        sender_name,
        phone_number_id,
        processed_messages,
        call_endpoint_with_retry,
    ):
        message_id = self.get_message_id(
            payload
        )  # Extract unique message ID from the payload

        if message_id in processed_messages:
            logging.info("Message ID %s already processed. Skipping.", {message_id})
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

        if interactive_response := self.get_interactive_response(payload):
            response = interactive_response
            return f"Dear {sender_name}, Thanks for that response."

        if location := self.get_location(payload):
            response = location
            return f"Dear {sender_name}, We have no support for messages of type locations."

        if image := self.get_image(payload):
            response = image
            return f"Dear {sender_name}, We have no support for messages of type image."

        if video := self.get_video(payload):
            response = video
            return f"Dear {sender_name}, We have no support for messages of type video."

        if docs := self.get_document(payload):
            response = docs
            return f"Dear {sender_name}, We do not support documents."

        # Step 1: Retrieve audio information from the payload
        if audio_info := self.get_audio(payload):
            if not audio_info:
                logging.error("No audio information provided.")
                return "Failed to transcribe audio."

            self.send_message(
                "Audio has been received ...",
                os.getenv("WHATSAPP_TOKEN"),
                from_number,
                phone_number_id,
            )

            if not target_language:
                target_language = "lug"

            # Step 2: Fetch the media URL using the WhatsApp token
            audio_url = self.fetch_media_url(
                audio_info["id"], os.getenv("WHATSAPP_TOKEN")
            )
            if not audio_url:
                logging.error("Failed to fetch media URL.")
                return "Failed to transcribe audio."

            # Step 3: Download the audio file locally
            local_audio_path = self.download_whatsapp_audio(
                audio_url, os.getenv("WHATSAPP_TOKEN")
            )
            if not local_audio_path:
                logging.error("Failed to download audio from WhatsApp.")
                return "Failed to transcribe audio."

            # Upload the audio file to GCS and return the blob and URL
            blob_name, blob_url = upload_audio_file(local_audio_path)

            if blob_name and blob_url:
                logging.info("Audio file successfully uploaded to GCS: %s", blob_url)
            else:
                raise Exception("Failed to upload audio to GCS")

            # Step 4: Notify the user that the audio has been received
            self.send_message(
                "Audio has been loaded ...",
                os.getenv("WHATSAPP_TOKEN"),
                from_number,
                phone_number_id,
            )

            # Step 5: Initialize the Runpod endpoint for transcription
            endpoint = runpod.Endpoint(os.getenv("RUNPOD_ENDPOINT_ID"))

            # logging.info("Audio data found for langauge detection")
            # data = {
            #     "input": {
            #         "task": "auto_detect_audio_language",
            #         "audio_file": blob_name,
            #     }
            # }

            # start_time = time.time()

            # try:
            #     logging.info("Audio file ready for langauge detection")
            #     audio_lang_response = call_endpoint_with_retry(endpoint, data)
            # except TimeoutError as e:

            #     logging.error("Job timed out %s", str(e))
            #     raise HTTPException(
            #         status_code=503, detail="Service unavailable due to timeout."
            #     ) from e

            # except ConnectionError as e:

            #     logging.error("Connection lost: %s", str(e))
            #     raise HTTPException(
            #         status_code=503, detail="Service unavailable due to connection error."
            #     ) from e

            # end_time = time.time()
            # logging.info(
            #     "Audio language auto detection response: %s ",
            #     audio_lang_response.get("detected_language"),
            # )

            # # Calculate the elapsed time
            # elapsed_time = end_time - start_time
            # logging.info(
            #     "Audio language auto detection elapsed time: %s seconds", elapsed_time
            # )

            # audio_language = audio_lang_response.get("detected_language")
            request_response = {}

            if target_language in language_mapping:
                # Language is in the mapping
                logging.info("Language detected in audio is %s", target_language)
            else:
                # Language is not in our scope
                return "Audio Language not detected"

            try:

                start_time = time.time()

                # Step 6: Notify the user that transcription is in progress
                self.send_message(
                    "Your transcription is being processed ...",
                    os.getenv("WHATSAPP_TOKEN"),
                    from_number,
                    phone_number_id,
                )

                try:
                    # Step 7: Call the transcription service with the correct parameters
                    request_response = endpoint.run_sync(
                        {
                            "input": {
                                "task": "transcribe",
                                "target_lang": target_language,
                                "adapter": target_language,
                                "audio_file": blob_name,  # Corrected to pass local file path
                                "recognise_speakers": False,
                            }
                        },
                        timeout=150,  # Set a timeout for the transcription job.
                    )

                    # Step 8: Notify the user that transcription is in progress
                    self.send_message(
                        "Your transcription is ready ...",
                        os.getenv("WHATSAPP_TOKEN"),
                        from_number,
                        phone_number_id,
                    )

                except TimeoutError as e:
                    logging.error("Transcription job timed out: %s", str(e))
                    return "Failed to transcribe audio."
                except Exception as e:
                    logging.error("Unexpected error during transcription: %s", str(e))
                    return "Failed to transcribe audio."

                # Step 9: Log the time taken for the transcription
                end_time = time.time()
                elapsed_time = end_time - start_time
                logging.info("Here is the response: %s", request_response)
                logging.info(
                    "Elapsed time: %s seconds for transcription.", elapsed_time
                )

                self.send_message(
                    "Translating to your target language if you haven't set a target language the default is Lugande.....",
                    os.getenv("WHATSAPP_TOKEN"),
                    from_number,
                    phone_number_id,
                )

                detected_language = self.detect_language(
                    request_response.get("audio_transcription")
                )
                translation = self.translate_text(
                    request_response.get("audio_transcription"),
                    detected_language,
                    target_language,
                )

                # Step 10: Return the translation result
                return translation

            finally:
                # Step 11: Clean up the local audio file
                if os.path.exists(local_audio_path):
                    os.remove(local_audio_path)
                    logging.info("Cleaned up local audio file: %s", request_response)

        elif reaction := self.get_reaction(payload):
            mess_id = reaction["message_id"]
            emoji = reaction["emoji"]
            update_feedback(mess_id, emoji)
            return f"Dear {sender_name}, Thanks for your feedback {emoji}."

        else:
            # Extract relevant information
            input_text = self.get_message(payload)
            mess_id = self.get_message_id(payload)
            save_message(from_number, input_text)

            # Get last five messages for context
            last_five_messages = get_user_last_five_messages(from_number)

            # Format the previous messages for context clarity
            formatted_message_history = "\n".join(
                [
                    f"Message {i+1}: {msg['message_text']}"
                    for i, msg in enumerate(last_five_messages)
                ]
            )

            # Combine the message context to inform the model
            messages_context = f"Previous messages (starting from the most recent):\n{formatted_message_history}\nCurrent message:\n{input_text}"

            # Classify the user input and get the appropriate guide
            classification = classify_input(input_text)
            guide = get_guide_based_on_classification(classification)

            # Generate response from OpenAI
            messages = [
                {"role": "system", "content": guide},
                {"role": "user", "content": messages_context},
            ]
            response = get_completion_from_messages(messages)

            if is_json(response):
                json_object = json.loads(response)
                # print ("Is valid json? true")
                logging.info("Open AI response: %s", json_object)
                task = json_object["task"]
                # print(task)

                if task == "translation":
                    detected_language = self.detect_language(json_object["text"])
                    # save_user_preference(
                    #     from_number, detected_language, json_object["target_language"]
                    # )
                    if json_object["target_language"]:
                        translation = self.translate_text(
                            json_object["text"],
                            detected_language,
                            json_object["target_language"],
                        )
                    elif target_language:
                        translation = self.translate_text(
                            json_object["text"],
                            detected_language,
                            target_language,
                        )
                    else:
                        translation = self.translate_text(
                            json_object["text"],
                            detected_language,
                            "lug",
                        )

                    save_translation(
                        from_number,
                        json_object["text"],
                        translation,
                        detected_language,
                        target_language,
                        mess_id,
                    )
                    return f""" Here is the translation: {translation} """

                elif task == "greeting":
                    detected_language = self.detect_language(input_text)
                    translation = " "
                    if target_language:
                        translation = self.translate_text(
                            input_text,
                            detected_language,
                            target_language,
                        )
                    else:
                        translation = self.translate_text(
                            input_text,
                            detected_language,
                            "lug",
                        )

                    target_language = self.detect_language(translation)
                    message = json_object["text"]

                    save_translation(
                        from_number,
                        input_text,
                        translation,
                        detected_language,
                        target_language,
                        mess_id,
                    )

                    self.send_message(
                        message,
                        os.getenv("WHATSAPP_TOKEN"),
                        from_number,
                        phone_number_id,
                    )

                    # reply_to_message(
                    # os.getenv("WHATSAPP_TOKEN"), mess_id,  from_number, phone_number_id, message,
                    # )

                    return f""" Here is the translation: {translation} """

                elif task == "currentLanguage":
                    # Get the full language name using the code
                    target_language = get_user_preference(from_number)

                    language_name = language_mapping.get(target_language)
                    if language_name:
                        return f"Your current target language is {language_name}"
                    else:
                        return "You currently don't have a set language."

                elif task == "setLanguage":
                    settargetlanguage = json_object["language"]

                    logging.info("This language set: %s", settargetlanguage)

                    save_user_preference(from_number, None, settargetlanguage)

                    language_name = language_mapping.get(settargetlanguage)

                    return f"Language set to {language_name}"

                elif task == "conversation":

                    detected_language = self.detect_language(input_text)
                    translation = ""
                    if target_language:
                        translation = self.translate_text(
                            input_text,
                            detected_language,
                            target_language,
                        )
                    else:
                        translation = self.translate_text(
                            input_text,
                            detected_language,
                            "lug",
                        )
                    target_language = self.detect_language(translation)
                    message = json_object["text"]

                    save_translation(
                        from_number,
                        input_text,
                        translation,
                        detected_language,
                        target_language,
                        mess_id,
                    )

                    self.send_message(
                        message,
                        os.getenv("WHATSAPP_TOKEN"),
                        from_number,
                        phone_number_id,
                    )

                    # reply_to_message(
                    # os.getenv("WHATSAPP_TOKEN"), mess_id,  from_number, phone_number_id, message,
                    # )

                    return f""" Here is the translation: {translation} """

                elif task == "help":
                    detected_language = self.detect_language(input_text)
                    translation = ""
                    if target_language:
                        translation = self.translate_text(
                            input_text,
                            detected_language,
                            target_language,
                        )
                    else:
                        translation = self.translate_text(
                            input_text,
                            detected_language,
                            "lug",
                        )
                    target_language = self.detect_language(translation)
                    message = json_object["text"]

                    save_translation(
                        from_number,
                        input_text,
                        translation,
                        detected_language,
                        target_language,
                        mess_id,
                    )

                    self.send_message(
                        message,
                        os.getenv("WHATSAPP_TOKEN"),
                        from_number,
                        phone_number_id,
                    )

                    # reply_to_message(
                    # os.getenv("WHATSAPP_TOKEN"), mess_id,  from_number, phone_number_id, message,
                    # )

                    return f""" Here is the translation: {translation} """

            else:
                return response

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
            return f"Dear {sender_name}, Thanks for that response."

        if location := self.get_location(payload):
            return f"Dear {sender_name}, We have no support for messages of type locations."

        if image := self.get_image(payload):
            return f"Dear {sender_name}, We have no support for messages of type image."

        if video := self.get_video(payload):
            return f"Dear {sender_name}, We have no support for messages of type video."

        if docs := self.get_document(payload):
            return f"Dear {sender_name}, We do not support documents."

        # Handle audio messages
        if audio_info := self.get_audio(payload):
            return self._handle_audio_with_ug40(
                audio_info, target_language, from_number, sender_name, 
                phone_number_id, call_endpoint_with_retry
            )

        # Handle reactions
        elif reaction := self.get_reaction(payload):
            mess_id = reaction["message_id"]
            emoji = reaction["emoji"]
            update_feedback(mess_id, emoji)
            return f"Dear {sender_name}, Thanks for your feedback {emoji}."

        # Handle text messages with UG40 model
        else:
            return self._handle_text_with_ug40(
                payload, target_language, from_number, sender_name, 
                phone_number_id, language_mapping
            )

    def _handle_audio_with_ug40(
        self, audio_info, target_language, from_number, sender_name, 
        phone_number_id, call_endpoint_with_retry
    ):
        """Handle audio messages using UG40 model for processing"""
        if not audio_info:
            logging.error("No audio information provided.")
            return "Failed to transcribe audio."

        self.send_message(
            "Audio has been received ...",
            os.getenv("WHATSAPP_TOKEN"),
            from_number,
            phone_number_id,
        )

        if not target_language:
            target_language = "lug"

        try:
            # Fetch the media URL
            audio_url = self.fetch_media_url(
                audio_info["id"], os.getenv("WHATSAPP_TOKEN")
            )
            if not audio_url:
                logging.error("Failed to fetch media URL.")
                return "Failed to transcribe audio."

            # Download the audio file locally
            local_audio_path = self.download_whatsapp_audio(
                audio_url, os.getenv("WHATSAPP_TOKEN")
            )
            if not local_audio_path:
                logging.error("Failed to download audio from WhatsApp.")
                return "Failed to transcribe audio."

            # Upload the audio file to GCS
            blob_name, blob_url = upload_audio_file(local_audio_path)
            if not (blob_name and blob_url):
                raise Exception("Failed to upload audio to GCS")

            logging.info("Audio file successfully uploaded to GCS: %s", blob_url)

            self.send_message(
                "Audio has been loaded ...",
                os.getenv("WHATSAPP_TOKEN"),
                from_number,
                phone_number_id,
            )

            # Initialize the Runpod endpoint for transcription
            endpoint = runpod.Endpoint(os.getenv("RUNPOD_ENDPOINT_ID"))

            self.send_message(
                "Your transcription is being processed ...",
                os.getenv("WHATSAPP_TOKEN"),
                from_number,
                phone_number_id,
            )

            # Call the transcription service
            request_response = endpoint.run_sync(
                {
                    "input": {
                        "task": "transcribe",
                        "target_lang": target_language,
                        "adapter": target_language,
                        "audio_file": blob_name,
                        "recognise_speakers": False,
                    }
                },
                timeout=150,
            )

            self.send_message(
                "Your transcription is ready ...",
                os.getenv("WHATSAPP_TOKEN"),
                from_number,
                phone_number_id,
            )

            # Use UG40 model to process the transcription
            transcribed_text = request_response.get("audio_transcription", "")
            if transcribed_text:
                self.send_message(
                    "Processing with our advanced language model...",
                    os.getenv("WHATSAPP_TOKEN"),
                    from_number,
                    phone_number_id,
                )

                # Create prompt for UG40 model
                ug40_prompt = f"""
                I have transcribed the following audio message: "{transcribed_text}"
                
                Please:
                1. Detect the language of this transcription
                2. If the language is not {target_language}, translate it to {target_language}
                3. Provide a natural, conversational response
                
                Please respond in JSON format:
                {{
                    "detected_language": "language_code",
                    "translation": "translated_text_if_needed",
                    "response": "your_response_to_user"
                }}
                """

                # Use UG40 model (default to gemma)
                ug40_response = run_inference(ug40_prompt, "gemma")
                response_content = ug40_response.get("content", "")
                
                # Try to parse JSON response
                try:
                    import json
                    response_data = json.loads(response_content)
                    return response_data.get("response", response_content)
                except json.JSONDecodeError:
                    # If not valid JSON, return the content directly
                    return response_content
            else:
                return "Failed to transcribe audio."

        except Exception as e:
            logging.error(f"Error in audio processing: {str(e)}")
            return "Failed to process audio message."
        finally:
            # Clean up local audio file
            if 'local_audio_path' in locals() and os.path.exists(local_audio_path):
                os.remove(local_audio_path)
                logging.info("Cleaned up local audio file")

    def _handle_text_with_ug40(
        self, payload, target_language, from_number, sender_name, 
        phone_number_id, language_mapping
    ):
        """Handle text messages using UG40 model for classification and processing"""
        input_text = self.get_message(payload)
        mess_id = self.get_message_id(payload)
        save_message(from_number, input_text)

        # Get last five messages for context
        last_five_messages = get_user_last_five_messages(from_number)
        formatted_message_history = "\n".join([
            f"Message {i+1}: {msg['message_text']}"
            for i, msg in enumerate(last_five_messages)
        ])

        # Create comprehensive prompt for UG40 model
        ug40_prompt = f"""
        You are a WhatsApp language assistant for Ugandan languages. The user has sent you a message.
        
        Previous conversation context:
        {formatted_message_history}
        
        Current message: "{input_text}"
        User's preferred target language: {target_language if target_language else 'lug (Luganda)'}
        
        Please analyze this message and respond appropriately. Consider these scenarios:
        
        1. **Translation Request**: If the user wants translation, detect the source language and translate to their preferred language
        2. **Greeting**: If it's a greeting, respond naturally and offer help
        3. **Language Setting**: If they want to change their language preference, help them set it
        4. **Help Request**: If they need help, provide guidance
        5. **General Conversation**: Engage naturally while being helpful about language services
        
        Available languages: Luganda (lug), Acholi (ach), Ateso (teo), Lugbara (lgg), Runyankole (nyn), English (eng)
        
        Please respond in JSON format:
        {{
            "task": "translation|greeting|setLanguage|help|conversation",
            "detected_language": "detected_language_code",
            "target_language": "target_language_code_if_applicable",
            "text_to_translate": "text_if_translation_needed",
            "response": "your_response_to_user",
            "needs_translation": true/false,
            "translation": "translated_text_if_needed"
        }}
        """

        try:
            # Use UG40 model for processing (default to gemma)
            ug40_response = run_inference(ug40_prompt, "gemma")
            response_content = ug40_response.get("content", "")
            
            # Try to parse JSON response
            try:
                import json
                response_data = json.loads(response_content)
                
                task = response_data.get("task", "conversation")
                detected_language = response_data.get("detected_language", "eng")
                response_text = response_data.get("response", "")
                
                # Handle different tasks
                if task == "translation" and response_data.get("needs_translation", False):
                    translation = response_data.get("translation", "")
                    if translation:
                        save_translation(
                            from_number,
                            response_data.get("text_to_translate", input_text),
                            translation,
                            detected_language,
                            target_language,
                            mess_id,
                        )
                        return f"Here is the translation: {translation}"
                
                elif task == "setLanguage":
                    new_language = response_data.get("target_language")
                    if new_language in language_mapping:
                        save_user_preference(from_number, None, new_language)
                        language_name = language_mapping.get(new_language)
                        return f"Language set to {language_name}"
                
                elif task == "greeting":
                    # Send the response message first
                    self.send_message(
                        response_text,
                        os.getenv("WHATSAPP_TOKEN"),
                        from_number,
                        phone_number_id,
                    )
                    
                    # If there's a translation, save it
                    if response_data.get("needs_translation", False):
                        translation = response_data.get("translation", "")
                        save_translation(
                            from_number,
                            input_text,
                            translation,
                            detected_language,
                            target_language,
                            mess_id,
                        )
                        return f"Translation: {translation}"
                    
                    return response_text
                
                else:  # conversation, help, or other tasks
                    # Send the response message
                    self.send_message(
                        response_text,
                        os.getenv("WHATSAPP_TOKEN"),
                        from_number,
                        phone_number_id,
                    )
                    
                    # If there's a translation component, save it
                    if response_data.get("needs_translation", False):
                        translation = response_data.get("translation", "")
                        save_translation(
                            from_number,
                            input_text,
                            translation,
                            detected_language,
                            target_language,
                            mess_id,
                        )
                        return f"Translation: {translation}"
                    
                    return response_text
                    
            except json.JSONDecodeError:
                # If not valid JSON, return the content directly
                logging.warning("UG40 response was not valid JSON, returning content directly")
                return response_content
                
        except Exception as e:
            logging.error(f"Error in UG40 processing: {str(e)}")
            # Fallback to basic translation if UG40 fails
            try:
                detected_language = self.detect_language(input_text)
                if target_language and detected_language != target_language:
                    translation = self.translate_text(input_text, detected_language, target_language)
                    save_translation(from_number, input_text, translation, detected_language, target_language, mess_id)
                    return f"Here is the translation: {translation}"
                else:
                    return "I understand your message. How can I help you with language services today?"
            except Exception as fallback_error:
                logging.error(f"Fallback also failed: {str(fallback_error)}")
                return "I'm sorry, I'm having trouble processing your message right now. Please try again."

    def handle_message(
        self,
        payload,
        from_number,
        sender_name,
        source_language,
        target_language,
        phone_number_id,
        languages_obj,
    ):
        if interactive_response := self.get_interactive_response(payload):
            response = interactive_response
            return f"Dear {sender_name}, Thanks for that response."

        if location := self.get_location(payload):
            response = location
            return f"Dear {sender_name}, We have no support for messages of type locations."

        if image := self.get_image(payload):
            response = image
            return f"Dear {sender_name}, We have no support for messages of type image."

        if video := self.get_video(payload):
            response = video
            return f"Dear {sender_name}, We have no support for messages of type video."

        if docs := self.get_document(payload):
            response = docs
            return f"Dear {sender_name}, We do not support documents."

        # if audio := get_audio(payload):
        #     return handle_audio_message(audio, target_language, sender_name)

        if reaction := self.get_reaction(payload):
            mess_id = reaction["message_id"]
            emoji = reaction["emoji"]
            update_feedback(mess_id, emoji)
            return f"Dear {sender_name}, Thanks for your feedback {emoji}."

        return self.handle_text_message(
            payload,
            from_number,
            sender_name,
            source_language,
            target_language,
            languages_obj,
        )

    def handle_text_message(
        self,
        payload,
        from_number,
        sender_name,
        source_language,
        target_language,
        languages_obj,
    ):
        msg_body = self.get_message(payload)

        if not target_language or not source_language:
            self.set_default_target_language(from_number, save_user_preference)
            return self.welcome_message(sender_name)

        if msg_body.lower() in ["hi", "start"]:
            return self.welcome_message(sender_name)

        if msg_body.isdigit() and msg_body in languages_obj:
            return self.handle_language_selection(
                from_number,
                msg_body,
                source_language,
                save_user_preference,
                languages_obj,
            )

        if msg_body.lower() == "help":
            return self.help_message()

        if 3 <= len(msg_body) <= 200:
            detected_language = self.detect_language(msg_body)
            translation = self.translate_text(
                msg_body, detected_language, target_language
            )
            mess_id = self.send_message(
                translation, self.token, from_number, self.get_phone_number_id(payload)
            )

            save_translation(
                from_number,
                msg_body,
                translation,
                detected_language,
                target_language,
                mess_id,
            )
            save_user_preference(from_number, detected_language, target_language)

            return None

        return "_Please send text that contains between 3 and 200 characters (about 30 to 50 words)._"

    def translate_text(self, text, source_language, target_language):
        """
        Translates the given text from source_language to target_language.

        :param text: The text to be translated.
        :param source_language: The source language code.
        :param target_language: The target language code.
        :return: The translated text.
        """
        logging.info("Starting translation process")

        # URL for the endpoint
        RUNPOD_ENDPOINT_ID = os.getenv("RUNPOD_ENDPOINT_ID")
        url = f"https://api.runpod.ai/v2/{RUNPOD_ENDPOINT_ID}/runsync"
        # logging.info(f"Endpoint URL: {url}")

        # Authorization token
        token = os.getenv("RUNPOD_API_KEY")
        logging.info("Authorization token retrieved")

        # Data to be sent in the request body
        data = {
            "input": {
                "task": "translate",
                "source_language": source_language,
                "target_language": target_language,
                "text": text.strip(),
            }
        }
        # logging.info(f"Request data prepared: {data}")

        # Headers with authorization token
        headers = {"Authorization": token, "Content-Type": "application/json"}
        # logging.info(f"Request headers prepared: {headers}")

        # Sending the request to the API
        logging.info("Sending request to the translation API")
        response = requests.post(url, headers=headers, json=data)
        # logging.info(f"Response received: {response.json()}")

        # Handling the response
        if response.status_code == 200:
            translated_text = response.json()["output"]["translated_text"]
            # logging.info(f"Translation successful: {translated_text}")
        else:
            # logging.error(f"Error {response.status_code}: {response.text}")
            raise Exception(f"Error {response.status_code}: {response.text}")

        return translated_text

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
