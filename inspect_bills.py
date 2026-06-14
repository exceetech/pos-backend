import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv("app/.env")
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
session = SessionLocal()

from app.models.bill import Bill
from app.models.bill_items import BillItem

bills = session.query(Bill).order_by(Bill.id.desc()).limit(5).all()

for b in bills:
    print(f"Bill ID: {b.id}, final_amount: {b.final_amount}, cgst: {b.cgst_amount}, subtotal: {b.subtotal}, round_off: {b.round_off}, supply: {b.supply_type}, gst_scheme: {b.gst_scheme}")
    
    items = session.query(BillItem).filter(BillItem.bill_id == b.id).all()
    for i in items:
        print(f"  Item: {i.product_name}, unit_price: {i.unit_price}, qty: {i.quantity}, line_subtotal: {i.line_subtotal}, gst_rate: {i.gst_rate}, cgst_amount: {i.cgst_amount}")
    print("-" * 40)
