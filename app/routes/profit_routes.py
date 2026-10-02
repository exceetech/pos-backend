from app.models.bill import Bill
from app.models.shop_products import ShopProduct
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from datetime import datetime, timedelta
from app.util.time_utils import local_now

from app.database import get_db
from app.models.sale_item import SaleItem
from app.models.inventory_log import InventoryLog
from app.dependencies import require_premium_tier
from app.models.shop import Shop
from app.models.credit_note import CreditNote, CreditNoteItem
from app.models.purchase_return import PurchaseReturn

router = APIRouter(prefix="/profit", tags=["Profit"])


@router.get("/")
def get_profit(
    filter: str = "all",
    start_date: str = None,
    end_date: str = None,
    db: Session = Depends(get_db),
    # Premium-gated: profit reports/charts are Premium-only (onboarding/
    # subscription plan §5.1/§5.2). require_premium_tier already runs the
    # same auth/subscription checks get_current_shop did, plus the tier
    # check.
    current_shop: Shop = Depends(require_premium_tier)
):

    now = local_now()
    
    start = None
    end = None
    prev_start = None
    prev_end = None

    if filter == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        prev_start = start - timedelta(days=1)
        prev_end = start
    elif filter == "week":
        # Calendar week starts on Monday
        monday = now - timedelta(days=now.weekday())
        start = monday.replace(hour=0, minute=0, second=0, microsecond=0)
        prev_start = start - timedelta(days=7)
        prev_end = start
    elif filter == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        prev_start = (start - timedelta(days=1)).replace(day=1)
        prev_end = start
    elif filter == "custom" and start_date and end_date:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)

    # ================= DATE FILTER =================
    def apply_date_filter(query, column):

        if filter in ["today", "week", "month"]:
            return query.filter(column >= start)

        elif filter == "custom" and start and end:
            return query.filter(column >= start, column < end)

        return query

    # ================= SALES =================
    sales_query = db.query(SaleItem).filter(
        SaleItem.shop_id == current_shop.id
    )

    sales_query = apply_date_filter(sales_query, SaleItem.created_at)
    sales = sales_query.all()

    product_map = {}

    for s in sales:
        pid = s.product_id

        if pid not in product_map:

            product = db.query(ShopProduct).filter(

                ShopProduct.id == s.product_id

            ).first()
            
            product_map[pid] = {
                "product_id": pid,
                "product_name": s.product_name,
                "variant": s.variant,
                "unit": product.unit,
                "qty": 0.0,
                "revenue": 0.0,
                "cost": 0.0,
                "profit": 0.0,
                "added": 0.0,
                "sold": 0.0,
                "lossAmount": 0.0,
                "returned_qty": 0.0,
                "returned_cost": 0.0
            }

        product_map[pid]["qty"] += s.quantity
        product_map[pid]["revenue"] += s.total_revenue
        product_map[pid]["cost"] += s.total_cost
        product_map[pid]["profit"] += (s.total_revenue - s.total_cost)

    # ================= RETURNS =================
    # Deep-dive fix, Issue 1: this query used to have no CreditNote.note_type
    # filter at all, so it pulled BOTH Credit Notes ("C" — a customer return,
    # revenue really did shrink) AND Debit Notes ("D" — extra units billed
    # after the fact, revenue actually GREW). Both were subtracted here as if
    # they were returns, and a Debit Note's revenue/cost was never added
    # anywhere else (it never becomes a SaleItem row) — so every debit note
    # only ever made profit look worse, never better. Scoped to note_type
    # == "C" so only real returns land here; Debit Notes are handled in their
    # own block below, added instead of subtracted.
    returns_query = db.query(CreditNoteItem).join(
        CreditNote, CreditNote.id == CreditNoteItem.note_id
        ).outerjoin(
        Bill, CreditNote.original_invoice_number == Bill.bill_number
    ).filter(
        CreditNote.shop_id == current_shop.id,
        CreditNote.note_type == "C",
        or_(
            Bill.id == None,
            and_(
                Bill.active == True,
                Bill.is_cancelled == False
            )
        )
    )

    returns_query = apply_date_filter(returns_query, CreditNote.created_at)
    returns = returns_query.all()

    for r in returns:
        pid = r.product_id
        if pid not in product_map:
            product = db.query(ShopProduct).filter(
                ShopProduct.id == pid
            ).first()

            if not product:
                continue

            product_map[pid] = {
                "product_id": pid,
                "product_name": r.product_name,
                "variant": r.variant,
                "unit": product.unit if product.unit else "",
                "qty": 0.0,
                "revenue": 0.0,
                "cost": 0.0,
                "profit": 0.0,
                "added": 0.0,
                "sold": 0.0,
                "lossAmount": 0.0,
                "returned_qty": 0.0,
                "returned_cost": 0.0
            }

        qty_returned = r.quantity_returned
        rev_returned = float(r.taxable_value)      # Net Revenue returned (fixes double-tax mismatch)
        cost_returned = float(r.cost_price_used)   # Gross Cost returned

        product_map[pid]["qty"] -= qty_returned
        product_map[pid]["revenue"] -= rev_returned
        product_map[pid]["cost"] -= cost_returned
        product_map[pid]["profit"] -= (rev_returned - cost_returned)

        product_map[pid]["returned_qty"] += qty_returned
        product_map[pid]["returned_cost"] += cost_returned

    # ================= DEBIT NOTES (extra quantity billed after the fact) =====
    # Deep-dive fix, Issue 1: a Debit Note ("D") represents additional units
    # that left the shop but were only billed for afterwards — real extra
    # revenue and real extra cost, never recorded as a SaleItem. Added here
    # (not subtracted) using the same total_amount/cost_price_used columns
    # the returns block reads, mirroring the sign flip in
    # CreditNoteRepository.createDebitNote / InventoryManager.reduceStock on
    # the client, which already treats a debit note like an extra sale.
    debits_query = db.query(CreditNoteItem).join(
        CreditNote, CreditNote.id == CreditNoteItem.note_id
        ).outerjoin(
        Bill, CreditNote.original_invoice_number == Bill.bill_number
    ).filter(
        CreditNote.shop_id == current_shop.id,
        CreditNote.note_type == "D",
        or_(
            Bill.id == None,
            and_(
                Bill.active == True,
                Bill.is_cancelled == False
            )
        )
    )

    debits_query = apply_date_filter(debits_query, CreditNote.created_at)
    debits = debits_query.all()

    for d in debits:
        pid = d.product_id
        if pid not in product_map:
            product = db.query(ShopProduct).filter(
                ShopProduct.id == pid
            ).first()

            if not product:
                continue

            product_map[pid] = {
                "product_id": pid,
                "product_name": d.product_name,
                "variant": d.variant,
                "unit": product.unit if product.unit else "",
                "qty": 0.0,
                "revenue": 0.0,
                "cost": 0.0,
                "profit": 0.0,
                "added": 0.0,
                "sold": 0.0,
                "lossAmount": 0.0,
                "returned_qty": 0.0,
                "returned_cost": 0.0
            }

        qty_debited = d.quantity_returned          # same column, reused for debited qty
        rev_debited = float(d.taxable_value)       # Net Revenue
        cost_debited = float(d.cost_price_used)    # Gross Cost

        product_map[pid]["qty"] += qty_debited
        product_map[pid]["revenue"] += rev_debited
        product_map[pid]["cost"] += cost_debited
        product_map[pid]["profit"] += (rev_debited - cost_debited)

    # Audit Round 2, P-3 (fixed 2026-07-23): snapshot the FULL product map
    # (every product with real sales/returns this period) before the
    # inventory-history filter below narrows it down. A product with no
    # InventoryLog rows — e.g. trackInventory=false, or stock predating this
    # logging — has completely legitimate revenue/cost/profit from SaleItem,
    # and was previously being silently dropped from the summary totals
    # entirely, not just the per-product breakdown table. Per your decision:
    # summary totals now reflect every real sale; the per-product breakdown
    # and inventory figures (added/remaining/loss) still only make sense for
    # products that actually have inventory history, so that part keeps the
    # filter.
    all_products_map = dict(product_map)

    # ================= INVENTORY FILTER (NO DATE FILTER HERE) =================
    # This filtered map now feeds ONLY the per-product breakdown list and the
    # inventory-figures loop below — not the summary totals.
    inventory_ids = db.query(InventoryLog.product_id).filter(
        InventoryLog.shop_id == current_shop.id,
        InventoryLog.is_active == True
    ).distinct().all()

    inventory_set = set(i.product_id for i in inventory_ids)

    product_map = {
        pid: data for pid, data in product_map.items()
        if pid in inventory_set
    }

    # ================= INVENTORY CALCULATIONS =================
    total_loss = 0
    total_expense = 0

    for pid in product_map:

        logs_query = db.query(InventoryLog).filter(
            InventoryLog.product_id == pid,
            InventoryLog.shop_id == current_shop.id,
            InventoryLog.is_active == True
        )

        logs_query = apply_date_filter(logs_query, InventoryLog.created_at)
        logs = logs_query.all()

        raw_added = sum(l.quantity for l in logs if l.type == "ADD")
        loss_qty = sum(l.quantity for l in logs if l.type == "LOSS")

        loss_amount = sum(l.quantity * l.price for l in logs if l.type == "LOSS")
        raw_expense = sum(l.quantity * l.price for l in logs if l.type == "ADD")

        # Audit Round 2, P-1 (fixed 2026-07-23): this used to subtract
        # product_map[pid]["returned_qty"/"returned_cost"] here, but those
        # values come from CUSTOMER SALES RETURNS (CreditNoteItem, computed
        # above) — nothing to do with how much stock was purchased. There is
        # no "PURCHASE_RETURN" InventoryLog type (see models/inventory_log.py),
        # so subtracting a sales-return quantity from purchased/expense stock
        # was pure variable-name reuse, not a real adjustment. It silently
        # understated "Added"/"Expense" (and therefore "Remaining") by the
        # sales-return amount on every product that had a customer return.
        # Sales returns are already correctly applied to qty/revenue/cost/
        # profit further up (the `product_map[pid]["qty"] -= qty_returned`
        # block) and need no second adjustment here.
        added = raw_added
        expense = raw_expense

        # Audit Round 2, P-2 (fixed 2026-07-23): the app writes InventoryLog
        # rows with several more types than this query used to recognize —
        # confirmed by grep: ADD, SALE, LOSS, RETURN (purchase return to
        # supplier — InventoryReductionRepository.kt), ADJUST (manual stock
        # count correction — InventoryManager.setStock), and CANCEL_RESTOCK
        # (bill cancellation — BillDetailsActivity.kt). All of them sync to
        # the backend unfiltered (SyncManager.kt syncInventory), but this
        # query only ever checked "ADD" and "LOSS", so a cancelled bill's
        # restock or a supplier return never moved "Remaining" here even
        # though the rows were sitting right there in the database.
        #
        # Added now:
        #   CANCEL_RESTOCK → treated like ADD for physical quantity (units
        #     are genuinely back in stock), but NOT added to "expense" — no
        #     new money was spent, so counting it as purchase expense would
        #     overstate spend for a sale that was voided, not re-bought.
        #   RETURN (to supplier) → subtracted from physical quantity only,
        #     for the same reason in reverse: "expense" here means money
        #     spent on ADD-type purchases, and a later return doesn't
        #     retroactively un-spend that money without a separate refund
        #     record, so leaving raw_expense alone is the conservative call.
        #
        #   SALE → intentionally not read from InventoryLog at all: "sold"
        #     below already comes from SaleItem (product_map[pid]["qty"]),
        #     which is the authoritative revenue/cost source; counting SALE
        #     rows here too would double-subtract the same units.
        restock_qty = sum(l.quantity for l in logs if l.type == "CANCEL_RESTOCK")
        # Purchase-return-to-supplier logs now use the "PURCHASE_RETURN" type
        # (see InventoryManager.LogType.PURCHASE_RETURN / inventory_routes.py
        # sign fix); "RETURN" is kept in this filter for backward
        # compatibility with rows synced before that change and is otherwise
        # unused by any current write path.
        purchase_return_qty = sum(l.quantity for l in logs if l.type in ("RETURN", "PURCHASE_RETURN"))

        sold = product_map[pid]["qty"]

        # Audit Round 2, ADJUST fix (2026-07-23): a manual stock-count
        # correction (InventoryManager.resetStock) logs the resulting stock
        # as an ABSOLUTE count, not a delta — so it can't just be added into
        # the additive added/sold/loss/return formula above like every other
        # type. Instead: if a correction happened within the queried window,
        # treat its logged quantity as a checkpoint ("remaining was exactly
        # this, at this moment") and only apply everything that happened
        # AFTER that checkpoint on top of it. Everything before the most
        # recent correction is irrelevant to "remaining" by definition — the
        # correction already accounted for it. If no correction exists in
        # the window, this falls back to the original from-zero formula.
        adjust_logs = [l for l in logs if l.type == "ADJUST"]
        last_adjust = max(adjust_logs, key=lambda l: l.created_at) if adjust_logs else None

        if last_adjust is not None:
            anchor_time = last_adjust.created_at
            anchor_qty = last_adjust.quantity  # absolute count at that moment

            post_add = sum(l.quantity for l in logs if l.type == "ADD" and l.created_at > anchor_time)
            post_restock = sum(l.quantity for l in logs if l.type == "CANCEL_RESTOCK" and l.created_at > anchor_time)
            post_loss_qty = sum(l.quantity for l in logs if l.type == "LOSS" and l.created_at > anchor_time)
            post_return_qty = sum(l.quantity for l in logs if l.type in ("RETURN", "PURCHASE_RETURN") and l.created_at > anchor_time)
            post_sales_return = sum(l.quantity for l in logs if l.type == "SALES_RETURN" and l.created_at > anchor_time)

            # "sold" above is the WHOLE period's sold quantity (correct for
            # revenue/cost/profit, which must never be truncated) — but
            # "remaining" after a checkpoint only cares about sales that
            # happened after it, so this is a separate, narrower query.
            post_sold_query = db.query(func.sum(SaleItem.quantity)).filter(
                SaleItem.shop_id == current_shop.id,
                SaleItem.product_id == pid,
                SaleItem.created_at > anchor_time
            )
            if filter == "custom" and end:
                post_sold_query = post_sold_query.filter(SaleItem.created_at < end)
            post_sold = post_sold_query.scalar() or 0.0

            remaining = anchor_qty + post_add + post_restock + post_sales_return - post_sold - post_loss_qty - post_return_qty
        else:
            remaining = added + restock_qty - sold - loss_qty - purchase_return_qty

        product_map[pid]["added"] = added
        product_map[pid]["sold"] = sold
        product_map[pid]["remaining"] = remaining
        product_map[pid]["lossQty"] = loss_qty
        product_map[pid]["lossAmount"] = loss_amount

        total_loss += loss_amount
        total_expense += expense

    # ================= SUMMARY =================
    # P-3: totals come from the unfiltered snapshot (every real sale),
    # not the inventory-history-filtered `product_map`.
    total_revenue = sum(p["revenue"] for p in all_products_map.values())
    total_cost = sum(p["cost"] for p in all_products_map.values())

    # Moving-average redesign, Phase 5: net gain/loss booked on purchase
    # returns (Debit Notes only — inventory_valuation_variance is always
    # 0.0 on a Credit Note). Positive = loss, negative = gain, so it's
    # subtracted the same way total_loss is: a loss reduces profit, a
    # gain (negative variance) increases it.
    purchase_return_variance_query = db.query(
        func.sum(PurchaseReturn.inventory_valuation_variance)
    ).filter(
        PurchaseReturn.shop_id == current_shop.id,
        PurchaseReturn.note_type == "D"
    )
    purchase_return_variance_query = apply_date_filter(
        purchase_return_variance_query, PurchaseReturn.created_at
    )
    total_purchase_return_variance = purchase_return_variance_query.scalar() or 0.0

    final_profit = total_revenue - total_cost - total_loss - total_purchase_return_variance

    growth_percentage = None
    if filter in ["today", "week", "month"]:
        # P-3: previously gated on `inventory_set` being non-empty and
        # scoped to only inventory-tracked products (`inv_list`) — now that
        # final_profit above includes every product, the previous-period
        # comparison must too, or growth% would compare an all-products
        # figure against a tracked-products-only one. Scoped to shop_id only.

        # Previous Sales Profit
        prev_sales_profit = db.query(func.sum(SaleItem.total_revenue - SaleItem.total_cost)).filter(
            SaleItem.shop_id == current_shop.id,
            SaleItem.created_at >= prev_start,
            SaleItem.created_at < prev_end
        ).scalar() or 0.0

        # Previous Returns Profit
        prev_returns_profit = db.query(func.sum(CreditNoteItem.total_amount - CreditNoteItem.cost_price_used)).join(
            CreditNote, CreditNote.id == CreditNoteItem.note_id
        ).outerjoin(
            Bill, CreditNote.original_invoice_number == Bill.bill_number
        ).filter(
            CreditNote.shop_id == current_shop.id,
            CreditNote.created_at >= prev_start,
            CreditNote.created_at < prev_end,
            or_(
                Bill.id == None,
                and_(Bill.active == True, Bill.is_cancelled == False)
            )
        ).scalar() or 0.0

        # Previous Loss (inherently inventory-scoped — InventoryLog only
        # exists for tracked products, so no product_id filter is needed).
        prev_loss = db.query(func.sum(InventoryLog.quantity * InventoryLog.price)).filter(
            InventoryLog.shop_id == current_shop.id,
            InventoryLog.is_active == True,
            InventoryLog.type == "LOSS",
            InventoryLog.created_at >= prev_start,
            InventoryLog.created_at < prev_end
        ).scalar() or 0.0

        prev_purchase_return_variance = db.query(
            func.sum(PurchaseReturn.inventory_valuation_variance)
        ).filter(
            PurchaseReturn.shop_id == current_shop.id,
            PurchaseReturn.note_type == "D",
            PurchaseReturn.created_at >= prev_start,
            PurchaseReturn.created_at < prev_end
        ).scalar() or 0.0

        prev_profit = prev_sales_profit - prev_returns_profit - prev_loss - prev_purchase_return_variance
        
        if prev_profit != 0:
            growth_percentage = ((final_profit - prev_profit) / abs(prev_profit)) * 100
        else:
            growth_percentage = 100.0 if final_profit > 0 else (0.0 if final_profit == 0 else -100.0)

    summary_data = {
        "revenue": total_revenue,
        "cost": total_cost,
        "profit": final_profit,
        "loss": total_loss,
        "expense": total_expense,
        # Moving-average redesign, Phase 5. Already folded into "profit"
        # above; exposed separately so the UI can show it as its own line
        # item instead of it being invisibly absorbed into "loss".
        "purchaseReturnVariance": total_purchase_return_variance
    }
    
    if growth_percentage is not None:
        summary_data["growth"] = {
            "profit_percentage": round(growth_percentage, 2)
        }

    return {
        "summary": summary_data,
        "products": list(product_map.values())
    }


