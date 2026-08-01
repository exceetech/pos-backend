"""
Thin wrapper around the Razorpay SDK. Keeps the secret key and all HMAC
verification logic in one place so no route ever touches the raw secret
or reimplements signature checking.

Env vars required (see .env / deployment config):
  RAZORPAY_KEY_ID       — public, safe to also return to the Android app
  RAZORPAY_KEY_SECRET   — backend-only, NEVER returned in any API response
  RAZORPAY_WEBHOOK_SECRET — separate secret for webhook signature
                            verification; deliberately NOT the same value
                            as RAZORPAY_KEY_SECRET (see verify_webhook_signature)

If these aren't set (e.g. local dev before a Razorpay account exists),
get_client() raises clearly rather than failing with a confusing SDK
error deep inside create_order.
"""
import os
import hmac
import hashlib
from dotenv import load_dotenv

load_dotenv()

_client = None


def get_client():
    global _client
    if _client is not None:
        return _client

    import razorpay

    key_id = os.getenv("RAZORPAY_KEY_ID")
    key_secret = os.getenv("RAZORPAY_KEY_SECRET")
    if not key_id or not key_secret:
        raise RuntimeError(
            "RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET not configured. "
            "Set these env vars before calling any subscription payment endpoint."
        )

    _client = razorpay.Client(auth=(key_id, key_secret))
    return _client


def get_public_key_id() -> str:
    """The only Razorpay credential ever safe to return to the app."""
    key_id = os.getenv("RAZORPAY_KEY_ID")
    if not key_id:
        raise RuntimeError("RAZORPAY_KEY_ID not configured.")
    return key_id


def create_razorpay_order(amount_paise: int, receipt: str, notes: dict) -> dict:
    """
    amount_paise must already be the FINAL, server-computed price (see
    subscription_payment_routes.create_order) — this function does not
    apply any discount logic itself, it only talks to Razorpay.
    """
    client = get_client()
    return client.order.create({
        "amount": amount_paise,
        "currency": "INR",
        "receipt": receipt,
        "notes": notes,
        "payment_capture": 1,
    })


def verify_payment_signature(razorpay_order_id: str, razorpay_payment_id: str, razorpay_signature: str) -> bool:
    """
    The actual proof a payment happened — recomputes the HMAC using the
    backend-only secret and compares against what the client reported.
    This is the check that must pass before any Subscription is
    activated; a client-side "success" callback alone proves nothing.
    """
    key_secret = os.getenv("RAZORPAY_KEY_SECRET")
    if not key_secret:
        raise RuntimeError("RAZORPAY_KEY_SECRET not configured.")

    payload = f"{razorpay_order_id}|{razorpay_payment_id}"
    expected_signature = hmac.new(
        key_secret.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected_signature, razorpay_signature)


def verify_webhook_signature(raw_body: bytes, received_signature: str) -> bool:
    """
    Independent from verify_payment_signature above — uses
    RAZORPAY_WEBHOOK_SECRET (set separately in the Razorpay dashboard
    webhook config), not RAZORPAY_KEY_SECRET. Skipping this check would
    let anyone who discovers the webhook URL POST a fake "payment
    succeeded" event and get a subscription activated for free.
    """
    webhook_secret = os.getenv("RAZORPAY_WEBHOOK_SECRET")
    if not webhook_secret:
        raise RuntimeError("RAZORPAY_WEBHOOK_SECRET not configured.")

    expected_signature = hmac.new(
        webhook_secret.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected_signature, received_signature)
