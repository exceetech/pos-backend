import os

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
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


from app.models.shop_products import ShopProduct
from app.models.global_products import GlobalProduct

SHOP_WEIGHTS = {

    "grocery":  {"qty": 0.1, "rev": 0.7, "freq": 0.2},

    "hotel":    {"qty": 0.2, "rev": 0.3, "freq": 0.5},

    "bakery":   {"qty": 0.3, "rev": 0.4, "freq": 0.3},

    "general":  {"qty": 0.2, "rev": 0.5, "freq": 0.3}

}

router = APIRouter(prefix="/reports", tags=["Reports"])


# ================= DAILY SALES =================

@router.get("/daily")
def daily_report(db: Session = Depends(get_db), current_shop=Depends(get_current_shop)):

    rows = db.query(
        func.date(Bill.created_at),
        func.sum(Bill.total_amount),
        func.count(Bill.id)
    ).filter(
        Bill.shop_id == current_shop.id,
        Bill.active == True
    ).group_by(
        func.date(Bill.created_at)
    ).order_by(
        func.date(Bill.created_at).desc()
    ).all()

    return [
        {
            "date": str(r[0]),
            "revenue": float(r[1] or 0),
            "bills": int(r[2] or 0)
        }
        for r in rows
    ]


# ================= MONTHLY SALES =================

@router.get("/monthly")
def monthly_report(db: Session = Depends(get_db), current_shop=Depends(get_current_shop)):

    rows = db.query(
        func.date_trunc("month", Bill.created_at),
        func.sum(Bill.total_amount),
        func.count(Bill.id)
    ).filter(
        Bill.shop_id == current_shop.id,
        Bill.active == True
    ).group_by(
        func.date_trunc("month", Bill.created_at)
    ).order_by(
        func.date_trunc("month", Bill.created_at).desc()
    ).all()

    return [
        {
            "month": str(r[0]),
            "revenue": float(r[1] or 0),
            "bills": int(r[2] or 0)
        }
        for r in rows
    ]


# ================= YEARLY SALES =================

@router.get("/yearly")
def yearly_report(db: Session = Depends(get_db), current_shop=Depends(get_current_shop)):

    rows = db.query(
        func.extract("year", Bill.created_at),
        func.sum(Bill.total_amount),
        func.count(Bill.id)
    ).filter(
        Bill.shop_id == current_shop.id,
        Bill.active == True
    ).group_by(
        func.extract("year", Bill.created_at)
    ).order_by(
        func.extract("year", Bill.created_at).desc()
    ).all()

    return [
        {
            "year": int(r[0]),
            "revenue": float(r[1] or 0),
            "bills": int(r[2] or 0)
        }
        for r in rows
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
        func.sum(BillItem.subtotal).label("revenue"),
        func.count(BillItem.id).label("frequency")
    ).join(Bill).filter(
    Bill.shop_id == current_shop.id,
    Bill.active == True
)

    if type == "today":
        today = date.today()
        query = query.filter(func.date(Bill.created_at) == today)

    elif type == "custom" and start and end:
        try:
            start_date = datetime.strptime(start, "%Y-%m-%d").date()
            end_date = datetime.strptime(end, "%Y-%m-%d").date()

            query = query.filter(
                func.date(Bill.created_at) >= start_date,
                func.date(Bill.created_at) <= end_date
            )
        except Exception as e:
            print("Date parse error:", e)

    rows = query.group_by(
        BillItem.product_name,
        BillItem.variant,
        BillItem.unit
    ).limit(100).all()

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
        "quantity": int(x["quantity"]),
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
        func.sum(Bill.total_amount)
    ).filter(
        Bill.shop_id == current_shop.id,
        Bill.active == True
    )

    now = datetime.utcnow()

    if type == "today":

        start = datetime.combine(date.today(), datetime.min.time())
        end = start + timedelta(days=1)

        query = query.filter(
            Bill.created_at >= start,
            Bill.created_at < end
        )

    elif type == "week":

        start = now - timedelta(days=7)
        end = now

        query = query.filter(
            Bill.created_at >= start,
            Bill.created_at < end
        )

    elif type == "month":

        start = now - timedelta(days=30)
        end = now

        query = query.filter(
            Bill.created_at >= start,
            Bill.created_at < end
        )

    elif type == "year":

        start = now - timedelta(days=365)
        end = now

        query = query.filter(
            Bill.created_at >= start,
            Bill.created_at < end
        )

    elif type == "custom" and start_date and end_date:

        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)

        query = query.filter(
            Bill.created_at >= start,
            Bill.created_at < end
        )

    rows = query.group_by(
        func.extract("hour", Bill.created_at)
    ).order_by(
        func.extract("hour", Bill.created_at)
    ).all()

    return [
        {
            "hour": int(r[0]),
            "bills": int(r[1] or 0),
            "revenue": float(r[2] or 0)
        }
        for r in rows
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

    now = datetime.now()

    if type == "today":

        start = datetime(now.year, now.month, now.day)
        end = start + timedelta(days=1)

        prev_start = start - timedelta(days=1)
        prev_end = start

    elif type == "week":

        today = date.today()

        start = today - timedelta(days=today.weekday() + 1)
        end = start + timedelta(days=7)

        prev_start = start - timedelta(days=7)
        prev_end = start

    elif type == "month":

        start = datetime(now.year, now.month, 1)

        if now.month == 12:
            end = datetime(now.year + 1, 1, 1)
        else:
            end = datetime(now.year, now.month + 1, 1)

        prev_start = start - (end - start)
        prev_end = start

    elif type == "year":

        start = datetime(now.year, 1, 1)
        end = datetime(now.year + 1, 1, 1)

        prev_start = datetime(now.year - 1, 1, 1)
        prev_end = start

    elif type == "custom" and start_date and end_date:

        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date) + timedelta(days=1)

        delta = end - start

        prev_start = start - delta
        prev_end = start

    else:
        start = datetime.min
        end = datetime.max
        prev_start = datetime.min
        prev_end = start

    current = db.query(
        func.sum(Bill.total_amount),
        func.count(Bill.id),
        func.avg(Bill.total_amount)
    ).filter(
        Bill.shop_id == current_shop.id,
        Bill.active == True,
        Bill.created_at >= start,
        Bill.created_at < end
    ).first()

    previous = db.query(
        func.sum(Bill.total_amount),
        func.count(Bill.id),
        func.avg(Bill.total_amount)
    ).filter(
        Bill.shop_id == current_shop.id,
        Bill.active == True,
        Bill.created_at >= prev_start,
        Bill.created_at < prev_end
    ).first()

    return {
        "total_revenue": float(current[0] or 0),
        "total_bills": int(current[1] or 0),
        "average_bill": float(current[2] or 0),

        "prev_revenue": float(previous[0] or 0),
        "prev_bills": int(previous[1] or 0),
        "prev_avg": float(previous[2] or 0)
    }


