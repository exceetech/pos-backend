import os
import re
import shutil
import tempfile

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from sqlalchemy import func, case, exists, and_
from datetime import datetime, timedelta, date


from fastapi_mail import FastMail, MessageSchema
from fastapi import Depends, HTTPException
from app.dependencies import get_current_shop

from app.database import get_db
from app.dependencies import get_current_shop
from app.models.bill import Bill
from app.models.bill_items import BillItem
from app.core.config import mail_config
from app.util.report_generator import generate_report_pdf
from app.util.time_utils import local_now, local_today, APP_TZ
from app.models.credit_note import CreditNote, CreditNoteItem


from app.models.shop_products import ShopProduct
from app.models.global_products import GlobalProduct

SHOP_WEIGHTS = {

    "grocery":  {"qty": 0.1, "rev": 0.7, "freq": 0.2},

    "hotel":    {"qty": 0.2, "rev": 0.3, "freq": 0.5},

    "bakery":   {"qty": 0.3, "rev": 0.4, "freq": 0.3},

    "general":  {"qty": 0.2, "rev": 0.5, "freq": 0.3}

}

router = APIRouter(prefix="/reports", tags=["Reports"])


# ================= SALES ADJUSTMENTS — CREDIT & DEBIT NOTES (R1) =================
# Reports show NET revenue. The credit_notes table holds BOTH note types:
#   note_type "C" — credit note / sales return  → REDUCES revenue
#   note_type "D" — debit note / additional sale → INCREASES revenue
# Amounts below are SIGNED with "C" positive, so every caller's existing
# `revenue -= adjustment` nets both kinds correctly.
#
# IMPORTANT: a note's business timestamp is `note_date` (epoch ms, set on
# the device when the note was made). `created_at` is the UTC sync-receipt
# time and must NOT be used for business-date grouping (it would
# reintroduce the H6 timezone bug). note_date == 0 (unset) is excluded.
#
# DOUBLE-COUNT GUARD: notes whose original bill is no longer active
# (voided or archived) are excluded. The bill's FULL amount is already
# out of revenue, so letting its notes adjust revenue again would
# double-subtract (cancel-after-return understated revenue by the
# returned amount).
#
# Bases reconcile: CreditNote.total_amount is GST-inclusive, the same
# basis as Bill.final_amount; CreditNoteItem.total_amount matches
# BillItem.total_amount.

def _cn_ts():
    """Note's business time as a naive app-local timestamp (SQL expr)."""
    return func.timezone(str(APP_TZ), func.to_timestamp(CreditNote.note_date / 1000.0))


def _cn_signed(amount_col):
    """Sign an amount column by note type: C positive (reduces revenue
    when subtracted), D negative (increases it)."""
    return case(
        (func.upper(CreditNote.note_type) == "D", -amount_col),
        else_=amount_col
    )


def _cn_window(q, ts, start=None, end=None, end_inclusive=False):
    q = q.filter(CreditNote.note_date > 0)

    # Double-count guard: skip notes of voided/archived bills.
    inactive_original = exists().where(and_(
        Bill.shop_id == CreditNote.shop_id,
        Bill.bill_number == CreditNote.original_invoice_number,
        Bill.active == False
    ))
    q = q.filter(~inactive_original)

    if start is not None:
        q = q.filter(ts >= start)
    if end is not None:
        q = q.filter(ts <= end if end_inclusive else ts < end)
    return q


def _returns_total(db, shop_id, start=None, end=None, end_inclusive=False):
    """Signed net adjustment (returns − debits) for one shop in window."""
    ts = _cn_ts()
    q = db.query(func.sum(_cn_signed(CreditNote.total_amount))).filter(
        CreditNote.shop_id == shop_id
    )
    q = _cn_window(q, ts, start, end, end_inclusive)
    return float(q.scalar() or 0)


def _returns_map(db, shop_id, group, start=None, end=None, end_inclusive=False):
    """{group_key: signed_adjustment} for one shop within the window.

    `group` is a callable taking the local-time SQL expression and
    returning the grouping expression (e.g. func.date)."""
    ts = _cn_ts()
    expr = group(ts)
    q = db.query(expr, func.sum(_cn_signed(CreditNote.total_amount))).filter(
        CreditNote.shop_id == shop_id
    )
    q = _cn_window(q, ts, start, end, end_inclusive)
    return {r[0]: float(r[1] or 0) for r in q.group_by(expr).all()}


def _product_returns_map(db, shop_id, start=None, end=None, end_inclusive=False):
    """{(product, variant, unit): {"qty", "revenue"}} signed adjustments
    in window — C reduces a product's sold qty/revenue, D adds to it."""
    ts = _cn_ts()
    q = db.query(
        CreditNoteItem.product_name,
        CreditNoteItem.variant,
        CreditNoteItem.unit,
        func.sum(_cn_signed(CreditNoteItem.quantity_returned)),
        func.sum(_cn_signed(CreditNoteItem.total_amount))
    ).join(
        CreditNote, CreditNote.id == CreditNoteItem.note_id
    ).filter(
        CreditNote.shop_id == shop_id
    )
    q = _cn_window(q, ts, start, end, end_inclusive)
    rows = q.group_by(
        CreditNoteItem.product_name,
        CreditNoteItem.variant,
        CreditNoteItem.unit
    ).all()
    return {
        (r[0], r[1], r[2] or ""): {
            "qty": float(r[3] or 0),
            "revenue": float(r[4] or 0)
        }
        for r in rows
    }


