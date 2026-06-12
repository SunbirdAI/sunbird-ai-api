"""
Chat Completions Router Module.

OpenAI-compatible chat completions for the Sunflower model. This endpoint
supersedes the deprecated /tasks/sunflower_inference and
/tasks/sunflower_simple endpoints: a single instruction is simply a request
with one user message, and conversational context is the messages array.

Endpoints:
    - POST /chat/completions: OpenAI-format chat completion (JSON or SSE)

Architecture:
    Routes -> InferenceService -> RunPod OpenAI-compatible API

Spec:
    docs/superpowers/specs/2026-06-12-chat-completions-design.md
"""

import json  # noqa: F401 — used by Task 6 streaming path
import logging
import time
import uuid
from typing import Any, Dict, Generator, List, Optional  # noqa: F401 — Generator/Optional used by Task 6

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.core.exceptions import (
    BadRequestError,
    ExternalServiceError,
    ServiceUnavailableError,
)
from app.deps import CurrentUserDep, DbDep, InferenceServiceDep, QuotaServiceDep
from app.schemas.chat import (
    SUPPORTED_MODELS,
    ChatCompletionChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionResponseMessage,
    ChatCompletionUsage,
)
from app.services.inference_service import (
    InferenceService,
    InferenceTimeoutError,
    ModelLoadingError,
)
from app.utils.feedback import INFERENCE_TYPES, save_api_inference
from app.utils.quota_guard import check_quota
from app.utils.rate_limit import get_account_type_limit, limiter

logger = logging.getLogger(__name__)

router = APIRouter()

# RunPod endpoint key that serves Sunbird/Sunflower-14B (see
# InferenceService.endpoints).
INTERNAL_MODEL_TYPE = "qwen"


def _completion_id() -> str:
    """Generate an OpenAI-style completion id."""
    return f"chatcmpl-{uuid.uuid4().hex}"


def _prepare_messages(chat_request: ChatCompletionRequest) -> List[Dict[str, str]]:
    """Convert request messages to dicts, injecting the default system message
    when the client did not provide one (mirrors the legacy endpoints)."""
    messages = [
        {"role": m.role, "content": m.content.strip()}
        for m in chat_request.messages
    ]
    if not any(m["role"] == "system" for m in messages):
        messages.insert(
            0, {"role": "system", "content": InferenceService.SYSTEM_MESSAGE}
        )
    return messages


def _validate_model(chat_request: ChatCompletionRequest) -> None:
    """Strict model validation: only models in SUPPORTED_MODELS are accepted."""
    if chat_request.model not in SUPPORTED_MODELS:
        raise BadRequestError(
            message=(
                f"Model '{chat_request.model}' is not supported. "
                f"Supported models: {', '.join(SUPPORTED_MODELS)}"
            )
        )


@router.post(
    "/chat/completions",
    response_model=ChatCompletionResponse,
    summary="OpenAI-compatible chat completion (Sunflower)",
)
@limiter.limit(get_account_type_limit)
async def chat_completions(
    request: Request,
    chat_request: ChatCompletionRequest,
    quota: QuotaServiceDep,
    background_tasks: BackgroundTasks,
    db: DbDep,
    current_user: CurrentUserDep,
    service: InferenceServiceDep,
):
    """OpenAI-compatible chat completion powered by Sunbird's Sunflower model.

    Single-instruction usage is a request with one user message; conversational
    usage passes the running message history. Set ``stream: true`` for
    Server-Sent Events in OpenAI ``chat.completion.chunk`` format, terminated
    by ``data: [DONE]``.
    """
    await check_quota(quota, db, current_user)
    _validate_model(chat_request)
    messages = _prepare_messages(chat_request)

    logger.info(
        f"Chat completion requested by user {current_user.id} "
        f"({len(messages)} messages, stream={chat_request.stream})"
    )

    if chat_request.stream:
        return await _stream_chat_completion(
            chat_request, messages, service, background_tasks, current_user
        )
    return await _create_chat_completion(
        chat_request, messages, service, background_tasks, current_user
    )


async def _create_chat_completion(
    chat_request: ChatCompletionRequest,
    messages: List[Dict[str, str]],
    service: InferenceService,
    background_tasks: BackgroundTasks,
    user: Any,
) -> ChatCompletionResponse:
    """Non-streaming path: run inference and build a chat.completion object."""
    start_time = time.time()

    try:
        result = await run_in_threadpool(
            lambda: service.run_inference(
                messages=messages,
                model_type=INTERNAL_MODEL_TYPE,
                temperature=chat_request.temperature,
                max_tokens=chat_request.max_tokens,
                top_p=chat_request.top_p,
                stop=chat_request.stop,
            )
        )
    except ModelLoadingError as e:
        logger.error(f"Model loading error: {e}")
        raise ServiceUnavailableError(
            message=(
                "The AI model is currently loading. This usually takes "
                "2-3 minutes. Please try again shortly."
            )
        )
    except InferenceTimeoutError as e:
        logger.error(f"Inference timeout: {e}")
        raise ServiceUnavailableError(
            message="The request timed out. Please try again with a shorter prompt."
        )
    except ValueError as e:
        logger.error(f"Invalid request: {e}")
        raise BadRequestError(message=f"Invalid request: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected inference error: {e}")
        raise ExternalServiceError(
            service_name="Sunflower Inference Service",
            message="An unexpected error occurred during inference. Please try again.",
            original_error=str(e),
        )

    content = (result or {}).get("content")
    if not content:
        raise ExternalServiceError(
            service_name="Sunflower Model",
            message=(
                "The model returned an empty response. "
                "Please try rephrasing your request."
            ),
        )

    total_time = time.time() - start_time
    usage = (result or {}).get("usage") or {}

    background_tasks.add_task(
        save_api_inference,
        messages,
        content,
        user,
        model_type=chat_request.model,
        processing_time=total_time,
        inference_type=INFERENCE_TYPES["chat_completions"],
    )

    logger.info(f"Chat completion finished in {total_time:.2f}s")

    return ChatCompletionResponse(
        id=_completion_id(),
        created=int(time.time()),
        model=chat_request.model,
        choices=[
            ChatCompletionChoice(
                index=0,
                message=ChatCompletionResponseMessage(content=content),
                finish_reason="stop",
            )
        ],
        usage=ChatCompletionUsage(
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
        ),
    )


async def _stream_chat_completion(
    chat_request: ChatCompletionRequest,
    messages: List[Dict[str, str]],
    service: InferenceService,
    background_tasks: BackgroundTasks,
    user: Any,
) -> StreamingResponse:
    """Streaming path — implemented in Task 6."""
    raise BadRequestError(message="Streaming is not implemented yet")
