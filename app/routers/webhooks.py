"""
Webhooks Router Module.

This module defines the API endpoints for webhook operations,
primarily for WhatsApp Business API webhook handling.

Endpoints:
    - POST /webhook: Handle incoming WhatsApp webhooks
    - GET /webhook: Verify webhook endpoint ownership

Architecture:
    Routes -> WhatsAppService -> WhatsApp API

Usage:
    This router is included in the main application with the /tasks prefix
    to maintain backward compatibility with existing API consumers.

Note:
    This module was extracted from app/routers/tasks.py as part of the
    services layer refactoring to improve modularity.
"""

import hashlib
import hmac
import json
import logging
import os
import time
from typing import Optional

from dotenv import load_dotenv
from fastapi import APIRouter, BackgroundTasks, Request, Response
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.exceptions import AuthorizationError, BadRequestError
from app.integrations.whatsapp_store import save_response
from app.schemas.webhooks import WebhookResponse
from app.services.message_processor import OptimizedMessageProcessor, ResponseType
from app.services.whatsapp_service import get_whatsapp_service

load_dotenv()
logging.basicConfig(level=logging.INFO)

router = APIRouter()

# Initialize WhatsApp service using singleton
whatsapp_service = get_whatsapp_service()

# Initialize processor
processor = OptimizedMessageProcessor()

# Header Meta uses to sign webhook payloads.
SIGNATURE_HEADER = "X-Hub-Signature-256"
_VALID_SIGNATURE_MODES = {"off", "log", "enforce"}


def _evaluate_webhook_signature(
    raw_body: bytes, signature_header: Optional[str]
) -> dict:
    """Evaluate the X-Hub-Signature-256 header against the raw request body.

    Computes the expected HMAC-SHA256 signature using ``WHATSAPP_APP_SECRET``
    (never ``VERIFY_TOKEN``) and compares it to the provided header in
    constant time. This function only evaluates; it never raises and never
    logs the secret, the signature value, or the body.

    Args:
        raw_body: The exact raw bytes of the request body.
        signature_header: Value of the ``X-Hub-Signature-256`` header, if any.

    Returns:
        A dict with safe-to-log metadata:
            - mode: effective mode ('off' | 'log' | 'enforce')
            - active: whether verification is actually applied (mode != off
              and a secret is configured)
            - present: whether a signature header was supplied
            - valid: True/False when active, else None
    """
    mode = (settings.whatsapp_signature_mode or "off").strip().lower()
    if mode not in _VALID_SIGNATURE_MODES:
        logging.warning("Unknown WHATSAPP_SIGNATURE_MODE %r; treating as 'off'.", mode)
        mode = "off"

    present = bool(signature_header)

    if mode == "off":
        return {"mode": "off", "active": False, "present": present, "valid": None}

    secret = settings.whatsapp_app_secret
    if not secret:
        # log/enforce requested but no secret available: fail safe to 'off'
        # behavior without crashing and without exposing any secret value.
        logging.warning(
            "WHATSAPP_SIGNATURE_MODE=%s but WHATSAPP_APP_SECRET is not set; "
            "skipping signature verification (behaving as 'off').",
            mode,
        )
        return {"mode": mode, "active": False, "present": present, "valid": None}

    valid = False
    if present:
        expected = (
            "sha256="
            + hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        )
        valid = hmac.compare_digest(signature_header, expected)

    return {"mode": mode, "active": True, "present": present, "valid": valid}


async def send_template_response(
    template_name: str, phone_number_id: str, from_number: str, sender_name: str
):
    """
    Send template responses to WhatsApp users.

    This function sends predefined interactive button templates
    based on the template name.

    Args:
        template_name: Name of the template to send.
        phone_number_id: WhatsApp phone number ID.
        from_number: Sender's phone number.
        sender_name: Sender's name.

    Templates:
        -  stom_feedback: Feedback collection button
        - welcome_message: Welcome button
        - choose_language: Language selection button
    """
    try:
        if template_name == "custom_feedback":
            whatsapp_service.send_button(
                button=processor.create_feedback_button(),
                phone_number_id=phone_number_id,
                recipient_id=from_number,
            )

        elif template_name == "welcome_message":
            whatsapp_service.send_button(
                button=processor.create_welcome_button(),
                phone_number_id=phone_number_id,
                recipient_id=from_number,
            )

        elif template_name == "choose_language":
            whatsapp_service.send_button(
                button=processor.create_language_selection_button(),
                phone_number_id=phone_number_id,
                recipient_id=from_number,
            )

    except Exception as e:
        logging.error(f"Error sending template {template_name}: {e}")


