import smtplib
import os
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")


def send_email(to_email: str, subject: str, body: str):
    msg = EmailMessage()
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.send_message(msg)


def send_registration_emails(shop):
    # Email to shop owner
    send_email(
        to_email=shop.email,
        subject="Registration Received - POS System",
        body=f"""
Hello {shop.owner_name},

Thank you for registering your shop "{shop.shop_name}".

Our team will contact you soon.

Regards,
eXCee Team
"""
    )

    # Email to admin
    send_email(
        to_email=ADMIN_EMAIL,
        subject="New Shop Registration",
        body=f"""
New shop registered:

Shop Name: {shop.shop_name}
Owner: {shop.owner_name}
Email: {shop.email}
Phone: {shop.phone}
"""
    )