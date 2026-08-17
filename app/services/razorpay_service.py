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


def get_client_for_shop(key_id: str, key_secret: str):
    """
    A Razorpay client built from a SHOP's own credentials — never the
    global RAZORPAY_TEST_*/RAZORPAY_LIVE_* env vars get_client() uses.
    Used exclusively by the "send to customer" POS payment-link flow
    (pos_payment_routes.py), so each shop's customer payments land in
    that shop's own Razorpay account/bank account, not a shared one.

    A fresh client per call (no caching like get_client()'s singleton) —
    correct here since the credentials vary per shop per request, unlike
    get_client() where the whole process only ever runs as one mode.
    """
    import razorpay

    return razorpay.Client(auth=(key_id, key_secret))


def create_payment_link(
    amount_paise: int,
    reference_id: str,
    description: str,
    shop_key_id: str,
    shop_key_secret: str,
    customer_name: str | None = None,
    customer_contact: str | None = None,
    notes: dict | None = None,
) -> dict:
    """
    Razorpay Payment Links — distinct from create_razorpay_order() above.
    Orders are for the app's own in-app checkout (client-side Razorpay
    Checkout SDK, needs a razorpay_order_id + key_id in the app). Payment
    Links are a hosted page Razorpay serves at a short URL — exactly what
    "send the customer a link to pay" needs, since nothing about
    collecting payment runs inside the POS app or the customer's device.

    Always uses the CALLING SHOP's own Razorpay credentials (shop_key_id
    / shop_key_secret, from that shop's BillingSettings row) — never the
    platform's global test/live account — so the payment deposits into
    that shop's own account.

    reference_id is set to the bill number — pos_payment_routes.webhook
    looks the bill back up by matching on this, so it must be unique per
    bill (bills.bill_number already is).

    upi_link: True makes this a UPI Payment Link instead of a regular
    one — the customer taps the link and goes straight to their phone's
    installed UPI apps (GPay/PhonePe/Paytm/...) to pay, skipping
    Razorpay's regular checkout page (which shows a full payment-method
    picker: UPI/cards/netbanking/wallets) entirely. Same payment_link
    entity, same "payment_link.paid" webhook event on completion — the
    webhook handler in pos_payment_routes.py needs no changes for this.
    One real constraint: Razorpay does not support UPI Payment Links in
    Test Mode, only Live — a shop's key_id tells us which one we're
    calling with (rzp_test_... vs rzp_live_...), so upi_link is only set
    for a live key. This isn't a workaround, it's required: sending
    upi_link=True on a test key would just make Razorpay reject the
    call outright. A shop still on test keys (no live account/KYC yet)
    gets the exact same regular payment link this used to always create
    — full method-picker checkout page — so the whole rest of the send-
    to-customer pipeline (link creation, SMS delivery, the
    payment_link.paid webhook, the bill flipping to "paid") stays fully
    testable with zero real money: Razorpay's test mode lets you
    complete a payment on that checkout page using its documented test
    UPI VPA (success@razorpay) or test card numbers, which simulates a
    real successful payment without moving money. Once a shop switches
    to live keys, this function automatically starts creating one-click
    UPI links — no code change needed then either.
    """
    is_live_key = shop_key_id.startswith("rzp_live_")

    client = get_client_for_shop(shop_key_id, shop_key_secret)
    payload = {
        "amount": amount_paise,
        "currency": "INR",
        "description": description,
        "reference_id": reference_id,
        "notes": notes or {},
    }
    if is_live_key:
        payload["upi_link"] = True
    if customer_name or customer_contact:
        payload["customer"] = {
            "name": customer_name or "",
            "contact": customer_contact or "",
        }
        # Razorpay auto-sends its own SMS/WhatsApp to the customer when a
        # contact is attached — we don't want that (the app sends its own
        # message with the invoice PDF), just the link back for the app
        # to include in its own share.
        payload["notify"] = {"sms": False, "email": False}
    return client.payment_link.create(payload)


def cancel_payment_link(link_id: str, shop_key_id: str, shop_key_secret: str) -> None:
    """
    Closes a still-open Payment Link so it can no longer be paid — used
    when the SAME bill's QR code gets paid first, so the two payment
    methods can never both succeed for one sale. Razorpay 400s if the
    link is already paid/expired/cancelled; that's fine, it means
    there's nothing left to cancel, not a real error.
    """
    client = get_client_for_shop(shop_key_id, shop_key_secret)
    try:
        client.payment_link.cancel(link_id)
    except Exception:
        logger.info("cancel_payment_link: link %s already closed/paid/expired, nothing to do", link_id)


def create_upi_qr_code(
    amount_paise: int,
    bill_number: str,
    shop_key_id: str,
    shop_key_secret: str,
    close_by_seconds: int = 1200,
) -> dict:
    """
    A UPI QR Code — distinct from create_payment_link above. The
    customer scans it with whatever UPI app they already have open
    (no link to tap, no SMS, no phone number needed at all), which is
    exactly what an in-person "show the screen, they scan, done" retail
    payment needs. This is the piece that makes automatic paid/pending
    tracking work even on a device with no SIM card — nothing about
    displaying a QR code on screen requires sending anything anywhere.

    single_use + fixed_amount=True: this QR is for exactly ONE sale, for
    exactly this bill's amount — it closes itself the moment it's paid,
    and can't be reused for a different amount. close_by (default 20
    minutes from creation) additionally auto-expires it even if never
    paid, since it's meant for "pay right now while standing at the
    counter," not something that should still be scannable hours later.

    Same shop-owned-credentials model as create_payment_link: always
    uses the CALLING SHOP's own Razorpay keys, so payments land in that
    shop's own account. Razorpay fires a "qr_code.credited" webhook on
    payment — see pos_payment_routes.webhook for how that's matched
    back to this bill (by the QR's own id, since QR codes don't carry a
    reference_id the way Payment Links do).
    """
    import time

    client = get_client_for_shop(shop_key_id, shop_key_secret)
    payload = {
        "type": "upi_qr",
        "name": f"Invoice {bill_number}",
        "usage": "single_use",
        "fixed_amount": True,
        "payment_amount": amount_paise,
        "description": f"Payment for invoice {bill_number}",
        "close_by": int(time.time()) + close_by_seconds,
        "notes": {"bill_number": bill_number},
    }
    return client.qrcode.create(payload)


def close_qr_code(qr_id: str, shop_key_id: str, shop_key_secret: str) -> None:
    """
    Mirrors cancel_payment_link — closes a still-open QR code, used when
    the SAME bill's Payment Link gets paid first instead, so the QR
    can't also be scanned and paid a second time for the same sale.
    """
    client = get_client_for_shop(shop_key_id, shop_key_secret)
    try:
        client.qrcode.close(qr_id)
    except Exception:
        logger.info("close_qr_code: qr %s already closed/paid/expired, nothing to do", qr_id)


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


def verify_webhook_signature_with_secret(raw_body: bytes, received_signature: str, webhook_secret: str) -> bool:
    """
    Same HMAC check as verify_webhook_signature above, but against an
    EXPLICIT secret rather than the platform's global one — used by
    pos_payment_routes.webhook, where each shop's own Razorpay account
    signs its webhook deliveries with that shop's own webhook secret
    (from BillingSettings.razorpay_webhook_secret), not the platform's.
    """
    if not webhook_secret:
        return False
    expected_signature = hmac.new(
        webhook_secret.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected_signature, received_signature)
