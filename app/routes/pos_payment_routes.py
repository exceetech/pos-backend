"""
"Send to customer" flow — a UPI payment link (via Razorpay Payment
Links, see app/services/razorpay_service.create_payment_link) plus a
temporary, publicly-fetchable URL for the invoice PDF the app already
generated locally. The app shares both through WhatsApp/SMS; nothing in
this file sends any message itself.

TRUST BOUNDARY / MULTI-TENANCY: every payment link is created with the
CALLING SHOP's own Razorpay credentials (BillingSettings.razorpay_key_id
/ razorpay_key_secret) — never a shared platform account. This means
customer payments deposit directly into that shop's own bank account.
The webhook below mirrors that: since each shop's Razorpay account signs
its own webhook deliveries with that shop's own webhook secret, the
right secret has to be looked up (via the bill the event references)
BEFORE the signature can even be checked — see webhook() for exactly how
that stays safe.

PDF storage is deliberately local-disk-only and short-lived: files are
swept _PDF_TTL_SECONDS after creation, whether or not they were ever
fetched. (Earlier version deleted a file the instant it was served
once — that broke real customer taps, because most SMS/RCS apps
silently pre-fetch a link to build a preview the moment the message
arrives, consuming the one-time link before the customer ever tapped
it. So: TTL-only now, not single-use.) This still trades some
reliability on Cloud Run — a request that lands on a different
instance than the one that saved the file will 404 — for zero storage
cost, which was an explicit, informed choice. If that 404 rate ever
becomes a real problem, replace _PDF_DIR with a Cloud Storage bucket;
nothing else in this file would need to change, the token-based URL
scheme stays the same.
"""
import json
import logging
import os
import re
import tempfile
import time
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_shop
from app.models.bill import Bill
from app.models.billing_settings import BillingSettings
from app.models.processed_webhook_event import ProcessedWebhookEvent
from app.services import razorpay_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pos-payments", tags=["POS Payments"])

_PDF_DIR = os.path.join(tempfile.gettempdir(), "pos_invoice_pdfs")
_PDF_TTL_SECONDS = 30 * 60  # orphaned files (link never opened) are swept after 30 min
_TOKEN_RE = re.compile(r"^[a-f0-9]{32}$")


def _sweep_stale_pdfs() -> None:
    """Best-effort cleanup of files nobody ever fetched — no scheduler
    needed, this runs inline on every upload since uploads are frequent
    enough (every "send to customer" tap) to keep the directory small."""
    if not os.path.isdir(_PDF_DIR):
        return
    cutoff = time.time() - _PDF_TTL_SECONDS
    for name in os.listdir(_PDF_DIR):
        path = os.path.join(_PDF_DIR, name)
        try:
            if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                os.remove(path)
        except OSError:
            pass


class CreatePaymentLinkRequest(BaseModel):
    customer_name: str | None = None
    customer_phone: str | None = None


class CreatePaymentLinkResponse(BaseModel):
    payment_link_id: str
    payment_link_url: str


class UploadPdfResponse(BaseModel):
    pdf_url: str


def _get_owned_bill(bill_number: str, db: Session, current_shop) -> Bill:
    # Keyed on bill_number, not a local id — the Android app's local Room
    # `Bill.id` is never the server's bill id, only bill_number is a
    # reliable cross-system key (same reason /bills/cancellations and
    # /bills/payment-status match on it instead of id).
    bill = db.query(Bill).filter(Bill.bill_number == bill_number, Bill.shop_id == current_shop.id).first()
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    return bill


