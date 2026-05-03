import os
from dotenv import load_dotenv
from fastapi_mail import ConnectionConfig

load_dotenv()

mail_config = ConnectionConfig(
    MAIL_USERNAME=os.getenv("EMAIL_ADDRESS"),
    MAIL_PASSWORD=os.getenv("EMAIL_PASSWORD"),
    MAIL_FROM=os.getenv("EMAIL_ADDRESS"),
    MAIL_PORT=587,
    MAIL_SERVER="smtp.gmail.com",
    MAIL_FROM_NAME="Shop Analytics",
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True
)