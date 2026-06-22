import logging
import os

import httpx
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv()

logger = logging.getLogger(__name__)

# Resend is used here because:
# 1. Google Cloud Run blocks outbound SMTP (ports 25, 465, 587) — Resend communicates
#    exclusively over HTTPS (port 443), which Cloud Run has no restrictions on.
# 2. Resend's permanent free tier (3,000 emails/month, 100/day) does not expire,
#    unlike SendGrid's 60-day trial.
# 3. Resend's API payload is simpler — no nested personalizations array required.
# 4. httpx.AsyncClient is used instead of the official Resend Python SDK because the
#    SDK is synchronous. Calling blocking I/O inside an async FastAPI handler blocks
#    the event loop — httpx.AsyncClient is the correct async approach.
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
MAIL_FROM = os.getenv("MAIL_FROM")
ENVIRONMENT = os.getenv("ENVIRONMENT")
FRONTEND_LOCAL_URL = os.getenv("FRONTEND_LOCAL_URL")
FRONTEND_PRODUCTION_URL = os.getenv("FRONTEND_PRODUCTION_URL")

# Timeout for the Resend API request in seconds.
# Without a timeout, a hung connection would block the request indefinitely.
RESEND_REQUEST_TIMEOUT = 10


async def send_password_reset_email(to_email: str, reset_token: str):
    FRONTEND_URL = FRONTEND_PRODUCTION_URL
    if ENVIRONMENT == "development":
        FRONTEND_URL = FRONTEND_LOCAL_URL

    reset_link = f"{FRONTEND_URL}?token={reset_token}"
    subject = "Password Reset Request"

    # HTML body aligns with the official Resend + FastAPI example which uses the
    # `html` field. A styled reset button is better UX than a plain text link and
    # is less likely to be flagged by spam filters.
    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 480px; margin: 0 auto; padding: 40px 20px;">
      <h2 style="color: #1a1a1a;">Password Reset Request</h2>
      <p style="color: #444;">
        You have requested to reset your password. Click the button below to proceed.
      </p>
      <a href="{reset_link}"
         style="display: inline-block; margin: 24px 0; padding: 12px 24px;
                background-color: #000; color: #fff; text-decoration: none;
                border-radius: 6px; font-weight: bold;">
        Reset Password
      </a>
      <p style="color: #999; font-size: 13px;">
        If you did not request this, please ignore this email. This link will expire shortly.
      </p>
      <p style="color: #999; font-size: 13px;">
        Or copy this link into your browser:<br/>
        <a href="{reset_link}" style="color: #555;">{reset_link}</a>
      </p>
      <hr style="border: none; border-top: 1px solid #eee; margin-top: 32px;" />
      <p style="color: #bbb; font-size: 12px;">SunbirdAI</p>
    </div>
    """

    # In development, print to console instead of sending a real email.
    # This avoids needing a Resend API key locally and keeps the dev feedback loop fast.
    if ENVIRONMENT == "development":
        print(f"Email to: {to_email}")
        print(f"Subject: {subject}")
        print(f"Reset link: {reset_link}")
        return

    # "Name <email>" format is supported by Resend and results in a cleaner
    # sender display in email clients (e.g. "SunbirdAI" instead of a raw address).
    payload = {
        "from": f"SunbirdAI <{MAIL_FROM}>",
        "to": [to_email],
        "subject": subject,
        "html": html_body,
    }

    try:
        # Use an async context manager so the HTTP connection is properly closed
        # after the request completes, even if an exception is raised.
        async with httpx.AsyncClient(timeout=RESEND_REQUEST_TIMEOUT) as client:
            response = await client.post(
                "https://api.resend.com/emails",
                json=payload,
                # Resend authenticates via Bearer token in the Authorization header.
                # The API key must have "Full access" or "Sending access" permission.
                headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            )

            # Handle specific Resend error codes with actionable log messages.
            # Errors are raised as HTTPException so FastAPI returns a clean JSON
            # error response to the caller — aligns with the official Resend + FastAPI
            # example which wraps all failures in HTTPException.
            if response.status_code == 401:
                logger.error(
                    "Resend authentication failed: invalid or missing API key. "
                    "Check the RESEND_API_KEY environment variable."
                )
                raise HTTPException(status_code=500, detail="Failed to send email")

            if response.status_code == 422:
                logger.error(
                    f"Resend rejected the request: {response.text}. "
                    "Verify that MAIL_FROM domain is verified in the Resend dashboard."
                )
                raise HTTPException(status_code=500, detail="Failed to send email")

            if response.status_code == 429:
                logger.error(
                    "Resend rate limit exceeded. "
                    "Free tier allows 100 emails/day and 3,000/month. "
                    "Consider upgrading your Resend plan."
                )
                raise HTTPException(status_code=500, detail="Failed to send email")

            # Raise for any other unexpected 4xx/5xx responses.
            response.raise_for_status()

        logger.info(f"Password reset email sent successfully to {to_email}")

    except HTTPException:
        # Re-raise HTTPExceptions directly — do not wrap in a second HTTPException.
        raise
    except Exception:
        logger.exception("Error sending password reset email")
        raise HTTPException(status_code=500, detail="Failed to send email")