@router.post("/{bill_number}/create-link", response_model=CreatePaymentLinkResponse)
def create_link(
    bill_number: str,
    body: CreatePaymentLinkRequest,
    db: Session = Depends(get_db),
    current_shop=Depends(get_current_shop),
):
    bill = _get_owned_bill(bill_number, db, current_shop)

    settings = db.query(BillingSettings).filter(BillingSettings.shop_id == current_shop.id).first()
    if not settings or not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise HTTPException(
            status_code=400,
            detail="Connect your Razorpay account in Billing Settings before sending a payment link.",
        )

    # Reuse an existing, still-unpaid link rather than spawning a new
    # Razorpay link every time the cashier reopens the send sheet for
    # the same bill.
    if bill.razorpay_payment_link_url and bill.payment_status != "paid":
        return CreatePaymentLinkResponse(
            payment_link_id=bill.razorpay_payment_link_id,
            payment_link_url=bill.razorpay_payment_link_url,
        )

    amount_paise = int(round(float(bill.final_amount) * 100))
    if amount_paise <= 0:
        raise HTTPException(status_code=400, detail="Bill amount must be greater than zero")

    try:
        link = razorpay_service.create_payment_link(
            amount_paise=amount_paise,
            reference_id=bill.bill_number,
            description=f"Payment for invoice {bill.bill_number}",
            shop_key_id=settings.razorpay_key_id,
            shop_key_secret=settings.razorpay_key_secret,
            customer_name=body.customer_name,
            customer_contact=body.customer_phone,
            notes={"shop_id": str(current_shop.id), "bill_id": str(bill.id)},
        )
    except Exception:
        logger.exception("Razorpay payment link creation failed for bill %s", bill.id)
        raise HTTPException(
            status_code=502,
            # UPI Payment Links (upi_link=True, see razorpay_service) are
            # a common cause here specifically: Razorpay rejects them
            # outright in Test Mode, only Live Mode keys work. A key/
            # secret typo would also land here, hence the second half.
            detail=(
                "Could not create payment link — if your Billing Settings Razorpay "
                "keys are Test Mode keys, switch to Live Mode keys (UPI payment "
                "links aren't supported in Test Mode). Otherwise check the keys are correct."
            ),
        )

    bill.razorpay_payment_link_id = link["id"]
    bill.razorpay_payment_link_url = link["short_url"]
    db.commit()

    return CreatePaymentLinkResponse(
        payment_link_id=link["id"],
        payment_link_url=link["short_url"],
    )


class CreateQrCodeResponse(BaseModel):
    qr_code_id: str
    qr_image_url: str
    close_by: int | None = None


@router.post("/{bill_number}/create-qr", response_model=CreateQrCodeResponse)
def create_qr(
    bill_number: str,
    db: Session = Depends(get_db),
    current_shop=Depends(get_current_shop),
):
    """
    Scan-to-pay in-person alternative to create-link — see
    razorpay_service.create_upi_qr_code's doc comment for why this
    exists and how it stays mutually exclusive with a payment link for
    the same bill.
    """
    bill = _get_owned_bill(bill_number, db, current_shop)

    settings = db.query(BillingSettings).filter(BillingSettings.shop_id == current_shop.id).first()
    if not settings or not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise HTTPException(
            status_code=400,
            detail="Connect your Razorpay account in Billing Settings before showing a QR code.",
        )

    # Reuse an existing, still-open QR rather than spawning a new one
    # every time the invoice screen is reopened for the same bill — but
    # ONLY if Razorpay hasn't already auto-closed it. Razorpay kills every
    # QR at its own close_by regardless of what this app does, so reusing
    # past that moment would hand back a dead code that can never be
    # scanned/paid again.
    qr_still_live = (
        bill.razorpay_qr_close_by is not None
        and int(time.time()) < bill.razorpay_qr_close_by
    )
    if bill.razorpay_qr_id and bill.razorpay_qr_image_url and bill.payment_status != "paid" and qr_still_live:
        return CreateQrCodeResponse(
            qr_code_id=bill.razorpay_qr_id,
            qr_image_url=bill.razorpay_qr_image_url,
            close_by=bill.razorpay_qr_close_by,
        )

    amount_paise = int(round(float(bill.final_amount) * 100))
    if amount_paise <= 0:
        raise HTTPException(status_code=400, detail="Bill amount must be greater than zero")

    try:
        qr = razorpay_service.create_upi_qr_code(
            amount_paise=amount_paise,
            bill_number=bill.bill_number,
            shop_key_id=settings.razorpay_key_id,
            shop_key_secret=settings.razorpay_key_secret,
        )
    except Exception:
        logger.exception("Razorpay QR code creation failed for bill %s", bill.id)
        raise HTTPException(
            status_code=502,
            detail="Could not create a QR code — check that your Razorpay API keys in Billing Settings are correct.",
        )

    bill.razorpay_qr_id = qr["id"]
    bill.razorpay_qr_image_url = qr["image_url"]
    bill.razorpay_qr_close_by = qr.get("close_by")
    db.commit()

    return CreateQrCodeResponse(qr_code_id=qr["id"], qr_image_url=qr["image_url"], close_by=qr.get("close_by"))


