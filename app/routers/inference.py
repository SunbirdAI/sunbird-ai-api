"""
Inference Router Module.

This module defines the API endpoints for Sunflower AI inference operations.
It provides endpoints for multilingual chat completions and simple instruction-based
inference using Sunbird AI's Sunflower model.

Endpoints:
    - POST /sunflower_inference: Chat completions with message history
    - POST /sunflower_simple: Simple single instruction/response

Architecture:
    Routes -> InferenceService -> RunPod OpenAI-compatible API

Usage:
    This router is included in the main application with the /tasks prefix
    to maintain backward compatibility with existing API consumers.

Note:
    This module was extracted from app/routers/tasks.py as part of the
    services layer refactoring to improve modularity.
"""

import logging
import os
import time
from typing import Any, Dict

from dotenv import load_dotenv
from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from jose import jwt
from slowapi import Limiter

from app.deps import get_current_user
from app.schemas.inference import (
    SunflowerChatRequest,
    SunflowerChatResponse,
    SunflowerSimpleResponse,
    SunflowerUsageStats,
)
from app.services.inference_service import (
    InferenceService,
    ModelLoadingError,
    get_inference_service,
    run_inference,
)
from app.utils.auth import ALGORITHM, SECRET_KEY
from app.utils.feedback import INFERENCE_TYPES, save_api_inference

load_dotenv()
logging.basicConfig(level=logging.INFO)

router = APIRouter()


def custom_key_func(request: Request) -> str:
    """Extract account type from JWT token for rate limiting.

    Args:
        request: The FastAPI request object.

    Returns:
        The account type string or 'anonymous' if not found.
    """
    header = request.headers.get("Authorization")
    if not header:
        return "anonymous"
    _, _, token = header.partition(" ")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        account_type: str = payload.get("account_type", "")
        return account_type or ""
    except Exception:
        return ""


def get_account_type_limit(key: str) -> str:
    """Get rate limit based on account type.

    Args:
        key: The account type key.

    Returns:
        Rate limit string (e.g., '50/minute').
    """
    if not key:
        return "50/minute"
    if key.lower() == "admin":
        return "1000/minute"
    if key.lower() == "premium":
        return "100/minute"
    return "50/minute"


# Initialize the Limiter
limiter = Limiter(key_func=custom_key_func)


def get_service() -> InferenceService:
    """Dependency for getting the Inference service instance.

    Returns:
        The InferenceService singleton instance.
    """
    return get_inference_service()


