import sys
import os
from datetime import datetime, timedelta
import requests

# Set python path to allow importing app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal
from app.models.shop import Shop
from app.models.subscription import Subscription
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.purchase_batch import PurchaseBatch
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
        # Clear existing test records from purchases
        db.query(PurchaseItem).filter(PurchaseItem.purchase_id.in_(
            db.query(Purchase.id).filter(Purchase.local_id.in_([9999, 9998]))
        )).delete(synchronize_session=False)
        db.query(PurchaseBatch).filter(PurchaseBatch.purchase_invoice_id.in_(
            db.query(Purchase.id).filter(Purchase.local_id.in_([9999, 9998]))
        )).delete(synchronize_session=False)
        db.query(Purchase).filter(Purchase.local_id.in_([9999, 9998])).delete(synchronize_session=False)
        db.commit()

        print("\n--- Test 1: Sync a valid purchase with GSTR-2 item fields ---")
        payload = {
            "purchases": [
                {
                    "local_id": 9999,
                    "invoice_number": "PUR-9999",
                    "supplier_gstin": "29AAAAA1111A1Z1",
                    "supplier_name": "Supplier 1",
                    "state": "Karnataka",
                    "taxable_amount": 100.0,
                    "cgst_percentage": 9.0,
                    "sgst_percentage": 9.0,
                    "cgst_amount": 9.0,
                    "sgst_amount": 9.0,
                    "invoice_value": 118.0,
                    "created_at": int(datetime.utcnow().timestamp() * 1000),
                    "place_of_supply_code": "29",
                    "reverse_charge": "N",
                    "invoice_type": "Regular",
                    "supply_type": "intrastate",
                    "cess_paid": 5.0,
                    "eligibility_for_itc": "Inputs",
                    "availed_itc_integrated_tax": 0.0,
                    "availed_itc_central_tax": 9.0,
                    "availed_itc_state_tax": 9.0,
                    "availed_itc_cess": 5.0,
                    "items": [
                        {
                            "local_id": 1111,
                            "product_name": "Test Product",
                            "quantity": 10.0,
                            "taxable_amount": 100.0,
                            "invoice_value": 118.0,
                            "cost_price": 10.0,
                            "purchase_cgst_percentage": 9.0,
                            "purchase_sgst_percentage": 9.0,
                            "purchase_cgst_amount": 9.0,
                            "purchase_sgst_amount": 9.0,
                            "cess_percentage": 5.0,
                            "cess_amount": 5.0,
                            "eligibility_for_itc": "Inputs",
                            "availed_itc_igst": 0.0,
                            "availed_itc_cgst": 9.0,
                            "availed_itc_sgst": 9.0,
                            "availed_itc_cess": 5.0,
                            "hsn_description": "My HSN Desc",
                            "official_uqc": "BOX"
                        }
                    ]
                }
            ]
        }
        res = requests.post(f"{base_url}/purchases/sync", json=payload, headers=headers)
        print("Status Code:", res.status_code)
        print("Response:", res.json())
        assert res.status_code == 200, "Should succeed"

        # Verify DB entry
        db.expire_all()
        purchase = db.query(Purchase).filter(Purchase.local_id == 9999).first()
        assert purchase is not None
        items = db.query(PurchaseItem).filter(PurchaseItem.purchase_id == purchase.id).all()
        assert len(items) == 1
        item = items[0]
        assert item.cess_percentage == 5.0
        assert item.cess_amount == 5.0
        assert item.eligibility_for_itc == "Inputs"
        assert item.availed_itc_cgst == 9.0
        assert item.availed_itc_sgst == 9.0
        assert item.availed_itc_cess == 5.0
        assert item.hsn_description == "My HSN Desc"
        assert item.official_uqc == "BOX"
        print("Test 1 Passed!")

        print("\n--- Test 2: Validation check: item availed ITC > paid tax (Should fail) ---")
        payload["purchases"][0]["items"][0]["availed_itc_cgst"] = 12.0  # Paid was 9.0
        res = requests.post(f"{base_url}/purchases/sync", json=payload, headers=headers)
        print("Status Code:", res.status_code)
        print("Response:", res.json())
        assert res.status_code == 400, "Should fail because item availed ITC > purchase_cgst_amount"
        assert "item availed_itc_cgst cannot exceed purchase_cgst_amount" in res.json()["message"]
        print("Test 2 Passed!")

        print("\n--- Test 3: Validation check: item eligibility Ineligible, availed ITC > 0 (Should fail) ---")
        payload["purchases"][0]["items"][0]["availed_itc_cgst"] = 9.0  # Reset
        payload["purchases"][0]["items"][0]["eligibility_for_itc"] = "Ineligible"
        res = requests.post(f"{base_url}/purchases/sync", json=payload, headers=headers)
        print("Status Code:", res.status_code)
        print("Response:", res.json())
        assert res.status_code == 400, "Should fail because item availed ITC must be 0 when Ineligible"
        assert "item availed ITC fields must be 0 when ineligible/None" in res.json()["message"]
        print("Test 3 Passed!")

        print("\n--- Test 4: Validation check: item eligibility Ineligible, availed ITC = 0 (Should pass) ---")
        payload["purchases"][0]["items"][0]["availed_itc_cgst"] = 0.0
        payload["purchases"][0]["items"][0]["availed_itc_sgst"] = 0.0
        payload["purchases"][0]["items"][0]["availed_itc_cess"] = 0.0
        res = requests.post(f"{base_url}/purchases/sync", json=payload, headers=headers)
        print("Status Code:", res.status_code)
        print("Response:", res.json())
        assert res.status_code == 200, "Should pass when item availed ITC is 0"
        db.expire_all()
        purchase = db.query(Purchase).filter(Purchase.local_id == 9999).first()
        items = db.query(PurchaseItem).filter(PurchaseItem.purchase_id == purchase.id).all()
        item = items[0]
        assert item.eligibility_for_itc == "Ineligible"
        assert item.availed_itc_cgst == 0.0
        print("Test 4 Passed!")

        print("\n--- Test 5: Validation check: official_uqc required when hsn_code is present (Should fail) ---")
        # Reset eligibility to Inputs and set proper availed values
        payload["purchases"][0]["items"][0]["eligibility_for_itc"] = "Inputs"
        payload["purchases"][0]["items"][0]["availed_itc_cgst"] = 9.0
        payload["purchases"][0]["items"][0]["availed_itc_sgst"] = 9.0
        payload["purchases"][0]["items"][0]["availed_itc_cess"] = 5.0
        # Add hsn_code but empty official_uqc
        payload["purchases"][0]["items"][0]["hsn_code"] = "123456"
        payload["purchases"][0]["items"][0]["official_uqc"] = ""
        res = requests.post(f"{base_url}/purchases/sync", json=payload, headers=headers)
        print("Status Code:", res.status_code)
        print("Response:", res.json())
        assert res.status_code == 400, "Should fail because official_uqc is empty when hsn_code is present"
        assert "item official_uqc is required when hsn_code is present" in res.json()["message"]
        print("Test 5 Passed!")

        print("\n--- Test 6: Idempotency update (Modify existing local_id = 9999 item GSTR-2 fields) ---")
        # Set valid official_uqc and change cess_percentage, cess_amount, and hsn_description
        payload["purchases"][0]["items"][0]["official_uqc"] = "NOS"
        payload["purchases"][0]["items"][0]["cess_percentage"] = 10.0
        payload["purchases"][0]["items"][0]["cess_amount"] = 10.0
        payload["purchases"][0]["items"][0]["hsn_description"] = "Updated HSN Desc"
        payload["purchases"][0]["items"][0]["availed_itc_cess"] = 10.0
        payload["purchases"][0]["cess_paid"] = 10.0
        payload["purchases"][0]["availed_itc_cess"] = 10.0
        res = requests.post(f"{base_url}/purchases/sync", json=payload, headers=headers)
        print("Status Code:", res.status_code)
        print("Response:", res.json())
        assert res.status_code == 200, "Should succeed on update"

        # Verify DB entry
        db.expire_all()
        purchase = db.query(Purchase).filter(Purchase.local_id == 9999).first()
        assert purchase is not None
        items = db.query(PurchaseItem).filter(PurchaseItem.purchase_id == purchase.id).all()
        assert len(items) == 1
        item = items[0]
        assert item.cess_percentage == 10.0
        assert item.cess_amount == 10.0
        assert item.official_uqc == "NOS"
        assert item.hsn_description == "Updated HSN Desc"
        assert item.availed_itc_cess == 10.0
        # Ensure count of purchases with local_id 9999 is 1 (no duplicate was created)
        cnt = db.query(Purchase).filter(Purchase.local_id == 9999).count()
        assert cnt == 1, f"Expected 1 purchase, got {cnt}"
        print("Test 6 Passed!")

        # Clean up
        db.query(PurchaseItem).filter(PurchaseItem.purchase_id.in_(
            db.query(Purchase.id).filter(Purchase.local_id.in_([9999, 9998]))
        )).delete(synchronize_session=False)
        db.query(PurchaseBatch).filter(PurchaseBatch.purchase_invoice_id.in_(
            db.query(Purchase.id).filter(Purchase.local_id.in_([9999, 9998]))
        )).delete(synchronize_session=False)
        db.query(Purchase).filter(Purchase.local_id.in_([9999, 9998])).delete(synchronize_session=False)
        db.commit()
        print("\nCleanup completed.")
        print("\nALL GSTR-2 PURCHASE ITEM SYNC TESTS PASSED SUCCESSFULLY!")

    except AssertionError as e:
        print(f"\n❌ ASSERTION ERROR: {e}")
        db.rollback()
    except Exception as e:
        print(f"\n❌ ERROR RUNNING TESTS: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    run_tests()
