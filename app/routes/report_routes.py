import os

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta

from fastapi_mail import FastMail, MessageSchema
from fastapi import Depends
from app.dependencies import get_current_shop

from app.database import get_db
from app.dependencies import get_current_shop
from app.models.bill import Bill
from app.models.bill_items import BillItem
from app.core.config import mail_config
from app.util.report_generator import generate_report_pdf

router = APIRouter(prefix="/reports", tags=["Reports"])


# ================= DAILY SALES =================

@router.get("/daily")
def daily_report(db: Session = Depends(get_db), current_shop=Depends(get_current_shop)):

    rows = db.query(
        func.date(Bill.created_at),
        func.sum(Bill.total_amount),
        func.count(Bill.id)
    ).filter(
        Bill.shop_id == current_shop.id
    ).group_by(
        func.date(Bill.created_at)
    ).order_by(
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


# ================= MONTHLY SALES =================

@router.get("/monthly")
def monthly_report(db: Session = Depends(get_db), current_shop=Depends(get_current_shop)):

    rows = db.query(
        func.date_trunc("month", Bill.created_at),
        func.sum(Bill.total_amount),
        func.count(Bill.id)
    ).filter(
        Bill.shop_id == current_shop.id
    ).group_by(
        func.date_trunc("month", Bill.created_at)
    ).order_by(
        func.date_trunc("month", Bill.created_at)
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
        Bill.shop_id == current_shop.id
    ).group_by(
        func.extract("year", Bill.created_at)
    ).order_by(
        func.extract("year", Bill.created_at)
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
def top_products(db: Session = Depends(get_db), current_shop=Depends(get_current_shop)):

    rows = db.query(
        BillItem.product_name,
        func.sum(BillItem.quantity),
        func.sum(BillItem.subtotal)
    ).join(Bill).filter(
        Bill.shop_id == current_shop.id
    ).group_by(
        BillItem.product_name
    ).order_by(
        func.sum(BillItem.quantity).desc()
    ).limit(10).all()

    return [
        {
            "product": r[0],
            "quantity": int(r[1] or 0),
            "revenue": float(r[2] or 0)
        }
        for r in rows
    ]


# ================= PEAK HOURS =================

@router.get("/peak-hours")
def peak_hours(db: Session = Depends(get_db), current_shop=Depends(get_current_shop)):

    rows = db.query(
        func.extract("hour", Bill.created_at),
        func.count(Bill.id),
        func.sum(Bill.total_amount)
    ).filter(
        Bill.shop_id == current_shop.id
    ).group_by(
        func.extract("hour", Bill.created_at)
    ).order_by(
        func.sum(Bill.total_amount).desc()
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
def average_bill(db: Session = Depends(get_db), current_shop=Depends(get_current_shop)):

    r = db.query(
        func.avg(Bill.total_amount),
        func.sum(Bill.total_amount),
        func.count(Bill.id)
    ).filter(
        Bill.shop_id == current_shop.id
    ).first()

    return {
        "average_bill": float(r[0] or 0),
        "total_revenue": float(r[1] or 0),
        "total_bills": int(r[2] or 0)
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


# ================= TOP REVENUE PRODUCTS =================

@router.get("/top-revenue-products")
def top_revenue_products(db: Session = Depends(get_db), current_shop=Depends(get_current_shop)):

    rows = db.query(
        BillItem.product_name,
        func.sum(BillItem.subtotal)
    ).join(Bill).filter(
        Bill.shop_id == current_shop.id
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
        Bill.shop_id == current_shop.id
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
async def email_report(db: Session = Depends(get_db), current_shop=Depends(get_current_shop)):

    # ===== SUMMARY =====

    r = db.query(
        func.sum(Bill.total_amount),
        func.count(Bill.id),
        func.avg(Bill.total_amount)
    ).filter(
        Bill.shop_id == current_shop.id
    ).first()

    summary = {
        "revenue": float(r[0] or 0),
        "bills": int(r[1] or 0),
        "average": float(r[2] or 0)
    }

    # ===== DAILY =====

    daily = daily_report(db, current_shop)

    # ===== MONTHLY =====

    monthly = monthly_report(db, current_shop)

    # ===== PRODUCTS =====

    products = top_products(db, current_shop)

    # ===== PEAK HOURS =====

    peak_hours_data = peak_hours(db, current_shop)

    # ===== GENERATE PDF =====

    file_path = f"{current_shop.shop_name}_{current_shop.id}_analytics_report_{datetime.now().strftime('%Y-%m-%d')}.pdf"

    generate_report_pdf(
        file_path,
        summary,
        daily,
        monthly,
        products,
        peak_hours_data
    )

    # ===== SEND EMAIL =====

    message = MessageSchema(
        subject="Shop Analytics Report",
        recipients=[current_shop.email],
        body="Attached is your shop analytics report.",
        subtype="plain",
        attachments=[file_path]
    )

    fm = FastMail(mail_config)
    await fm.send_message(message)

    if os.path.exists(file_path):
        os.remove(file_path)
    return {"message": "Report sent successfully"}