# ================= BILL BASE FILTER =================
# Every report query MUST use this. Three conditions:
#   1. active == True        — excludes voided/archived bills
#   2. is_cancelled == False — belt-and-braces; active=False is set on cancel
#                              but any state mismatch would leak into revenue
#   3. created_at IS NOT NULL— bills predating the column have NULL here;
#                              grouping on NULL creates spurious buckets and
#                              their amounts pollute un-dated aggregates
def _bill_filters(shop_id):
    return [
        Bill.shop_id == shop_id,
        Bill.active == True,
        Bill.is_cancelled == False,
        Bill.created_at.isnot(None),
    ]


# ================= DAILY SALES =================

@router.get("/daily")
def daily_report(db: Session = Depends(get_db), current_shop=Depends(get_current_shop)):

    rows = db.query(
        func.date(Bill.created_at),
        func.sum(Bill.final_amount),
        func.count(Bill.id)
    ).filter(
        *_bill_filters(current_shop.id)
    ).group_by(
        func.date(Bill.created_at)
    ).order_by(
        func.date(Bill.created_at).desc()
    ).limit(720).all()

    # R1: net out returns; a date with only returns (no sales) still
    # appears, with bills=0 and negative revenue.
    rmap = _returns_map(db, current_shop.id, func.date)

    merged = {}
    for r in rows:
        merged[r[0]] = {"revenue": float(r[1] or 0), "bills": int(r[2] or 0)}
    for d, amt in rmap.items():
        entry = merged.setdefault(d, {"revenue": 0.0, "bills": 0})
        entry["revenue"] -= amt

    out = sorted(merged.items(), key=lambda kv: kv[0], reverse=True)[:720]

    return [
        {
            "date": str(d),
            "revenue": v["revenue"],
            "bills": v["bills"]
        }
        for d, v in out
    ]


# ================= MONTHLY SALES =================

@router.get("/monthly")
def monthly_report(db: Session = Depends(get_db), current_shop=Depends(get_current_shop)):

    rows = db.query(
        func.date_trunc("month", Bill.created_at),
        func.sum(Bill.final_amount),
        func.count(Bill.id)
    ).filter(
        *_bill_filters(current_shop.id)
    ).group_by(
        func.date_trunc("month", Bill.created_at)
    ).order_by(
        func.date_trunc("month", Bill.created_at).desc()
    ).limit(60).all()

    # R1: net out returns (return-only months included with bills=0)
    rmap = _returns_map(
        db, current_shop.id,
        lambda ts: func.date_trunc("month", ts)
    )

    merged = {}
    for r in rows:
        merged[r[0]] = {"revenue": float(r[1] or 0), "bills": int(r[2] or 0)}
    for m, amt in rmap.items():
        entry = merged.setdefault(m, {"revenue": 0.0, "bills": 0})
        entry["revenue"] -= amt

    out = sorted(merged.items(), key=lambda kv: kv[0], reverse=True)[:60]

    return [
        {
            "month": str(m),
            "revenue": v["revenue"],
            "bills": v["bills"]
        }
        for m, v in out
    ]


# ================= YEARLY SALES =================

@router.get("/yearly")
def yearly_report(db: Session = Depends(get_db), current_shop=Depends(get_current_shop)):

    rows = db.query(
        func.extract("year", Bill.created_at),
        func.sum(Bill.final_amount),
        func.count(Bill.id)
    ).filter(
        *_bill_filters(current_shop.id)
    ).group_by(
        func.extract("year", Bill.created_at)
    ).order_by(
        func.extract("year", Bill.created_at).desc()
    ).all()

    # R1: net out returns (keys normalized to int — extract() is Decimal)
    rmap = _returns_map(
        db, current_shop.id,
        lambda ts: func.extract("year", ts)
    )

    merged = {}
    for r in rows:
        merged[int(r[0])] = {"revenue": float(r[1] or 0), "bills": int(r[2] or 0)}
    for y, amt in rmap.items():
        entry = merged.setdefault(int(y), {"revenue": 0.0, "bills": 0})
        entry["revenue"] -= amt

    return [
        {
            "year": y,
            "revenue": v["revenue"],
            "bills": v["bills"]
        }
        for y, v in sorted(merged.items(), reverse=True)
    ]


# ================= TOP PRODUCTS =================

