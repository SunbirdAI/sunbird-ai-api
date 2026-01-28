"""
Inference Service Module.

This module provides the InferenceService class for running language model
inference using the Sunflower/UG40 models via RunPod's serverless API.

Architecture:
    The service wraps the RunPod API with:
    - Exponential backoff retry logic for transient failures
    - Error classification for retryable vs non-retryable errors
    - OpenAI-compatible chat completions interface

Usage:
    from app.services.inference_service import (
        InferenceService,
        get_inference_service,
        run_inference,
    )

    # Using the service class
    service = InferenceService()
    result = service.run_inference(
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Translate 'hello' to Luganda."},
        ],
        model_type="qwen"
    )

    # Using the standalone function (backward compatible)
    result = run_inference(
        instruction="Translate 'hello' to Luganda.",
        model_type="qwen"
    )

Note:
    This module was consolidated from app/inference_services/ug40_inference.py
    as part of the services layer refactoring.
"""

import json
import logging
import os
import random
import re
import time
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, TypeVar

from dotenv import load_dotenv
from openai import APIError, OpenAI, RateLimitError
from pydantic import BaseModel, Field
from requests.exceptions import ConnectionError, HTTPError, Timeout

from app.services.base import BaseService

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

# Type variable for generic functions
F = TypeVar("F", bound=Callable[..., Any])


# =============================================================================
# Custom Exception Classes
# =============================================================================


class ModelLoadingError(Exception):
    """Exception raised when the model is still loading or unavailable.

    This error indicates that the RunPod endpoint is experiencing a cold start
    or the model is being initialized. The request should be retried.

    Attributes:
        message: Explanation of the error.
    """

    pass


class InferenceTimeoutError(Exception):
    """Exception raised when the inference request times out.

    This error indicates that the request took too long to complete.
    The request may be retried with exponential backoff.

    Attributes:
        message: Explanation of the error.
    """

    pass


# =============================================================================
# Pydantic Models for Request/Response
# =============================================================================


class SunflowerChatMessage(BaseModel):
    """A single message in the chat conversation.

    Attributes:
        role: The role of the message sender ('system', 'user', or 'assistant').
        content: The content of the message.
    """

    role: str = Field(..., description="Message role: 'system', 'user', or 'assistant'")
    content: str = Field(..., description="Message content")


class SunflowerChatRequest(BaseModel):
    """Request model for Sunflower chat inference.

    Attributes:
        messages: List of conversation messages.
        model_type: The model to use ('qwen').
        temperature: Sampling temperature (0.0 to 2.0).
        stream: Whether to stream the response.
        system_message: Optional custom system message.
    """

    messages: List[SunflowerChatMessage] = Field(
        ..., description="List of conversation messages"
    )
    model_type: str = Field("qwen", description="Model type: 'qwen'")
    temperature: float = Field(0.3, ge=0.0, le=2.0, description="Sampling temperature")
    stream: bool = Field(False, description="Whether to stream the response")
    system_message: Optional[str] = Field(None, description="Custom system message")


class SunflowerUsageStats(BaseModel):
    """Token usage statistics from the inference.

    Attributes:
        completion_tokens: Number of tokens in the completion.
        prompt_tokens: Number of tokens in the prompt.
        total_tokens: Total number of tokens used.
    """

    completion_tokens: Optional[int] = Field(
        None, description="Number of tokens in the completion"
    )
    prompt_tokens: Optional[int] = Field(
        None, description="Number of tokens in the prompt"
    )
    total_tokens: Optional[int] = Field(None, description="Total number of tokens used")


class SunflowerChatResponse(BaseModel):
    """Response model from Sunflower chat inference.

    Attributes:
        content: The AI's response text.
        model_type: The model used for inference.
        usage: Token usage statistics.
        processing_time: Total processing time in seconds.
        inference_time: Model inference time in seconds.
        message_count: Number of messages processed.
    """

    content: str = Field(..., description="The AI's response")
    model_type: str = Field(..., description="Model used for inference")
    usage: SunflowerUsageStats = Field(..., description="Token usage statistics")
    processing_time: float = Field(..., description="Total processing time in seconds")
    inference_time: float = Field(
        default=0.0, description="Model inference time in seconds"
    )
    message_count: int = Field(default=0, description="Number of messages processed")


