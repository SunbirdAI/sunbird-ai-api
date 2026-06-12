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

import json
import logging
import time
import uuid
from typing import Any, Dict, Generator, List, Optional

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
    ChatCompletionChunk,
    ChatCompletionChunkChoice,
    ChatCompletionChunkDelta,
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
        {"role": m.role, "content": m.content.strip()} for m in chat_request.messages
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


async def _fetch_first_stream_item(stream_gen: Any) -> Any:
    """Eagerly fetch the first item from a sync generator in a threadpool.

    Translates inference errors into proper HTTP exceptions so that
    pre-first-token failures surface as error responses, not 200 SSE streams.
    Raises ExternalServiceError(502) when the generator is empty.
    """
    try:
        first_item = await run_in_threadpool(lambda: next(stream_gen, None))
    except ModelLoadingError as e:
        logger.error(f"Model loading error before stream start: {e}")
        raise ServiceUnavailableError(
            message=(
                "The AI model is currently loading. This usually takes "
                "2-3 minutes. Please try again shortly."
            )
        )
    except InferenceTimeoutError as e:
        logger.error(f"Timeout before stream start: {e}")
        raise ServiceUnavailableError(
            message="The request timed out. Please try again with a shorter prompt."
        )
    except ValueError as e:
        logger.error(f"Invalid streaming request: {e}")
        raise BadRequestError(message=f"Invalid request: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error before stream start: {e}")
        raise ExternalServiceError(
            service_name="Sunflower Inference Service",
            message="An unexpected error occurred during inference. Please try again.",
            original_error=str(e),
        )

    if first_item is None:
        raise ExternalServiceError(
            service_name="Sunflower Model",
            message=(
                "The model returned an empty response. "
                "Please try rephrasing your request."
            ),
        )
    return first_item


def _event_stream(
    completion_id: str,
    created: int,
    model: str,
    first_item: Any,
    stream_gen: Any,
    accumulated: List[str],
) -> Generator[str, None, None]:
    """Sync generator that emits OpenAI SSE chunks from a stream_gen iterator.

    Yields one role-priming chunk, then one content chunk per delta item,
    then a finish chunk, an optional usage chunk, and finally ``data: [DONE]``.
    Midstream exceptions yield an SSE error event before the terminal DONE.
    """

    def _sse_chunk(
        delta: ChatCompletionChunkDelta,
        finish_reason: Optional[str] = None,
    ) -> str:
        chunk = ChatCompletionChunk(
            id=completion_id,
            created=created,
            model=model,
            choices=[
                ChatCompletionChunkChoice(
                    index=0, delta=delta, finish_reason=finish_reason
                )
            ],
        )
        return f"data: {chunk.model_dump_json()}\n\n"

    def _sse_usage_chunk(usage: Dict[str, Any]) -> str:
        chunk = ChatCompletionChunk(
            id=completion_id,
            created=created,
            model=model,
            choices=[],
            usage=ChatCompletionUsage(
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
            ),
        )
        return f"data: {chunk.model_dump_json()}\n\n"

    usage_stats: Optional[Dict[str, Any]] = None
    try:
        yield _sse_chunk(ChatCompletionChunkDelta(role="assistant", content=""))
        item = first_item
        while item is not None:
            if item.get("type") == "delta":
                text = item.get("content") or ""
                if text:
                    accumulated.append(text)
                    yield _sse_chunk(ChatCompletionChunkDelta(content=text))
            elif item.get("type") == "usage":
                usage_stats = item.get("usage")
            item = next(stream_gen, None)

        yield _sse_chunk(ChatCompletionChunkDelta(), finish_reason="stop")
        if usage_stats:
            yield _sse_usage_chunk(usage_stats)
    except Exception as e:
        logger.error(f"Error during chat completion stream: {e}")
        error_payload = {
            "error": {
                "message": (
                    "The stream was interrupted by an unexpected error. "
                    "Please retry the request."
                ),
                "type": "server_error",
            }
        }
        yield f"data: {json.dumps(error_payload)}\n\n"
    finally:
        yield "data: [DONE]\n\n"


async def _save_stream_feedback(
    messages: List[Dict[str, str]],
    accumulated: List[str],
    user: Any,
    model: str,
    start_time: float,
) -> None:
    """Background task: persist the streamed completion for analytics."""
    if accumulated:
        await save_api_inference(
            messages,
            "".join(accumulated),
            user,
            model_type=model,
            processing_time=time.time() - start_time,
            inference_type=INFERENCE_TYPES["chat_completions"],
        )


async def _stream_chat_completion(
    chat_request: ChatCompletionRequest,
    messages: List[Dict[str, str]],
    service: InferenceService,
    background_tasks: BackgroundTasks,
    user: Any,
) -> StreamingResponse:
    """Streaming path: emit OpenAI chat.completion.chunk SSE events.

    The first item is fetched eagerly (in a worker thread) so that failures
    occurring before any token has been produced surface as proper HTTP
    errors instead of a 200 SSE stream. After streaming begins, failures
    terminate the stream with an SSE error event and are never retried.
    """
    completion_id = _completion_id()
    created = int(time.time())
    start_time = time.time()

    stream_gen = service.run_inference_stream(
        messages=messages,
        model_type=INTERNAL_MODEL_TYPE,
        temperature=chat_request.temperature,
        max_tokens=chat_request.max_tokens,
        top_p=chat_request.top_p,
        stop=chat_request.stop,
    )

    first_item = await _fetch_first_stream_item(stream_gen)

    accumulated: List[str] = []

    background_tasks.add_task(
        _save_stream_feedback,
        messages,
        accumulated,
        user,
        chat_request.model,
        start_time,
    )

    return StreamingResponse(
        _event_stream(
            completion_id,
            created,
            chat_request.model,
            first_item,
            stream_gen,
            accumulated,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