@router.get("/top-products")
def top_products(
    type: str = "today",
    sort_by: str = "quantity",
    start: str = None,
    end: str = None,
    db: Session = Depends(get_db),
    current_shop=Depends(get_current_shop)
):

    query = db.query(
        BillItem.product_name,
        BillItem.variant,
        BillItem.unit,
        func.sum(BillItem.quantity).label("qty"),
        func.sum(BillItem.total_amount).label("revenue"),
        # I3 FIX: count distinct bills (orders), not line items — the same
        # product on two lines of one bill was counted as 2 "orders".
        func.count(func.distinct(BillItem.bill_id)).label("frequency")
    ).join(Bill).filter(
    *_bill_filters(current_shop.id)
)

    if type == "today":
        today = local_today()  # H6: app-timezone "today", not server clock
        query = query.filter(func.date(Bill.created_at) == today)

    elif type == "custom":

        # M2 FIX: missing or invalid dates used to fall through silently
        # and return ALL-TIME data as if it were filtered.
        if not start or not end:
            raise HTTPException(
                status_code=422,
                detail="start and end are required when type=custom"
            )

        try:
            start_date = datetime.strptime(start, "%Y-%m-%d").date()
            end_date = datetime.strptime(end, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail="Dates must be in YYYY-MM-DD format"
            )

        query = query.filter(
            func.date(Bill.created_at) >= start_date,
            func.date(Bill.created_at) <= end_date
        )

    elif type not in ("today", "custom"):
        # Unknown type — reject explicitly instead of silently returning
        # all-time data (which looks correct but is wrong).
        raise HTTPException(
            status_code=422,
            detail=f"Unknown type '{type}'. Use 'today' or 'custom'."
        )

    # M1 FIX: no .limit(100) before sorting — with no ORDER BY the DB
    # returned an ARBITRARY 100 groups, so real best-sellers could be
    # missing entirely. Group count is bounded by catalog size; the
    # response is still capped at 50 after sorting below.
    rows = query.group_by(
        BillItem.product_name,
        BillItem.variant,
        BillItem.unit
    ).all()

    data = [

        {

            "product": r[0],

            "variant": r[1],
            "unit": r[2] or "",

            "quantity": float(r[3] or 0),

            "revenue": float(r[4] or 0),
            "frequency": float(r[5] or 0)

        }

        for r in rows

    ]

    # R1: net out returned quantity/revenue per product BEFORE sorting,
    # using the same date window as the sales query.
    if type == "today":
        pr = _product_returns_map(
            db, current_shop.id,
            start=today, end=today + timedelta(days=1)
        )
    elif type == "custom":
        pr = _product_returns_map(
            db, current_shop.id,
            start=start_date, end=end_date + timedelta(days=1)
        )
    else:
        pr = _product_returns_map(db, current_shop.id)

    index = {(x["product"], x["variant"], x["unit"]): x for x in data}
    for key, ret in pr.items():
        x = index.get(key)
        if x is None:
            # product returned in this window but not sold in it
            x = {
                "product": key[0], "variant": key[1], "unit": key[2],
                "quantity": 0.0, "revenue": 0.0, "frequency": 0.0
            }
            data.append(x)
            index[key] = x
        x["quantity"] -= ret["qty"]
        x["revenue"] -= ret["revenue"]

    if sort_by == "quantity":

        data.sort(key=lambda x: x["quantity"], reverse=True)

    elif sort_by == "revenue":

        data.sort(key=lambda x: x["revenue"], reverse=True)

    elif sort_by == "frequency":

        data.sort(key=lambda x: x["frequency"], reverse=True)

    elif sort_by == "smart":

        max_qty = max((x["quantity"] for x in data), default=1)
        max_rev = max((x["revenue"] for x in data), default=1)
        max_freq = max((x["frequency"] for x in data), default=1)

        shop_type = (current_shop.type or "general").lower()

        weights = SHOP_WEIGHTS.get(shop_type, SHOP_WEIGHTS["general"])

        w_qty = weights["qty"]
        w_rev = weights["rev"]
        w_freq = weights["freq"]

        total = w_qty + w_rev + w_freq
        if total != 1:
            w_qty /= total
            w_rev /= total
            w_freq /= total

        for x in data:
            norm_qty = x["quantity"] / max_qty if max_qty else 0
            norm_rev = x["revenue"] / max_rev if max_rev else 0
            norm_freq = x["frequency"] / max_freq if max_freq else 0

            x["score"] = (
                w_qty * norm_qty +
                w_rev * norm_rev +
                w_freq * norm_freq
            )

        data.sort(key=lambda x: x["score"], reverse=True)

    return [
    {
        "product": x["product"],
        "variant": x["variant"],
        "unit": x["unit"],
        # I2 FIX: keep fractional quantities (2.5 kg was truncated to 2)
        "quantity": float(x["quantity"]),
        "revenue": float(x["revenue"]),
        "frequency": int(x["frequency"])
    }
    for x in data[:50]
]


# ================= PEAK HOURS =================