# =============================================================================
# Error Classification
# =============================================================================


def classify_error(error: Exception, response_text: Optional[str] = None) -> Exception:
    """Classify errors to determine if they should trigger a retry.

    Args:
        error: The original exception.
        response_text: Optional response text for additional context.

    Returns:
        The classified exception (ModelLoadingError, InferenceTimeoutError,
        or the original exception if not retryable).
    """
    error_str = str(error).lower()

    # Check response text for RunPod-specific error messages
    if response_text:
        response_str = response_text.lower()

        # RunPod-specific model loading errors
        loading_keywords = [
            "model is loading",
            "model not ready",
            "downloading",
            "loading model",
            "model unavailable",
            "service unavailable",
            "endpoint not ready",
            "cold start",
            "initializing",
            "starting up",
            "worker is starting",
            "worker not ready",
            "error: worker is not ready",
            "job failed to start",
        ]

        if any(keyword in response_str for keyword in loading_keywords):
            return ModelLoadingError(f"Model is still loading: {response_text}")

    # Model loading/downloading errors from exception message
    loading_keywords = [
        "model is loading",
        "model not ready",
        "downloading",
        "loading model",
        "model unavailable",
        "service unavailable",
        "endpoint not ready",
        "cold start",
        "worker is starting",
        "worker not ready",
        "worker is not ready",
        "initializing",
    ]

    if any(keyword in error_str for keyword in loading_keywords):
        return ModelLoadingError(f"Model is still loading: {error}")

    # Timeout errors
    timeout_keywords = [
        "timeout",
        "timed out",
        "read timeout",
        "connection timeout",
        "request timeout",
    ]

    if any(keyword in error_str for keyword in timeout_keywords):
        return InferenceTimeoutError(f"Request timed out: {error}")

    # HTTP error handling
    if isinstance(error, HTTPError):
        status_code = error.response.status_code if error.response else None

        # 5xx errors are retryable (server errors)
        if status_code and 500 <= status_code < 600:
            return ModelLoadingError(f"Server error {status_code}: {error}")

        # 429 (Too Many Requests) is retryable
        if status_code == 429:
            return InferenceTimeoutError(f"Rate limited: {error}")

        # 503 (Service Unavailable) is retryable
        if status_code == 503:
            return ModelLoadingError(f"Service unavailable: {error}")

    # Connection errors - retryable
    if isinstance(error, (ConnectionError, Timeout)):
        return InferenceTimeoutError(f"Connection error: {error}")

    # OpenAI SDK errors
    if isinstance(error, RateLimitError):
        return InferenceTimeoutError(f"Rate limited: {error}")

    if isinstance(error, APIError):
        if hasattr(error, "status_code"):
            if error.status_code and 500 <= error.status_code < 600:
                return ModelLoadingError(f"API server error: {error}")

    # Return original error if not retryable
    return error


# =============================================================================
# Retry Decorator
# =============================================================================


