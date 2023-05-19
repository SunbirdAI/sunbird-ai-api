description = """
Welcome to the Sunbird AI API documentation. The Sunbird AI API provides you access to Sunbird's language models. The currently supported models are:
- **Translation (English to Multiple)**: translate from English to Acholi, Ateso, Luganda, Lugbara and Runyankole.
- **Translation (Multiple to English)**: translate from the 5 local language above to English.
- **Speech To Text (Luganda)**: Convert Luganda speech audio to text.

You can create an account and test the endpoints directly on this page.

## Getting started
### Signing up
If you don't already have an account, use the `/auth/register` endpoint to create one. (You can scroll down this page to try it out)

### Logging in and getting an access token.
Authentication is done via a Bearer token. Use the `/auth/token` endpoint to get your access token. This token lasts for 7 days.


### AI Tasks
- Use the `/tasks/stt` endpoint for speech to text inference for one audio file.
- Use the `/tasks/translate` endpoint for translation of one text input.
- Use the `/tasks/translate-batch` endpoint for translation of multiple text inputs.

You can use the interactive documentation below to test out these endpoints and get a feel for their structure. 
You can use the `Authorize` button below to login and access the protected endpoints.

Also checkout this repository (TODO) for code samples in Python and Javascript.
"""

tags_metadata = [
    {
        "name": "AI Tasks",
        "description": "Operations for AI inference."
    },
    {
        "name": "Authentication Endpoints",
        "description": "Operations for Authentication, including Sign up and Login"
    }
]
