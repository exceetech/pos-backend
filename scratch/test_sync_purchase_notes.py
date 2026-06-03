import sys
import os
from datetime import datetime, timedelta
import requests

# Set python path to allow importing app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal
from app.models.shop import Shop
from app.models.subscription import Subscription
from app.models.purchase_return import PurchaseReturn
from app.security import create_access_token

def setup_test_shop_and_token():
    db = SessionLocal()
    try:
        # 1. Get or create shop
        shop = db.query(Shop).first()
        if not shop:
            print("No shops found, creating a test shop...")
            shop = Shop(
                shop_name="Test Shop",
                owner_name="Test Owner",
                email="test_shop@example.com",
                phone="1234567890",
                device_id="test_device_123",
                status="APPROVED",
                is_first_login=False
            )
            db.add(shop)
            db.commit()
            db.refresh(shop)
        else:
            if not shop.device_id:
                shop.device_id = "test_device_123"
                db.commit()
                db.refresh(shop)
            print(f"Using existing shop: {shop.shop_name} (ID: {shop.id}, Device ID: {shop.device_id})")

        # 2. Ensure active subscription
        sub = db.query(Subscription).filter(Subscription.shop_id == shop.id).first()
        if not sub:
            print("No subscription found, creating active subscription...")
            sub = Subscription(
                shop_id=shop.id,
                plan="monthly",
                start_date=datetime.utcnow() - timedelta(days=1),
                expiry_date=datetime.utcnow() + timedelta(days=30),
                status="active"
            )
            db.add(sub)
            db.commit()
        else:
            sub.status = "active"
            sub.expiry_date = datetime.utcnow() + timedelta(days=30)
            db.commit()
            print(f"Subscription verified active until {sub.expiry_date}")

        # 3. Generate token
        token = create_access_token({"shop_id": shop.id})
        return shop, token
    finally:
        db.close()

