import logging
import json
import requests
import re
import time
from requests.exceptions import Timeout, ConnectionError, HTTPError, RequestException
from openai import OpenAI
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get configuration from environment variables
RUNPOD_API_KEY = os.getenv("RUNPOD_API_KEY")
GEMMA_ENDPOINT_ID = os.getenv("GEMMA_ENDPOINT_ID")
QWEN_ENDPOINT_ID = os.getenv("QWEN_ENDPOINT_ID")

ENDPOINTS = {
    "gemma": {
        "endpoint_id": GEMMA_ENDPOINT_ID,
        "model_name": "patrickcmd/gemma3-12b-ug40-merged"
    },
    "qwen": {
        "endpoint_id": QWEN_ENDPOINT_ID,
        "model_name": "Sunbird/qwen3-14b-sunflower-20250905-1k-translations-merged"
    },
}

SYSTEM_MESSAGE = """You are Sunflower, a multilingual assistant for Ugandan languages made by Sunbird AI. You specialise in accurate translations, explanations, summaries and other cross-lingual tasks."""


class ModelLoadingError(Exception):
    """Exception raised when the model is still loading"""
    pass


class TimeoutError(Exception):
    """Exception raised when the request times out"""
    pass


def exponential_backoff_retry(max_retries=4, base_delay=3.0, max_delay=180.0, 
                             exponential_base=2.0, jitter=True, retryable_exceptions=(ModelLoadingError, TimeoutError)):
    """
    Decorator for exponential backoff retry logic
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            delay = base_delay
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    classified_error = _classify_error(e)
                    
                    if attempt == max_retries:
                        logger.error(f"All {max_retries + 1} attempts failed. Last error: {classified_error}")
                        raise classified_error
                    
                    if not isinstance(classified_error, retryable_exceptions):
                        logger.error(f"Non-retryable error: {classified_error}")
                        raise classified_error
                    
                    last_exception = classified_error
                    
                    # Add jitter if enabled
                    actual_delay = delay
                    if jitter:
                        import random
                        actual_delay = delay * (0.5 + random.random() * 0.5)
                    
                    actual_delay = min(actual_delay, max_delay)
                    
                    logger.warning(f"Attempt {attempt + 1} failed: {classified_error}. Retrying in {actual_delay:.2f} seconds...")
                    time.sleep(actual_delay)
                    
                    delay *= exponential_base
            
            raise last_exception
        return wrapper
    return decorator


def _classify_error(error: Exception, response_text: str = None) -> Exception:
    """
    Classify errors to determine if they should trigger a retry
    """
    error_str = str(error).lower()
    
    # Check response text for RunPod-specific error messages
    if response_text:
        response_str = response_text.lower()
        
        # RunPod-specific model loading errors
        if any(keyword in response_str for keyword in [
            'model is loading',
            'model not ready',
            'downloading',
            'loading model',
            'model unavailable',
            'service unavailable',
            'endpoint not ready',
            'cold start',
            'initializing',
            'starting up',
            'worker is starting',
            'worker not ready',
            'error: worker is not ready',
            'job failed to start'
        ]):
            return ModelLoadingError(f"Model is still loading: {response_text}")
    
    # Model loading/downloading errors from exception message
    if any(keyword in error_str for keyword in [
        'model is loading',
        'model not ready',
        'downloading',
        'loading model',
        'model unavailable',
        'service unavailable',
        'endpoint not ready',
        'cold start',
        'worker is starting',
        'worker not ready',
        'initializing'
    ]):
        return ModelLoadingError(f"Model is still loading: {error}")
    
    # Timeout errors
    if any(keyword in error_str for keyword in [
        'timeout',
        'timed out',
        'read timeout',
        'connection timeout',
        'request timeout'
    ]):
        return TimeoutError(f"Request timed out: {error}")
    
    # HTTP error handling
    if isinstance(error, HTTPError):
        status_code = error.response.status_code if error.response else None
        
        # 5xx errors are retryable (server errors)
        if status_code and 500 <= status_code < 600:
            return ModelLoadingError(f"Server error {status_code}: {error}")
        
        # 429 (Too Many Requests) is retryable
        if status_code == 429:
            return TimeoutError(f"Rate limited: {error}")
        
        # 503 (Service Unavailable) is retryable
        if status_code == 503:
            return ModelLoadingError(f"Service unavailable: {error}")
    
    # Connection errors - retryable
    if isinstance(error, (ConnectionError, Timeout)):
        return TimeoutError(f"Connection error: {error}")
    
    # Return original error if not retryable
    return error


@exponential_backoff_retry(
    max_retries=4,  # Total of 5 attempts (initial + 4 retries)
    base_delay=3.0,  # Start with 3 second delay (increased for model loading)
    max_delay=180.0,  # Max 3 minutes between retries (increased for cold starts)
    exponential_base=2.0,  # Double the delay each time
    jitter=True,  # Add randomness to prevent thundering herd
    retryable_exceptions=(ModelLoadingError, TimeoutError)
)
def run_inference(instruction: str, model_type: str, stream: bool = False, custom_system_message: str = None) -> dict:
    """
    Run inference using the UG40 model via RunPod
    
    Args:
        instruction (str): The input text/instruction for the model
        model_type (str): Either "gemma" or "qwen"
        stream (bool): Whether to stream the response
        custom_system_message (str): Custom system message to override the default
        
    Returns:
        dict: Response containing content, usage stats, and processing time
    """
    logger.info("Starting run_inference function")
    logger.info(f"Instruction: {instruction[:100]}..." if len(instruction) > 100 else f"Instruction: {instruction}")
    logger.info(f"Model Type: {model_type}")
    logger.info(f"Stream: {stream}")
    logger.info(f"Custom system message: {'Yes' if custom_system_message else 'No'}")

    config = ENDPOINTS.get(model_type.lower())
    if not config:
        logger.error(f"Unsupported model type: {model_type}")
        raise ValueError(f"Unsupported model type: {model_type}")

    logger.info(f"Using endpoint ID: {config['endpoint_id']} and model: {config['model_name']}")

    # Use RunPod's vllm OPENAI compatible API
    url = f"https://api.runpod.ai/v2/{config['endpoint_id']}/openai/v1"
    
    # Initialize the OpenAI client
    client = OpenAI(
        api_key=RUNPOD_API_KEY,
        base_url=url,
    )
    
    # Use custom system message if provided, otherwise use default
    system_message = custom_system_message if custom_system_message else SYSTEM_MESSAGE
    
    payload = {
        "model": config['model_name'],
        "messages": [
            {"role": "system", "content": system_message},
            {"role": "user", "content": instruction}
        ],
        "temperature": 0.5,
        "stream": stream  # Enable streaming if requested
    }

    response_text = None
    start_time = time.time()
    try:
        logger.info("Sending request to RunPod API...")
        logger.debug(f"Request URL: {url}")
        logger.debug(f"Request payload: {json.dumps(payload, indent=2)}")

        logger.info(f"Payload request to RunPod API: {payload}\n")
        response = client.chat.completions.create(**payload)
        logger.info(f"Raw response: {response}\n\n")

        end_time = time.time()
        processing_time = end_time - start_time

        # OpenAI-like response handling
        if hasattr(response, 'choices') and response.choices:
            choice = response.choices[0]
            response_content = choice.message.content if hasattr(choice, 'message') and hasattr(choice.message, 'content') else None
            logger.info(f"Raw response content: {response_content}\n\n")
            # Remove all <think> and </think> tags
            cleaned_content_output = re.sub(r"</?think>", "", response_content).strip() if response_content else ""
            logger.info(f"Cleaned output: {cleaned_content_output}")

            # Usage stats
            usage = getattr(response, 'usage', None)
            usage_dict = {
                "completion_tokens": getattr(usage, 'completion_tokens', None) if usage else None,
                "prompt_tokens": getattr(usage, 'prompt_tokens', None) if usage else None,
                "total_tokens": getattr(usage, 'total_tokens', None) if usage else None
            }

            # Return as JSON
            result_json = {
                "content": cleaned_content_output,
                "usage": usage_dict,
                "model_type": model_type,
                "processing_time": processing_time
            }
            logger.info(f"Request to RunPod API successful: {result_json}")
            return result_json

        else:
            logger.error("No choices in response")
            raise ValueError("No response choices available")

    except requests.exceptions.Timeout as e:
        logger.error(f"Request timed out: {e}")
        raise TimeoutError(f"Request to RunPod API timed out: {e}")
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error: {e}")
        if e.response is not None:
            logger.error(f"Response status: {e.response.status_code}")
            logger.error(f"Response content: {e.response.text}")
        classified_error = _classify_error(e, e.response.text if e.response else None)
        raise classified_error
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error: {e}")
        raise TimeoutError(f"Connection error to RunPod API: {e}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response content: {e.response.text}")
            classified_error = _classify_error(e, e.response.text)
        else:
            classified_error = _classify_error(e, response_text)
        raise classified_error
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        logger.error(f"Raw response that failed to decode: {response_text}")
        raise ValueError(f"Invalid JSON response from RunPod API: {e}")
    except (ModelLoadingError, TimeoutError):
        raise
    except Exception as e:
        logger.error(f"Unexpected error during API request: {e}")
        classified_error = _classify_error(e, response_text)
        raise classified_error
