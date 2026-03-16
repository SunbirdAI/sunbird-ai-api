import os

import httpx
from dotenv import load_dotenv

load_dotenv()

# SendGrid HTTP Web API approach is used here instead of SMTP (fastapi_mail) because
# Google Cloud Run blocks outbound SMTP connections on ports 25, 465, and 587 at the
# network level. Any SMTP-based library (fastapi_mail, smtplib, etc.) will fail with
# "Connection lost" on Cloud Run regardless of credentials or TLS settings.
#
# SendGrid's REST API communicates over HTTPS (port 443), which Cloud Run allows freely.
# Authentication is via an API key in the Authorization header — no SMTP handshake,
# no TLS negotiation over a blocked port.
#
# httpx is already a project dependency, so no new packages are required.
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
MAIL_FROM = os.getenv("MAIL_FROM")
ENVIRONMENT = os.getenv("ENVIRONMENT")
FRONTEND_LOCAL_URL = os.getenv("FRONTEND_LOCAL_URL")
FRONTEND_PRODUCTION_URL = os.getenv("FRONTEND_PRODUCTION_URL")


async def send_password_reset_email(to_email: str, reset_token: str):
    FRONTEND_URL = FRONTEND_PRODUCTION_URL
    if ENVIRONMENT == "development":
        FRONTEND_URL = FRONTEND_LOCAL_URL

    reset_link = f"{FRONTEND_URL}?token={reset_token}"
    subject = "Password Reset Request"
    body = f"""
    Dear User,

    You have requested to reset your password. Please use the following link to reset your password:

    Reset Link: {reset_link}

    If you did not request this, please ignore this email.

    Best regards,
    SunbirdAI
    """

    # In development, print to console instead of sending a real email.
    # This avoids needing a SendGrid key locally and keeps the dev feedback loop fast.
    if ENVIRONMENT == "development":
        print(f"Email to: {to_email}")
        print(f"Subject: {subject}")
        print(f"Body:\n{body}")
        return

    # SendGrid's /v3/mail/send endpoint accepts a JSON payload over HTTPS.
    # The personalizations array supports per-recipient overrides (e.g. dynamic
    # template variables); here we keep it simple with a single recipient.
    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": MAIL_FROM},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body}],
    }

    # Use an async context manager so the HTTP connection is properly closed after
    # the request completes, even if an exception is raised.
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.sendgrid.com/v3/mail/send",
            json=payload,
            # SendGrid authenticates via Bearer token in the Authorization header.
            # The API key must have the "Mail Send" permission scope enabled.
            headers={"Authorization": f"Bearer {SENDGRID_API_KEY}"},
        )
        # Raise immediately on 4xx/5xx so the caller gets a clear error
        # (e.g. 401 Unauthorized if the API key is wrong, 403 if the sender
        # domain is not verified in SendGrid).
        response.raise_for_status()
