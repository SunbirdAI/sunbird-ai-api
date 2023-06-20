# Sunbird AI API Tutorial
This page describes how to use the Sunbird AI API and includes code samples in Python.

## Part 1: How to authenticate
1. Create an account by emailing us at `info [at] sunbird.ai`. (We're working on a portal where you'll be able to create an account on your own).
2. We'll send you your credentials and an access token. To obtain another access token, send a POST request to the `/auth/token` endpoint:
```python
import requests
url = 'https://sunbird-ai-api-5bq6okiwgq-ew.a.run.app'
creds = {
    'username': '{your_username}',
    'password': '{your_password}'
}
response = requests.post(f'{url}/auth/token', data=creds)
token = response.json()['access_token']
print(token)
```

## Part 2: How to call the translation endpoint
Refer to the sample code below. Replace `{access_token}` with the token you received from the `/auth/token` endpoint.
```python
import requests

url = 'https://sunbird-ai-api-5bq6okiwgq-ew.a.run.app'

headers = {
    "Authorization": "Bearer {access_token}",
    "Content-Type": "application/json"
}

payload = {
  "source_language": "English",
  "target_language": "Luganda",
  "text": "Hello, how are you?"
}

response = requests.post(f"{url}/tasks/translate", headers=headers, json=payload)

if response.status_code == 200:
    translated_text = response.json()["text"]
    print("Translate text:", translated_text)
else:
    print("Error:", response.status_code, response.text)
```

## Part 3: How to call the speech-to-text endpoint
Refer to the sample code below. Replace `{access_token}` with the token you got from the `/auth/token` endpoint. And replace `/path/to/file` with the path to the file you want to transcribe. 

```python
import requests

url = "https://sunbird-ai-api-5bq6okiwgq-ew.a.run.app/tasks/stt"

payload = {}
files=[
  ('audio',('file.wav',open('/path/to/file','rb'),'audio/wav'))
]
headers = {
  'Authorization': 'Bearer {access_token}'
}

response = requests.request("POST", url, headers=headers, data=payload, files=files)

print(response.text)
```

## Part 4: How to use the text-to-speech endpoint
The sample code below receives a base64 encoded string from the endpoint and decodes it into a `temp.wav` audio file containing the speech audio.
```python
import requests
import base64

url = 'https://sunbird-ai-api-5bq6okiwgq-ew.a.run.app'

headers = {
    "Authorization": "Bearer {access_token}",
    "Content-Type": "application/json"
}

payload = {
    "text": "Oli otya?"
}
response = requests.post(f"{url}/tasks/tts", headers=headers, json=payload)

if response.status_code == 200:
    base64_string = response.json()["base64_string"]
    
    with open("temp.wav", "wb") as wav_file:
        decoded_audio = base64.decodebytes(base64_string.encode('utf-8'))
        wav_file.write(decoded_audio)
        wav_file.close()
else:
    print("Error:", response.status_code, response.text)
```

You can refer to the [docs](https://sunbird-ai-api-5bq6okiwgq-ew.a.run.app/docs) for more info about the endpoints.

## Feedback and Questions.
Don't hesitate to leave us any feedback or questions you have by opening an [issue in this repo](https://github.com/SunbirdAI/sunbird-ai-api/issues).
