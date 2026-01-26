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

import logging
import os
import time

from dotenv import load_dotenv
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response

from app.inference_services.user_preference import get_user_preference
from app.inference_services.whatsapp_service import WhatsAppService
from app.schemas.webhooks import WebhookResponse
from app.services.message_processor import OptimizedMessageProcessor, ResponseType

load_dotenv()
logging.basicConfig(level=logging.INFO)

router = APIRouter()

# Access token for your app
whatsapp_token = os.getenv("WHATSAPP_TOKEN")
verify_token = os.getenv("VERIFY_TOKEN")

whatsapp_service = WhatsAppService(
    token=whatsapp_token, phone_number_id=os.getenv("PHONE_NUMBER_ID")
)

# Initialize processor
processor = OptimizedMessageProcessor()


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
        - custom_feedback: Feedback collection button
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
async def webhook(
    payload: dict,
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

    Args:
        payload: WhatsApp webhook payload.
        background_tasks: FastAPI background tasks for async processing.

    Returns:
        WebhookResponse with processing status and time.

    Response Status Codes:
        - 200: Successfully processed
        - 400: Invalid payload format
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
            return WebhookResponse(
                status="no_messages",
                processing_time=time.time() - start_time,
                message="No messages found in payload",
            )

        # Extract message details
        try:
            phone_number_id = payload["entry"][0]["changes"][0]["value"]["metadata"][
                "phone_number_id"
            ]
            from_number = payload["entry"][0]["changes"][0]["value"]["messages"][0][
                "from"
            ]
            sender_name = payload["entry"][0]["changes"][0]["value"]["contacts"][0][
                "profile"
            ]["name"]
        except (KeyError, IndexError) as e:
            logging.error(f"Error extracting message details: {e}")
            return WebhookResponse(
                status="invalid_message_format",
                processing_time=time.time() - start_time,
                message="Invalid message format",
            )

        # Get user preference
        target_language = get_user_preference(from_number)

        if not target_language:
            target_language = "eng"  # Default to English if no preference set

        # Process message
        result = await processor.process_message(
            payload, from_number, sender_name, target_language, phone_number_id
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
                whatsapp_service.send_button(
                    button=result.button_data,
                    phone_number_id=phone_number_id,
                    recipient_id=from_number,
                )
            except Exception as e:
                logging.error(f"Error sending button: {e}")
                # Fallback to text message
                whatsapp_service.send_message(
                    result.message
                    or "I'm having trouble with interactive buttons. Please try typing your request.",
                    whatsapp_token,
                    from_number,
                    phone_number_id,
                )
        elif result.response_type == ResponseType.TEXT and result.message:
            try:
                whatsapp_service.send_message(
                    result.message, whatsapp_token, from_number, phone_number_id
                )
            except Exception as e:
                logging.error(f"Error sending message: {e}")

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
                    "I'm experiencing technical difficulties. Please try again.",
                    whatsapp_token,
                    from_number,
                    phone_number_id,
                )
        except:
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
        HTTPException: 403 if verification fails, 400 if parameters missing.

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

    logging.info(
        f"Webhook verification request - Mode: {mode}, Challenge: {challenge}, Token: {token}"
    )

    if mode and token and challenge:
        if mode != "subscribe" or token != os.getenv("VERIFY_TOKEN"):
            logging.error(
                f"Webhook verification failed - Expected token: {os.getenv('VERIFY_TOKEN')}, Received: {token}"
            )
            raise HTTPException(status_code=403, detail="Forbidden")

        logging.info("WEBHOOK_VERIFIED")
        # WhatsApp expects a plain text response with just the challenge value
        return Response(content=challenge, media_type="text/plain")

    logging.error("Missing required parameters for webhook verification")
    raise HTTPException(status_code=400, detail="Bad Request")
