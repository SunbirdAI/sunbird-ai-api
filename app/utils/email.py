import os

from dotenv import load_dotenv
from fastapi_mail import ConnectionConfig, FastMail, MessageSchema

load_dotenv()

SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
MAIL_FROM = os.getenv("MAIL_FROM")
ENVIRONMENT = os.getenv("ENVIRONMENT")
FRONTEND_LOCAL_URL = os.getenv("FRONTEND_LOCAL_URL")
FRONTEND_PRODUCTION_URL = os.getenv("FRONTEND_PRODUCTION_URL")

# Fastapi-mail configuration
conf = ConnectionConfig(
    MAIL_USERNAME=SMTP_USERNAME,
    MAIL_PASSWORD=SMTP_PASSWORD,
    MAIL_FROM=MAIL_FROM,
    MAIL_PORT=SMTP_PORT,
    MAIL_SERVER=SMTP_SERVER,
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=True,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True,
)


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

    message = MessageSchema(
        subject=subject,
        recipients=[to_email],  # List of recipients
        body=body,
        subtype="plain",
    )

    fm = FastMail(conf)
    if ENVIRONMENT == "development":
        print(f"Email to: {to_email}")
        print(f"Subject: {subject}")
        print(f"Body:\n{body}")
    else:
        await fm.send_message(message)
