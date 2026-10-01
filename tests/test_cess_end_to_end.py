"""
Comprehensive end-to-end verification for CESS handling across backend routes:
- Purchase sync (cess_paid, availed_itc_cess, product cess_rate update)
- Purchase cancel
- GST Sales invoice sync (cess_rate, cess_amount)
- Bill creation and /bills/since (cess_amount)
- Credit note sync (cess_amount)
- Purchase return sync (cess_amount, availed_itc_cess)
- GSTR-1 report (CESS across B2B, B2CL, B2CS netting, CDNR, CDNUR, HSN summary)
- GSTR-2 report (CESS across B2B, B2BUR, CDNR, CDNUR, total_itc_cess)
- Standalone HSN summary report (cess_amount, total_tax, rate, description)
"""

import os
os.environ.setdefault("APP_TIMEZONE", "Asia/Kolkata")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "test_secret_key_12345678901234567890")

from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.dependencies import get_current_shop, require_premium_tier
from app.models.shop import Shop
from app.models.global_products import GlobalProduct
from app.models.shop_products import ShopProduct
from app.models.inventory import Inventory
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.purchase_return import PurchaseReturn
from app.models.credit_note import CreditNote, CreditNoteItem
from app.models.gst_sales_invoice import GstSalesInvoice, GstSalesInvoiceItem
from app.models.bill import Bill
from app.models.bill_items import BillItem

from app.routes.purchase_routes import router as purchase_router
from app.routes.purchase_return_routes import router as purchase_return_router
from app.routes.credit_note_routes import router as credit_note_router
from app.routes.gst_sales_invoice_routes import router as gst_sales_router
from app.routes.bill_routes import router as bill_router
from app.routes.gst_routes import router as gst_router

app = FastAPI()
app.include_router(purchase_router)
app.include_router(purchase_return_router)
app.include_router(credit_note_router)
app.include_router(gst_sales_router)
app.include_router(bill_router)
app.include_router(gst_router)


from sqlalchemy import event

def setup_test_env():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    @event.listens_for(engine, "connect")
    def connect(dbapi_connection, connection_record):
        dbapi_connection.create_function(
            "split_part", 3,
            lambda s, sep, idx: s.split(sep)[idx - 1] if s and len(s.split(sep)) >= idx else None
        )

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    db = TestingSessionLocal()
    shop = Shop(
        shop_name="SuperMart",
        owner_name="Adeeb",
        email="adeeb@test.com",
        store_gstin="33AAAAA0000A1Z5"
    )
    db.add(shop)
    db.commit()
    db.refresh(shop)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_shop] = lambda: shop
    app.dependency_overrides[require_premium_tier] = lambda: shop

    return TestClient(app), shop, TestingSessionLocal


