import json
import os
import mimetypes
import requests
import logging
# from requests_toolbelt.multipart.encoder import MultipartEncoder
from requests_toolbelt import MultipartEncoder
from typing import Dict, Any, List, Union

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)



# token = os.getenv("WHATSAPP_TOKEN")
base_url = "https://graph.facebook.com/v12.0"
v15_base_url = "https://graph.facebook.com/v15.0"

headers={"Content-Type": "application/json"}


def send_message(
        message, token, recipient_id, phone_number_id, preview_url=True
    ):
        """
         Sends a text message to a WhatsApp user

         Args:
                message[str]: Message to be sent to the user
                recipient_id[str]: Phone number of the user with country code wihout +
                recipient_type[str]: Type of the recipient, either individual or group
                preview_url[bool]: Whether to send a preview url or not

        """
        url = f"{base_url}/{phone_number_id}/messages?access_token={token}"
        data = {
            "messaging_product": "whatsapp",
            "to": recipient_id,
            "text": {"preview_url": preview_url, "body": message},
        }
        logging.info(f"Sending message to {recipient_id}")
        r = requests.post(f"{url}", headers=headers, json=data)
        if r.status_code == 200:
            logging.info(f"Message sent to {recipient_id}")
            return r.json()
        logging.info(f"Message not sent to {recipient_id}")
        logging.info(f"Status code: {r.status_code}")
        logging.info(f"Response: {r.json()}")
        return r.json()

def reply_to_message(
        token, message_id: str, recipient_id: str, phone_number_id: str, message: str, preview_url: bool = True
    ):
        """
        Replies to a message

        Args:
            message_id[str]: Message id of the message to be replied to
            recipient_id[str]: Phone number of the user with country code wihout +
            message[str]: Message to be sent to the user
            preview_url[bool]: Whether to send a preview url or not
        """
        url = f"{base_url}/{phone_number_id}/messages?access_token={token}"
        data = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient_id,
            "type": "text",
            "context": {"message_id": message_id},
            "text": {"preview_url": preview_url, "body": message},
        }

        logging.info(f"Replying to {message_id}")
        r = requests.post(f"{url}", headers=headers, json=data)
        if r.status_code == 200:
            logging.info(f"Message sent to {recipient_id}")
            return r.json()
        logging.info(f"Message not sent to {recipient_id}")
        logging.info(f"Status code: {r.status_code}")
        logging.info(f"Response: {r.json()}")
        return r.json()

def send_template(token, template: str, phone_number_id:str, recipient_id: str, recipient_type="individual",
                        lang: str = "en_US", components: List = None):  
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
            url = f"{base_url}/{phone_number_id}/messages?access_token={token}"
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
            r = requests.post(url, headers=headers, json=data)

            if r.status_code == 200:
                logging.info(f"Template sent to {recipient_id}")
                return r.json()
            logging.info(f"Template not sent to {recipient_id}")
            logging.info(f"Status code: {r.status_code}")
            logging.info(f"Response: {r.json()}")
            return r.json()

def send_templatev2(token, template, recipient_id, components, phone_number_id, lang="en_US"):
        url = f"{base_url}/{phone_number_id}/messages?access_token={token}"
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
        r = requests.post(url, headers=headers, json=data)
        if r.status_code == 200:
            logging.info(f"Template sent to {recipient_id}")
            return r.json()
        logging.info(f"Template not sent to {recipient_id}")
        logging.info(f"Status code: {r.status_code}")
        logging.info(f"Response: {r.json()}")
        return r.json()

def send_location(token, lat, long, name, address, recipient_id, phone_number_id):
        """
        Sends a location message to a WhatsApp user

        Args:
            lat[str]: Latitude of the location
            long[str]: Longitude of the location
            name[str]: Name of the location
            address[str]: Address of the location
            recipient_id[str]: Phone number of the user with country code wihout +

        """
        url = f"{base_url}/{phone_number_id}/messages?access_token={token}"
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
        r = requests.post(url, headers=headers, json=data)
        if r.status_code == 200:
            logging.info(f"Location sent to {recipient_id}")
            return r.json()
        logging.info(f"Location not sent to {recipient_id}")
        logging.info(f"Status code: {r.status_code}")
        logging.error(r.json())
        return r.json()

