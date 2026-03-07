from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.dependencies import get_current_shop
from app.models.bill import Bill
from app.models.bill_items import BillItem

router = APIRouter(prefix="/reports", tags=["Reports"])

@router.get("/daily")
def daily_report(
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):

    result = db.query(
        func.date(Bill.created_at),
        func.sum(Bill.total_amount)
    ).filter(
        Bill.shop_id == current_shop.id
    ).group_by(
        func.date(Bill.created_at)
    ).all()

    return result

@router.get("/top-products")
def top_products(
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):

    result = db.query(
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

    return result

@router.get("/peak-hours")
def peak_hours(
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):

    result = db.query(
        func.extract("hour", Bill.created_at).label("hour"),
        func.count(Bill.id).label("total_bills"),
        func.sum(Bill.total_amount).label("revenue")
    ).filter(
        Bill.shop_id == current_shop.id
    ).group_by(
        func.extract("hour", Bill.created_at)
    ).order_by(
        func.sum(Bill.total_amount).desc()
    ).all()

    return result

@router.get("/monthly")
def monthly_report(
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):

    result = db.query(
        func.date_trunc("month", Bill.created_at).label("month"),
        func.sum(Bill.total_amount).label("revenue"),
        func.count(Bill.id).label("total_bills")
    ).filter(
        Bill.shop_id == current_shop.id
    ).group_by(
        func.date_trunc("month", Bill.created_at)
    ).order_by(
        func.date_trunc("month", Bill.created_at)
    ).all()

    return result

@router.get("/yearly")
def yearly_report(
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):

    result = db.query(
        func.extract("year", Bill.created_at).label("year"),
        func.sum(Bill.total_amount).label("revenue"),
        func.count(Bill.id).label("total_bills")
    ).filter(
        Bill.shop_id == current_shop.id
    ).group_by(
        func.extract("year", Bill.created_at)
    ).order_by(
        func.extract("year", Bill.created_at)
    ).all()

    return result

@router.get("/average-bill")
def average_bill_value(
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):

    result = db.query(
        func.avg(Bill.total_amount).label("average_bill"),
        func.sum(Bill.total_amount).label("total_revenue"),
        func.count(Bill.id).label("total_bills")
    ).filter(
        Bill.shop_id == current_shop.id
    ).first()

    return result