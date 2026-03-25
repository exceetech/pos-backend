from datetime import datetime
from app.database import SessionLocal
from app.models.subscription import Subscription

from fastapi_mail import FastMail, MessageSchema
from app.core.config import mail_config


def send_email(email, days_left):

    subject = "Subscription Expiry Alert"

    if days_left <= 0:
        body = "Your subscription has expired."
    else:
        body = f"Your subscription expires in {days_left} days."

    message = MessageSchema(
        subject=subject,
        recipients=[email],
        body=body,
        subtype="plain"
    )

    fm = FastMail(mail_config)
    fm.send_message(message)


def check_subscriptions():

    db = SessionLocal()

    subs = db.query(Subscription).all()

    for sub in subs:

        days_left = (sub.expiry_date - datetime.utcnow()).days

        if days_left in [30, 15, 10, 5, 1]:
            send_email("your_email_here", days_left)

        if days_left <= 0:
            sub.status = "expired"
            send_email("your_email_here", 0)

    db.commit()
    db.close()