# ================= SALES TREND (LAST 30 DAYS) =================

@router.get("/trend")
def sales_trend(db: Session = Depends(get_db), current_shop=Depends(get_current_shop)):

    last_30_days = datetime.utcnow() - timedelta(days=30)

    rows = db.query(
        func.date(Bill.created_at),
        func.sum(Bill.total_amount)
    ).filter(
        Bill.shop_id == current_shop.id,
        Bill.active == True,
        Bill.created_at >= last_30_days
    ).group_by(
        func.date(Bill.created_at)
    ).order_by(
        func.date(Bill.created_at)
    ).all()

    return [
        {
            "date": str(r[0]),
            "revenue": float(r[1] or 0)
        }
        for r in rows
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
            func.sum(Bill.total_amount).label("revenue"),
        )
        .filter(
            Bill.shop_id == current_shop.id,   # 🔥 CRITICAL FIX
            Bill.active == True,               # 🔥 IMPORTANT
            func.date(Bill.created_at) == date.today()
        )
        .group_by(func.extract("hour", Bill.created_at))
        .order_by(func.extract("hour", Bill.created_at))
        .all()
    )

    return [
        {
            "hour": int(r.hour),
            "bills": int(r.bills),
            "revenue": float(r.revenue or 0)
        }
        for r in result
    ]

# ================= TOP REVENUE PRODUCTS =================

@router.get("/top-revenue-products")
def top_revenue_products(db: Session = Depends(get_db), current_shop=Depends(get_current_shop)):

    rows = db.query(
        BillItem.product_name,
        func.sum(BillItem.subtotal)
    ).join(Bill).filter(
        Bill.shop_id == current_shop.id,
        Bill.active == True
    ).group_by(
        BillItem.product_name
    ).order_by(
        func.sum(BillItem.subtotal).desc()
    ).limit(3).all()

    return [
        {
            "product": r[0],
            "revenue": float(r[1] or 0)
        }
        for r in rows
    ]


# ================= WEEKDAY ANALYSIS =================

@router.get("/weekday-analysis")
def weekday_analysis(db: Session = Depends(get_db), current_shop=Depends(get_current_shop)):

    rows = db.query(
        func.extract("dow", Bill.created_at),
        func.sum(Bill.total_amount)
    ).filter(
        Bill.shop_id == current_shop.id,
        Bill.active == True
    ).group_by(
        func.extract("dow", Bill.created_at)
    ).order_by(
        func.sum(Bill.total_amount).desc()
    ).all()

    return [
        {
            "weekday": int(r[0]),
            "revenue": float(r[1] or 0)
        }
        for r in rows
    ]


