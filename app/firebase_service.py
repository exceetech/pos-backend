import logging
import firebase_admin
from firebase_admin import credentials, messaging

logger = logging.getLogger(__name__)

# ✅ Initialize Firebase ONLY ONCE
cred = credentials.Certificate("app/firebase-key.json")

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)


# ================= SINGLE NOTIFICATION =================
def send_notification(token: str, title: str, body: str):

    # Not logging the raw token — it's a per-device credential, same
    # class of sensitivity as a session token.
    logger.info("Sending push notification: %s", title)

    message = messaging.Message(
        data={   # ✅ IMPORTANT: use DATA
            "title": title,
            "body": body
        },
        token=token
    )

    response = messaging.send(message)

    logger.info("Push sent: %s", response)


# ================= BROADCAST =================
def send_broadcast(tokens: list[str], title: str, body: str):

    if not tokens:
        logger.warning("send_broadcast called with no tokens")
        return

    logger.info("Broadcasting '%s' to %d device(s)", title, len(tokens))

    message = messaging.MulticastMessage(
        data={   # ✅ IMPORTANT: use DATA
            "title": title,
            "body": body
        },
        tokens=tokens
    )

    response = messaging.send_each_for_multicast(message)

    logger.info("Broadcast success=%d failure=%d", response.success_count, response.failure_count)