"""
OpenAI Integration Module.

This module provides a client for interacting with OpenAI's API,
primarily for chat completions used in the WhatsApp translation bot.

The client supports:
    - Chat completions for message classification
    - Translation task guidance
    - User intent classification (greeting, help, translation, etc.)

Architecture:
    Services -> OpenAIClient -> OpenAI API

Usage:
    from app.integrations.openai_client import OpenAIClient, get_openai_client

    # Using the singleton
    client = get_openai_client()
    response = await client.chat_completion(messages)

    # Or create a custom instance
    client = OpenAIClient(api_key="my-key", model="gpt-4o")
    response = await client.chat_completion(messages)

Example:
    >>> client = OpenAIClient()
    >>> messages = [
    ...     {"role": "system", "content": "You are a helpful assistant."},
    ...     {"role": "user", "content": "Hello!"}
    ... ]
    >>> response = await client.chat_completion(messages)
    >>> print(response)
    "Hello! How can I help you today?"
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional, Union

from openai import AsyncOpenAI, OpenAI

# Module-level logger
logger = logging.getLogger(__name__)


# =============================================================================
# Prompt Templates for WhatsApp Bot
# =============================================================================

GREETING_GUIDE = """
You are a translation bot developed by Sunbird AI. The user may send multiple messages at a time, with the most recent message listed first. Your task is to identify whether the user is greeting you based on their most recent message and respond warmly.

Provide a brief introduction about your capabilities and inform the user that you can help with translations in the following Ugandan languages:

- Luganda
- Acholi
- Ateso
- Lugbara
- Runyankole
- English

If no target language for translation is specified, the default language is Luganda ('lug').

Respond in **this exact JSON format**:
{
    "task": "greeting",
    "text": "<greeting and introduction>"
}
"""

HELP_GUIDE = """
You are a translation bot developed by Sunbird AI. The user may send multiple messages at a time, and the most recent message is the most important. If the user asks for help or seems confused in any of the recent messages, provide clear and concise guidance on how they can use the bot.

Inform them that the bot supports the following languages:

- Luganda
- Acholi
- Ateso
- Lugbara
- Runyankole
- English

If they do not specify a target language, the bot will use Luganda ('lug') by default.

Respond in **this exact JSON format**:
{
    "task": "help",
    "text": "<guidance message>"
}
"""

TRANSLATION_GUIDE = """
You are a translation bot. The user may send multiple messages at once, with the most recent one being the most important. However, you should analyze all recent messages for context. Your job is to guide the translation process without performing any translation.

When a user asks for a translation, follow these guidelines:

1. **Text Validation**:
   - Check all recent messages for structured text that can be translated.
   - Ignore empty messages, single emojis, or unstructured text (like random characters).

2. **Target Language**:
   - Identify the target language based on user input, considering all recent messages.
   - If the target language isn't specified, do not include the `target_language` field in the JSON response.

3. **Supported Languages**:
   - Luganda: code 'lug'
   - Acholi: code 'ach'
   - Ateso: code 'teo'
   - Lugbara: code 'lgg'
   - Runyankole: code 'nyn'
   - English: code 'eng'

4. **Response**:
   - If the target language is specified, provide a JSON response with the `text` to be translated and the `target_language`.
   - If the target language is **not** specified, provide a JSON response with only the `text` field, omitting the `target_language` field.
   - Do not perform the actual translation. The Sunbird AI system will handle that.

Respond in **one of these two JSON formats** depending on whether the target language is specified or not:

- If the target language is specified, respond in this format:
{
    "task": "translation",
    "text": "<text to be translated>",
    "target_language": "<target language code>"
}

- If the target language is **not** specified, respond in this format:
{
    "task": "translation",
    "text": "<text to be translated>"
}

If the input text is invalid, respond with a message indicating the error instead of attempting a translation.
"""

CONVERSATION_GUIDE = """
You are a translation bot. The user may send multiple messages at once, with the most recent being the most important. Analyze all recent messages to determine if the user is engaging in a general conversation unrelated to translations.

If the user's message(s) seem unrelated to translations, explain that your main function is to assist with translations and provide a brief introduction to Sunbird AI.

Respond in **this exact JSON format**:
{
    "task": "conversation",
    "text": "<response>"
}
"""

CURRENT_LANGUAGE_GUIDE = """
You are a translation bot. If a user asks about their current target language is.

Respond in **this exact JSON format**:
{
    "task": "currentLanguage"
}
"""

SET_LANGUAGE_GUIDE = """
You are a translation bot. The user may send multiple messages about setting a language for future translations, with the most recent message being the most important. Follow these steps:

1. **Spelling Correction**:
   - If the user inputs a language that seems misspelled in any of the recent messages, try to infer the correct language.
   - If no close match is found, inform the user of the supported languages and request clarification.