@router.get("/peak-hours")
def peak_hours(
    type: str = "all",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):

    query = db.query(
        func.extract("hour", Bill.created_at),
        func.count(Bill.id),
        func.sum(Bill.final_amount)
    ).filter(
        *_bill_filters(current_shop.id)
    )

    now = local_now()  # H6: app-timezone clock, was utcnow()

    # R1: window captured for the returns query below (None = all-time)
    start = None
    end = None

    if type == "today":

        start = datetime.combine(local_today(), datetime.min.time())
        end = start + timedelta(days=1)

        query = query.filter(
            Bill.created_at >= start,
            Bill.created_at < end
        )

    elif type == "week":

        # I8 FIX: calendar week Sunday→Saturday (was a rolling 7-day
        # window, inconsistent with /average-bill and /email-report).
        today = local_today()
        days_since_sunday = (today.weekday() + 1) % 7

        start = datetime.combine(
            today - timedelta(days=days_since_sunday),
            datetime.min.time()
        )
        end = start + timedelta(days=7)  # exclusive: next Sunday 00:00

        query = query.filter(
            Bill.created_at >= start,
            Bill.created_at < end
        )

    elif type == "month":

        # Calendar month (1st → next 1st), matching /average-bill and
        # /overview. Was a rolling 30-day window, so peak-hours totals did
        # not reconcile with the revenue KPI under the same "Month" chip.
        start = datetime(now.year, now.month, 1)
        end = (
            datetime(now.year + 1, 1, 1)
            if now.month == 12
            else datetime(now.year, now.month + 1, 1)
        )

        query = query.filter(
            Bill.created_at >= start,
            Bill.created_at < end
        )

    elif type == "year":

        # Calendar year (Jan 1 → next Jan 1), matching the KPI endpoints.
        # Was a rolling 365-day window.
        start = datetime(now.year, 1, 1)
        end = datetime(now.year + 1, 1, 1)

        query = query.filter(
            Bill.created_at >= start,
            Bill.created_at < end
        )

    elif type == "custom":

        # B2 FIX: missing/invalid dates used to fall through silently and
        # return ALL-TIME data as if it were filtered (same as M2).
        if not start_date or not end_date:
            raise HTTPException(
                status_code=422,
                detail="start_date and end_date are required when type=custom"
            )

        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail="Dates must be in YYYY-MM-DD format"
            )

        query = query.filter(
            Bill.created_at >= start,
            Bill.created_at < end
        )

    rows = query.group_by(
        func.extract("hour", Bill.created_at)
    ).order_by(
        func.extract("hour", Bill.created_at)
    ).all()

    # R1: net out returns per hour over the same window
    rmap = _returns_map(
        db, current_shop.id,
        lambda ts: func.extract("hour", ts),
        start=start, end=end
    )

    merged = {}
    for r in rows:
        merged[int(r[0])] = {"bills": int(r[1] or 0), "revenue": float(r[2] or 0)}
    for h, amt in rmap.items():
        entry = merged.setdefault(int(h), {"bills": 0, "revenue": 0.0})
        entry["revenue"] -= amt

    return [
        {
            "hour": h,
            "bills": v["bills"],
            "revenue": v["revenue"]
        }
        for h, v in sorted(merged.items())
    ]


# ================= AVERAGE BILL =================

@router.get("/average-bill")
def average_bill(
    type: str = "today",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):

    now = local_now()  # H6: app-timezone clock, was server-local now()

    # B1 FIX: only apply the M3 period-to-date adjustment when a real
    # period branch matched. "custom" without dates falls into the else
    # (all-time) branch below — applying M3 there turned the empty
    # previous window into ALL of history (prev == current → 0% growth).
    ptd_applies = True

    if type == "today":

        start = datetime(now.year, now.month, now.day)
        end = start + timedelta(days=1)

        prev_start = start - timedelta(days=1)
        prev_end = start

    elif type == "week":

        today = local_today()  # H6

        # I8 FIX: % 7 — without it, on Sundays weekday()+1 == 7 and the
        # "current week" started at the PREVIOUS Sunday.
        days_since_sunday = (today.weekday() + 1) % 7

        # M3: datetimes (not dates) so elapsed-time maths below works
        start = datetime.combine(
            today - timedelta(days=days_since_sunday),
            datetime.min.time()
        )
        end = start + timedelta(days=7)

        prev_start = start - timedelta(days=7)
        prev_end = start

    elif type == "month":

        start = datetime(now.year, now.month, 1)

        if now.month == 12:
            end = datetime(now.year + 1, 1, 1)
        else:
            end = datetime(now.year, now.month + 1, 1)

        # Anchor to the FIRST day of the previous calendar month, the same
        # way the year branch anchors to the previous calendar year.
        # Using start-(end-start) subtracted the *current* month's length
        # and drifted the comparison window by ±1–3 days across 28/31-day
        # months. The M3 cap below still trims prev_end to elapsed duration.
        prev_start = (start - timedelta(days=1)).replace(day=1)
        prev_end = start

    elif type == "year":

        start = datetime(now.year, 1, 1)
        end = datetime(now.year + 1, 1, 1)

        prev_start = datetime(now.year - 1, 1, 1)
        prev_end = start

    elif type == "custom":

        # B2 FIX: missing/invalid dates used to fall through silently into
        # the all-time branch (and, pre-B1, corrupt the growth window).
        if not start_date or not end_date:
            raise HTTPException(
                status_code=422,
                detail="start_date and end_date are required when type=custom"
            )

        try:
            start = datetime.fromisoformat(start_date)
            end = datetime.fromisoformat(end_date) + timedelta(days=1)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail="Dates must be in YYYY-MM-DD format"
            )

        delta = end - start

        prev_start = start - delta
        prev_end = start

    else:
        # unknown type: all-time, empty previous
        start = datetime(2000, 1, 1)
        end = datetime(2100, 1, 1)
        prev_start = datetime(2000, 1, 1)
        prev_end = start
        ptd_applies = False  # B1 FIX

    # M3 FIX: period-to-date comparison. The current period is usually
    # still running (e.g. Jun 1–12 of a 30-day month) while the previous
    # period is complete — comparing partial-current vs full-previous
    # systematically understated every growth figure. Cap the previous
    # window to the same ELAPSED duration as the current one. For ranges
    # already in the past, elapsed == full period, so nothing changes.
    # NOTE: the app sends Week/Month/Year chips as type="custom" with
    # full calendar ranges, so this must cover "custom" too.
    if ptd_applies:
        effective_end = end if end < now else now
        elapsed = effective_end - start
        if elapsed < timedelta(0):
            elapsed = timedelta(0)
        prev_end = prev_start + elapsed

    current = db.query(
        func.sum(Bill.final_amount),
        func.count(Bill.id),
        func.avg(Bill.final_amount)
    ).filter(
        *_bill_filters(current_shop.id),
        Bill.created_at >= start,
        Bill.created_at < end
    ).first()

    previous = db.query(
        func.sum(Bill.final_amount),
        func.count(Bill.id),
        func.avg(Bill.final_amount)
    ).filter(
        *_bill_filters(current_shop.id),
        Bill.created_at >= prev_start,
        Bill.created_at < prev_end
    ).first()

    # R1: net out returns from revenue. average_bill stays the GROSS
    # average ticket (avg of bill totals) — deliberately, since a return
    # doesn't change what the average customer spent at the counter.
    ret_cur = _returns_total(db, current_shop.id, start=start, end=end)
    ret_prev = _returns_total(db, current_shop.id, start=prev_start, end=prev_end)

    return {
        "total_revenue": float(current[0] or 0) - ret_cur,
        "total_bills": int(current[1] or 0),
        "average_bill": float(current[2] or 0),

        "prev_revenue": float(previous[0] or 0) - ret_prev,
        "prev_bills": int(previous[1] or 0),
        "prev_avg": float(previous[2] or 0)
    }