@router.post(
    "/sunflower_inference",
    response_model=SunflowerChatResponse,
)
@limiter.limit(get_account_type_limit)
async def sunflower_inference(
    request: Request,
    chat_request: SunflowerChatRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
    service: InferenceService = Depends(get_service),
) -> SunflowerChatResponse:
    """Professional Sunflower inference endpoint for multilingual chat completions.

    This endpoint provides access to Sunbird AI's Sunflower model, specialized in:
    - Multilingual conversations in Ugandan languages (Luganda, Acholi, Ateso, etc.)
    - Cross-lingual translations and explanations
    - Cultural context understanding
    - Educational content in local languages

    Features:
    - Automatic retry with exponential backoff
    - Context-aware responses
    - Usage tracking and monitoring
    - Support for custom system messages
    - Message history management

    Args:
        request: The FastAPI request object (required for rate limiting).
        chat_request: The chat request containing messages and parameters.
        background_tasks: FastAPI background tasks for async operations.
        current_user: The authenticated user (enforces authentication).
        service: The inference service instance.

    Returns:
        SunflowerChatResponse containing the AI's response and usage stats.

    Raises:
        HTTPException: 400 for validation errors.
        HTTPException: 502 for empty model response.
        HTTPException: 503 if the model is still loading.
        HTTPException: 504 if the request times out.
        HTTPException: 500 for unexpected errors.

    Example:
        Request body with message history:
        {
            "messages": [
                {"role": "system", "content": "You are Sunflower..."},
                {"role": "user", "content": "Translate 'How are you?' to Luganda."},
                {"role": "assistant", "content": "In Luganda, 'How are you?' is 'Oli otya?'."},
                {"role": "user", "content": "How do I say 'Good morning' in Acholi?"}
            ],
            "model_type": "qwen",
            "temperature": 0.3
        }

        Response:
        {
            "content": "In Acholi, 'Good morning' is 'Icwiny atir'.",
            "model_type": "qwen",
            "usage": {"completion_tokens": 15, "prompt_tokens": 50, "total_tokens": 65},
            "processing_time": 2.5,
            "inference_time": 2.0,
            "message_count": 5
        }
    """
    start_time = time.time()
    user = current_user

    try:
        # Validate input
        if not chat_request.messages:
            raise HTTPException(
                status_code=400, detail="At least one message is required"
            )

        # Validate message format
        valid_roles = {"system", "user", "assistant"}
        for i, message in enumerate(chat_request.messages):
            if not hasattr(message, "role") or not hasattr(message, "content"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Message {i} must have 'role' and 'content' fields",
                )
            if message.role not in valid_roles:
                raise HTTPException(
                    status_code=400,
                    detail=f"Message {i} role must be one of: {', '.join(valid_roles)}",
                )
            if not message.content or not message.content.strip():
                raise HTTPException(
                    status_code=400, detail=f"Message {i} content cannot be empty"
                )

        # Convert messages to dict format for the inference function
        messages_dict = [
            {"role": msg.role, "content": msg.content.strip()}
            for msg in chat_request.messages
        ]

        # Add default system message if none provided
        has_system_message = any(msg["role"] == "system" for msg in messages_dict)
        if not has_system_message:
            default_system = (
                "You are Sunflower, a multilingual assistant for Ugandan languages "
                "made by Sunbird AI. You specialise in accurate translations, "
                "explanations, summaries and other cross-lingual tasks."
            )
            messages_dict.insert(0, {"role": "system", "content": default_system})

        # Log the inference attempt
        logging.info(
            f"Sunflower inference requested by user {user.id} with {len(messages_dict)} messages"
        )
        logging.info(f"Model type: {chat_request.model_type}")
        logging.info(f"Temperature: {chat_request.temperature}")

        # Call the inference with retry logic
        try:
            response = run_inference(
                messages=messages_dict,
                model_type=chat_request.model_type,
                stream=chat_request.stream,
                custom_system_message=chat_request.system_message,
            )

            logging.info(f"Sunflower inference successful for user {user.id}")

        except ModelLoadingError as e:
            logging.error(f"Model loading error: {e}")
            raise HTTPException(
                status_code=503,
                detail="The AI model is currently loading. This usually takes 2-3 minutes. Please try again shortly.",
            )
        except TimeoutError as e:
            logging.error(f"Inference timeout: {e}")
            raise HTTPException(
                status_code=504,
                detail="The request timed out. Please try again with a shorter prompt or check your network connection.",
            )
        except ValueError as e:
            logging.error(f"Invalid request: {e}")
            raise HTTPException(status_code=400, detail=f"Invalid request: {str(e)}")
        except Exception as e:
            logging.error(f"Unexpected inference error: {e}")
            raise HTTPException(
                status_code=500,
                detail="An unexpected error occurred during inference. Please try again.",
            )

        # Process the response
        if not response or not response.get("content"):
            raise HTTPException(
                status_code=502,
                detail="The model returned an empty response. Please try rephrasing your request.",
            )

        end_time = time.time()
        total_time = end_time - start_time

        # Save feedback (non-blocking)
        try:
            background_tasks.add_task(
                save_api_inference,
                messages_dict,
                response.get("content", ""),
                user,
                model_type=chat_request.model_type,
                processing_time=total_time,
                inference_type=INFERENCE_TYPES["sunflower_chat"],
            )
        except Exception as e:
            logging.warning(f"Failed to schedule feedback save task: {e}")

        # Create response object
        chat_response = SunflowerChatResponse(
            content=response["content"],
            model_type=response.get("model_type", chat_request.model_type),
            usage=SunflowerUsageStats(
                completion_tokens=response.get("usage", {}).get("completion_tokens"),
                prompt_tokens=response.get("usage", {}).get("prompt_tokens"),
                total_tokens=response.get("usage", {}).get("total_tokens"),
            ),
            processing_time=total_time,
            inference_time=response.get("processing_time", 0),
            message_count=len(messages_dict),
        )

        # Endpoint usage logging is handled automatically by MonitoringMiddleware

        logging.info(
            f"Sunflower inference completed in {total_time:.2f}s "
            f"(model: {response.get('processing_time', 0):.2f}s)"
        )

        return chat_response

    except HTTPException:
        raise
    except Exception as e:
        end_time = time.time()
        total_time = end_time - start_time

        logging.error(
            f"Unexpected error in sunflower_inference after {total_time:.2f}s: {e}"
        )
        raise HTTPException(
            status_code=500,
            detail="An unexpected server error occurred. Please try again later.",
        )