2. **Out-of-Scope Languages**:
   - If the language provided by the user is not in scope, return an instructional message in plain text (not JSON) politely informing the user about the supported languages:
     Luganda, Acholi, Ateso, Lugbara, Runyankole, and English.

3. **Valid Language Codes**:
   - If the language is valid, use the following language codes:
     - 'lug' for Luganda
     - 'ach' for Acholi
     - 'teo' for Ateso
     - 'lgg' for Lugbara
     - 'nyn' for Runyankole
     - 'eng' for English

3. **Successful Response**:
   - If the language is valid or successfully corrected, respond in JSON format with the correct language code.

For valid language settings, respond in **this exact JSON format**:
{
    "task": "setLanguage",
    "language": "<language code>"
}

For invalid or out-of-scope languages, respond with an instructional message like this:
"Sorry, the language you provided is not supported. Please choose from Luganda, Acholi, Ateso, Lugbara, Runyankole, or English."
"""

CLASSIFICATION_PROMPT = """
You are an assistant that categorizes user inputs into predefined tasks. Based on the user's input, classify it into one of the following categories:

1. Greeting: For messages like "Hello", "Hi", etc.
2. Help: When the user needs guidance or asks how to use the bot.
3. Translation: When the user asks for a translation.
4. Set Language: When the user wants to set a language for future translations.
5. Current Language: When the user wants to know their current target language.
6. Conversation: For general conversations not related to the above tasks.

Categorize the user's input and return the category name.
"""

# Mapping of classification to guide
CLASSIFICATION_GUIDES = {
    "greeting": GREETING_GUIDE,
    "help": HELP_GUIDE,
    "translation": TRANSLATION_GUIDE,
    "set language": SET_LANGUAGE_GUIDE,
    "current language": CURRENT_LANGUAGE_GUIDE,
    "conversation": CONVERSATION_GUIDE,
}


class OpenAIClient:
    """Client for interacting with OpenAI's chat completions API.

    This client provides both synchronous and asynchronous methods for
    chat completions, with support for the WhatsApp translation bot's
    classification and response generation workflows.

    Attributes:
        api_key: The OpenAI API key for authentication.
        model: The default model to use for completions.
        temperature: The default temperature for completions.

    Example:
        >>> client = OpenAIClient()
        >>> response = await client.chat_completion([
        ...     {"role": "user", "content": "Hello!"}
        ... ])
        >>> print(response)
        "Hello! How can I assist you today?"
    """

    DEFAULT_MODEL = "gpt-4o-mini"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0,
    ) -> None:
        """Initialize the OpenAI client.

        Args:
            api_key: OpenAI API key. Defaults to OPENAI_API_KEY env var.
            model: Default model for completions. Defaults to gpt-4o-mini.
            temperature: Default temperature (0-2). Lower is more deterministic.

        Example:
            >>> # Use environment variables
            >>> client = OpenAIClient()

            >>> # Use custom configuration
            >>> client = OpenAIClient(
            ...     api_key="sk-...",
            ...     model="gpt-4o",
            ...     temperature=0.7
            ... )
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or self.DEFAULT_MODEL
        self.temperature = temperature

        # Initialize clients
        self._sync_client: Optional[OpenAI] = None
        self._async_client: Optional[AsyncOpenAI] = None

        if not self.api_key:
            logger.warning("OPENAI_API_KEY not set - OpenAI calls will fail")

    @property
    def sync_client(self) -> OpenAI:
        """Get or create the synchronous OpenAI client."""
        if self._sync_client is None:
            self._sync_client = OpenAI(api_key=self.api_key)
        return self._sync_client

    @property
    def async_client(self) -> AsyncOpenAI:
        """Get or create the asynchronous OpenAI client."""
        if self._async_client is None:
            self._async_client = AsyncOpenAI(api_key=self.api_key)
        return self._async_client

    def chat_completion_sync(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """Generate a chat completion synchronously.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            model: Model to use. Defaults to self.model.
            temperature: Temperature for sampling. Defaults to self.temperature.

        Returns:
            The assistant's response content as a string.

        Example:
            >>> messages = [{"role": "user", "content": "Hello!"}]
            >>> response = client.chat_completion_sync(messages)
            >>> print(response)
            "Hello! How can I help you?"
        """
        model = model or self.model
        temperature = temperature if temperature is not None else self.temperature

        logger.debug(f"Generating chat completion with model={model}")

        response = self.sync_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
        )

        return response.choices[0].message.content

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """Generate a chat completion asynchronously.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            model: Model to use. Defaults to self.model.
            temperature: Temperature for sampling. Defaults to self.temperature.

        Returns:
            The assistant's response content as a string.

        Example:
            >>> messages = [{"role": "user", "content": "Hello!"}]
            >>> response = await client.chat_completion(messages)
            >>> print(response)
            "Hello! How can I help you?"
        """
        model = model or self.model
        temperature = temperature if temperature is not None else self.temperature

        logger.debug(f"Generating async chat completion with model={model}")

        response = await self.async_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
        )

        return response.choices[0].message.content

    def classify_input(self, input_text: str) -> str:
        """Classify user input into a task category.

        Uses the classification prompt to determine the user's intent
        from their message text.

        Args:
            input_text: The user's input message.

        Returns:
            The classification category (lowercase), one of:
            - "greeting"
            - "help"
            - "translation"
            - "set language"
            - "current language"
            - "conversation"

        Example:
            >>> client.classify_input("Hello!")
            "greeting"
            >>> client.classify_input("Translate hello to Luganda")
            "translation"
        """
        messages = [
            {"role": "system", "content": CLASSIFICATION_PROMPT},
            {"role": "user", "content": input_text},
        ]
        response = self.chat_completion_sync(messages)
        return response.strip().lower()

    def get_guide_for_classification(self, classification: str) -> str:
        """Get the appropriate prompt guide for a classification.

        Args:
            classification: The task classification (e.g., "greeting").

        Returns:
            The corresponding prompt guide string.

        Example:
            >>> guide = client.get_guide_for_classification("greeting")
            >>> "translation bot" in guide
            True
        """
        return CLASSIFICATION_GUIDES.get(classification, CONVERSATION_GUIDE)