# ============================================================================
# PROFIT TREND CHART
# ============================================================================
# Bucketed profit for the trend chart on the Profit Analytics page's chart
# screen. Same five period words as GET /profit ("today", "week", "month",
# "all", "custom"), and the exact same profit formula used there
# (revenue - cost - loss - purchase_return_variance, Expense never
# subtracted) -- summed PER BUCKET instead of once for the whole period, so
# the bars always add up to the same total already shown on the main
# Profit Analytics screen. Optional product_id scopes every bucket to one
# product instead of the whole shop.
#
# Bucketing (see expos-profit-trend-chart-plan.md for the full plan this
# implements):
#   today  -> 24 hourly buckets for the current calendar day
#   week   -> 7 daily buckets, Monday -> Sunday of the current week
#   month  -> one bucket per calendar day in the current month
#   all    -> one bucket per calendar month, from the month the shop was
#             registered (Shop.created_at) through the current month
#   custom -> one bucket per calendar day between start_date and end_date,
#             clamped so it can never start before the shop was registered
#             or end after today
# ============================================================================

_MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_HOUR_LABELS = (
    ["12 AM"] + [f"{h} AM" for h in range(1, 12)] +
    ["12 PM"] + [f"{h} PM" for h in range(1, 12)]
)
_DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _month_add(dt: datetime, months: int) -> datetime:
    """dt moved forward by `months` whole calendar months, day fixed to 1."""
    total = dt.month - 1 + months
    year = dt.year + total // 12
    month = total % 12 + 1
    return dt.replace(year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0)