def run_tests():
    shop, token = setup_test_shop_and_token()
    base_url = "http://localhost:8000"
    headers = {
        "Authorization": f"Bearer {token}",
        "device_id": shop.device_id,
        "Content-Type": "application/json"
    }

    db = SessionLocal()
    try:
        # Clear existing test records from purchase_returns (e.g. note_number DN-9999 or CN-9999)
        db.query(PurchaseReturn).filter(PurchaseReturn.note_number.in_(["DN-99999", "CN-99999"])).delete(synchronize_session=False)
        db.commit()

        print("\n--- Test 1: Sync a purchase Debit Note (note_type = D) ---")
        payload_dn = {
            "records": [
                {
                    "local_id": 8888,
                    "shop_id": shop.device_id,
                    "product_name": "Test Product",
                    "quantity_returned": 2.0,
                    "taxable_amount": 20.0,
                    "invoice_value": 23.6,
                    "cgst_percentage": 9.0,
                    "sgst_percentage": 9.0,
                    "cgst_amount": 1.8,
                    "sgst_amount": 1.8,
                    "state": "Karnataka",
                    "supplier_gstin": "29AAAAA1111A1Z1",
                    "supplier_name": "Supplier 1",
                    "created_at": int(datetime.utcnow().timestamp() * 1000),
                    "note_number": "DN-99999",
                    "note_date": int(datetime.utcnow().timestamp() * 1000),
                    "note_type": "D",
                    "original_invoice_id": 9999,
                    "original_invoice_number": "PUR-9999",
                    "original_invoice_date": int(datetime.utcnow().timestamp() * 1000),
                    "place_of_supply": "Karnataka",
                    "supply_type": "intrastate",
                    "cess_amount": 0.0,
                    "tax_amount": 3.6,
                    "total_amount": 23.6,
                    "document_type": "Debit Note",
                    "document_nature": "Debit Note",
                    "document_series": "DN",
                    "pre_gst": "N",
                    "reason_for_issuing_document": "Purchase return",
                    "note_refund_voucher_value": 23.6,
                    "rate": 18.0,
                    "eligibility_for_itc": "Inputs",
                    "availed_itc_integrated_tax": 0.0,
                    "availed_itc_central_tax": 1.8,
                    "availed_itc_state_tax": 1.8,
                    "availed_itc_cess": 0.0,
                    "invoice_type": "Regular",
                    "place_of_supply_code": "29"
                }
            ]
        }
        res_dn = requests.post(f"{base_url}/purchase-returns/sync", json=payload_dn, headers=headers)
        print("Status Code:", res_dn.status_code)
        print("Response:", res_dn.json())
        assert res_dn.status_code == 200, "Should succeed"

        print("\n--- Test 2: Sync a purchase Credit Note (note_type = C) ---")
        payload_cn = {
            "records": [
                {
                    "local_id": 8889,
                    "shop_id": shop.device_id,
                    "product_name": "Test Product",
                    "quantity_returned": 1.0,
                    "taxable_amount": 10.0,
                    "invoice_value": 11.8,
                    "cgst_percentage": 9.0,
                    "sgst_percentage": 9.0,
                    "cgst_amount": 0.9,
                    "sgst_amount": 0.9,
                    "state": "Karnataka",
                    "supplier_gstin": "29AAAAA1111A1Z1",
                    "supplier_name": "Supplier 1",
                    "created_at": int(datetime.utcnow().timestamp() * 1000),
                    "note_number": "CN-99999",
                    "note_date": int(datetime.utcnow().timestamp() * 1000),
                    "note_type": "C",
                    "original_invoice_id": 9999,
                    "original_invoice_number": "PUR-9999",
                    "original_invoice_date": int(datetime.utcnow().timestamp() * 1000),
                    "place_of_supply": "Karnataka",
                    "supply_type": "intrastate",
                    "cess_amount": 0.0,
                    "tax_amount": 1.8,
                    "total_amount": 11.8,
                    "document_type": "Credit Note",
                    "document_nature": "Credit Note",
                    "document_series": "CN"
                }
            ]
        }
        res_cn = requests.post(f"{base_url}/purchase-returns/sync", json=payload_cn, headers=headers)
        print("Status Code:", res_cn.status_code)
        print("Response:", res_cn.json())
        assert res_cn.status_code == 200, "Should succeed"

        print("\n--- Test 3: Validation failure for Debit Note (excess central ITC) ---")
        payload_fail = {
            "records": [
                {
                    "local_id": 8890,
                    "shop_id": shop.device_id,
                    "product_name": "Test Product Fail",
                    "quantity_returned": 2.0,
                    "taxable_amount": 20.0,
                    "invoice_value": 23.6,
                    "cgst_percentage": 9.0,
                    "sgst_percentage": 9.0,
                    "cgst_amount": 1.8,
                    "sgst_amount": 1.8,
                    "state": "Karnataka",
                    "supplier_gstin": "29AAAAA1111A1Z1",
                    "supplier_name": "Supplier 1",
                    "created_at": int(datetime.utcnow().timestamp() * 1000),
                    "note_number": "DN-88888",
                    "note_date": int(datetime.utcnow().timestamp() * 1000),
                    "note_type": "D",
                    "original_invoice_id": 9999,
                    "original_invoice_number": "PUR-9999",
                    "original_invoice_date": int(datetime.utcnow().timestamp() * 1000),
                    "place_of_supply": "Karnataka",
                    "supply_type": "intrastate",
                    "cess_amount": 0.0,
                    "tax_amount": 3.6,
                    "total_amount": 23.6,
                    "document_type": "Debit Note",
                    "document_nature": "Debit Note",
                    "document_series": "DN",
                    "pre_gst": "N",
                    "reason_for_issuing_document": "Purchase return",
                    "note_refund_voucher_value": 23.6,
                    "rate": 18.0,
                    "eligibility_for_itc": "Inputs",
                    "availed_itc_integrated_tax": 0.0,
                    "availed_itc_central_tax": 5.0,  # exceeds actual CGST of 1.8
                    "availed_itc_state_tax": 1.8,
                    "availed_itc_cess": 0.0,
                    "invoice_type": "Regular",
                    "place_of_supply_code": "29"
                }
            ]
        }
        res_fail = requests.post(f"{base_url}/purchase-returns/sync", json=payload_fail, headers=headers)
        print("Status Code:", res_fail.status_code)
        print("Response:", res_fail.json())
        assert res_fail.status_code == 200, "Sync HTTP should return 200 even with some failing records"
        failed_records = res_fail.json().get("failed", [])
        assert len(failed_records) == 1, "Should have one failed record"
        assert failed_records[0]["local_id"] == 8890
        assert "cannot exceed" in failed_records[0]["reason"], "Should report availed ITC excess"

        # Verify DB entries
        db.expire_all()
        dn_record = db.query(PurchaseReturn).filter(PurchaseReturn.note_number == "DN-99999").first()
        assert dn_record is not None, "Debit Note record should exist in DB"
        assert dn_record.note_type == "D"
        assert dn_record.document_type == "Debit Note"
        assert dn_record.document_nature == "Debit Note"
        assert dn_record.document_series == "DN"
        assert dn_record.place_of_supply_code == "29"
        assert dn_record.note_refund_voucher_value == 23.6

        cn_record = db.query(PurchaseReturn).filter(PurchaseReturn.note_number == "CN-99999").first()
        assert cn_record is not None, "Credit Note record should exist in DB"
        assert cn_record.note_type == "C"
        assert cn_record.document_type == "Credit Note"
        assert cn_record.document_nature == "Credit Note"
        assert cn_record.document_series == "CN"

        print("\nAll database checks passed!")

    finally:
        # Cleanup
        db.query(PurchaseReturn).filter(PurchaseReturn.note_number.in_(["DN-99999", "CN-99999"])).delete(synchronize_session=False)
        db.commit()
        db.close()

if __name__ == "__main__":
    run_tests()
