import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from datetime import datetime, timezone
from app.database import SessionLocal
from app.models.shop import Shop
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.routes.gst_routes import get_gstr2
import uuid

def run_test():
    db = SessionLocal()
    
    # 1. Ensure we have a test shop
    shop = db.query(Shop).first()
    if not shop:
        shop = Shop(
            name="Test Shop",
            owner_id="test_owner",
            phone="1234567890",
            email="test@test.com",
            subscription_status="active",
            created_at=datetime.now(timezone.utc)
        )
        db.add(shop)
        db.commit()
        db.refresh(shop)
        
    print(f"Using shop_id={shop.id}")
    
    # Clean up old test data
    db.query(PurchaseItem).filter(PurchaseItem.product_name.like("Test%")).delete(synchronize_session=False)
    db.query(Purchase).filter(Purchase.invoice_number.like("TEST-%")).delete(synchronize_session=False)
    db.commit()
    
    dt = datetime.now(timezone.utc)
    
    # 2. Insert Invoice 1: Regular invoice but items are Nil Rated and Exempt (Interstate)
    p1 = Purchase(
        shop_id=shop.id,
        invoice_number="TEST-INV-1",
        invoice_date=dt,
        supplier_name="Supplier 1",
        state="Kerala",
        invoice_type="Regular",
        supply_type="Interstate",
        taxable_amount=100.0,
        invoice_value=100.0
    )
    db.add(p1)
    db.commit()
    db.refresh(p1)
    
    pi1_nil = PurchaseItem(
        purchase_id=p1.id,
        product_name="Test Nil Rated",
        quantity=1,
        taxable_amount=40.0,
        invoice_value=40.0,
        supply_classification="NIL_RATED",
        cost_price=40.0
    )
    pi1_exempt = PurchaseItem(
        purchase_id=p1.id,
        product_name="Test Exempt",
        quantity=1,
        taxable_amount=60.0,
        invoice_value=60.0,
        supply_classification="EXEMPT",
        cost_price=60.0
    )
    db.add_all([pi1_nil, pi1_exempt])
    
    # 3. Insert Invoice 2: Composition Dealer invoice (Intrastate)
    p2 = Purchase(
        shop_id=shop.id,
        invoice_number="TEST-INV-2",
        invoice_date=dt,
        supplier_name="Composition Supplier",
        state="Kerala",
        invoice_type="From Composition Taxable Person",
        supply_type="Intrastate",
        taxable_amount=200.0,
        invoice_value=200.0
    )
    db.add(p2)
    db.commit()
    db.refresh(p2)
    
    pi2_comp = PurchaseItem(
        purchase_id=p2.id,
        product_name="Test Composition Good",
        quantity=2,
        taxable_amount=200.0,
        invoice_value=200.0,
        supply_classification="TAXABLE", # Should be overridden by invoice type
        cost_price=100.0
    )
    db.add(pi2_comp)
    
    # 4. Insert Invoice 3: NON_GST (Intrastate)
    p3 = Purchase(
        shop_id=shop.id,
        invoice_number="TEST-INV-3",
        invoice_date=dt,
        supplier_name="Non GST Supplier",
        state="Kerala",
        invoice_type="Regular",
        supply_type="Intrastate",
        taxable_amount=50.0,
        invoice_value=50.0
    )
    db.add(p3)
    db.commit()
    db.refresh(p3)
    
    pi3_nongst = PurchaseItem(
        purchase_id=p3.id,
        product_name="Test Non GST",
        quantity=1,
        taxable_amount=50.0,
        invoice_value=50.0,
        supply_classification="NON_GST",
        cost_price=50.0
    )
    db.add(pi3_nongst)
    
    db.commit()
    
    # 5. Call get_gstr2
    date_str = dt.strftime("%Y-%m-%d")
    resp = get_gstr2(start_date=date_str, end_date=date_str, db=db, current_shop=shop)
    
    print("\n--- GSTR-2 Verification Results ---")
    print(f"Composition Dealer (Intrastate expected 200): {resp.composition_dealer.intra_state}")
    print(f"Exempt (Interstate expected 60): {resp.exempt.inter_state}")
    print(f"Nil Rated (Interstate expected 40): {resp.nil_rated.inter_state}")
    print(f"Non-GST (Intrastate expected 50): {resp.non_gst.intra_state}")
    
    assert resp.composition_dealer.intra_state == 200.0
    assert resp.exempt.inter_state == 60.0
    assert resp.nil_rated.inter_state == 40.0
    assert resp.non_gst.intra_state == 50.0
    
    print("All GSTR-2 exemption aggregations are working correctly!")
    
if __name__ == "__main__":
    run_test()