def _build_trend_buckets(filter: str, now: datetime, shop_created_at: datetime,
                          start_date: str = None, end_date: str = None):
    """Returns (buckets, overall_start, overall_end). buckets is a list of
    (label, bucket_start, bucket_end) tuples, bucket_end exclusive."""

    buckets = []

    if filter == "today":
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        for h in range(24):
            b_start = day_start + timedelta(hours=h)
            buckets.append((_HOUR_LABELS[h], b_start, b_start + timedelta(hours=1)))
        return buckets, day_start, day_start + timedelta(days=1)

    if filter == "week":
        monday = now - timedelta(days=now.weekday())
        week_start = monday.replace(hour=0, minute=0, second=0, microsecond=0)
        for i in range(7):
            b_start = week_start + timedelta(days=i)
            buckets.append((_DAY_LABELS[i], b_start, b_start + timedelta(days=1)))
        return buckets, week_start, week_start + timedelta(days=7)

    if filter == "month":
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        next_month = _month_add(month_start, 1)
        days_in_month = (next_month - month_start).days
        for d in range(days_in_month):
            b_start = month_start + timedelta(days=d)
            buckets.append((str(d + 1), b_start, b_start + timedelta(days=1)))
        return buckets, month_start, next_month

    if filter == "all":
        shop_month_start = shop_created_at.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0)
        cur_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        m = shop_month_start
        while m <= cur_month_start:
            m_end = _month_add(m, 1)
            label = _MONTH_NAMES[m.month - 1]
            if m.year != now.year:
                label = f"{label} {m.year}"
            buckets.append((label, m, m_end))
            m = m_end
        overall_end = buckets[-1][2] if buckets else cur_month_start
        return buckets, shop_month_start, overall_end

    if filter == "custom" and start_date and end_date:
        shop_day = shop_created_at.replace(hour=0, minute=0, second=0, microsecond=0)
        today_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")

        # Guardrail: never before the shop was registered, never after today.
        if start < shop_day:
            start = shop_day
        if end > today_day:
            end = today_day
        if end < start:
            end = start

        d = start
        while d <= end:
            buckets.append((d.strftime("%-d %b"), d, d + timedelta(days=1)))
            d += timedelta(days=1)
        overall_end = buckets[-1][2] if buckets else start + timedelta(days=1)
        return buckets, start, overall_end

    # Unknown filter -> no buckets.
    return [], now, now