# ================= SALES TREND (LAST 30 DAYS) =================

@router.get("/trend")
def sales_trend(db: Session = Depends(get_db), current_shop=Depends(get_current_shop)):

    last_30_days = local_now() - timedelta(days=30)  # H6: was utcnow()

    rows = db.query(
        func.date(Bill.created_at),
        func.sum(Bill.final_amount)
    ).filter(
        *_bill_filters(current_shop.id),
        Bill.created_at >= last_30_days
    ).group_by(
        func.date(Bill.created_at)
    ).order_by(
        func.date(Bill.created_at)
    ).all()

    # R1: net out returns per day over the same window
    rmap = _returns_map(db, current_shop.id, func.date, start=last_30_days)

    merged = {}
    for r in rows:
        merged[r[0]] = float(r[1] or 0)
    for d, amt in rmap.items():
        merged[d] = merged.get(d, 0.0) - amt

    return [
        {
            "date": str(d),
            "revenue": v
        }
        for d, v in sorted(merged.items())
    ]

# ================= TODAY'S HOURLY SALES =================

from datetime import date
from sqlalchemy import func

@router.get("/today-hourly")
def today_hourly_sales(
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):

    result = (
        db.query(
            func.extract("hour", Bill.created_at).label("hour"),
            func.count(Bill.id).label("bills"),
            func.sum(Bill.final_amount).label("revenue"),
        )
        .filter(
            *_bill_filters(current_shop.id),
            func.date(Bill.created_at) == local_today()  # H6
        )
        .group_by(func.extract("hour", Bill.created_at))
        .order_by(func.extract("hour", Bill.created_at))
        .all()
    )

    # R1: net out today's returns per hour
    day_start = datetime.combine(local_today(), datetime.min.time())
    rmap = _returns_map(
        db, current_shop.id,
        lambda ts: func.extract("hour", ts),
        start=day_start, end=day_start + timedelta(days=1)
    )

    merged = {}
    for r in result:
        merged[int(r.hour)] = {"bills": int(r.bills), "revenue": float(r.revenue or 0)}
    for h, amt in rmap.items():
        entry = merged.setdefault(int(h), {"bills": 0, "revenue": 0.0})
        entry["revenue"] -= amt

    return [
        {
            "hour": h,
            "bills": v["bills"],
            "revenue": v["revenue"]
        }
        for h, v in sorted(merged.items())
    ]

# ================= TOP REVENUE PRODUCTS =================

@router.get("/top-revenue-products")
def top_revenue_products(db: Session = Depends(get_db), current_shop=Depends(get_current_shop)):

    rows = db.query(
        BillItem.product_name,
        func.sum(BillItem.total_amount)
    ).join(Bill).filter(
        *_bill_filters(current_shop.id)
    ).group_by(
        BillItem.product_name
    ).all()

    # R1: net out returns per product BEFORE taking the top 3 — a heavily
    # returned product must not hold a top slot on gross numbers.
    merged = {r[0]: float(r[1] or 0) for r in rows}
    for key, ret in _product_returns_map(db, current_shop.id).items():
        name = key[0]
        merged[name] = merged.get(name, 0.0) - ret["revenue"]

    top = sorted(merged.items(), key=lambda kv: kv[1], reverse=True)[:3]

    return [
        {
            "product": name,
            "revenue": rev
        }
        for name, rev in top
    ]


# ================= WEEKDAY ANALYSIS =================