@router.post(
    "/sunflower_simple",
    response_model=Dict[str, Any],
)
@limiter.limit(get_account_type_limit)
async def sunflower_simple_inference(
    request: Request,
    background_tasks: BackgroundTasks,
    instruction: str = Form(..., description="The instruction or question for the AI"),
    model_type: str = Form("qwen", description="Model type (qwen or gemma)"),
    temperature: float = Form(0.3, ge=0.0, le=2.0, description="Sampling temperature"),
    system_message: str = Form(None, description="Custom system message"),
    current_user=Depends(get_current_user),
) -> Dict[str, Any]:
    """Simple Sunflower inference endpoint for single instruction/response.

    This is a simplified interface for users who want to send a single instruction
    rather than managing conversation history. Uses form-based input for easier
    integration with simple clients.

    Args:
        request: The FastAPI request object (required for rate limiting).
        background_tasks: FastAPI background tasks for async operations.
        instruction: The question or instruction for the AI.
        model_type: Either 'qwen' (default) or 'gemma'.
        temperature: Controls randomness (0.0 = deterministic, 1.0 = creative).
        system_message: Optional custom system message.
        db: Database session.
        current_user: The authenticated user.

    Returns:
        Dictionary containing response, model_type, processing_time, usage, and success.

    Raises:
        HTTPException: 400 for validation errors.
        HTTPException: 503 if the model is still loading.
        HTTPException: 504 if the request times out.
        HTTPException: 500 for unexpected errors.

    Example:
        Form data:
        - instruction: "Translate 'hello' to Luganda"
        - model_type: "qwen"
        - temperature: 0.3

        Response:
        {
            "response": "In Luganda, 'hello' is 'Gyebaleko' or 'Wasuze otya' (Good morning).",
            "model_type": "qwen",
            "processing_time": 1.5,
            "usage": {"completion_tokens": 20, "prompt_tokens": 10, "total_tokens": 30},
            "success": true
        }
    """
    start_time = time.time()
    user = current_user

    try:
        # Validate input
        if not instruction or not instruction.strip():
            raise HTTPException(status_code=400, detail="Instruction cannot be empty")

        if len(instruction.strip()) > 4000:
            raise HTTPException(
                status_code=400,
                detail="Instruction too long. Please limit to 4000 characters.",
            )

        # Validate model type
        if model_type not in ["qwen", "gemma"]:
            raise HTTPException(
                status_code=400, detail="Model type must be either 'qwen' or 'gemma'"
            )

        logging.info(f"Simple Sunflower inference requested by user {user.id}")
        logging.info(f"Instruction length: {len(instruction)} characters")

        # Call the inference
        try:
            response = run_inference(
                instruction=instruction.strip(),
                model_type=model_type,
                stream=False,
                custom_system_message=system_message,
            )

        except ModelLoadingError as e:
            logging.error(f"Model loading error: {e}")
            raise HTTPException(
                status_code=503,
                detail="The AI model is currently loading. Please wait 2-3 minutes and try again.",
            )
        except TimeoutError as e:
            logging.error(f"Inference timeout: {e}")
            raise HTTPException(
                status_code=504,
                detail="Request timed out. Please try again with a shorter instruction.",
            )
        except Exception as e:
            logging.error(f"Inference error: {e}")
            raise HTTPException(
                status_code=500, detail="Inference failed. Please try again."
            )

        end_time = time.time()
        total_time = end_time - start_time

        # Save feedback (non-blocking)
        try:
            background_tasks.add_task(
                save_api_inference,
                instruction.strip(),
                response.get("content", ""),
                user,
                model_type=model_type,
                processing_time=total_time,
                inference_type=INFERENCE_TYPES["sunflower_simple"],
            )
        except Exception as e:
            logging.warning(f"Failed to schedule feedback save task: {e}")

        # Endpoint usage logging is handled automatically by MonitoringMiddleware

        # Return simple response
        result = {
            "response": response.get("content", ""),
            "model_type": response.get("model_type", model_type),
            "processing_time": total_time,
            "usage": response.get("usage", {}),
            "success": True,
        }

        logging.info(f"Simple Sunflower inference completed in {total_time:.2f}s")
        return result

    except HTTPException:
        raise
    except Exception as e:
        end_time = time.time()
        total_time = end_time - start_time

        logging.error(f"Unexpected error in simple inference: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred")