def _profit_for_range(db: Session, shop_id: int, start: datetime, end: datetime,
                       product_id: int = None):
    """Revenue/cost/loss/profit for one [start, end) slice, optionally scoped
    to one product. Mirrors GET /profit's own summary math exactly (never
    subtracts Expense)."""

    sales_q = db.query(
        func.coalesce(func.sum(SaleItem.total_revenue), 0.0),
        func.coalesce(func.sum(SaleItem.total_cost), 0.0)
    ).filter(
        SaleItem.shop_id == shop_id,
        SaleItem.created_at >= start,
        SaleItem.created_at < end
    )
    if product_id is not None:
        sales_q = sales_q.filter(SaleItem.product_id == product_id)
    revenue, cost = sales_q.one()
    revenue = float(revenue or 0.0)
    cost = float(cost or 0.0)

    # Customer returns (note_type "C") shrink revenue/cost; Debit Notes
    # ("D" -- extra units billed after the fact) grow them. Same join/active
    # bill filter as GET /profit.
    returns_q = db.query(
        CreditNoteItem.taxable_value,
        CreditNoteItem.cost_price_used,
        CreditNote.note_type
    ).join(
        CreditNote, CreditNote.id == CreditNoteItem.note_id
    ).outerjoin(
        Bill, CreditNote.original_invoice_number == Bill.bill_number
    ).filter(
        CreditNote.shop_id == shop_id,
        CreditNote.created_at >= start,
        CreditNote.created_at < end,
        or_(
            Bill.id == None,
            and_(Bill.active == True, Bill.is_cancelled == False)
        )
    )
    if product_id is not None:
        returns_q = returns_q.filter(CreditNoteItem.product_id == product_id)

    for taxable_value, cost_price_used, note_type in returns_q.all():
        sign = -1.0 if note_type == "C" else (1.0 if note_type == "D" else 0.0)
        revenue += sign * float(taxable_value or 0.0)
        cost += sign * float(cost_price_used or 0.0)

    loss_q = db.query(
        func.coalesce(func.sum(InventoryLog.quantity * InventoryLog.price), 0.0)
    ).filter(
        InventoryLog.shop_id == shop_id,
        InventoryLog.is_active == True,
        InventoryLog.type == "LOSS",
        InventoryLog.created_at >= start,
        InventoryLog.created_at < end
    )
    if product_id is not None:
        loss_q = loss_q.filter(InventoryLog.product_id == product_id)
    loss = float(loss_q.scalar() or 0.0)

    variance_q = db.query(
        func.coalesce(func.sum(PurchaseReturn.inventory_valuation_variance), 0.0)
    ).filter(
        PurchaseReturn.shop_id == shop_id,
        PurchaseReturn.note_type == "D",
        PurchaseReturn.created_at >= start,
        PurchaseReturn.created_at < end
    )
    if product_id is not None:
        variance_q = variance_q.filter(PurchaseReturn.shop_product_id == product_id)
    variance = float(variance_q.scalar() or 0.0)

    profit = revenue - cost - loss - variance

    return {
        "revenue": round(revenue, 2),
        "cost": round(cost, 2),
        "loss": round(loss, 2),
        "profit": round(profit, 2)
    }


@router.get("/trend")
def get_profit_trend(
    filter: str = "today",
    start_date: str = None,
    end_date: str = None,
    product_id: int = None,
    db: Session = Depends(get_db),
    current_shop: Shop = Depends(require_premium_tier)
):
    now = local_now()
    shop_created_at = current_shop.created_at or now

    buckets, overall_start, overall_end = _build_trend_buckets(
        filter, now, shop_created_at, start_date, end_date
    )

    bucket_results = []
    for label, b_start, b_end in buckets:
        figures = _profit_for_range(db, current_shop.id, b_start, b_end, product_id)
        bucket_results.append({
            "label": label,
            "start": b_start.isoformat(),
            "end": b_end.isoformat(),
            **figures
        })

    total_profit = round(sum(b["profit"] for b in bucket_results), 2)

    return {
        "filter": filter,
        "buckets": bucket_results,
        "total_profit": total_profit
    }