@router.get("/weekday-analysis")
def weekday_analysis(db: Session = Depends(get_db), current_shop=Depends(get_current_shop)):

    rows = db.query(
        func.extract("dow", Bill.created_at),
        func.sum(Bill.final_amount)
    ).filter(
        *_bill_filters(current_shop.id)
    ).group_by(
        func.extract("dow", Bill.created_at)
    ).order_by(
        func.sum(Bill.final_amount).desc()
    ).all()

    # R1: net out returns per weekday, then re-rank by net revenue
    rmap = _returns_map(
        db, current_shop.id,
        lambda ts: func.extract("dow", ts)
    )

    merged = {}
    for r in rows:
        merged[int(r[0])] = float(r[1] or 0)
    for dow, amt in rmap.items():
        merged[int(dow)] = merged.get(int(dow), 0.0) - amt

    return [
        {
            "weekday": dow,
            "revenue": rev
        }
        for dow, rev in sorted(merged.items(), key=lambda kv: kv[1], reverse=True)
    ]


# ================= EMAIL REPORT =================

@router.post("/email-report")
async def email_report(
    type: str = Query("today"),
    start_date: str | None = None,
    end_date: str | None = None,
    currency: str | None = None,  # I7 FIX: symbol sent by the app
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):

    # ===== DATE RANGE =====

    today = local_today()  # H6: app-timezone "today"

    if type == "today":
        start = today
        end = today

    elif type == "weekly":

        today = local_today()  # H6

        days_since_sunday = (today.weekday() + 1) % 7

        start = today - timedelta(days=days_since_sunday)

        end = start + timedelta(days=6)

    elif type == "monthly":

        start = today.replace(day=1)

        # I1 FIX: end on the LAST day of the current month. Previously end
        # was the 1st of next month, and end_dt (23:59:59 of `end`) pulled
        # that entire day into the monthly report.
        if today.month == 12:
            end = date(today.year + 1, 1, 1) - timedelta(days=1)
        else:
            end = date(today.year, today.month + 1, 1) - timedelta(days=1)

    elif type == "custom":
        if not start_date or not end_date:
            raise HTTPException(status_code=400, detail="Custom dates required")

        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()

    else:
        start = today
        end = today

    # ===== CONVERT TO DATETIME (IMPORTANT FIX) =====

    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.max.time())

    # ===== SUMMARY =====

    r = db.query(
        func.sum(Bill.final_amount),
        func.count(Bill.id),
        func.avg(Bill.final_amount)
    ).filter(
        *_bill_filters(current_shop.id),
        Bill.created_at >= start_dt,
        Bill.created_at <= end_dt
    ).first()

    # R1: net out returns (window end inclusive, matching the bill query)
    returns_total = _returns_total(
        db, current_shop.id,
        start=start_dt, end=end_dt, end_inclusive=True
    )

    summary = {
        "revenue": float(r[0] or 0) - returns_total,
        "bills": int(r[1] or 0),
        "average": float(r[2] or 0)
    }

    # ===== FETCH REPORT DATA =====

    daily = get_daily_report(db, current_shop, start_dt, end_dt)
    monthly = get_monthly_report(db, current_shop, start_dt, end_dt)
    products = get_top_products(db, current_shop, start_dt, end_dt)
    peak_hours_data = get_peak_hours(db, current_shop, start_dt, end_dt)

    # ===== GENERATE PDF =====

    # M4 FIX:
    #  • unique temp dir per request — two same-day requests used to share
    #    one filename, and the first cleanup deleted the second's attachment
    #  • sanitized file name — a shop name containing "/" crashed the build,
    #    and the attachment still shows a clean name (the dir is the random part)
    #  • try/finally — an SMTP failure used to leave the PDF on disk forever
    #  • run_in_threadpool — the ReportLab build is CPU/IO-blocking and used
    #    to stall the whole event loop
    #  • local_today() in the name, matching the report's own timezone
    safe_name = re.sub(
        r"[^A-Za-z0-9_-]+", "_", current_shop.shop_name or "shop"
    ).strip("_") or "shop"

    tmp_dir = tempfile.mkdtemp(prefix="expos_report_")
    file_path = os.path.join(
        tmp_dir,
        f"{safe_name}_{type}_report_{local_today().isoformat()}.pdf"
    )

    try:
        await run_in_threadpool(
            generate_report_pdf,
            file_path,
            summary,
            daily,
            monthly,
            products,
            peak_hours_data,
            shop={
                "name": current_shop.shop_name,
                "address": current_shop.store_address,
                "email": current_shop.email,
                "phone": current_shop.phone,
                "gstin": current_shop.store_gstin,
                "currency": currency  # I7 FIX: was never passed — PDF always showed ₹
            },
        )

        # ===== SEND EMAIL =====

        message = MessageSchema(
            subject=f"{type.upper()} Analytics Report",
            recipients=[current_shop.email],
            body=f"{type.capitalize()} report attached.",
            subtype="plain",
            attachments=[file_path]
        )

        fm = FastMail(mail_config)
        await fm.send_message(message)

    finally:
        # ===== CLEANUP (always, even when PDF build or SMTP fails) =====
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return {"message": f"{type.capitalize()} report sent successfully 📧"}

# ================= OVERVIEW (single-call for Overview fragment) =================