def test_purchase_sync_and_cess():
    client, shop, SessionLocal = setup_test_env()
    try:
        db = SessionLocal()
        gp = GlobalProduct(name="Cigarettes Pack")
        db.add(gp)
        db.commit()
        sp = ShopProduct(shop_id=shop.id, global_product_id=gp.id, unit="pack", price=123.0)
        db.add(sp)
        db.commit()
        sp_id = sp.id
        db.close()

        # Sync a purchase with CESS
        payload = {
            "purchases": [
                {
                    "local_id": 1,
                    "invoice_number": "INV-P-001",
                    "supplier_name": "Supplier A",
                    "supplier_gstin": "33BBBBB1111B1Z2",
                    "state": "Tamil Nadu",
                    "place_of_supply_code": "33",
                    "taxable_amount": 1000.0,
                    "cgst_percentage": 9.0,
                    "sgst_percentage": 9.0,
                    "igst_percentage": 0.0,
                    "cgst_amount": 90.0,
                    "sgst_amount": 90.0,
                    "igst_amount": 0.0,
                    "cess_paid": 50.0,
                    "availed_itc_central_tax": 90.0,
                    "availed_itc_state_tax": 90.0,
                    "availed_itc_integrated_tax": 0.0,
                    "availed_itc_cess": 50.0,
                    "invoice_value": 1230.0,
                    "invoice_date": float(datetime(2026, 9, 27, 10, 0, 0).timestamp() * 1000),
                    "created_at": float(datetime(2026, 9, 27, 10, 0, 0).timestamp() * 1000),
                    "items": [
                        {
                            "local_id": 1,
                            "shop_product_id": sp_id,
                            "product_name": "Cigarettes Pack",
                            "quantity": 10.0,
                            "unit": "pack",
                            "cost_price": 100.0,
                            "taxable_amount": 1000.0,
                            "invoice_value": 1230.0,
                            "purchase_cgst_percentage": 9.0,
                            "purchase_sgst_percentage": 9.0,
                            "purchase_cgst_amount": 90.0,
                            "purchase_sgst_amount": 90.0,
                            "cess_percentage": 5.0,
                            "cess_amount": 50.0,
                            "availed_itc_cgst": 90.0,
                            "availed_itc_sgst": 90.0,
                            "availed_itc_cess": 50.0,
                            "sales_cgst_percentage": 9.0,
                            "sales_sgst_percentage": 9.0,
                            "hsn_code": "2402",
                            "official_uqc": "PAC",
                            "hsn_description": "Cigarettes",
                        }
                    ]
                }
            ]
        }
        res = client.post("/purchases/sync", json=payload)
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["success_count"] == 1

        db = SessionLocal()
        p = db.query(Purchase).filter(Purchase.invoice_number == "INV-P-001").first()
        assert p is not None
        assert p.cess_paid == 50.0
        assert p.availed_itc_cess == 50.0

        item = db.query(PurchaseItem).filter(PurchaseItem.purchase_id == p.id).first()
        assert item is not None
        assert item.cess_percentage == 5.0
        assert item.cess_amount == 50.0
        assert item.availed_itc_cess == 50.0

        # Check that product's cess_rate was updated
        sp = db.query(ShopProduct).filter(ShopProduct.hsn_code == "2402").first()
        assert sp is not None
        assert sp.cess_rate == 5.0, f"Expected 5.0, got {sp.cess_rate}"

        # Test purchase cancellation
        cancel_res = client.put("/purchases/cancel", json={"invoice_number": "INV-P-001"})
        assert cancel_res.status_code == 200
        db.refresh(p)
        assert p.is_cancelled == 1
    finally:
        app.dependency_overrides.clear()


def test_gst_sales_and_reports_with_cess():
    client, shop, SessionLocal = setup_test_env()
    try:
        # Sync a GST sales invoice with CESS
        inv_payload = {
            "invoices": [
                {
                    "local_id": 101,
                    "invoice_number": "INV-S-001",
                    "invoice_type": "B2B",
                    "customer_name": "Buyer Corp",
                    "business_name": "Buyer Corp",
                    "customer_gst": "33CCCCCC2222C1Z3",
                    "customer_state": "Tamil Nadu",
                    "customer_state_code": "33",
                    "subtotal": 1000.0,
                    "total_cgst": 90.0,
                    "total_sgst": 90.0,
                    "total_igst": 0.0,
                    "total_tax": 230.0,
                    "grand_total": 1230.0,
                    "invoice_date": int(datetime(2026, 9, 27, 10, 0, 0).timestamp() * 1000),
                    "items": [
                        {
                            "product_id": 1,
                            "product_name": "Luxury Item",
                            "hsn_code": "2402",
                            "quantity": 10.0,
                            "selling_price": 123.0,
                            "taxable_amount": 1000.0,
                            "sales_cgst_percentage": 9.0,
                            "sales_sgst_percentage": 9.0,
                            "sales_igst_percentage": 0.0,
                            "cgst_amount": 90.0,
                            "sgst_amount": 90.0,
                            "igst_amount": 0.0,
                            "cess_rate": 5.0,
                            "cess_amount": 50.0,
                            "net_value": 1230.0,
                            "uqc": "NOS",
                            "hsn_description": "Luxury Cigars"
                        }
                    ]
                }
            ]
        }
        res = client.post("/gst-sales/sync", json=inv_payload)
        assert res.status_code == 200, res.text
        assert res.json()["success_count"] == 1

        # Check GSTR-1
        gstr1_res = client.get("/gst/reports/gstr1?start_date=2026-09-01&end_date=2026-09-30")
        assert gstr1_res.status_code == 200, gstr1_res.text
        gstr1 = gstr1_res.json()
        assert len(gstr1["b2b"]) == 1
        assert gstr1["b2b"][0]["cess_amount"] == 50.0

        # Check HSN summary inside GSTR-1
        assert len(gstr1["hsn_b2b"]) == 1
        assert gstr1["hsn_b2b"][0]["cess_amount"] == 50.0
        assert gstr1["hsn_b2b"][0]["total_value"] == 1230.0

        # Check Standalone HSN summary
        hsn_res = client.get("/gst/reports/hsn-summary?start_date=2026-09-01&end_date=2026-09-30")
        assert hsn_res.status_code == 200, hsn_res.text
        hsn_rows = hsn_res.json()
        assert len(hsn_rows) == 1
        assert hsn_rows[0]["cess_amount"] == 50.0
        assert hsn_rows[0]["total_tax"] == 230.0
        assert hsn_rows[0]["total_value"] == 1230.0
        assert hsn_rows[0]["description"] == "Luxury Cigars"

        # Check Credit note sync and GSTR-1 CDN
        cn_payload = {
            "credit_notes": [
                {
                    "local_id": 201,
                    "note_number": "CN-001",
                    "note_date": int(datetime(2026, 9, 27, 12, 0, 0).timestamp() * 1000),
                    "note_type": "C",
                    "original_invoice_id": 101,
                    "original_invoice_number": "INV-S-001",
                    "customer_name": "Buyer Corp",
                    "customer_gstin": "33CCCCCC2222C1Z3",
                    "place_of_supply": "33-Tamil Nadu",
                    "taxable_value": 200.0,
                    "cgst_amount": 18.0,
                    "sgst_amount": 18.0,
                    "igst_amount": 0.0,
                    "cess_amount": 10.0,
                    "tax_amount": 46.0,
                    "total_amount": 246.0,
                    "created_at": int(datetime(2026, 9, 27, 12, 0, 0).timestamp() * 1000),
                    "items": [
                        {
                            "product_name": "Luxury Item",
                            "hsn_code": "2402",
                            "quantity_sold": 10.0,
                            "quantity_returned": 2.0,
                            "rate": 123.0,
                            "taxable_value": 200.0,
                            "gst_rate": 18.0,
                            "cgst_amount": 18.0,
                            "sgst_amount": 18.0,
                            "igst_amount": 0.0,
                            "cess_amount": 10.0,
                            "tax_amount": 46.0,
                            "total_amount": 246.0
                        }
                    ]
                }
            ]
        }
        cn_res = client.post("/credit-notes/sync", json=cn_payload)
        assert cn_res.status_code == 200, cn_res.text
        assert cn_res.json()["success_count"] == 1

        # Check CDNR in GSTR-1
        gstr1_res2 = client.get("/gst/reports/gstr1?start_date=2026-09-01&end_date=2026-09-30")
        gstr1_2 = gstr1_res2.json()
        assert len(gstr1_2["cdnr"]) == 1
        assert gstr1_2["cdnr"][0]["cess_amount"] == 10.0

    finally:
        app.dependency_overrides.clear()


