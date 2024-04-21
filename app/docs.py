description = """
Welcome to the Sunbird AI API documentation. The Sunbird AI API provides you access to Sunbird's language models. The currently supported models are:  # noqa E501
- **Translation (English to Multiple)**: translate from English to Acholi, Ateso, Luganda, Lugbara and Runyankole.
- **Translation (Multiple to English)**: translate from the 5 local language above to English.
- **Speech To Text (Luganda)**: Convert Luganda speech audio to text.

You can create an account and test the endpoints directly on this page.

## Getting started
You can checkout the [usage guide](https://github.com/SunbirdAI/sunbird-ai-api/blob/main/tutorial.md) for a full tutorial.

### Signing up
If you don't already have an account, use the `/auth/register` endpoint to create one. (You can scroll down this page to try it out)

### Logging in and getting an access token.
Authentication is done via a Bearer token. Use the `/auth/token` endpoint to get your access token. This token lasts for 7 days.

Use the `Authorize` button below to login and access the protected endpoints.

### AI Tasks
- Use the `/tasks/stt` endpoint for speech to text inference for one audio file.
- Use the `/tasks/translate` endpoint for translation of one text input.
- Use the `/tasks/translate-batch` endpoint for translation of multiple text inputs.
- Use the `tasks/nllb-translate` endpoint for translation of text input with the NLLB model.
"""

tags_metadata = [
    {"name": "AI Tasks", "description": "Operations for AI inference."},
    {
        "name": "Authentication Endpoints",
        "description": "Operations for Authentication, including Sign up and Login",
    },
]
