# Sunbird AI API Tutorial
This comprehensive tutorial describes how to use the Sunbird AI API and includes code samples in Python.

## Supported Languages
- **English** (eng)
- **Acholi** (ach)
- **Ateso** (teo)
- **Luganda** (lug)
- **Lugbara** (lgg)
- **Runyankole** (nyn)
- **Swahili** (swa)
- **Plus 20 more Uganda languages**

---

## Part 1: Authentication

### Creating an Account
1. If you don't already have an account, create one at https://api.sunbird.ai/register
2. Go to the [tokens page](https://api.sunbird.ai/tokens) to get your access token

### Using the Authentication API

#### Register a New User
```python
import requests

url = "https://api.sunbird.ai/auth/register"
data = {
    "username": "your_username",
    "email": "your_email@example.com",
    "password": "your_secure_password"
}

response = requests.post(url, json=data)
print(response.json())
```

#### Get Access Token
```python
import requests

url = "https://api.sunbird.ai/auth/token"
data = {
    "username": "your_username",
    "password": "your_password"
}

response = requests.post(url, data=data)
token_data = response.json()
access_token = token_data["access_token"]
print(f"Your token: {access_token}")
```

---

## Part 2: Translation (NLLB Model)

Translate text between English and local languages using the NLLB model. Supports bidirectional translation.

```python
import os
import requests
from dotenv import load_dotenv

load_dotenv()

url = "https://api.sunbird.ai/tasks/translate"
access_token = os.getenv("AUTH_TOKEN")

headers = {
    "accept": "application/json",
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json",
}

# Example: Translate from Luganda to English
data = {
    "source_language": "lug",
    "target_language": "eng",
    "text": "Ekibiina ekiddukanya omuzannyo gw'emisinde mu ggwanga ekya Uganda Athletics Federation kivuddeyo nekitegeeza nga lawundi esooka eyemisinde egisunsulamu abaddusi abanakiika mu mpaka ezenjawulo ebweru w'eggwanga egya National Athletics Trials nga bwegisaziddwamu.",
}

response = requests.post(url, headers=headers, json=data)
print(response.json())
```

**Supported Language Pairs:**
- English ↔ Acholi
- English ↔ Ateso
- English ↔ Luganda
- English ↔ Lugbara
- English ↔ Runyankole


The dictionary below represents the language codes available now for the translate endpoint

```python
language_codes: {
    "English": "eng",
    "Luganda": "lug",
    "Runyankole": "nyn",
    "Acholi": "ach",
    "Ateso": "teo",
    "Lugbara": "lgg"
}
```

---

## Part 3: Speech-to-Text (STT)

Convert speech audio to text for supported languages. The API supports various audio formats including MP3, WAV, and M4A.

### Modal STT (Recommended)

The Modal-based STT endpoint uses the Whisper large-v3 model for high-quality transcription. Simply upload an audio file and get the transcription back. You can optionally specify a `language` to improve accuracy; if omitted the model auto-detects the language.

```python
import os
import requests
from dotenv import load_dotenv

load_dotenv()

url = "https://api.sunbird.ai/tasks/modal/stt"
access_token = os.getenv("AUTH_TOKEN")

headers = {
    "accept": "application/json",
    "Authorization": f"Bearer {access_token}",
}

# Replace with your audio file path
audio_file_path = "/path/to/audio_file.wav"

files = {
    "audio": (
        "recording.wav",
        open(audio_file_path, "rb"),
        "audio/wav",
    ),
}

# Without language (auto-detect)
response = requests.post(url, headers=headers, files=files)
result = response.json()
print(f"Transcription: {result['audio_transcription']}")
```

#### Specifying a language

Pass a `language` field to guide the model. Accepts either a 3-letter ISO 639-2 code or a full language name (case-insensitive).

```python
files = {
    "audio": (
        "recording.wav",
        open(audio_file_path, "rb"),
        "audio/wav",
    ),
}

# Using a 3-letter code
data = {"language": "lug"}
response = requests.post(url, headers=headers, files=files, data=data)

# Or using a full language name
data = {"language": "Luganda"}
response = requests.post(url, headers=headers, files=files, data=data)
```

**Supported languages:** English (`eng`), Luganda (`lug`), Runyankole (`nyn`), Acholi (`ach`), Ateso (`teo`), Lugbara (`lgg`), Swahili (`swa`), Kinyarwanda (`kin`), Lusoga (`xog`), Lumasaba (`myx`).

### RunPod STT (with language selection)

The RunPod-based STT endpoint allows you to specify a target language and adapter for transcription.

```python
import os
import requests
from dotenv import load_dotenv

load_dotenv()

url = "https://api.sunbird.ai/tasks/stt"
access_token = os.getenv("AUTH_TOKEN")

headers = {
    "accept": "application/json",
    "Authorization": f"Bearer {access_token}",
}

# Replace with your audio file path
audio_file_path = "/path/to/audio_file.mp3"

files = {
    "audio": (
        "recording.mp3",
        open(audio_file_path, "rb"),
        "audio/mpeg",
    ),
}

data = {
    "language": "lug",  # Language code (eng, ach, teo, lug, lgg, nyn)
    "adapter": "lug",   # Model adapter to use
    "whisper": True,    # Use Whisper model
}

response = requests.post(url, headers=headers, files=files, data=data)
print(response.json())
```

**Supported Languages:** English, Acholi, Ateso, Luganda, Lugbara, Runyankole, Lusoga, Rutooro, Lumasaba, Kinyarwanda, Swahili.

**Note:** For files larger than 100MB, only the first 10 minutes will be transcribed.


The dictionary below represents the language codes available now for the stt endpoint

```python
SALT_LANGUAGE_IDS_WHISPER = {
    'eng': "English (Ugandan)",
    'swa': "Swahili",
    'ach': "Acholi",
    'lgg': "Lugbara",
    'lug': "Luganda",
    'nyn': "Runyankole",
    'teo': "Ateso",
    'xog': "Lusoga",
    'ttj': "Rutooro",
    'kin': "Kinyarwanda",
    'myx': "Lumasaba",
}

```

---

## Part 4: Language Detection

Automatically detect the language of text input. Useful for routing text to appropriate translation or processing pipelines.

```python
import os
import requests
from dotenv import load_dotenv

load_dotenv()

url = "https://api.sunbird.ai/tasks/language_id"
access_token = os.getenv("AUTH_TOKEN")

headers = {
    "accept": "application/json",
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json",
}

text = "Oli otya? Webale nnyo ku kujja wano."

data = {"text": text}

response = requests.post(url, headers=headers, json=data)
result = response.json()
print(f"Detected language: {result}")
```

**Supported Languages:** Acholi, Ateso, English, Luganda, Lugbara, Runyankole

---

## Part 5: Text-to-Speech (TTS)

Convert text to audio using Ugandan language voices. The API supports multiple response modes including streaming and signed URLs.

```python
import os
import requests
from dotenv import load_dotenv

load_dotenv()

url = "https://api.sunbird.ai/tasks/modal/tts"
access_token = os.getenv("AUTH_TOKEN")

headers = {
    "accept": "application/json",
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json",
}

data = {
    "text": "Webale nnyo ku kuyita mu Sunbird AI.",
    "language": "lug",
    "response_mode": "url"  # Options: "url", "stream", "both"
}

response = requests.post(url, headers=headers, json=data)
result = response.json()

if "url" in result:
    print(f"Audio URL: {result['url']}")
    print(f"Expires at: {result['expires_at']}")
```

**Response Modes:**
- `url` - Generate audio, upload to GCP, return signed URL (valid for 30 minutes)
- `stream` - Stream raw audio chunks directly
- `both` - Stream audio AND return final signed URL

**Supported Languages:** Acholi, Ateso, Runyankore, Lugbara, Swahili, Luganda

---

## Part 6: Conversational AI (Sunflower)

The Sunflower model provides conversational AI capabilities with support for chat history and context. Supports 20+ Ugandan languages.

### Chat with History
```python
import requests

url = "https://api.sunbird.ai/tasks/sunflower_inference"

headers = {
    "accept": "application/json",
    "Authorization": "Bearer <your-access-token>",
    "Content-Type": "application/json",
}

payload = {
    "messages": [
        {
            "role": "user",
            "content": "Good morning, what is weather today?",
        }
    ],
    "model_type": "qwen",
    "temperature": 0.3,
    "stream": False,
    "system_message": "string",
}

response = requests.post(url, headers=headers, json=payload)

print(response.status_code)
print(response.json())
```

**Example Response:**
```json
{
  "content": "I'm glad you're up! While I can't provide real-time weather updates, I can help you understand how to interpret weather forecasts or explain common weather patterns in Uganda. Could you share the current weather conditions you're experiencing?",
  "model_type": "qwen",
  "usage": {
    "completion_tokens": 47,
    "prompt_tokens": 22,
    "total_tokens": 69
  },
  "processing_time": 4.802350997924805,
  "inference_time": 4.792236804962158,
  "message_count": 2
}
```

### Simple Text Generation
```python
import requests

url = "https://api.sunbird.ai/tasks/sunflower_simple"

headers = {
    "accept": "application/json",
    "Authorization": "Bearer <your-access-token>",
}

data = {
    "instruction": "translate from english to luganda: i am very hungry they should serve food in time",
    "model_type": "qwen",
    "temperature": "0.1",
    "system_message": "",
}

response = requests.post(url, headers=headers, data=data)

print(response.status_code)
print(response.json())
```

**Example Response:**
```json
{
  "response": "Ndi muyala nnyo, emmere erina okugabibwa mu budde.",
  "model_type": "qwen",
  "processing_time": 3.2431752681732178,
  "usage": {
    "completion_tokens": 19,
    "prompt_tokens": 54,
    "total_tokens": 73
  },
  "success": true
}
```

---

## Part 7: File Upload (Signed URLs)

Generate secure signed URLs for direct client uploads to GCP Storage. Useful for uploading audio files before transcription.

```python
import os
import requests
from dotenv import load_dotenv

load_dotenv()

# Step 1: Generate upload URL
url = "https://api.sunbird.ai/tasks/generate-upload-url"
access_token = os.getenv("AUTH_TOKEN")

headers = {
    "accept": "application/json",
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json",
}

data = {
    "file_name": "recording.wav",
    "content_type": "audio/wav"
}

response = requests.post(url, headers=headers, json=data)
result = response.json()

upload_url = result["upload_url"]
file_id = result["file_id"]

print(f"Upload URL: {upload_url}")
print(f"File ID: {file_id}")
print(f"Expires at: {result['expires_at']}")

# Step 2: Upload file directly to GCS
with open("/path/to/your/recording.wav", "rb") as f:
    upload_response = requests.put(
        upload_url,
        data=f,
        headers={"Content-Type": "audio/wav"}
    )

if upload_response.status_code == 200:
    print("File uploaded successfully!")
```

**Features:**
- Temporary signed URLs (valid for 30 minutes)
- Direct upload to Google Cloud Storage
- Path traversal protection
- Support for multiple content types

---

## Additional Resources

- **API Documentation**: [https://api.sunbird.ai/docs](https://api.sunbird.ai/docs)
- **OpenAPI Specification**: [https://api.sunbird.ai/openapi.json](https://api.sunbird.ai/openapi.json)
- **Usage Guide**: [https://salt.sunbird.ai/API/](https://salt.sunbird.ai/API/)

## Rate Limiting

API endpoints are rate-limited to ensure fair usage. If you need higher rate limits for production use, please contact the Sunbird AI team.

## Feedback and Questions

Don't hesitate to leave us any feedback or questions by opening an [issue in this repo](https://github.com/SunbirdAI/sunbird-ai-api/issues).