def is_json(data: str) -> bool:
    """Check if a string is valid JSON.

    Args:
        data: The string to check.

    Returns:
        True if the string is valid JSON, False otherwise.

    Example:
        >>> is_json('{"key": "value"}')
        True
        >>> is_json('not json')
        False
    """
    try:
        json.loads(data)
        return True
    except (ValueError, TypeError):
        return False


# -----------------------------------------------------------------------------
# Singleton and Dependency Injection
# -----------------------------------------------------------------------------

_openai_client: Optional[OpenAIClient] = None


def get_openai_client() -> OpenAIClient:
    """Get or create the OpenAI client singleton.

    Returns:
        OpenAIClient instance configured with environment settings.

    Example:
        >>> client = get_openai_client()
        >>> response = await client.chat_completion(messages)
    """
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAIClient()
    return _openai_client


def reset_openai_client() -> None:
    """Reset the OpenAI client singleton.

    Primarily used for testing to ensure a fresh instance.
    """
    global _openai_client
    _openai_client = None


# -----------------------------------------------------------------------------
# Backward Compatibility Functions
# -----------------------------------------------------------------------------


def get_completion(prompt: str, model: str = "gpt-4o-mini") -> str:
    """Get a completion from a prompt (backward-compatible).

    Args:
        prompt: The user prompt.
        model: The model to use.

    Returns:
        The completion text.
    """
    client = get_openai_client()
    messages = [{"role": "user", "content": prompt}]
    return client.chat_completion_sync(messages, model=model)


def get_completion_from_messages(
    messages: List[Dict[str, str]],
    model: str = "gpt-4o-mini",
    temperature: float = 0,
) -> str:
    """Get a completion from messages (backward-compatible).

    Args:
        messages: List of message dicts.
        model: The model to use.
        temperature: The temperature for sampling.

    Returns:
        The completion text.
    """
    client = get_openai_client()
    return client.chat_completion_sync(messages, model=model, temperature=temperature)


def classify_input(input_text: str) -> str:
    """Classify user input (backward-compatible).

    Args:
        input_text: The user's input message.

    Returns:
        The classification category.
    """
    client = get_openai_client()
    return client.classify_input(input_text)


def get_guide_based_on_classification(classification: str) -> str:
    """Get guide for classification (backward-compatible).

    Args:
        classification: The task classification.

    Returns:
        The corresponding prompt guide.
    """
    client = get_openai_client()
    return client.get_guide_for_classification(classification)


__all__ = [
    # Client class
    "OpenAIClient",
    "get_openai_client",
    "reset_openai_client",
    # Utility functions
    "is_json",
    # Prompt guides
    "GREETING_GUIDE",
    "HELP_GUIDE",
    "TRANSLATION_GUIDE",
    "CONVERSATION_GUIDE",
    "CURRENT_LANGUAGE_GUIDE",
    "SET_LANGUAGE_GUIDE",
    "CLASSIFICATION_PROMPT",
    "CLASSIFICATION_GUIDES",
    # Backward compatibility
    "get_completion",
    "get_completion_from_messages",
    "classify_input",
    "get_guide_based_on_classification",
]
