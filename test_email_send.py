import sys
import os

# Add app folder to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.email_service import send_registration_emails, send_otp_email, send_subscription_email
from app.services.expiry_email import send_expiry_email

class MockShop:
    def __init__(self, shop_name="Royal Bakers", owner_name="Farhan Adeeb", email="test@example.com", phone="+91 9876543210"):
        self.shop_name = shop_name
        self.owner_name = owner_name
        self.email = email
        self.phone = phone
        self.store_gstin = "32AABCS1429B1Z8"

if __name__ == "__main__":
    to_email = sys.argv[1] if len(sys.argv) > 1 else None
    email_type = sys.argv[2] if len(sys.argv) > 2 else "welcome"

    if not to_email:
        print("Usage: python3 test_email_send.py <your_email@gmail.com> <type>")
        print("Types: welcome | otp | base_active | base_expired | premium_active | premium_expired | trial_warning | trial_expired")
        sys.exit(1)

    shop = MockShop(email=to_email)

    if email_type == "welcome":
        print(f"Sending test Registration Welcome & Admin Alert emails to: {to_email} ...")
        send_registration_emails(shop)

    elif email_type == "otp":
        print(f"Sending test OTP Verification email to: {to_email} ...")
        send_otp_email(shop, "849201")

    elif email_type in ("base_active", "base_activated", "subscription_base"):
        print(f"Sending test Base Plan Activated email to: {to_email} ...")
        send_subscription_email(shop, "Base Plan (Monthly)", "13 September 2026")

    elif email_type in ("premium_active", "subscription_premium", "subscription"):
        print(f"Sending test Premium Plan Activated email to: {to_email} ...")
        send_subscription_email(shop, "Premium Annual Plan", "13 August 2027")

    elif email_type in ("trial_warning", "trial_ending"):
        print(f"Sending test Trial Ending Warning email (3 days left) to: {to_email} ...")
        send_expiry_email(shop, days_left=3, is_trial=True)

    elif email_type in ("trial_expired", "base_expired"):
        print(f"Sending test Free Trial / Base Plan Expired email to: {to_email} ...")
        send_expiry_email(shop, days_left=0, is_trial=True)

    elif email_type in ("premium_warning", "expiry_warning"):
        print(f"Sending test Paid Plan Expiry Warning email (3 days left) to: {to_email} ...")
        send_expiry_email(shop, days_left=3, is_trial=False)

    elif email_type in ("premium_expired", "expiry_expired", "expiry"):
        print(f"Sending test Paid Subscription Expired email to: {to_email} ...")
        send_expiry_email(shop, days_left=0, is_trial=False)

    else:
        print(f"Unknown email type '{email_type}'. Sending Base Plan Activated email...")
        send_subscription_email(shop, "Base Plan", "13 September 2026")

    print("✅ Email sent successfully! Check your inbox / spam folder.")
