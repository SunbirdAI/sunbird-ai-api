description = """
Welcome to the Sunbird AI API documentation. The Sunbird AI API provides access to Sunbird's language models and AI services for Ugandan languages.

## Supported Languages
**English**, **Acholi**, **Ateso**, **Luganda**, **Lugbara**, **Runyankole**, **Swahili** and **20+** more Ugandan languages supported via sunflower.

## Getting Started
You can checkout the [usage guide](https://salt.sunbird.ai/API/) for a full tutorial.

For quickstart tutorials, visit our [GitHub repository](https://github.com/SunbirdAI/sunbird-ai-api/blob/main/docs/tutorial.md)

### Authentication

#### Signing Up
If you don't already have an account, use the `/auth/register` endpoint to create one.

#### Getting an Access Token
Authentication is done via a Bearer token. Use the `/auth/token` endpoint to get your access token. This token lasts for 7 days.

Use the `Authorize` button below to login and access the protected endpoints.

## API Endpoints

### Speech-to-Text (STT)
- **`POST /tasks/modal/stt`** - Modal-based STT using Whisper large-v3 model
  - Upload audio files directly for transcription
  - Powered by Modal serverless GPU infrastructure
  - Supports various audio formats (WAV, MP3, OGG, M4A, etc.)
  - Optional `language` parameter: pass a 3-letter code (e.g. `eng`, `lug`) or full name (e.g. `english`, `luganda`) to improve transcription accuracy for local languages. Auto-detects if omitted.
- **`POST /tasks/stt`** - RunPod-based STT for supported languages with language/adapter selection

### Translation
- **`POST /tasks/translate`** - Translate text between English and local languages (Acholi, Ateso, Luganda, Lugbara, Runyankole)

### Language Detection
- **`POST /tasks/language_id`** - Auto-detect the language of text input (supports Acholi, Ateso, English, Luganda, Lugbara, Runyankole)

### Text-to-Speech (TTS)
- **`POST /tasks/modal/tts`** - Modal-based TTS with streaming support
  - **Multiple Languages**: Acholi, Ateso, Runyankore, Lugbara, Swahili, and Luganda
  - **Signed URLs**: Audio files are stored in GCP Storage with 30-minute expiring URLs
  - **Streaming Support**: Stream audio chunks for large text inputs
  - **Response Modes**:
    - `url` - Generate audio, upload to GCP, return signed URL
    - `stream` - Stream raw audio chunks directly
    - `both` - Stream audio AND get a final signed URL
- **`POST /tasks/runpod/tts`** - RunPod-based TTS for Ugandan language voices
  - Supports all major Ugandan languages
  - Fast inference with RunPod serverless infrastructure

### Inference (Sunflower Chat)
- **`POST /tasks/sunflower_inference`** - Conversational AI powered by Sunflower model with chat history
- **`POST /tasks/sunflower_simple`** - Simple text generation without chat history

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
        "description": "Operations for authentication, including user registration and login. Get access tokens to use protected endpoints.",
    },
    {
        "name": "Speech-to-Text",
        "description": "Convert speech audio to text. Supports English, Acholi, Ateso, Luganda, Lugbara, and Runyankole.",
    },
    {
        "name": "Translation",
        "description": "Translate text between English and local languages using the NLLB model. Supports bidirectional translation for Acholi, Ateso, Luganda, Lugbara, and Runyankole.",
    },
    {
        "name": "Language",
        "description": "Language identification and detection. Automatically detect the language of text input from supported languages.",
    },
    {
        "name": "TTS (Modal)",
        "description": "Modal-based Text-to-Speech services for Ugandan languages. Generate audio from text with support for streaming, signed URLs, and multiple language voices.",
    },
    {
        "name": "TTS (RunPod)",
        "description": "RunPod-based Text-to-Speech services for Ugandan languages. Fast inference using RunPod serverless infrastructure with support for multiple speaker voices.",
    },
    {
        "name": "Sunflower",
        "description": "Conversational AI powered by the Sunflower model. Supports chat-based interactions with context and simple text generation.",
    },
    {
        "name": "Upload",
        "description": "File upload utilities. Generate signed URLs for direct client uploads to GCP Storage with security validation.",
    },
    {
        "name": "Webhooks",
        "description": "WhatsApp Business API webhook integration. Handle incoming messages and verify webhook endpoints for WhatsApp chatbot functionality.",
    },
    {
        "name": "AI Tasks",
        "description": "Legacy AI task endpoints. Contains deprecated endpoints maintained for backward compatibility.",
    },
    {
        "name": "Frontend Routes",
        "description": "Web interface routes for the Sunbird AI application.",
    },
]