def exponential_backoff_retry(
    max_retries: int = 4,
    base_delay: float = 3.0,
    max_delay: float = 180.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: Tuple[Type[Exception], ...] = (
        ModelLoadingError,
        InferenceTimeoutError,
    ),
) -> Callable[[F], F]:
    """Decorator for exponential backoff retry logic.

    Args:
        max_retries: Maximum number of retry attempts.
        base_delay: Initial delay between retries in seconds.
        max_delay: Maximum delay between retries in seconds.
        exponential_base: Base for exponential backoff calculation.
        jitter: Whether to add random jitter to delays.
        retryable_exceptions: Tuple of exception types that trigger retries.

    Returns:
        Decorated function with retry logic.

    Example:
        @exponential_backoff_retry(max_retries=3)
        def my_function():
            # Function that may fail transiently
            pass
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            delay = base_delay
            last_exception: Optional[Exception] = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    classified_error = classify_error(e)

                    if attempt == max_retries:
                        logger.error(
                            f"All {max_retries + 1} attempts failed. "
                            f"Last error: {classified_error}"
                        )
                        raise classified_error

                    if not isinstance(classified_error, retryable_exceptions):
                        logger.error(f"Non-retryable error: {classified_error}")
                        raise classified_error

                    last_exception = classified_error

                    # Add jitter if enabled
                    actual_delay = delay
                    if jitter:
                        actual_delay = delay * (0.5 + random.random() * 0.5)

                    actual_delay = min(actual_delay, max_delay)

                    logger.warning(
                        f"Attempt {attempt + 1} failed: {classified_error}. "
                        f"Retrying in {actual_delay:.2f} seconds..."
                    )
                    time.sleep(actual_delay)

                    delay *= exponential_base

            if last_exception:
                raise last_exception
            raise RuntimeError("Unexpected retry loop exit")

        return wrapper  # type: ignore

    return decorator


# =============================================================================
# Inference Service Class
# =============================================================================


class InferenceService(BaseService):
    """Service for running language model inference.

    This service provides methods for running inference using the Sunflower/UG40
    language models via RunPod's serverless API. It includes automatic retry
    logic with exponential backoff for transient failures.

    Attributes:
        SYSTEM_MESSAGE: Default system message for the assistant.
        ENDPOINTS: Configuration for available model endpoints.

    Example:
        service = InferenceService()
        result = service.run_inference(
            messages=[
                {"role": "user", "content": "Hello!"}
            ]
        )
        print(result["content"])
    """

    SYSTEM_MESSAGE = (
        "You are Sunflower, a multilingual assistant for Ugandan languages "
        "made by Sunbird AI. You specialise in accurate translations, "
        "explanations, summaries and other cross-lingual tasks."
    )

    def __init__(
        self,
        runpod_api_key: Optional[str] = None,
        qwen_endpoint_id: Optional[str] = None,
    ) -> None:
        """Initialize the inference service.

        Args:
            runpod_api_key: RunPod API key. Defaults to RUNPOD_API_KEY env var.
            qwen_endpoint_id: Qwen endpoint ID. Defaults to QWEN_ENDPOINT_ID env var.
        """
        super().__init__()

        self.runpod_api_key = runpod_api_key or os.getenv("RUNPOD_API_KEY")
        self.qwen_endpoint_id = qwen_endpoint_id or os.getenv("QWEN_ENDPOINT_ID")

        self.endpoints = {
            "qwen": {
                "endpoint_id": self.qwen_endpoint_id,
                "model_name": "Sunbird/Sunflower-14B",
            },
        }

        if not self.runpod_api_key:
            self.log_warning("RUNPOD_API_KEY not configured")

        if not self.qwen_endpoint_id:
            self.log_warning("QWEN_ENDPOINT_ID not configured")

    def _get_client(self, model_type: str = "qwen") -> OpenAI:
        """Get an OpenAI client configured for the specified model.

        Args:
            model_type: The model type to use.

        Returns:
            Configured OpenAI client.

        Raises:
            ValueError: If the model type is not supported.
        """
        config = self.endpoints.get(model_type.lower())
        if not config:
            raise ValueError(f"Unsupported model type: {model_type}")

        url = f"https://api.runpod.ai/v2/{config['endpoint_id']}/openai/v1"

        return OpenAI(
            api_key=self.runpod_api_key,
            base_url=url,
        )

    def _build_messages(
        self,
        instruction: Optional[str] = None,
        messages: Optional[List[Dict[str, str]]] = None,
        custom_system_message: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """Build the messages array for the API request.

        Args:
            instruction: Legacy instruction string.
            messages: Full conversation messages in OpenAI format.
            custom_system_message: Custom system message to override default.

        Returns:
            List of message dictionaries.
        """
        if messages:
            # Use provided messages array (preferred approach)
            final_messages = [dict(m) for m in messages]  # Copy to avoid mutation

            # Override system message if custom one provided
            if custom_system_message:
                # Find and replace system message
                system_found = False
                for i, msg in enumerate(final_messages):
                    if msg.get("role") == "system":
                        final_messages[i]["content"] = custom_system_message
                        system_found = True
                        break

                if not system_found:
                    # No system message found, add at beginning
                    final_messages.insert(
                        0, {"role": "system", "content": custom_system_message}
                    )

            self.log_info(f"Using messages array with {len(final_messages)} messages")
            return final_messages

        else:
            # Legacy support - build from instruction
            system_message = custom_system_message or self.SYSTEM_MESSAGE
            final_messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": instruction or ""},
            ]

            if instruction:
                preview = (
                    instruction[:100] + "..." if len(instruction) > 100 else instruction
                )
                self.log_info(f"Using legacy instruction format: {preview}")

            return final_messages

    def _clean_response(self, content: Optional[str]) -> str:
        """Clean the response content by removing thinking tags and their content.

        Args:
            content: Raw response content.

        Returns:
            Cleaned response content.
        """
        if not content:
            return ""

        # Remove all <think>...</think> tags and their content
        cleaned = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        return cleaned

    @exponential_backoff_retry(
        max_retries=4,
        base_delay=3.0,
        max_delay=180.0,
        exponential_base=2.0,
        jitter=True,
        retryable_exceptions=(ModelLoadingError, InferenceTimeoutError),
    )
    def run_inference(
        self,
        instruction: Optional[str] = None,
        model_type: str = "qwen",
        stream: bool = False,
        custom_system_message: Optional[str] = None,
        messages: Optional[List[Dict[str, str]]] = None,
        temperature: float = 0.3,
    ) -> Dict[str, Any]:
        """Run inference using the language model.

        Args:
            instruction: The input text/instruction for the model (legacy support).
            model_type: The model to use ('qwen').
            stream: Whether to stream the response.
            custom_system_message: Custom system message to override the default.
            messages: Full conversation messages in OpenAI format (preferred).
            temperature: Sampling temperature (0.0 to 2.0).

        Returns:
            Dictionary containing:
                - content: The AI's response text.
                - usage: Token usage statistics.
                - model_type: The model used.
                - processing_time: Time taken in seconds.

        Raises:
            ValueError: If the model type is not supported.
            ModelLoadingError: If the model is still loading (retryable).
            InferenceTimeoutError: If the request times out (retryable).

        Example:
            result = service.run_inference(
                messages=[
                    {"role": "system", "content": "You are helpful."},
                    {"role": "user", "content": "Hello!"},
                ]
            )
        """
        self.log_info("Starting run_inference")
        self.log_info(f"Model Type: {model_type}")
        self.log_info(f"Stream: {stream}")
        self.log_info(f"Messages format: {'Yes' if messages else 'No'}")

        config = self.endpoints.get(model_type.lower())
        if not config:
            self.log_error(f"Unsupported model type: {model_type}")
            raise ValueError(f"Unsupported model type: {model_type}")

        self.log_info(
            f"Using endpoint ID: {config['endpoint_id']} and model: {config['model_name']}"
        )

        # Get client and build messages
        client = self._get_client(model_type)
        final_messages = self._build_messages(
            instruction=instruction,
            messages=messages,
            custom_system_message=custom_system_message,
        )

        payload = {
            "model": config["model_name"],
            "messages": final_messages,
            "temperature": temperature,
            "stream": stream,
        }

        start_time = time.time()
        response_text: Optional[str] = None

        try:
            self.log_info("Sending request to RunPod API...")
            self.log_debug(f"Request payload: {json.dumps(payload, indent=2)}")

            response = client.chat.completions.create(**payload)
            self.log_info(f"Raw response received")

            end_time = time.time()
            processing_time = end_time - start_time

            # OpenAI-like response handling
            if hasattr(response, "choices") and response.choices:
                choice = response.choices[0]
                response_content = (
                    choice.message.content
                    if hasattr(choice, "message") and hasattr(choice.message, "content")
                    else None
                )

                self.log_debug(f"Raw response content: {response_content}")

                # Clean response
                cleaned_content = self._clean_response(response_content)
                self.log_info(f"Cleaned output: {cleaned_content[:100]}...")

                # Usage stats
                usage = getattr(response, "usage", None)
                usage_dict = {
                    "completion_tokens": (
                        getattr(usage, "completion_tokens", None) if usage else None
                    ),
                    "prompt_tokens": (
                        getattr(usage, "prompt_tokens", None) if usage else None
                    ),
                    "total_tokens": (
                        getattr(usage, "total_tokens", None) if usage else None
                    ),
                }

                result = {
                    "content": cleaned_content,
                    "usage": usage_dict,
                    "model_type": model_type,
                    "processing_time": processing_time,
                }

                self.log_info("Request to RunPod API successful")
                return result

            else:
                self.log_error("No choices in response")
                raise ValueError("No response choices available")

        except (ModelLoadingError, InferenceTimeoutError):
            # Re-raise retryable errors
            raise
        except RateLimitError as e:
            self.log_error(f"Rate limit error: {e}")
            raise classify_error(e)
        except APIError as e:
            self.log_error(f"API error: {e}")
            raise classify_error(e, str(e))
        except Timeout as e:
            self.log_error(f"Request timed out: {e}")
            raise InferenceTimeoutError(f"Request to RunPod API timed out: {e}")
        except ConnectionError as e:
            self.log_error(f"Connection error: {e}")
            raise InferenceTimeoutError(f"Connection error to RunPod API: {e}")
        except json.JSONDecodeError as e:
            self.log_error(f"JSON decode error: {e}")
            self.log_error(f"Raw response that failed to decode: {response_text}")
            raise ValueError(f"Invalid JSON response from RunPod API: {e}")
        except Exception as e:
            self.log_error(f"Unexpected error during API request: {e}")
            classified_error = classify_error(e, response_text)
            raise classified_error


# =============================================================================
# Singleton and Dependency Injection
# =============================================================================

_inference_service: Optional[InferenceService] = None


def get_inference_service() -> InferenceService:
    """Get or create the singleton inference service instance.

    Returns:
        The InferenceService singleton instance.

    Example:
        service = get_inference_service()
        result = service.run_inference(...)
    """
    global _inference_service
    if _inference_service is None:
        _inference_service = InferenceService()
    return _inference_service


def reset_inference_service() -> None:
    """Reset the singleton inference service instance.

    Useful for testing to ensure a fresh instance.
    """
    global _inference_service
    _inference_service = None


# =============================================================================
# Standalone Function (Backward Compatible)
# =============================================================================


def run_inference(
    instruction: Optional[str] = None,
    model_type: str = "qwen",
    stream: bool = False,
    custom_system_message: Optional[str] = None,
    messages: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Run inference using the UG40 model via RunPod (standalone function).

    This function provides backward compatibility with the original
    ug40_inference module. For new code, prefer using the InferenceService class.

    The retry logic is handled by the InferenceService.run_inference method,
    so this function does not need its own retry decorator.

    Args:
        instruction: The input text/instruction for the model (legacy support).
        model_type: Either "qwen" (currently only qwen is supported).
        stream: Whether to stream the response.
        custom_system_message: Custom system message to override the default.
        messages: Full conversation messages in OpenAI format (preferred).

    Returns:
        Dictionary containing content, usage stats, and processing time.

    Example:
        # Legacy usage
        result = run_inference(instruction="Hello!")

        # Preferred usage
        result = run_inference(
            messages=[
                {"role": "user", "content": "Hello!"}
            ]
        )
    """
    service = get_inference_service()

    return service.run_inference(
        instruction=instruction,
        model_type=model_type,
        stream=stream,
        custom_system_message=custom_system_message,
        messages=messages,
    )