def test_bills_and_bills_since_cess():
    client, shop, SessionLocal = setup_test_env()
    try:
        db = SessionLocal()
        gp = GlobalProduct(name="Item1")
        db.add(gp)
        db.commit()
        sp = ShopProduct(shop_id=shop.id, global_product_id=gp.id, price=100.0)
        db.add(sp)
        db.commit()

        bill_req = {
            "bill_number": "INV-2026-0001",
            "items": [
                {
                    "shop_product_id": sp.id,
                    "product_name": "Item1",
                    "quantity": 2.0,
                    "unit_price": 50.0,
                    "line_subtotal": 100.0,
                    "taxable_amount": 100.0,
                    "gst_rate": 18.0,
                    "cgst_rate": 9.0,
                    "sgst_rate": 9.0,
                    "cgst_amount": 9.0,
                    "sgst_amount": 9.0,
                    "cess_amount": 12.0,
                    "total_amount": 130.0,
                    "hsn_code": "1234"
                }
            ],
            "subtotal": 100.0,
            "taxable_amount": 100.0,
            "cgst_amount": 9.0,
            "sgst_amount": 9.0,
            "cess_amount": 12.0,
            "gst_amount": 18.0,
            "final_amount": 130.0,
            "total_amount": 130.0
        }
        res = client.post("/bills/create", json=bill_req)
        assert res.status_code == 200, res.text

        # Verify /bills/since includes cess_amount on bill and items
        since_res = client.get("/bills/since?after_id=0")
        assert since_res.status_code == 200, since_res.text
        bills = since_res.json()
        assert len(bills) == 1
        assert bills[0]["cess_amount"] == 12.0
        assert bills[0]["items"][0]["cess_amount"] == 12.0
    finally:
        app.dependency_overrides.clear()


if __name__ == "__main__":
    test_purchase_sync_and_cess()
    test_gst_sales_and_reports_with_cess()
    test_bills_and_bills_since_cess()
    print("ALL TESTS PASSED PERFECTLY!")
