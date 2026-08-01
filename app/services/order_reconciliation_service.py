"""
Catches the rare case where BOTH verify-payment AND the Razorpay webhook
fail to land for a genuinely successful payment (e.g. the app crashed
right after Razorpay's success callback, AND the webhook delivery itself
also failed or was delayed past this shop's session). Without this, an
Order stuck in "created" status with a real, successful Razorpay payment
behind it would sit unresolved forever with no automatic recovery path —
per plan §6.4.

Runs periodically (see main.py scheduler wiring), checking any Order
still "created" past a reasonable grace window against Razorpay's own
order/payment status API. If Razorpay confirms it was actually paid,
activates it through the same activate_order() path verify-payment and
the webhook use — same idempotency guarantees apply.
"""
import logging
from datetime import timedelta
from sqlalchemy.orm import Session

from app.models.order import Order
from app.services import razorpay_service
from app.services.subscription_activation_service import activate_order
from app.util.time_utils import utc_now

logger = logging.getLogger(__name__)

# Give verify-payment and the webhook a real chance to land normally
# before treating an order as "stuck" — anything shorter risks false
# positives on an order that's simply still mid-flight.
GRACE_PERIOD_MINUTES = 30


def reconcile_stuck_orders(db: Session) -> None:
    cutoff = utc_now() - timedelta(minutes=GRACE_PERIOD_MINUTES)

    stuck_orders = (
        db.query(Order)
        .filter(
            Order.status == "created",
            Order.created_at <= cutoff,
            Order.razorpay_order_id.isnot(None),
            Order.razorpay_order_id != "",
        )
        .all()
    )

    if not stuck_orders:
        return

    try:
        client = razorpay_service.get_client()
    except Exception as e:
        logger.warning("Reconciliation skipped — Razorpay client unavailable: %s", e)
        return

    for order in stuck_orders:
        try:
            rp_order = client.order.fetch(order.razorpay_order_id)
            # Razorpay orders report amount_paid > 0 (or status "paid")
            # once a successful payment is captured against them.
            if rp_order.get("status") == "paid" or rp_order.get("amount_paid", 0) >= order.amount_paise:
                payments = client.order.payments(order.razorpay_order_id)
                payment_items = payments.get("items", [])
                captured = next(
                    (p for p in payment_items if p.get("status") == "captured"), None
                )
                payment_id = captured["id"] if captured else None
                activate_order(db, order, razorpay_payment_id=payment_id)
                logger.info("Reconciliation: activated stuck order %s (razorpay_order_id=%s)", order.id, order.razorpay_order_id)
            else:
                logger.info("Reconciliation: order %s still unpaid at Razorpay (status=%s)", order.id, rp_order.get("status"))
        except Exception as e:
            logger.warning("Reconciliation failed for order %s: %s", order.id, e)
