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

    # Candidate scan only — no lock taken here. The actual claim happens
    # per-order below via with_for_update(skip_locked=True), so this list
    # can be stale by the time we get to it without causing any harm.
    stuck_order_ids = [
        oid
        for (oid,) in db.query(Order.id)
        .filter(
            Order.status == "created",
            Order.created_at <= cutoff,
            Order.razorpay_order_id.isnot(None),
            Order.razorpay_order_id != "",
        )
        .all()
    ]

    if not stuck_order_ids:
        return

    try:
        client = razorpay_service.get_client()
    except Exception as e:
        logger.warning("Reconciliation skipped — Razorpay client unavailable: %s", e)
        return

    for order_id in stuck_order_ids:
        # Row-level lock, taken fresh per order (not on the candidate
        # scan above). SKIP LOCKED means a concurrent reconciliation run
        # — another gunicorn worker that also got the scheduler lock via
        # a race at startup, a manually-triggered run, or a future
        # horizontally-scaled instance — simply skips any order this
        # process has already claimed instead of blocking on it or,
        # worse, both processes reading "created" and both activating it.
        # Locking per-order (instead of locking the whole batch up front)
        # also means committing one order's activation doesn't release
        # the lock on the others still queued in this same call.
        order = (
            db.query(Order)
            .filter(Order.id == order_id, Order.status == "created")
            .with_for_update(skip_locked=True)
            .first()
        )
        if order is None:
            # Either another process already claimed/activated it, or its
            # status changed since the candidate scan above — either way,
            # nothing to do here.
            db.rollback()
            continue

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
                # activate_order() commits internally — that commit is
                # also what releases this order's row lock.
                activate_order(db, order, razorpay_payment_id=payment_id)
                logger.info("Reconciliation: activated stuck order %s (razorpay_order_id=%s)", order.id, order.razorpay_order_id)
            else:
                db.commit()  # release the row lock; nothing to change
                logger.info("Reconciliation: order %s still unpaid at Razorpay (status=%s)", order.id, rp_order.get("status"))
        except Exception as e:
            db.rollback()
            logger.warning("Reconciliation failed for order %s: %s", order.id, e)
