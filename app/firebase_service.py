import logging
import os
import firebase_admin
from firebase_admin import credentials, messaging

logger = logging.getLogger(__name__)

# ✅ Initialize Firebase ONLY ONCE
#
# Credentials path is overridable via FIREBASE_KEY_PATH (2026-08-15).
# In production, this secret is mounted by Cloud Run as a file — but it
# must NOT be mounted anywhere under app/, since Cloud Run mounts a
# secret file by creating a volume at the file's *parent directory*,
# which would silently replace the entire app/ package (main.py,
# routes/, everything) with just this one file. Mount it to a separate
# path instead (e.g. /secrets/firebase-key.json) and set
# FIREBASE_KEY_PATH to match. Defaults to the original local-dev path
# when unset, so nothing changes for local development.
_firebase_key_path = os.getenv("FIREBASE_KEY_PATH", "app/firebase-key.json")
cred = credentials.Certificate(_firebase_key_path)

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