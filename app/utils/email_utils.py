from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
import os
from dotenv import load_dotenv
load_dotenv()


conf = ConnectionConfig(
    MAIL_USERNAME=os.getenv("MAIL_USERNAME"),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD"),
    MAIL_FROM=os.getenv("MAIL_FROM"),
    MAIL_PORT=int(os.getenv("MAIL_PORT")),
    MAIL_SERVER=os.getenv("MAIL_SERVER"),
    MAIL_FROM_NAME=os.getenv("MAIL_FROM_NAME"),
    MAIL_TLS=os.getenv("MAIL_TLS") == 'True',
    MAIL_SSL=os.getenv("MAIL_SSL") == 'True',
    USE_CREDENTIALS=os.getenv("USE_CREDENTIALS") == 'True',
    VALIDATE_CERTS=os.getenv("VALIDATE_CERTS") == 'True',
)



async def send_password_reset_email(email: str, token: str):
    api_domain = os.getenv("ApiDomain")
    
    if api_domain is None:
        raise ValueError("Environment variable 'Apidomain' is not set.")
    
    reset_link = api_domain + "/get-user-by-token?" + token
    message = MessageSchema(
        subject="Password Reset Request",
        recipients=[email],
        body=f"Please use the following link to reset your password: {reset_link}",
        subtype="html"
    )
    fm = FastMail(conf)
    await fm.send_message(message)