@router.post("/webhook")
@router.post("/webhook/")
async def webhook(  # noqa: C901
    request: Request,
    background_tasks: BackgroundTasks,
) -> WebhookResponse:
    """
    Handle incoming WhatsApp webhooks.

    This endpoint processes incoming WhatsApp messages and events,
    providing fast responses for text messages and background processing
    for heavy operations.

    Features:
    - Fast text responses (2-4 seconds)
    - Background processing for heavy operations
    - No external caching dependencies
    - Duplicate message detection
    - Language preference support

    The raw request body is read directly so the X-Hub-Signature-256 header
    can be verified over the exact signed bytes before JSON parsing. Signature
    verification behavior is controlled by WHATSAPP_SIGNATURE_MODE
    ('off' | 'log' | 'enforce'); see ``_evaluate_webhook_signature``.

    Args:
        request: The incoming HTTP request (raw body + headers).
        background_tasks: FastAPI background tasks for async processing.

    Returns:
        WebhookResponse with processing status and time.

    Response Status Codes:
        - 200: Successfully processed
        - WHATSAPP_SIGNATURE_REJECT_STATUS (default 403): invalid signature in
          enforce mode
        - 500: Internal server error

    Example Payload:
        {
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": "1234567890",
                            "text": {"body": "Hello"}
                        }],
                        "contacts": [{
                            "profile": {"name": "John"}
                        }],
                        "metadata": {
                            "phone_number_id": "9876543210"
                        }
                    }
                }]
            }]
        }

    Example Response:
        {
            "status": "success",
            "processing_time": 2.5
        }
    """
    start_time = time.time()

    try:
        # Read the raw body first: signature verification must run over the
        # exact bytes Meta signed, before any JSON parsing.
        raw_body = await request.body()
        signature_header = request.headers.get(SIGNATURE_HEADER)
        signature = _evaluate_webhook_signature(raw_body, signature_header)

        if signature["active"]:
            if signature["valid"]:
                logging.info(
                    "WhatsApp webhook signature verified (mode=%s)",
                    signature["mode"],
                )
            else:
                # Only safe metadata is logged: never the header value or body.
                logging.warning(
                    "WhatsApp webhook signature check failed "
                    "(mode=%s, signature_present=%s, signature_valid=%s)",
                    signature["mode"],
                    signature["present"],
                    signature["valid"],
                )
                if signature["mode"] == "enforce":
                    reject_status = settings.whatsapp_signature_reject_status
                    return JSONResponse(
                        status_code=reject_status,
                        content={
                            "status": "rejected",
                            "processing_time": time.time() - start_time,
                            "message": "Invalid webhook signature",
                        },
                    )

        # Parse JSON safely from the raw body after signature handling.
        try:
            payload = json.loads(raw_body)
        except (json.JSONDecodeError, ValueError, TypeError):
            logging.info("Webhook payload was not valid JSON; ignoring.")
            return WebhookResponse(
                status="ignored",
                processing_time=time.time() - start_time,
                message="Invalid JSON payload",
            )

        # Quick validation
        if not whatsapp_service.valid_payload(payload):
            logging.info("Invalid payload received")
            return WebhookResponse(
                status="ignored",
                processing_time=time.time() - start_time,
                message="Invalid payload format",
            )

        messages = whatsapp_service.get_messages_from_payload(payload)
        if not messages:
            is_status_update = any(
                "statuses" in change.get("value", {})
                for entry in payload.get("entry", [])
                for change in entry.get("changes", [])
            )
            return WebhookResponse(
                status="ignored" if is_status_update else "no_messages",
                processing_time=time.time() - start_time,
                message=(
                    "Status update received"
                    if is_status_update
                    else "No messages found in payload"
                ),
            )

        # Extract message details
        try:
            value = payload["entry"][0]["changes"][0]["value"]
            phone_number_id = value["metadata"]["phone_number_id"]
            from_number = value["messages"][0]["from"]
            sender_name = (
                value.get("contacts", [{}])[0].get("profile", {}).get("name")
                or from_number
            )
        except (KeyError, IndexError, TypeError) as e:
            logging.error(f"Error extracting message details: {e}")
            return WebhookResponse(
                status="invalid_message_format",
                processing_time=time.time() - start_time,
                message="Invalid message format",
            )

        # Process message
        result = await processor.process_message(
            payload, from_number, sender_name, "eng", phone_number_id
        )

        # Handle response
        if result.response_type == ResponseType.SKIP:
            pass
        elif result.response_type == ResponseType.TEMPLATE:
            background_tasks.add_task(
                send_template_response,
                result.template_name,
                phone_number_id,
                from_number,
                sender_name,
            )
        elif result.response_type == ResponseType.BUTTON and result.button_data:
            try:
                if result.button_data.get("interactive_type") == "reply":
                    whatsapp_service.send_reply_button(
                        button=result.button_data.get("payload", {}),
                        phone_number_id=phone_number_id,
                        recipient_id=from_number,
                    )
                else:
                    whatsapp_service.send_button(
                        button=result.button_data,
                        phone_number_id=phone_number_id,
                        recipient_id=from_number,
                    )
            except Exception as e:
                logging.error(f"Error sending button: {e}")
                # Fallback to text message
                whatsapp_service.send_message(
                    recipient_id=from_number,
                    message=(
                        result.message
                        or "I'm having trouble with interactive buttons. Please try typing your request."
                    ),
                    phone_number_id=phone_number_id,
                )
                raise
        elif result.response_type == ResponseType.TEXT and result.message:
            try:
                outbound_message_id = whatsapp_service.send_message(
                    recipient_id=from_number,
                    message=result.message,
                    phone_number_id=phone_number_id,
                    context_message_id=result.reply_to_message_id or None,
                )
                if not outbound_message_id:
                    raise RuntimeError("Failed to send WhatsApp text response")
                if result.should_save and result.user_message:
                    background_tasks.add_task(
                        save_response,
                        from_number,
                        result.user_message,
                        result.message,
                        outbound_message_id,
                    )
                if result.send_tts:
                    background_tasks.add_task(
                        processor.send_tts_audio_response,
                        result.message,
                        result.resolved_target_language,
                        from_number,
                        phone_number_id,
                        result.reply_to_message_id or None,
                    )
                if result.post_template_name:
                    background_tasks.add_task(
                        send_template_response,
                        result.post_template_name,
                        phone_number_id,
                        from_number,
                        sender_name,
                    )
            except Exception as e:
                logging.error(f"Error sending message: {e}")
                raise

        # Log performance
        total_time = time.time() - start_time
        logging.info(
            f"Webhook processed in {total_time:.3f}s (processing: {result.processing_time:.3f}s)"
        )

        return WebhookResponse(
            status="success",
            processing_time=total_time,
        )

    except Exception as error:
        total_time = time.time() - start_time
        logging.error(f"Webhook error after {total_time:.3f}s: {str(error)}")

        # Try to send error message
        try:
            if "from_number" in locals() and "phone_number_id" in locals():
                whatsapp_service.send_message(
                    recipient_id=from_number,
                    message="I'm experiencing technical difficulties. Please try again.",
                    phone_number_id=phone_number_id,
                )
        except Exception:
            pass

        return WebhookResponse(
            status="error",
            processing_time=total_time,
            message=str(error),
        )