@router.get("/overview")
def overview(
    type: str = "today",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):
    """
    Everything the Overview fragment needs in one round-trip:
    KPIs, returns total, cancelled stats, payment split, 7-day sparkline.
    Uses the same period logic and M3 period-to-date fix as /average-bill.
    """
    now = local_now()
    ptd_applies = True

    if type == "today":
        start = datetime(now.year, now.month, now.day)
        end   = start + timedelta(days=1)
        prev_start = start - timedelta(days=1)
        prev_end   = start

    elif type == "week":
        today = local_today()
        days_since_sunday = (today.weekday() + 1) % 7
        start = datetime.combine(today - timedelta(days=days_since_sunday), datetime.min.time())
        end   = start + timedelta(days=7)
        prev_start = start - timedelta(days=7)
        prev_end   = start

    elif type == "month":
        start = datetime(now.year, now.month, 1)
        end   = datetime(now.year + 1, 1, 1) if now.month == 12 else datetime(now.year, now.month + 1, 1)
        # First day of previous calendar month (see /average-bill note).
        prev_start = (start - timedelta(days=1)).replace(day=1)
        prev_end   = start

    elif type == "year":
        start = datetime(now.year, 1, 1)
        end   = datetime(now.year + 1, 1, 1)
        prev_start = datetime(now.year - 1, 1, 1)
        prev_end   = start

    elif type == "custom":
        if not start_date or not end_date:
            raise HTTPException(status_code=422, detail="start_date and end_date required")
        try:
            start = datetime.fromisoformat(start_date)
            end   = datetime.fromisoformat(end_date) + timedelta(days=1)
        except ValueError:
            raise HTTPException(status_code=422, detail="Dates must be YYYY-MM-DD")
        delta = end - start
        prev_start = start - delta
        prev_end   = start

    else:
        start = datetime(2000, 1, 1)
        end   = datetime(2100, 1, 1)
        prev_start = datetime(2000, 1, 1)
        prev_end   = start
        ptd_applies = False

    # M3 FIX: period-to-date comparison (same as /average-bill)
    if ptd_applies:
        effective_end = end if end < now else now
        elapsed = max(effective_end - start, timedelta(0))
        prev_end = prev_start + elapsed

    # ── KPIs ──────────────────────────────────────────────────────────────────
    current = db.query(
        func.sum(Bill.final_amount),
        func.count(Bill.id),
        func.avg(Bill.final_amount)
    ).filter(
        *_bill_filters(current_shop.id),
        Bill.created_at >= start,
        Bill.created_at < end
    ).first()

    previous = db.query(
        func.sum(Bill.final_amount),
        func.count(Bill.id),
        func.avg(Bill.final_amount)
    ).filter(
        *_bill_filters(current_shop.id),
        Bill.created_at >= prev_start,
        Bill.created_at < prev_end
    ).first()

    ret_cur  = _returns_total(db, current_shop.id, start=start, end=end)
    ret_prev = _returns_total(db, current_shop.id, start=prev_start, end=prev_end)

    # ── Cancelled bills in this period ────────────────────────────────────────
    cancelled = db.query(
        func.count(Bill.id),
        func.coalesce(func.sum(Bill.final_amount), 0.0)
    ).filter(
        Bill.shop_id == current_shop.id,
        Bill.is_cancelled == True,
        Bill.cancelled_at >= start,
        Bill.cancelled_at < end
    ).first()

    # ── Payment split for active bills in this period ─────────────────────────
    pay_rows = db.query(
        Bill.payment_method,
        func.count(Bill.id),
        func.sum(Bill.final_amount)
    ).filter(
        *_bill_filters(current_shop.id),
        Bill.created_at >= start,
        Bill.created_at < end
    ).group_by(Bill.payment_method).all()

    gross_rev = float(current[0] or 0)
    pay_split = []
    for row in pay_rows:
        method_rev = float(row[2] or 0)
        pct = round((method_rev / gross_rev * 100) if gross_rev > 0 else 0)
        pay_split.append({
            "method":  row[0] or "Cash",
            "bills":   int(row[1] or 0),
            "revenue": method_rev,
            "percent": pct,
        })
    pay_split.sort(key=lambda x: x["revenue"], reverse=True)

    # ── 7-day sparkline (always last 7 calendar days, net of returns) ─────────
    spark_start = datetime(now.year, now.month, now.day) - timedelta(days=6)
    spark_rows = db.query(
        func.date(Bill.created_at),
        func.sum(Bill.final_amount)
    ).filter(
        *_bill_filters(current_shop.id),
        Bill.created_at >= spark_start
    ).group_by(func.date(Bill.created_at)).all()

    spark_map  = {str(r[0]): float(r[1] or 0) for r in spark_rows}
    spark_rmap = _returns_map(db, current_shop.id, func.date, start=spark_start)
    for d, amt in spark_rmap.items():
        key = str(d)
        spark_map[key] = spark_map.get(key, 0.0) - amt

    sparkline = [
        spark_map.get(str((spark_start + timedelta(days=i)).date()), 0.0)
        for i in range(7)
    ]

    return {
        "total_revenue":    float(current[0] or 0) - ret_cur,
        "total_bills":      int(current[1] or 0),
        "average_bill":     float(current[2] or 0),
        "returns_total":    ret_cur,
        "cancelled_count":  int(cancelled[0] or 0),
        "cancelled_amount": float(cancelled[1] or 0),
        "payment_split":    pay_split,
        "sparkline":        sparkline,
        "prev_revenue":     float(previous[0] or 0) - ret_prev,
        "prev_bills":       int(previous[1] or 0),
        "prev_avg":         float(previous[2] or 0),
    }


