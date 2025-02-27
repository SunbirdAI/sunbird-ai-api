import json
import logging
import mimetypes
import os
import secrets
from datetime import datetime
from typing import Any, Dict, List, Union

import requests
from fastapi import HTTPException
from requests_toolbelt import MultipartEncoder

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


base_url = "https://graph.facebook.com/v20.0"
v15_base_url = "https://graph.facebook.com/v15.0"

headers = {"Content-Type": "application/json"}


# def send_message(message, token, recipient_id, phone_number_id, preview_url=True):
#     """
#     Sends a text message to a WhatsApp user

#     Args:
#            message[str]: Message to be sent to the user
#            recipient_id[str]: Phone number of the user with country code wihout +
#            recipient_type[str]: Type of the recipient, either individual or group
#            preview_url[bool]: Whether to send a preview url or not

#     """
#     url = f"{base_url}/{phone_number_id}/messages?access_token={token}"
#     data = {
#         "messaging_product": "whatsapp",
#         "to": recipient_id,
#         "text": {"preview_url": preview_url, "body": message},
#     }
#     logging.info(f"Sending message to {recipient_id}")
#     r = requests.post(f"{url}", headers=headers, json=data)
#     if r.status_code == 200:
#         logging.info(f"Message sent to {recipient_id}")
#         return r.json()
#     logging.info(f"Message not sent to {recipient_id}")
#     logging.info(f"Status code: {r.status_code}")
#     logging.info(f"Response: {r.json()}")
#     return r.json()


def download_whatsapp_audio(url, access_token):
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

            logging.info(f"Whatsapp audio download was successfull: {local_audio_path}")
            return local_audio_path
        else:
            raise HTTPException(status_code=500, detail="Failed to download audio file")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def send_message(message, token, recipient_id, phone_number_id, preview_url=True):
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
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
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


def send_template(
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


def send_templatev2(
    token, template, recipient_id, components, phone_number_id, lang="en_US"
):
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
        link[bool]: Checks if image is id or link, True means id

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


def send_audio(token, audio, phone_number_id, recipient_id, link=True):
    """
    Sends an audio message to a WhatsApp user
    Audio messages can either be sent by passing the audio id or by passing the audio link.

    Args:
        audio[str]: Audio id or link of the audio
        recipient_id[str]: Phone number of the user with country code wihout +
        link[bool]: Choose audio id or audio link, True means audio is an id, False means audio is a link

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
        link[bool]: Choose to send video id or  video link, True means video is an id, False means video is a link

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
        link[bool]: Choose to send id or link for document, True means document is an id else it's a link

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


def send_contacts(
    contacts: List[Dict[Any, Any]], phone_number_id: str, recipient_id: str
):
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


def upload_media(headers, media: str, phone_number_id: str):
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


def mark_as_read(token, message_id: str, phone_number_id: str):
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
        f"{v15_base_url}/{phone_number_id}/messages", headers=headers, json=json_data
    ).json()
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


def query_media_url(media_id, access_token):
    """
    Query media url from media id obtained either by manually uploading media or received media

    Args:
        media_id[str]: Media id of the media

    Returns:
        str: Media url

    """

    headers = {"Authorization": f"Bearer {access_token}"}
    logging.info(f"Querying media url for {media_id}")
    r = requests.get(f"{base_url}/{media_id}", headers=headers)
    if r.status_code == 200:
        logging.info(f"Media url queried for {media_id}")
        return r.json()["url"]
    logging.info(f"Media url not queried for {media_id}")
    logging.info(f"Status code: {r.status_code}")
    logging.info(f"Response: {r.json()}")
    return None


def download_media(media_url, access_token, file_path="downloaded_media_file"):
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


def preprocess(data):
    """
    Preprocesses the data received from the webhook.

    This method is designed to only be used internally.

    Args:
        data[dict]: The data received from the webhook
    """
    return data["entry"][0]["changes"][0]["value"]


def get_mobile(data) -> Union[str, None]:
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


def get_name(data) -> Union[str, None]:
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


def get_message(data) -> Union[str, None]:
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


def get_message_id(data) -> Union[str, None]:
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


def get_messages_from_payload(payload):
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


def get_message_timestamp(data) -> Union[str, None]:
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


def get_interactive_response(data) -> Union[Dict, None]:
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


def get_location(data) -> Union[Dict, None]:
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


def get_image(data) -> Union[Dict, None]:
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


def get_document(data) -> Union[Dict, None]:
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


# def get_audio(data) -> Union[Dict, None]:
#     """
#     Extracts the audio of the sender from the data received from the webhook.

#     Args:
#         data[dict]: The data received from the webhook

#     Returns:
#         dict: The audio of the sender

#     """
#     data = preprocess(data)
#     if "messages" in data:
#         if "audio" in data["messages"][0]:
#             return data["messages"][0]["audio"]


def get_video(data) -> Union[Dict, None]:
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


def get_message_type(data) -> Union[str, None]:
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


def get_delivery(data) -> Union[Dict, None]:
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

    for entry in audio_message_received["entry"]:
        for change in entry["changes"]:
            audio_messages.extend(change["value"]["messages"])

    return audio_messages


def handle_request_exception(exception):
    """
    Handle request exceptions.

    Parameters:
    - exception (requests.RequestException): Request exception object.
    """
    print(f"Error fetching media URL: {exception}")
    # Add more specific error handling or logging if needed.


def download_audio_file(url, file_path="temp_audio_file.wav"):
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


def process_audio_message(payload):
    """
    Extract the audio URL from the WhatsApp message payload.
    :param payload: The webhook payload from WhatsApp.
    :return: The URL of the audio file.
    """
    # Example path within payload to the audio URL, adjust based on actual payload structure
    audio_id = payload["entry"][0]["changes"][0]["value"]["messages"][0]["audio"]["id"]
    return audio_id


def fetch_media_url(media_id, token):
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


def get_media_url(media_id, token):
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


def valid_payload(payload):
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


def get_phone_number_id(payload):
    return payload["entry"][0]["changes"][0]["value"]["metadata"]["phone_number_id"]


def get_from_number(payload):
    return payload["entry"][0]["changes"][0]["value"]["messages"][0]["from"]


def get_reaction(payload):
    # Check if the payload contains a reaction
    messages = payload["entry"][0]["changes"][0]["value"]["messages"]
    for message in messages:
        logging.info(f"Message: {message}")
        if "reaction" in message:
            reaction = message["reaction"]
            logging.info(f"Reaction: {reaction}")
            return message["reaction"]
    return None


def welcome_message(sender_name=""):
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


def help_message():
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


def set_default_target_language(user_id, save_user_preference):
    default_target_language = "Luganda"
    defualt_source_language = "English"
    save_user_preference(user_id, defualt_source_language, default_target_language)


def handle_language_selection(
    user_id, selection, source_language, save_user_preference, languages_obj
):
    if int(selection) == 6:
        save_user_preference(user_id, source_language, languages_obj[selection])
        return f"Language set to {languages_obj[selection]}. You can now send texts to translate."
    else:
        save_user_preference(user_id, source_language, languages_obj[selection])
        return f"Language set to {languages_obj[selection]}. You can now send texts to translate."


def get_audio(payload: dict):
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