@router.get("/webhook")
@router.get("/webhook/")
async def verify_webhook(
    request: Request,
    hub_mode: str = None,
    hub_challenge: str = None,
    hub_verify_token: str = None,
) -> Response:
    """
    Verify webhook endpoint ownership for WhatsApp.

    WhatsApp sends a verification request when you register a webhook URL.
    This endpoint validates the request and returns the challenge string
    to complete the verification process.

    Args:
        request: The incoming HTTP request.
        hub_mode: Should be "subscribe" (query param: hub.mode).
        hub_challenge: Challenge string to echo back (query param: hub.challenge).
        hub_verify_token: Verification token (query param: hub.verify_token).

    Returns:
        Plain text response with the challenge string.

    Raises:
        AuthorizationError: If webhook verification fails.
        BadRequestError: If required parameters are missing.

    Verification Process:
        1. WhatsApp sends GET request with query parameters
        2. Endpoint validates hub.mode == "subscribe"
        3. Endpoint validates hub.verify_token matches configured token
        4. Endpoint returns hub.challenge as plain text response
        5. WhatsApp completes webhook registration

    Example Request:
        GET /tasks/webhook?hub.mode=subscribe&hub.challenge=12345&hub.verify_token=mytoken

    Example Response:
        12345  # Plain text
    """
    # Extract query parameters - WhatsApp uses hub.mode, hub.challenge, hub.verify_token
    mode = request.query_params.get("hub.mode")
    challenge = request.query_params.get("hub.challenge")
    token = request.query_params.get("hub.verify_token")

    # Never log the token values themselves; only whether they were provided.
    logging.info(
        "Webhook verification request - Mode: %s, challenge_present: %s, token_present: %s",
        mode,
        bool(challenge),
        bool(token),
    )

    if mode and token and challenge:
        expected_token = os.getenv("VERIFY_TOKEN") or ""
        # Constant-time comparison to avoid leaking the token via timing.
        token_matches = hmac.compare_digest(token, expected_token)
        if mode != "subscribe" or not token_matches:
            logging.error("Webhook verification failed")
            raise AuthorizationError(message="Webhook verification failed")

        logging.info("WEBHOOK_VERIFIED")
        # WhatsApp expects a plain text response with just the challenge value
        return Response(content=challenge, media_type="text/plain")

    logging.error("Missing required parameters for webhook verification")
    raise BadRequestError(
        message="Missing required parameters for webhook verification"
    )
