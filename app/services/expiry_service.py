from datetime import datetime
from sqlalchemy.orm import Session
from app.models.subscription import Subscription
from app.models.shop import Shop
from app.services.expiry_email import send_expiry_email
from app.firebase_service import send_notification


def check_subscriptions(db: Session):

    subs = db.query(Subscription).all()

    for sub in subs:

        days_left = (sub.expiry_date - datetime.utcnow()).days

        # 🔍 Get shop
        shop = db.query(Shop).filter(Shop.id == sub.shop_id).first()

        if not shop:
            continue

        print(f"📊 Shop: {shop.shop_name} | Days left: {days_left}")

        # ================= 🔔 REMINDER =================
        if days_left in [30, 15, 10, 5, 1]:

            print("🔔 Reminder triggered")

            # 📧 Email
            if shop.email:
                send_expiry_email(shop, days_left)

            # 📲 Push
            if shop.fcm_token:
                send_notification(
                    shop.fcm_token,
                    "⚠️ Subscription Expiry",
                    f"Your plan expires in {days_left} day(s)"
                )

        # ================= ❌ EXPIRED =================
        if days_left <= 0 and sub.status != "expired":

            print("🚫 Expired triggered")

            sub.status = "expired"

            # 📧 Email
            if shop.email:
                send_expiry_email(shop, 0)

            # 📲 Push
            if shop.fcm_token:
                send_notification(
                    shop.fcm_token,
                    "🚫 Subscription Expired",
                    "Your subscription has expired. Please renew."
                )

    db.commit()