class MarkPaidResponse(BaseModel):
    payment_status: str


@router.post("/{bill_number}/mark-paid", response_model=MarkPaidResponse)
def mark_paid(
    bill_number: str,
    db: Session = Depends(get_db),
    current_shop=Depends(get_current_shop),
):
    """
    Manual override for the cashier — used when a customer has genuinely
    paid (confirmed by looking at their own UPI app / the Razorpay
    dashboard) but the webhook hasn't landed for some reason (local dev
    network issue, delivery delay, webhook misconfigured, etc.). This is
    a trusted, authenticated shop action on their OWN bill — not a
    payment-verification path, so it deliberately does NOT touch
    razorpay_payment_id (there's no real payment id to record) and does
    NOT require Razorpay credentials to be configured at all.
    """
    bill = _get_owned_bill(bill_number, db, current_shop)

    if bill.payment_status != "paid":
        bill.payment_status = "paid"
        db.commit()

    return MarkPaidResponse(payment_status=bill.payment_status)


@router.post("/{bill_number}/upload-pdf", response_model=UploadPdfResponse)
def upload_pdf(
    bill_number: str,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_shop=Depends(get_current_shop),
):
    # Confirms the bill belongs to this shop before accepting the file —
    # otherwise any authenticated shop could upload a PDF "for" another
    # shop's bill.
    _get_owned_bill(bill_number, db, current_shop)

    _sweep_stale_pdfs()
    os.makedirs(_PDF_DIR, exist_ok=True)

    token = uuid.uuid4().hex
    path = os.path.join(_PDF_DIR, f"{token}.pdf")
    with open(path, "wb") as out:
        out.write(file.file.read())

    pdf_url = f"{str(request.base_url).rstrip('/')}/pos-payments/pdf/{token}"
    return UploadPdfResponse(pdf_url=pdf_url)


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    """
    Multi-tenant webhook — one URL, but each shop's Razorpay account
    signs its deliveries with THAT shop's own webhook secret, not a
    platform-wide one. So the order here is deliberate and safety-
    critical: reference_id (== bill_number, untrusted at this point) is
    used ONLY to look up which shop's secret to try; nothing from the
    payload is acted on until verify_webhook_signature_with_secret
    passes against that specific shop's real secret. A forged bill
    number just means verification fails against the real shop's real
    secret — the attacker never had it, so nothing happens.

    Registered by each shop individually in THEIR OWN Razorpay
    dashboard, pointed at this same URL, with the same secret they saved
    in Billing Settings.
    """
    raw_body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    try:
        payload = json.loads(raw_body)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")

    event_type = payload.get("event")
    if event_type not in ("payment_link.paid", "qr_code.credited"):
        # Any other event type from a shop's account isn't something this
        # endpoint acts on — accepted-but-ignored rather than a 400, so
        # Razorpay doesn't keep retrying a delivery this URL will never want.
        return {"status": "ignored"}

    is_qr_event = event_type == "qr_code.credited"

    if is_qr_event:
        # QR codes don't carry a reference_id the way Payment Links do —
        # matched back to the bill by the QR entity's own id instead,
        # which create_qr() saved on the bill at creation time.
        qr_entity = payload.get("payload", {}).get("qr_code", {}).get("entity", {})
        payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
        qr_id = qr_entity.get("id")
        rp_payment_id = payment_entity.get("id")
        if not qr_id:
            raise HTTPException(status_code=400, detail="Missing qr_code id")
        bill = db.query(Bill).filter(Bill.razorpay_qr_id == qr_id).first()
        if not bill:
            logger.warning("POS webhook qr_code.credited for unknown qr_id=%s", qr_id)
            return {"status": "unknown_bill"}
    else:
        link_entity = payload.get("payload", {}).get("payment_link", {}).get("entity", {})
        payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
        reference_id = link_entity.get("reference_id")
        rp_payment_id = payment_entity.get("id")
        if not reference_id:
            raise HTTPException(status_code=400, detail="Missing reference_id")
        bill = db.query(Bill).filter(Bill.bill_number == reference_id).first()
        if not bill:
            logger.warning("POS webhook payment_link.paid for unknown bill reference_id=%s", reference_id)
            return {"status": "unknown_bill"}

    event_id = payload.get("event_id") or request.headers.get("X-Razorpay-Event-Id")

    settings = db.query(BillingSettings).filter(BillingSettings.shop_id == bill.shop_id).first()
    if not settings or not settings.razorpay_webhook_secret:
        logger.error("POS webhook for bill %s but shop %s has no webhook secret configured", bill.id, bill.shop_id)
        raise HTTPException(status_code=400, detail="Webhook not configured for this shop")

    # The actual trust boundary — nothing above this line is acted on.
    if not razorpay_service.verify_webhook_signature_with_secret(raw_body, signature, settings.razorpay_webhook_secret):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    if event_id:
        already_processed = (
            db.query(ProcessedWebhookEvent)
            .filter(ProcessedWebhookEvent.razorpay_event_id == event_id)
            .first()
        )
        if already_processed:
            return {"status": "already_processed"}

    if bill.payment_status == "paid" and bill.razorpay_payment_id and bill.razorpay_payment_id != rp_payment_id:
        # A SECOND successful payment landed for a bill that's already
        # paid — normally impossible because cross-cancel below closes
        # the other method the instant the first payment lands, but a
        # customer scanning the QR and opening the SMS link within that
        # same narrow window could still pay both before the cancel call
        # completes. Don't silently overwrite the original
        # razorpay_payment_id (that's the shop's record of what actually
        # settled first) — just log loudly so this is discoverable and
        # the shop can manually refund the duplicate via their Razorpay
        # dashboard. Still marked "already_processed"-equivalent below so
        # Razorpay stops retrying this delivery.
        logger.error(
            "DUPLICATE PAYMENT for bill %s (bill_number=%s): original razorpay_payment_id=%s, "
            "second payment_id=%s via %s — shop should refund the duplicate manually",
            bill.id, bill.bill_number, bill.razorpay_payment_id, rp_payment_id,
            "QR" if is_qr_event else "payment link",
        )
        if event_id:
            db.add(ProcessedWebhookEvent(razorpay_event_id=event_id, event_type=event_type))
            db.commit()
        return {"status": "duplicate_payment_flagged"}

    bill.payment_status = "paid"
    bill.razorpay_payment_id = rp_payment_id
    db.commit()

    # Whichever of the QR / payment link got paid first, close the OTHER
    # one for this same bill (if it's still open) so the same sale can
    # never be paid twice through the two different methods.
    try:
        if is_qr_event and bill.razorpay_payment_link_id:
            razorpay_service.cancel_payment_link(
                bill.razorpay_payment_link_id, settings.razorpay_key_id, settings.razorpay_key_secret
            )
        elif not is_qr_event and bill.razorpay_qr_id:
            razorpay_service.close_qr_code(
                bill.razorpay_qr_id, settings.razorpay_key_id, settings.razorpay_key_secret
            )
    except Exception:
        # Best-effort — the bill is already correctly marked paid above;
        # a leftover still-open QR/link is a minor cleanup miss, not a
        # reason to fail this webhook (Razorpay would just retry it).
        logger.exception("Failed to close the other payment method for bill %s", bill.id)

    if event_id:
        db.add(ProcessedWebhookEvent(razorpay_event_id=event_id, event_type=event_type))
        db.commit()

    return {"status": "ok"}


@router.get("/pdf/{token}")
def get_pdf(token: str):
    # No shop auth here on purpose — this is the link the customer's own
    # phone opens. Trust comes from the token being an unguessable uuid4,
    # same model as a password-reset link.
    #
    # Deliberately NOT single-use (see module docstring): SMS/RCS apps
    # commonly pre-fetch a link the instant the message arrives to build
    # a preview, which would consume a one-time file before the customer
    # ever tapped it. Instead the file just sits until _sweep_stale_pdfs
    # clears it after _PDF_TTL_SECONDS — fetchable any number of times
    # within that window.
    if not _TOKEN_RE.match(token):
        raise HTTPException(status_code=404, detail="Not found")

    path = os.path.join(_PDF_DIR, f"{token}.pdf")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="This invoice link has expired")

    return FileResponse(path, media_type="application/pdf", filename="invoice.pdf")