# ================= INTERNAL HELPERS =================

def get_daily_report(db, current_shop, start, end):

    rows = db.query(
        func.date(Bill.created_at),
        func.sum(Bill.final_amount),
        func.count(Bill.id)
    ).filter(
        *_bill_filters(current_shop.id),
        Bill.created_at >= start,
        Bill.created_at <= end
    ).group_by(
        func.date(Bill.created_at)
    ).all()

    # R1: net out returns per day (return-only days included, bills=0)
    rmap = _returns_map(
        db, current_shop.id, func.date,
        start=start, end=end, end_inclusive=True
    )

    merged = {}
    for r in rows:
        merged[r[0]] = {"revenue": float(r[1] or 0), "bills": int(r[2] or 0)}
    for d, amt in rmap.items():
        entry = merged.setdefault(d, {"revenue": 0.0, "bills": 0})
        entry["revenue"] -= amt

    return [
        {
            "date": str(d),
            "revenue": v["revenue"],
            "bills": v["bills"]
        }
        for d, v in sorted(merged.items())
    ]


def get_monthly_report(db, current_shop, start, end):

    rows = db.query(
        func.to_char(Bill.created_at, 'YYYY-MM'),
        func.sum(Bill.final_amount),
        func.count(Bill.id)
    ).filter(
        *_bill_filters(current_shop.id),
        Bill.created_at >= start,
        Bill.created_at <= end
    ).group_by(
        func.to_char(Bill.created_at, 'YYYY-MM')
    ).order_by(
        func.to_char(Bill.created_at, 'YYYY-MM')
    ).all()

    # R1: net out returns per month
    rmap = _returns_map(
        db, current_shop.id,
        lambda ts: func.to_char(ts, 'YYYY-MM'),
        start=start, end=end, end_inclusive=True
    )

    merged = {}
    for r in rows:
        merged[r[0]] = {"revenue": float(r[1] or 0), "bills": int(r[2] or 0)}
    for m, amt in rmap.items():
        entry = merged.setdefault(m, {"revenue": 0.0, "bills": 0})
        entry["revenue"] -= amt

    return [
        {
            "month": m,
            "revenue": v["revenue"],
            "bills": v["bills"]
        }
        for m, v in sorted(merged.items())
    ]


def get_top_products(db, current_shop, start, end):

    rows = db.query(
        BillItem.product_name,
        BillItem.variant,
        BillItem.unit,
        func.sum(BillItem.quantity),
        func.sum(BillItem.total_amount),
        # I3 FIX: distinct bills, not line items (same as /top-products)
        func.count(func.distinct(BillItem.bill_id))
    ).join(Bill).filter(
        *_bill_filters(current_shop.id),
        Bill.created_at >= start,
        Bill.created_at <= end
    ).group_by(
        BillItem.product_name,
        BillItem.variant,
        BillItem.unit
    ).all()

    # R1: net out returns BEFORE picking the top 10 — previously the PDF's
    # top slots were decided on gross revenue, so a heavily-returned
    # product could displace genuinely profitable ones.
    data = [
        {
            "product": r[0],
            "variant": r[1],
            "unit": r[2] or "",
            "quantity": float(r[3] or 0),
            "revenue": float(r[4] or 0),
            "frequency": int(r[5] or 0)
        }
        for r in rows
    ]

    pr = _product_returns_map(
        db, current_shop.id,
        start=start, end=end, end_inclusive=True
    )

    index = {(x["product"], x["variant"], x["unit"]): x for x in data}
    for key, ret in pr.items():
        x = index.get(key)
        if x is None:
            x = {
                "product": key[0], "variant": key[1], "unit": key[2],
                "quantity": 0.0, "revenue": 0.0, "frequency": 0
            }
            data.append(x)
            index[key] = x
        x["quantity"] -= ret["qty"]
        x["revenue"] -= ret["revenue"]

    data.sort(key=lambda x: x["revenue"], reverse=True)

    return data[:10]


def get_peak_hours(db, current_shop, start, end):

    rows = db.query(
        func.extract("hour", Bill.created_at),
        func.count(Bill.id),
        func.sum(Bill.final_amount)
    ).filter(
        *_bill_filters(current_shop.id),
        Bill.created_at >= start,
        Bill.created_at <= end
    ).group_by(
        func.extract("hour", Bill.created_at)
    ).all()

    # R1: net out returns per hour
    rmap = _returns_map(
        db, current_shop.id,
        lambda ts: func.extract("hour", ts),
        start=start, end=end, end_inclusive=True
    )

    merged = {}
    for r in rows:
        merged[int(r[0])] = {"bills": int(r[1] or 0), "revenue": float(r[2] or 0)}
    for h, amt in rmap.items():
        entry = merged.setdefault(int(h), {"bills": 0, "revenue": 0.0})
        entry["revenue"] -= amt

    return [
        {
            "hour": h,
            "bills": v["bills"],
            "revenue": v["revenue"]
        }
        for h, v in sorted(merged.items())
    ]