def send_image(
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
            link[bool]: Whether to send an image id or an image link, True means that the image is an id, False means that the image is a link

        """
        url = f"{base_url}/{phone_number_id}/messages?access_token={token}"
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
        r = requests.post(url, headers=headers, json=data)
        if r.status_code == 200:
            logging.info(f"Image sent to {recipient_id}")
            return r.json()
        logging.info(f"Image not sent to {recipient_id}")
        logging.info(f"Status code: {r.status_code}")
        logging.error(r.json())
        return r.json()

def send_sticker(sticker: str, recipient_id: str, link=True):
        pass

def send_audio(token, audio,phone_number_id, recipient_id, link=True):
        """
        Sends an audio message to a WhatsApp user
        Audio messages can either be sent by passing the audio id or by passing the audio link.

        Args:
            audio[str]: Audio id or link of the audio
            recipient_id[str]: Phone number of the user with country code wihout +
            link[bool]: Whether to send an audio id or an audio link, True means that the audio is an id, False means that the audio is a link

        """
        url = f"{base_url}/{phone_number_id}/messages?access_token={token}"
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
        r = requests.post(url, headers=headers, json=data)
        if r.status_code == 200:
            logging.info(f"Audio sent to {recipient_id}")
            return r.json()
        logging.info(f"Audio not sent to {recipient_id}")
        logging.info(f"Status code: {r.status_code}")
        logging.error(f"Response: {r.json()}")
        return r.json()

def send_video(video, phone_number_id, recipient_id, caption=None, link=True):
        """ "
        Sends a video message to a WhatsApp user
        Video messages can either be sent by passing the video id or by passing the video link.

        Args:
            video[str]: Video id or link of the video
            recipient_id[str]: Phone number of the user with country code wihout +
            caption[str]: Caption of the video
            link[bool]: Whether to send a video id or a video link, True means that the video is an id, False means that the video is a link

        """
        url = f"{base_url}/{phone_number_id}/messages"
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
        r = requests.post(url, headers=headers, json=data)
        if r.status_code == 200:
            logging.info(f"Video sent to {recipient_id}")
            return r.json()
        logging.info(f"Video not sent to {recipient_id}")
        logging.info(f"Status code: {r.status_code}")
        logging.error(f"Response: {r.json()}")
        return r.json()

def send_document(document, phone_number_id, recipient_id, caption=None, link=True):
        """ "
        Sends a document message to a WhatsApp user
        Document messages can either be sent by passing the document id or by passing the document link.

        Args:
            document[str]: Document id or link of the document
            recipient_id[str]: Phone number of the user with country code wihout +
            caption[str]: Caption of the document
            link[bool]: Whether to send a document id or a document link, True means that the document is an id, False means that the document is a link

        """
        url = f"{base_url}/{phone_number_id}/messages"
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
        r = requests.post(url, headers=headers, json=data)
        if r.status_code == 200:
            logging.info(f"Document sent to {recipient_id}")
            return r.json()
        logging.info(f"Document not sent to {recipient_id}")
        logging.info(f"Status code: {r.status_code}")
        logging.error(f"Response: {r.json()}")
        return r.json()

def send_contacts(contacts: List[Dict[Any, Any]], phone_number_id:str, recipient_id: str):
        """send_contacts

        Send a list of contacts to a user

        Args:
            contacts(List[Dict[Any, Any]]): List of contacts to send
            recipient_id(str): Phone number of the user with country code wihout +

        REFERENCE: https://developers.facebook.com/docs/whatsapp/cloud-api/reference/messages#contacts-object
        """

        url = f"{base_url}/{phone_number_id}/messages"
        data = {
            "messaging_product": "whatsapp",
            "to": recipient_id,
            "type": "contacts",
            "contacts": contacts,
        }
        logging.info(f"Sending contacts to {recipient_id}")
        r = requests.post(url, headers=headers, json=data)
        if r.status_code == 200:
            logging.info(f"Contacts sent to {recipient_id}")
            return r.json()
        logging.info(f"Contacts not sent to {recipient_id}")
        logging.info(f"Status code: {r.status_code}")
        logging.error(f"Response: {r.json()}")
        return r.json()

def upload_media(media: str, phone_number_id:str):
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
            f"{base_url}/{phone_number_id}/media",
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

def delete_media(media_id: str):
        """
        Deletes a media from the cloud api

        Args:
            media_id[str]: Id of the media to be deleted
        """
        logging.info(f"Deleting media {media_id}")
        r = requests.delete(f"{base_url}/{media_id}", headers=headers)
        if r.status_code == 200:
            logging.info(f"Media {media_id} deleted")
            return r.json()
        logging.info(f"Error deleting media {media_id}")
        logging.info(f"Status code: {r.status_code}")
        logging.info(f"Response: {r.json()}")
        return None
    
def mark_as_read(message_id: str, phone_number_id: str):
        """
        Marks a message as read
        
        Args: 
            message_id[str]: Id of the message to be marked as read
        """
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        }

        json_data = {
            'messaging_product': 'whatsapp',
            'status': 'read',
            'message_id': message_id,
        }
        response = requests.post(
            f'{v15_base_url}/{phone_number_id}/messages', headers=headers, json=json_data).json()
        return response["success"]

def create_button(button):
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

def send_button(button, phone_number_id, recipient_id):
        """
        Sends an interactive buttons message to a WhatsApp user

        Args:
            button[dict]: A dictionary containing the button data(rows-title may not exceed 20 characters)
            recipient_id[str]: Phone number of the user with country code wihout +

        check https://github.com/Neurotech-HQ/heyoo#sending-interactive-reply-buttons for an example.
        """
        
        url = f"{base_url}/{phone_number_id}/messages"
        data = {
            "messaging_product": "whatsapp",
            "to": recipient_id,
            "type": "interactive",
            "interactive": create_button(button),
        }
        logging.info(f"Sending buttons to {recipient_id}")
        r = requests.post(url, headers=headers, json=data)
        if r.status_code == 200:
            logging.info(f"Buttons sent to {recipient_id}")
            return r.json()
        logging.info(f"Buttons not sent to {recipient_id}")
        logging.info(f"Status code: {r.status_code}")
        logging.info(f"Response: {r.json()}")
        return r.json()

def send_reply_button(button, recipient_id, phone_number_id):
        """
        Sends an interactive reply buttons[menu] message to a WhatsApp user

        Args:
            button[dict]: A dictionary containing the button data
            recipient_id[str]: Phone number of the user with country code wihout +

        Note:
            The maximum number of buttons is 3, more than 3 buttons will rise an error.
        """

        url = f"{base_url}/{phone_number_id}/messages"
        data = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient_id,
            "type": "interactive",
            "interactive": button,
        }
        r = requests.post(url, headers=headers, json=data)
        if r.status_code == 200:
            logging.info(f"Reply buttons sent to {recipient_id}")
            return r.json()
        logging.info(f"Reply buttons not sent to {recipient_id}")
        logging.info(f"Status code: {r.status_code}")
        logging.info(f"Response: {r.json()}")
        return r.json()

def query_media_url(media_id: str):
        """
        Query media url from media id obtained either by manually uploading media or received media

        Args:
            media_id[str]: Media id of the media

        Returns:
            str: Media url

        """

        logging.info(f"Querying media url for {media_id}")
        r = requests.get(f"{base_url}/{media_id}", headers=headers)
        if r.status_code == 200:
            logging.info(f"Media url queried for {media_id}")
            return r.json()["url"]
        logging.info(f"Media url not queried for {media_id}")
        logging.info(f"Status code: {r.status_code}")
        logging.info(f"Response: {r.json()}")
        return None

def download_media(media_url: str, mime_type: str, file_path: str = "temp"):
        """
        Download media from media url obtained either by manually uploading media or received media

        Args:
            media_url[str]: Media url of the media
            mime_type[str]: Mime type of the media
            file_path[str]: Path of the file to be downloaded to. Default is "temp"
                            Do not include the file extension. It will be added automatically.

        Returns:
            str: Media url

        """
        r = requests.get(media_url, headers=headers)
        content = r.content
        extension = mime_type.split("/")[1]
        # create a temporary file
        try:

            save_file_here = (
                f"{file_path}.{extension}" if file_path else f"temp.{extension}"
            )
            with open(save_file_here, "wb") as f:
                f.write(content)
            logging.info(f"Media downloaded to {save_file_here}")
            return f.name
        except Exception as e:
            print(e)
            logging.info(f"Error downloading media to {save_file_here}")
            return None

def preprocess(data):
        """
        Preprocesses the data received from the webhook.

        This method is designed to only be used internally.

        Args:
            data[dict]: The data received from the webhook
        """
        return data["entry"][0]["changes"][0]["value"]

def get_mobile(data)-> Union[str, None]:
        """
        Extracts the mobile number of the sender from the data received from the webhook.

        Args:
            data[dict]: The data received from the webhook
        Returns:
            str: The mobile number of the sender

        """
        data = preprocess(data)
        if "contacts" in data:
            return data["contacts"][0]["wa_id"]

def get_name(data)-> Union[str, None]:
        """
        Extracts the name of the sender from the data received from the webhook.

        Args:
            data[dict]: The data received from the webhook
        Returns:
            str: The name of the sender
 
        """
        contact = preprocess(data)
        if contact:
            return contact["contacts"][0]["profile"]["name"]

def get_message(data)-> Union[str, None]:
        """
        Extracts the text message of the sender from the data received from the webhook.

        Args:
            data[dict]: The data received from the webhook
        Returns:
            str: The text message received from the sender
    
        """
        data = preprocess(data)
        if "messages" in data:
            return data["messages"][0]["text"]["body"]

def get_message_id(data)-> Union[str, None]:
        """
        Extracts the message id of the sender from the data received from the webhook.

        Args:
            data[dict]: The data received from the webhook
        Returns:
            str: The message id of the sender
    
        """
        data = preprocess(data)
        if "messages" in data:
            return data["messages"][0]["id"]

def get_message_timestamp(data)-> Union[str, None]:
        """ "
        Extracts the timestamp of the message from the data received from the webhook.

        Args:
            data[dict]: The data received from the webhook
        Returns:
            str: The timestamp of the message
        
        """
        data = preprocess(data)
        if "messages" in data:
            return data["messages"][0]["timestamp"]

def get_interactive_response(data)-> Union[Dict, None]:
        """
         Extracts the response of the interactive message from the data received from the webhook.

         Args:
            data[dict]: The data received from the webhook
        Returns:
            dict: The response of the interactive message

        """
        data = preprocess(data)
        if "messages" in data:
            if "interactive" in data["messages"][0]:
                return data["messages"][0]["interactive"]

def get_location(data)-> Union[Dict, None]:
        """
        Extracts the location of the sender from the data received from the webhook.

        Args:
            data[dict]: The data received from the webhook

        Returns:
            dict: The location of the sender

        """
        data = preprocess(data)
        if "messages" in data:
            if "location" in data["messages"][0]:
                return data["messages"][0]["location"]

def get_image(data)-> Union[Dict, None]:
        """ "
        Extracts the image of the sender from the data received from the webhook.

        Args:
            data[dict]: The data received from the webhook
        Returns:
            dict: The image_id of an image sent by the sender

        """
        data = preprocess(data)
        if "messages" in data:
            if "image" in data["messages"][0]:
                return data["messages"][0]["image"]
     
def get_document(data)-> Union[Dict, None]:
        """ "
        Extracts the document of the sender from the data received from the webhook.

        Args:
            data[dict]: The data received from the webhook
        Returns:
            dict: The document_id of an image sent by the sender

        """
        data = preprocess(data)
        if "messages" in data:
            if "document" in data["messages"][0]:
                return data["messages"][0]["document"]


def get_audio(data)-> Union[Dict, None]:
        """
        Extracts the audio of the sender from the data received from the webhook.

        Args:
            data[dict]: The data received from the webhook

        Returns:
            dict: The audio of the sender

        """
        data = preprocess(data)
        if "messages" in data:
            if "audio" in data["messages"][0]:
                return data["messages"][0]["audio"]

def get_video(data)-> Union[Dict, None]:
        """
        Extracts the video of the sender from the data received from the webhook.

        Args:
            data[dict]: The data received from the webhook

        Returns:
            dict: Dictionary containing the video details sent by the sender

        """
        data = preprocess(data)
        if "messages" in data:
            if "video" in data["messages"][0]:
                return data["messages"][0]["video"]

def get_message_type(data)-> Union[str, None]:
        """
        Gets the type of the message sent by the sender from the data received from the webhook.


        Args:
            data [dict]: The data received from the webhook

        Returns:
            str: The type of the message sent by the sender

        """
        data = preprocess(data)
        if "messages" in data:
            return data["messages"][0]["type"]

def get_delivery(data)-> Union[Dict, None]:
        """
        Extracts the delivery status of the message from the data received from the webhook.
        Args:
            data [dict]: The data received from the webhook

        Returns:
            dict: The delivery status of the message and message id of the message
        """
        data = preprocess(data)
        if "statuses" in data:
            return data["statuses"][0]["status"]

def changed_field(data):
        """
        Helper function to check if the field changed in the data received from the webhook.

        Args:
            data [dict]: The data received from the webhook

        Returns:
            str: The field changed in the data received from the webhook

        """
        return data["entry"][0]["changes"][0]["field"]

def process_audio_message(message_received):
    """
    Process audio message and fetch media URL.

    Parameters:
    - message_received (str): JSON message containing audio information.
    - whats_app_business_client: WhatsApp Business API client.
    - base_url (str): Base URL for the API.
    - headers (dict): Headers for the API request.

    Returns:
    - str or None: Media URL if successful, None otherwise.
    """
    try:
        audio_messages = extract_audio_messages(message_received)
        if not audio_messages:
            return None

        audio_id = audio_messages[0]['audio']['id']
        media_url = get_media_url(base_url, headers, audio_id)

        return media_url

    except requests.RequestException as e:
        handle_request_exception(e)
        return None

def extract_audio_messages(message_received):
    """
    Extract audio messages from the received message.

    Parameters:
    - message_received (str): JSON message containing audio information.

    Returns:
    - list: List of audio messages.
    """
    audio_message_received = json.loads(message_received)
    audio_messages = []

    for entry in audio_message_received['entry']:
        for change in entry['changes']:
            audio_messages.extend(change['value']['messages'])

    return audio_messages

def get_media_url(base_url, headers, audio_id):
    """
    Get the media URL for the audio message.

    Parameters:
    - base_url (str): Base URL for the API.
    - headers (dict): Headers for the API request.
    - audio_id (str): ID of the audio message.

    Returns:
    - str or None: Media URL if successful, None otherwise.
    """
    endpoint = f"{base_url}/media/{audio_id}"

    response = requests.get(endpoint, headers=headers)
    response.raise_for_status()

    media_url = response.json().get('url')
    return media_url

def handle_request_exception(exception):
    """
    Handle request exceptions.

    Parameters:
    - exception (requests.RequestException): Request exception object.
    """
    print(f"Error fetching media URL: {exception}")
    # Add more specific error handling or logging if needed.
