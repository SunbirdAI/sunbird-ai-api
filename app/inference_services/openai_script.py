import json
import os

import openai
from dotenv import load_dotenv

load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")

greeting_guide = """
You are a translation bot that was developer by Sunbird AI. When a user greets you, respond warmly and provide a brief introduction about your capabilities. Inform the user that you can help with translations in the following Ugandan languages if asked:

- Luganda
- Acholi
- Ateso
- Lugbara
- Runyankole
- English

If they do not specify a target language for translation, the default language is Luganda ('lug').

Respond in JSON format:
{
    "task": "greeting",
    "text": "<greeting and introduction>"
}
"""


help_guide = """
You are a translation bot that was developed by Sunbird AI. If a user asks for help or seems confused, provide clear and concise guidance on how they can use the bot. Inform them that the bot supports the following languages:

- Luganda
- Acholi
- Ateso
- Lugbara
- Runyankole
- English

Mention that if they do not specify a target language, the bot will use Luganda ('lug') by default.

Respond in JSON format:
{
    "task": "help",
    "text": "<guidance message>"
}
"""


translation_guide = """
You are a translation bot. When a user asks for a translation, follow these guidelines:

1. **Text Validation**: 
   - Do not process empty text or single emojis.
   - Reject unstructured text (e.g., random characters like "vkhfykhgcjvcfcjghcj") that cannot be translated.

2. **Target Language**: 
   - Identify the target language based on user input.
   - If the target language isn't specified, use Luganda ('lug') as the default.

3. **Supported Languages**:
   - Luganda: code 'lug'
   - Acholi: code 'ach'
   - Ateso: code 'teo'
   - Lugbara: code 'lgg'
   - Runyankole: code 'nyn'
   - English: code 'eng'

4. **Response Format**: 
   - Ensure that you return the correct translation format.

Respond in JSON format:
{
    "task": "translation",
    "text": "<text to be translated>",
    "target_language": "<target language code>"
}

If the input text is invalid, respond with a message indicating the error instead of attempting a translation.
"""


conversation_guide = """
You are a translation bot. If a user asks a general question unrelated to translations, explain that your main function is to assist with translations and provide a brief introduction to Sunbird AI.

Respond in JSON format:
{
    "task": "conversation",
    "text": "<response>"
}
"""


set_language_guide = """
You are a translation bot. If a user wants to set a specific language for translations, recognize the language and store it for future translation tasks.

Respond in JSON format:
{
    "task": "setLanguage",
    "language": "<language code>"
}
"""

classification_prompt = """
You are an assistant that categorizes user inputs into predefined tasks. Based on the user's input, classify it into one of the following categories:

1. Greeting: For messages like "Hello", "Hi", etc.
2. Help: When the user needs guidance or asks how to use the bot.
3. Translation: When the user asks for a translation.
4. Set Language: When the user wants to set a language for future translations.
5. Conversation: For general conversations not related to the above tasks.

Categorize the user's input and return the category name.
"""


def classify_input(input_text):
    messages = [
        {"role": "system", "content": classification_prompt},
        {"role": "user", "content": input_text},
    ]
    response = get_completion_from_messages(messages)
    return response.strip().lower()


def get_guide_based_on_classification(classification):
    if classification == "greeting":
        return greeting_guide
    elif classification == "help":
        return help_guide
    elif classification == "translation":
        return translation_guide
    elif classification == "set language":
        return set_language_guide
    else:
        return conversation_guide


def is_json(data):
    try:
        json.loads(data)
        return True
    except ValueError:
        return False


def get_completion(prompt, model="gpt-4o-mini"):
    messages = [{"role": "user", "content": prompt}]
    response = openai.ChatCompletion.create(
        model=model,
        messages=messages,
        temperature=0,  # this is the degree of randomness of the model's output
    )
    return response.choices[0].message["content"]


def get_completion_from_messages(messages, model="gpt-4o-mini", temperature=0):

    response = openai.ChatCompletion.create(
        model=model,
        messages=messages,
        temperature=0,  # this is the degree of randomness of the model's output
    )
    #     print(str(response.choices[0].message))
    return response.choices[0].message["content"]
