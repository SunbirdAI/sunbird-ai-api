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
2. Go to the [tokens page](https://api.sunbird.ai/keys) to get your access token / api key

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

Convert speech audio to text. The unified **`POST /tasks/audio/transcriptions`** endpoint accepts an uploaded audio file (or a GCS object) and routes to the Modal (Whisper large-v3) or RunPod backend. Supports MP3, WAV, M4A, and more.

> **Migrating from the legacy STT routes?** `/tasks/modal/stt`, `/tasks/stt`, `/tasks/stt_from_gcs`, and `/tasks/org/stt` are **deprecated** (they still work but return `Deprecation`/`Sunset` headers). Switch to `/tasks/audio/transcriptions`.

### Transcribe a file (Modal / Whisper)

`language` is **required**. `platform` defaults to `modal` (Whisper large-v3).

```python
import os
import requests
from dotenv import load_dotenv

load_dotenv()

url = "https://api.sunbird.ai/tasks/audio/transcriptions"
access_token = os.getenv("AUTH_TOKEN")

headers = {
    "accept": "application/json",
    "Authorization": f"Bearer {access_token}",
}

audio_file_path = "/path/to/audio_file.wav"

files = {
    "audio": ("recording.wav", open(audio_file_path, "rb"), "audio/wav"),
}
data = {
    "language": "lug",     # required: 3-letter code or full name (e.g. "Luganda")
    "platform": "modal",   # "modal" (default, Whisper) or "runpod"
}

response = requests.post(url, headers=headers, files=files, data=data)
result = response.json()
print(f"Transcription: {result['audio_transcription']}")
```

### Transcribe with RunPod (adapter, Whisper, diarization)

The RunPod backend adds a language `adapter`, the `whisper` flag, and optional speaker diarization (`recognise_speakers`).

```python
files = {
    "audio": ("recording.mp3", open("/path/to/audio_file.mp3", "rb"), "audio/mpeg"),
}
data = {
    "language": "lug",
    "platform": "runpod",
    "adapter": "lug",             # optional; defaults to `language`
    "whisper": True,             # RunPod only
    "recognise_speakers": False,  # RunPod only — speaker diarization
}

response = requests.post(url, headers=headers, files=files, data=data)
print(response.json())
```

You can also transcribe audio already in GCS by passing `gcs_blob_name` (with `platform="runpod"`) instead of an `audio` file — see **Part 7: File Upload** for generating upload URLs.

**Example response:**
```json
{
  "audio_transcription": "Ekibiina ekiddukanya ...",
  "language": "lug",
  "audio_url": "https://storage.googleapis.com/.../audio.wav?...",
  "audio_transcription_id": 123,
  "diarization_output": null,
  "formatted_diarization_output": null,
  "was_audio_trimmed": false,
  "original_duration_minutes": null
}
```

**Supported languages:** English (`eng`), Luganda (`lug`), Runyankole (`nyn`), Acholi (`ach`), Ateso (`teo`), Lugbara (`lgg`), Swahili (`swa`), Lusoga (`xog`), Rutooro (`ttj`), Kinyarwanda (`kin`), Lumasaba (`myx`).

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

Synthesize speech from text. The unified **`POST /tasks/audio/speech`** endpoint replaces `/tasks/modal/tts`, `/tasks/runpod/tts`, and `/tasks/modal/orpheus/tts`. Two models are available:

- **`orpheus-3b-tts`** (default) — multilingual, multi-speaker; voices are catalog tags (e.g. `salt_lug_0001`). List them with `GET /tasks/voice/speakers`.
- **`spark-tts`** — the six fixed Ugandan voices below; supports streaming on Modal.

> **Migrating?** The legacy TTS, streaming (`/stream`, `/stream-with-url`), Orpheus batch, speaker-listing, and `refresh-url` endpoints are **deprecated**. Use the unified endpoints below.

### Single synthesis (orpheus-3b-tts, default)

```python
import os
import requests
from dotenv import load_dotenv

load_dotenv()

url = "https://api.sunbird.ai/tasks/audio/speech"
access_token = os.getenv("AUTH_TOKEN")

headers = {
    "accept": "application/json",
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json",
}

payload = {
    "text": "I am a nurse who takes care of many people.",
    "model": "orpheus-3b-tts",   # default
    "voice": "salt_lug_0001",     # catalog tag; see GET /tasks/voice/speakers
}

response = requests.post(url, headers=headers, json=payload)
print(response.status_code)
print(response.json())
```

### Single synthesis (spark-tts, fixed voices)

```python
payload = {
    "text": "I am a nurse who takes care of many people.",
    "model": "spark-tts",
    "voice": "luganda_female",   # voice name, or the numeric id as a string e.g. "248"
    "response_mode": "url",       # "url" (default), "stream", or "both"
}
response = requests.post(url, headers=headers, json=payload)
print(response.json())
```

#### spark-tts voices

| Voice name | ID | Description |
|---|---|---|
| `acholi_female` | 241 | Acholi (female) |
| `ateso_female` | 242 | Ateso (female) |
| `runyankore_female` | 243 | Runyankore (female) |
| `lugbara_female` | 245 | Lugbara (female) |
| `swahili_male` | 246 | Swahili (male) |
| `luganda_female` | 248 | Luganda (female) |

### Response modes

`response_mode` applies to **spark-tts on Modal**:
- `url` — generate audio, upload to GCP, return a signed URL (valid ~30 minutes) — default
- `stream` — stream raw audio chunks directly
- `both` — stream audio **and** return a final signed URL

### Listing voices

```python
auth = {"Authorization": f"Bearer {access_token}"}

# Orpheus voices grouped by language (default)
print(requests.get("https://api.sunbird.ai/tasks/voice/speakers", headers=auth).json())

# spark-tts fixed voices
print(requests.get(
    "https://api.sunbird.ai/tasks/voice/speakers",
    headers=auth,
    params={"model": "spark-tts"},
).json())
```

### Batch synthesis (orpheus-3b-tts)

Synthesize up to 128 items in a single request:

```python
url = "https://api.sunbird.ai/tasks/audio/speech/batch"
payload = {
    "items": [
        {"text": "Good morning.", "voice": "salt_lug_0001"},
        {"text": "How are you?", "voice": "salt_eng_0001"},
    ]
}
response = requests.post(url, headers=headers, json=payload)
print(response.json())
```

### Refreshing an expired URL

Signed URLs expire after ~30 minutes. Re-sign a stored object with `GET /tasks/audio/speech/url`:

```python
print(requests.get(
    "https://api.sunbird.ai/tasks/audio/speech/url",
    headers={"Authorization": f"Bearer {access_token}"},
    params={"gcs_object": "orpheus_tts/2026-06-03/abc.wav"},
).json())
```

**Example response (`POST /tasks/audio/speech`):**
```json
{
  "audio_url": "https://storage.googleapis.com/.../tts_audio/....wav?...",
  "model": "orpheus-3b-tts",
  "platform": "modal",
  "voice": "salt_lug_0001",
  "audio_url_expires_at": "2026-06-03T22:59:36.954061Z",
  "language": "lug",
  "sample_rate": 24000,
  "duration_seconds": 4.0,
  "gcs_object": "orpheus_tts/2026-06-03/....wav",
  "request_id": "0f1e2d3c4b5a...",
  "timings_ms": {"inference_ms": 1820.5, "upload_ms": 234.1, "total_ms": 2095.6}
}
```

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
