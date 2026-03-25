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

def send_otp_email(shop, otp):
    send_email(
    to_email=shop.email, 
    subject="Password Reset OTP - eXCee POS",
    body=f"""
    Hello {shop.owner_name},

    We received a request to reset your password.

    Your OTP is:

        {otp}

    This OTP is valid for 5 minutes.
    """
        )
    
def send_subscription_email(shop, plan, expiry):
    send_email(
        to_email=shop.email,
        subject="🎉 Subscription Activated Successfully - ExPOS",
        body=f"""
Hello {shop.owner_name},

Your subscription for ExPOS- Smart POS for modern businesses has been successfully activated! 🎉

━━━━━━━━━━━━━━━━━━━━━━━
📦 Subscription Details
━━━━━━━━━━━━━━━━━━━━━━━
🛒 Shop Name : {shop.shop_name}
📅 Plan       : {plan.capitalize()}
⏳ Valid Till : {expiry}

━━━━━━━━━━━━━━━━━━━━━━━
✨ What You Get
━━━━━━━━━━━━━━━━━━━━━━━
✔ Unlimited billing & invoices  
✔ Advanced reports & analytics  
✔ Secure data management  
✔ Priority support  

You can now enjoy all premium features without any interruption.

━━━━━━━━━━━━━━━━━━━━━━━
🔔 Important Reminder
━━━━━━━━━━━━━━━━━━━━━━━
You will receive notifications before your subscription expires, so you never miss a renewal.

If you have any questions or need assistance, feel free to contact our support team anytime.


Thank you for choosing ExPOS to power your business.

Warm regards,  
eXCee Team  
📧 Support: support@expos.in
"""
    )