# ================= EMAIL REPORT =================

@router.post("/email-report")
async def email_report(
    type: str = Query("today"),
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):

    # ===== DATE RANGE =====

    today = datetime.today().date()

    if type == "today":
        start = today
        end = today

    elif type == "weekly":

        today = date.today()

        days_since_sunday = (today.weekday() + 1) % 7

        start = today - timedelta(days=days_since_sunday)

        end = start + timedelta(days=6)

    elif type == "monthly":

        start = today.replace(day=1)

        if today.month == 12:
            end = date(today.year + 1, 1, 1)
        else:
            end = date(today.year, today.month + 1, 1)

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
        func.sum(Bill.total_amount),
        func.count(Bill.id),
        func.avg(Bill.total_amount)
    ).filter(
        Bill.shop_id == current_shop.id,
        Bill.active == True,
        Bill.created_at >= start_dt,
        Bill.created_at <= end_dt
    ).first()

    summary = {
        "revenue": float(r[0] or 0),
        "bills": int(r[1] or 0),
        "average": float(r[2] or 0)
    }

    # ===== FETCH REPORT DATA =====

    daily = get_daily_report(db, current_shop, start_dt, end_dt)
    monthly = get_monthly_report(db, current_shop, start_dt, end_dt)
    products = get_top_products(db, current_shop, start_dt, end_dt)
    peak_hours_data = get_peak_hours(db, current_shop, start_dt, end_dt)

    # ===== GENERATE PDF =====

    file_path = f"{current_shop.shop_name}_{type}_report_{datetime.now().strftime('%Y-%m-%d')}.pdf"

    generate_report_pdf(
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
        "gstin": current_shop.store_gstin
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

    # ===== CLEANUP =====

    if os.path.exists(file_path):
        os.remove(file_path)

    return {"message": f"{type.capitalize()} report sent successfully 📧"}

# ================= INTERNAL HELPERS =================

def get_daily_report(db, current_shop, start, end):

    rows = db.query(
        func.date(Bill.created_at),
        func.sum(Bill.total_amount),
        func.count(Bill.id)
    ).filter(
        Bill.shop_id == current_shop.id,
        Bill.active == True,
        Bill.created_at >= start,
        Bill.created_at <= end
    ).group_by(
        func.date(Bill.created_at)
    ).all()

    return [
        {
            "date": str(r[0]),
            "revenue": float(r[1] or 0),
            "bills": int(r[2] or 0)
        }
        for r in rows
    ]


def get_monthly_report(db, current_shop, start, end):

    rows = db.query(
        func.to_char(Bill.created_at, 'YYYY-MM'),
        func.sum(Bill.total_amount),
        func.count(Bill.id)
    ).filter(
        Bill.shop_id == current_shop.id,
        Bill.active == True,
        Bill.created_at >= start,
        Bill.created_at <= end        
    ).group_by(
        func.to_char(Bill.created_at, 'YYYY-MM')
    ).order_by(
        func.to_char(Bill.created_at, 'YYYY-MM')
    ).all()

    return [
        {
            "month": r[0],
            "revenue": float(r[1] or 0),
            "bills": int(r[2] or 0)
        }
        for r in rows
    ]


def get_top_products(db, current_shop, start, end):

    rows = db.query(
        BillItem.product_name,
        BillItem.variant,
        BillItem.unit,
        func.sum(BillItem.quantity),
        func.sum(BillItem.subtotal),
        func.count(BillItem.id)
    ).join(Bill).filter(
        Bill.shop_id == current_shop.id,
        Bill.active == True,
        Bill.created_at >= start,
        Bill.created_at <= end
    ).group_by(
        BillItem.product_name,
        BillItem.variant,
        BillItem.unit
    ).order_by(
        func.sum(BillItem.subtotal).desc()
    ).limit(10).all()

    return [
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


def get_peak_hours(db, current_shop, start, end):

    rows = db.query(
        func.extract("hour", Bill.created_at),
        func.count(Bill.id),
        func.sum(Bill.total_amount)
    ).filter(
        Bill.shop_id == current_shop.id,
        Bill.active == True,
        Bill.created_at >= start,
        Bill.created_at <= end
    ).group_by(
        func.extract("hour", Bill.created_at)
    ).all()

    return [
        {
            "hour": int(r[0]),
            "bills": int(r[1] or 0),
            "revenue": float(r[2] or 0)
        }
        for r in rows
    ]