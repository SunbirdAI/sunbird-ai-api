description = """
Welcome to the Sunbird AI API documentation. The Sunbird AI API provides access to
Sunbird's language models and AI services for Ugandan languages.

## Supported Languages
**English**, **Acholi**, **Ateso**, **Luganda**, **Lugbara**, **Runyankole**, **Swahili**
and **20+** more Ugandan languages supported via sunflower.

## Getting Started
You can checkout the [usage guide](https://salt.sunbird.ai/API/) for a full tutorial.

For quickstart tutorials, visit our
[GitHub repository](https://github.com/SunbirdAI/sunbird-ai-api/blob/main/docs/tutorial.md)

### Authentication

#### Signing Up
If you don't already have an account, use the `/auth/register` endpoint to create one.

#### Getting an Access Token
Authentication is done via a Bearer token. Use the `/auth/token` endpoint to get your
access token. This token lasts for 7 days.

Use the `Authorize` button below to login and access the protected endpoints.

## API Endpoints

### Translation
- **`POST /tasks/translate`** - Translate text between 32 Ugandan and East African
  languages using the Sunflower model. Languages are accepted as ISO codes (`lug`)
  or full names (`Luganda`); `source_language` is optional (auto-detected when
  omitted). Translation works between any pair of supported languages.

### Language Detection
- **`POST /tasks/language_id`** - Auto-detect the language of text input
  (supports Acholi, Ateso, English, Luganda, Lugbara, Runyankole)

### Speech-to-Text (STT)
- **`POST /tasks/audio/transcriptions`** - Unified STT endpoint (OpenAI-style).
  - Accepts an uploaded audio file (`audio`) or a GCS object (`gcs_blob_name`).
  - `platform`: `modal` (default, Whisper large-v3) or `runpod`.
  - RunPod options: `adapter` (language adapter), `whisper`, `recognise_speakers`
    (diarization), and the `org` organization workflow.
  - `language`: 3-letter code (e.g. `eng`, `lug`) or full name; improves accuracy.
    Supports WAV, MP3, OGG, M4A, and more. Auto-detects when omitted.
  - **Deprecated** → use `POST /tasks/audio/transcriptions`:
    - `POST /tasks/stt`, `POST /tasks/stt_from_gcs`, `POST /tasks/org/stt`,
      `POST /tasks/modal/stt`

### Text-to-Speech (TTS)
- **`POST /tasks/audio/speech`** - Unified single-synthesis endpoint.
  - `model`: `orpheus-3b-tts` (default) or `spark-tts`; `platform`: `modal` or `runpod`.
  - `voice`: speaker tag/name. `response_mode`: `url` (default), `stream`, or `both`
    (`stream`/`both` require `spark-tts` on `modal`).
  - Orpheus tuning: `language`, `temperature`, `top_p`, `repetition_penalty`,
    `max_tokens`, `seed`. Returns a signed GCP Storage URL.
- **`POST /tasks/audio/speech/batch`** - Batch synthesis (orpheus-3b-tts only), 1-128 items.
- **`GET /tasks/voice/speakers`** - List voices for a `model` (optional orpheus `language`).
- **`GET /tasks/audio/speech/url`** - Refresh an expired signed URL for a stored audio object.
  - **Deprecated** → superseded by the unified endpoints above:
    - `POST /tasks/modal/tts`, `POST /tasks/runpod/tts`,
      `POST /tasks/modal/orpheus/tts` → `POST /tasks/audio/speech`
    - `POST /tasks/modal/tts/stream` → `/tasks/audio/speech` (`response_mode=stream`)
    - `POST /tasks/modal/tts/stream-with-url` → `/tasks/audio/speech` (`response_mode=both`)
    - `POST /tasks/modal/orpheus/tts/batch` → `POST /tasks/audio/speech/batch`
    - `GET /tasks/modal/tts/speakers`, `GET /tasks/modal/orpheus/speakers`,
      `GET /tasks/modal/orpheus/speakers/{language}` → `GET /tasks/voice/speakers`
    - `GET /tasks/modal/tts/refresh-url` → `GET /tasks/audio/speech/url`

### Inference (Sunflower Chat)
- **`POST /tasks/chat/completions`** - OpenAI-compatible chat completions (Sunflower model).
  Supports single instructions, multi-turn conversations, and SSE streaming (`stream: true`).
  Use model `Sunbird/Sunflower-14B`.
  - **Deprecated** → superseded by the unified endpoint above:
    - `POST /tasks/sunflower_inference` → `POST /tasks/chat/completions`
    - `POST /tasks/sunflower_simple` → `POST /tasks/chat/completions` (send the instruction as a single user message)

### File Upload
- **`POST /tasks/generate-upload-url`** - Generate signed URLs for direct client uploads to GCP Storage
  - Supports audio files, images, and other content types
  - Includes path traversal protection and input validation
  - Returns temporary signed URL valid for 30 minutes

### WhatsApp Integration (Webhooks)
- **`POST /tasks/webhook`** - Handle incoming WhatsApp Business API messages
- **`GET /tasks/webhook`** - Verify webhook endpoint ownership for WhatsApp

### Legacy Endpoints
- **`POST /tasks/summarise`** - *(Deprecated)* Anonymized text summarization (use Sunflower inference instead)

## Rate Limiting
API endpoints are rate-limited to ensure fair usage. Authentication is required for most endpoints.
"""

tags_metadata = [
    {
        "name": "Authentication Endpoints",
        "description": "Operations for authentication, including user registration and login. Get access tokens to use protected endpoints.",  # noqa: E501
    },
    {
        "name": "Speech-to-Text",
        "description": "Convert speech audio to text. The unified /tasks/audio/transcriptions endpoint accepts an uploaded file or a GCS object, routes to the Modal or RunPod backend, and supports optional speaker diarization for Acholi, Ateso, English, Luganda, Lugbara, and Runyankole.",  # noqa: E501
    },
    {
        "name": "Text-to-Speech",
        "description": "Synthesize speech from text. Unified endpoints for single (/tasks/audio/speech) and batch (/tasks/audio/speech/batch) synthesis across the orpheus-3b-tts and spark-tts models, plus voice listing (/tasks/voice/speakers) and signed-URL refresh (/tasks/audio/speech/url). Returns signed GCS audio URLs.",  # noqa: E501
    },
    {
        "name": "Translation",
        "description": "Translate text using the Sunflower model. Supports 32 languages (e.g. Luganda, Acholi, Ateso, Lugbara, Runyankole, Swahili, Kinyarwanda) accepted as ISO codes or full names; source language is optional and translation works between any supported pair.",  # noqa: E501
    },
    {
        "name": "Language",
        "description": "Language identification and detection. Automatically detect the language of text input from supported languages.",  # noqa: E501
    },
    {
        "name": "Chat",
        "description": "OpenAI-compatible chat completions powered by the Sunflower model. Supports single instructions, multi-turn conversations, and SSE streaming.",  # noqa: E501
    },
    {
        "name": "Upload",
        "description": "File upload utilities. Generate signed URLs for direct client uploads to GCP Storage with security validation.",  # noqa: E501
    },
    {
        "name": "Webhooks",
        "description": "WhatsApp Business API webhook integration. Handle incoming messages and verify webhook endpoints for WhatsApp chatbot functionality.",  # noqa: E501
    },
    {
        "name": "legacy/deprecated",
        "description": "Deprecated endpoints retained for backward compatibility. Each is superseded by a unified endpoint — see its Deprecation/Sunset/Link response headers — and will be removed after the sunset date. Do not build new integrations against these.",  # noqa: E501
    },
]
