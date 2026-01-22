description = """
Welcome to the Sunbird AI API documentation. The Sunbird AI API provides you access to Sunbird's language models. The currently supported models are:  # noqa E501
- **Translation (English to Multiple)**: translate from English to Acholi, Ateso, Luganda, Lugbara and Runyankole.
- **Translation (Multiple to English)**: translate from the 5 local language above to English.
- **Speech To Text**: Convert speech audio to text. Currently the supported languages are (**English**, **Acholi**, **Ateso**, **Luganda**, **Lugbara** and **Runyankole**)

You can create an account and test the endpoints directly on this page.

## Getting started
You can checkout the [usage guide](https://salt.sunbird.ai/API/) for a full tutorial.

### Signing up
If you don't already have an account, use the `/auth/register` endpoint to create one. (You can scroll down this page to try it out)

### Logging in and getting an access token.
Authentication is done via a Bearer token. Use the `/auth/token` endpoint to get your access token. This token lasts for 7 days.

Use the `Authorize` button below to login and access the protected endpoints.

### AI Tasks
- Use the `/tasks/stt` endpoint for speech to text inference for one audio file.
- Use the `tasks/nllb-translate` endpoint for translation of text input with the NLLB model.
- Use the `/tasks/language_id` endpoint for auto language detection of text input. 
This endpoint identifies the language of a given text. It supports a limited set 
of local languages including Acholi (ach), Ateso (teo), English (eng),Luganda (lug), 
Lugbara (lgg), and Runyankole (nyn).
- Use the `/tasks/summarise` endpoint for anonymised summarization of text input. 
This endpoint does anonymised summarisation of a given text. The text languages
supported for now are English (eng) and Luganda (lug).

### TTS API with GCP Storage Integration

A Text-to-Speech API that converts text to audio using multiple Ugandan language voices.

#### TTS Features

- **Multiple Languages**: Acholi, Ateso, Runyankore, Lugbara, Swahili, and Luganda
- **Signed URLs**: Audio files are stored in GCP Storage with 30-minute expiring URLs
- **Streaming Support**: Stream audio chunks for large text inputs
- **Combined Mode**: Stream audio AND get a final signed URL

### Response Modes

| Mode | Description |
|------|-------------|
| `url` | Generate audio, upload to GCP, return signed URL |
| `stream` | Stream raw audio chunks directly |
| `both` | Stream audio + upload to GCP + return final URL |
"""

tags_metadata = [
    {"name": "AI Tasks", "description": "Operations for AI inference."},
    {
        "name": "Authentication Endpoints",
        "description": "Operations for Authentication, including Sign up and Login",
    },
]
