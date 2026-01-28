"""
Tests for OpenAI Integration Module.

This module contains unit tests for the OpenAIClient class and related
functions defined in app/integrations/openai_client.py.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.openai_client import (
    CLASSIFICATION_GUIDES,
    CONVERSATION_GUIDE,
    GREETING_GUIDE,
    HELP_GUIDE,
    OpenAIClient,
    classify_input,
    get_completion,
    get_completion_from_messages,
    get_guide_based_on_classification,
    get_openai_client,
    is_json,
    reset_openai_client,
)


class TestOpenAIClientInitialization:
    """Tests for OpenAIClient initialization."""

    def test_default_initialization_from_env(self) -> None:
        """Test that client initializes with environment variables."""
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test-key"}):
            client = OpenAIClient()

            assert client.api_key == "sk-test-key"
            assert client.model == "gpt-4o-mini"
            assert client.temperature == 0

    def test_custom_initialization(self) -> None:
        """Test that client accepts custom configuration."""
        client = OpenAIClient(
            api_key="sk-custom-key",
            model="gpt-4o",
            temperature=0.7,
        )

        assert client.api_key == "sk-custom-key"
        assert client.model == "gpt-4o"
        assert client.temperature == 0.7

    def test_missing_api_key_logs_warning(self) -> None:
        """Test that missing API key logs a warning."""
        with patch.dict("os.environ", {}, clear=True):
            with patch("app.integrations.openai_client.logger") as mock_logger:
                client = OpenAIClient()

                mock_logger.warning.assert_called()
                assert client.api_key is None


class TestOpenAIClientChatCompletion:
    """Tests for OpenAIClient chat completion methods."""

    def test_chat_completion_sync(self) -> None:
        """Test synchronous chat completion."""
        client = OpenAIClient(api_key="sk-test-key")

        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="Hello! How can I help?"))
        ]

        # Patch the internal _sync_client attribute
        mock_sync_client = MagicMock()
        mock_sync_client.chat.completions.create.return_value = mock_response
        client._sync_client = mock_sync_client

        messages = [{"role": "user", "content": "Hello!"}]
        result = client.chat_completion_sync(messages)

        assert result == "Hello! How can I help?"
        mock_sync_client.chat.completions.create.assert_called_once()

    def test_chat_completion_sync_with_custom_params(self) -> None:
        """Test synchronous chat completion with custom parameters."""
        client = OpenAIClient(api_key="sk-test-key")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Response"))]

        # Patch the internal _sync_client attribute
        mock_sync_client = MagicMock()
        mock_sync_client.chat.completions.create.return_value = mock_response
        client._sync_client = mock_sync_client

        messages = [{"role": "user", "content": "Test"}]
        client.chat_completion_sync(messages, model="gpt-4o", temperature=0.5)

        call_kwargs = mock_sync_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o"
        assert call_kwargs["temperature"] == 0.5

    @pytest.mark.asyncio
    async def test_chat_completion_async(self) -> None:
        """Test asynchronous chat completion."""
        client = OpenAIClient(api_key="sk-test-key")

        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="Async response!"))
        ]

        # Patch the internal _async_client attribute
        mock_async_client = MagicMock()
        mock_async_client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )
        client._async_client = mock_async_client

        messages = [{"role": "user", "content": "Hello!"}]
        result = await client.chat_completion(messages)

        assert result == "Async response!"
        mock_async_client.chat.completions.create.assert_called_once()


class TestOpenAIClientClassification:
    """Tests for OpenAIClient classification methods."""

    def test_classify_input(self) -> None:
        """Test input classification."""
        client = OpenAIClient(api_key="sk-test-key")

        with patch.object(client, "chat_completion_sync") as mock_completion:
            mock_completion.return_value = "Greeting"

            result = client.classify_input("Hello!")

            assert result == "greeting"
            mock_completion.assert_called_once()

    def test_get_guide_for_classification_greeting(self) -> None:
        """Test getting guide for greeting classification."""
        client = OpenAIClient(api_key="sk-test-key")

        guide = client.get_guide_for_classification("greeting")

        assert guide == GREETING_GUIDE
        assert "translation bot" in guide

    def test_get_guide_for_classification_help(self) -> None:
        """Test getting guide for help classification."""
        client = OpenAIClient(api_key="sk-test-key")

        guide = client.get_guide_for_classification("help")

        assert guide == HELP_GUIDE

    def test_get_guide_for_classification_unknown(self) -> None:
        """Test that unknown classification defaults to conversation guide."""
        client = OpenAIClient(api_key="sk-test-key")

        guide = client.get_guide_for_classification("unknown_type")

        assert guide == CONVERSATION_GUIDE


class TestIsJson:
    """Tests for is_json utility function."""

    def test_is_json_valid(self) -> None:
        """Test that valid JSON returns True."""
        assert is_json('{"key": "value"}') is True
        assert is_json("[]") is True
        assert is_json('"string"') is True
        assert is_json("123") is True
        assert is_json("null") is True

    def test_is_json_invalid(self) -> None:
        """Test that invalid JSON returns False."""
        assert is_json("not json") is False
        assert is_json("{invalid}") is False
        assert is_json("") is False


class TestOpenAIClientSingleton:
    """Tests for singleton pattern and dependency injection."""

    def test_get_openai_client_creates_singleton(self) -> None:
        """Test that get_openai_client returns the same instance."""
        reset_openai_client()

        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test-key"}):
            client1 = get_openai_client()
            client2 = get_openai_client()

            assert client1 is client2

    def test_reset_openai_client_clears_singleton(self) -> None:
        """Test that reset_openai_client clears the singleton."""
        reset_openai_client()

        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test-key"}):
            client1 = get_openai_client()
            reset_openai_client()
            client2 = get_openai_client()

            assert client1 is not client2


class TestBackwardCompatibility:
    """Tests for backward-compatible functions."""

    def test_get_completion(self) -> None:
        """Test backward-compatible get_completion function."""
        reset_openai_client()

        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test-key"}):
            with patch.object(
                OpenAIClient, "chat_completion_sync", return_value="Response"
            ) as mock_method:
                result = get_completion("Test prompt")

                assert result == "Response"
                mock_method.assert_called_once()

    def test_get_completion_from_messages(self) -> None:
        """Test backward-compatible get_completion_from_messages function."""
        reset_openai_client()

        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test-key"}):
            with patch.object(
                OpenAIClient, "chat_completion_sync", return_value="Response"
            ) as mock_method:
                messages = [{"role": "user", "content": "Hello"}]
                result = get_completion_from_messages(messages, temperature=0.5)

                assert result == "Response"
                mock_method.assert_called_once()

    def test_classify_input_backward_compat(self) -> None:
        """Test backward-compatible classify_input function."""
        reset_openai_client()

        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test-key"}):
            with patch.object(
                OpenAIClient, "classify_input", return_value="greeting"
            ) as mock_method:
                result = classify_input("Hello!")

                assert result == "greeting"
                mock_method.assert_called_once_with("Hello!")

    def test_get_guide_based_on_classification_backward_compat(self) -> None:
        """Test backward-compatible get_guide_based_on_classification function."""
        reset_openai_client()

        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test-key"}):
            result = get_guide_based_on_classification("greeting")

            assert result == GREETING_GUIDE


class TestPromptGuides:
    """Tests for prompt guide constants."""

    def test_classification_guides_contains_all_types(self) -> None:
        """Test that CLASSIFICATION_GUIDES has all expected keys."""
        expected_keys = {
            "greeting",
            "help",
            "translation",
            "set language",
            "current language",
            "conversation",
        }
        assert set(CLASSIFICATION_GUIDES.keys()) == expected_keys

    def test_greeting_guide_contains_languages(self) -> None:
        """Test that greeting guide mentions supported languages."""
        assert "Luganda" in GREETING_GUIDE
        assert "Acholi" in GREETING_GUIDE
        assert "Ateso" in GREETING_GUIDE

    def test_help_guide_contains_json_format(self) -> None:
        """Test that help guide specifies JSON format."""
        assert '"task": "help"' in HELP_GUIDE
