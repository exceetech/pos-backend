from datetime import datetime
from app.util.time_utils import utc_now
from sqlalchemy.orm import Session
from app.models.subscription import Subscription
from app.models.shop import Shop
from app.services.expiry_email import send_expiry_email
from app.firebase_service import send_notification


def check_subscriptions(db: Session):

    subs = db.query(Subscription).all()

    for sub in subs:

        days_left = (sub.expiry_date - utc_now()).days

        # 🔍 Get shop
        shop = db.query(Shop).filter(Shop.id == sub.shop_id).first()

        if not shop:
            continue

        print(f"📊 Shop: {shop.shop_name} | Days left: {days_left}")

        # Captured BEFORE the status flip below, so the "expired" branch
        # can still tell whether this was a trial ending vs. a paid plan
        # lapsing (plan §4.6) — sub.status gets overwritten to "expired"
        # a few lines down.
        was_trial = sub.status == "trial"

        # ================= 🔔 REMINDER =================
        if days_left in [30, 15, 10, 5, 1]:

            print("🔔 Reminder triggered")

            # 📧 Email
            if shop.email:
                send_expiry_email(shop, days_left, is_trial=was_trial)

            # 📲 Push
            if shop.fcm_token:
                send_notification(
                    shop.fcm_token,
                    "🎉 Trial Ending Soon" if was_trial else "⚠️ Subscription Expiry",
                    f"Your {'trial' if was_trial else 'plan'} expires in {days_left} day(s)"
                )

        # ================= ❌ EXPIRED =================
        if days_left <= 0 and sub.status != "expired":

            print("🚫 Expired triggered")

            sub.status = "expired"

            # 📧 Email
            if shop.email:
                send_expiry_email(shop, 0, is_trial=was_trial)

            # 📲 Push
            if shop.fcm_token:
                send_notification(
                    shop.fcm_token,
                    "Trial Ended" if was_trial else "🚫 Subscription Expired",
                    "Your free trial has ended." if was_trial else "Your subscription has expired. Please renew."
                )

    db.commit()