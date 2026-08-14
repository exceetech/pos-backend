"""
Thin wrapper around the Razorpay SDK. Keeps the secret key and all HMAC
verification logic in one place so no route ever touches the raw secret
or reimplements signature checking.

Test mode / live mode (2026-08-14)
-----------------------------------
Both a test credential set and a live credential set can be configured
at the same time; RAZORPAY_MODE picks which one is actually used. This
means going live — or going back to testing — is a single env var
change, not editing secrets in and out of the same three variables by
hand (which is easy to fumble mid-deploy).

Env vars required (see .env / deployment config):
  RAZORPAY_MODE                — "test" or "live". Defaults to "test" if
                                  unset, so a missing/misconfigured env
                                  var can never accidentally enable live
                                  charges.

  RAZORPAY_TEST_KEY_ID          — public, safe to also return to the app
  RAZORPAY_TEST_KEY_SECRET      — backend-only, NEVER returned in any API response
  RAZORPAY_TEST_WEBHOOK_SECRET  — separate secret for webhook signature
                                   verification, set in the Razorpay
                                   dashboard's TEST-mode webhook config

  RAZORPAY_LIVE_KEY_ID          — same three, for LIVE mode. Get these
  RAZORPAY_LIVE_KEY_SECRET        from Razorpay's dashboard with "Live
  RAZORPAY_LIVE_WEBHOOK_SECRET    Mode" toggled on (top-right switch).
                                   The live webhook must be registered
                                   separately from the test webhook, even
                                   though it points at the same URL.

Backward compatibility: if the mode-specific vars aren't set, this falls
back to the old unprefixed RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET /
RAZORPAY_WEBHOOK_SECRET (treated as whichever mode RAZORPAY_MODE says),
so an existing .env doesn't break the moment this ships.

Safety check: Razorpay key ids always start with "rzp_test_" or
"rzp_live_". get_client() verifies the configured key id's prefix
actually matches RAZORPAY_MODE and refuses to start if they disagree —
e.g. a live key pasted into the test slot while RAZORPAY_MODE=test would
otherwise silently take real payments while everyone believes it's a
test. This check is what turns that mistake into a loud startup error
instead of a quiet one discovered via a customer's bank statement.

If none of this is set (e.g. local dev before a Razorpay account
exists), get_client() raises clearly rather than failing with a
confusing SDK error deep inside create_order.
"""
import logging
import os
import hmac
import hashlib
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_client = None
_active_mode = None  # set the first time get_client()/_credentials() runs


def _mode() -> str:
    mode = os.getenv("RAZORPAY_MODE", "test").strip().lower()
    if mode not in ("test", "live"):
        raise RuntimeError(
            f"RAZORPAY_MODE={mode!r} is invalid — must be exactly 'test' or 'live'."
        )
    return mode


def _credentials() -> tuple[str, str, str, str]:
    """Returns (mode, key_id, key_secret, webhook_secret) for the active mode."""
    mode = _mode()
    prefix = "RAZORPAY_LIVE_" if mode == "live" else "RAZORPAY_TEST_"

    key_id = os.getenv(f"{prefix}KEY_ID") or os.getenv("RAZORPAY_KEY_ID")
    key_secret = os.getenv(f"{prefix}KEY_SECRET") or os.getenv("RAZORPAY_KEY_SECRET")
    webhook_secret = os.getenv(f"{prefix}WEBHOOK_SECRET") or os.getenv("RAZORPAY_WEBHOOK_SECRET")

    if not key_id or not key_secret:
        raise RuntimeError(
            f"Razorpay {mode} credentials not configured. Set "
            f"{prefix}KEY_ID / {prefix}KEY_SECRET (or the legacy "
            "RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET as a fallback)."
        )

    expected_key_prefix = f"rzp_{mode}_"
    if not key_id.startswith(expected_key_prefix):
        raise RuntimeError(
            f"RAZORPAY_MODE={mode!r} but the configured key id {key_id!r} does not "
            f"start with {expected_key_prefix!r}. Refusing to start — this usually "
            f"means a {'live' if mode == 'test' else 'test'} key was pasted into the "
            f"{mode} slot by mistake. Double-check {prefix}KEY_ID."
        )

    return mode, key_id, key_secret, webhook_secret


def get_client():
    global _client, _active_mode
    if _client is not None:
        return _client

    import razorpay

    mode, key_id, key_secret, _ = _credentials()
    _client = razorpay.Client(auth=(key_id, key_secret))
    _active_mode = mode
    logger.info("Razorpay client initialized in %s mode (key_id=%s).", mode.upper(), key_id)
    return _client


def get_public_key_id() -> str:
    """The only Razorpay credential ever safe to return to the app."""
    _, key_id, _, _ = _credentials()
    return key_id


def get_active_mode() -> str:
    """'test' or 'live' — whatever RAZORPAY_MODE currently resolves to."""
    return _mode()


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
    _, _, key_secret, _ = _credentials()

    payload = f"{razorpay_order_id}|{razorpay_payment_id}"
    expected_signature = hmac.new(
        key_secret.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected_signature, razorpay_signature)


def verify_webhook_signature(raw_body: bytes, received_signature: str) -> bool:
    """
    Independent from verify_payment_signature above — uses the active
    mode's webhook secret (set separately in the Razorpay dashboard's
    webhook config, TEST and LIVE each have their own), not the key
    secret. Skipping this check would let anyone who discovers the
    webhook URL POST a fake "payment succeeded" event and get a
    subscription activated for free.
    """
    _, _, _, webhook_secret = _credentials()
    if not webhook_secret:
        raise RuntimeError("RAZORPAY_WEBHOOK_SECRET not configured.")

    expected_signature = hmac.new(
        webhook_secret.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected_signature, received_signature)
