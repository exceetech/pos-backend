"""Stage 1 (Phase 0) backend tests: P0-3 GSTR-2 ITC sign, P0-4 over-return netting.
Run: cd pos-backend && python -m pytest tests/test_stage1_purchase_notes.py -v
"""
import os
from types import SimpleNamespace

os.environ.setdefault("APP_TIMEZONE", "Asia/Kolkata")

from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.shop import Shop
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.purchase_return import PurchaseReturn
from app.routes.purchase_return_routes import check_over_return
from app.routes.gst_routes import get_gstr2


def make_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    shop = Shop(shop_name="S", owner_name="O", email="t@example.com")
    db.add(shop); db.commit(); db.refresh(shop)
    return db, shop


def add_purchase(db, shop, qty=100.0, itc=180.0):
    p = Purchase(shop_id=shop.id, invoice_number="INV1", supplier_name="Sup", state="Tamil Nadu",
                 taxable_amount=1000.0, invoice_value=1180.0)
    db.add(p); db.commit(); db.refresh(p)
    it = PurchaseItem(purchase_id=p.id, shop_product_id=7, product_name="Pen", quantity=qty,
                      taxable_amount=1000.0, invoice_value=1180.0, cost_price=10.0)
    db.add(it); db.commit()
    return p


def add_note(db, shop, p, ntype, qty, **kw):
    now = int(datetime.now().timestamp() * 1000)
    r = PurchaseReturn(shop_id=shop.id, product_name="Pen", quantity_returned=qty,
                       original_invoice_id=p.id, shop_product_id=7, note_type=ntype,
                       note_date=now, **kw)
    db.add(r); db.commit()
    return r


def payload(p, qty, ntype="D"):
    return SimpleNamespace(original_invoice_id=p.id, shop_product_id=7, quantity_returned=qty,
                           note_type=ntype)


# ---- P0-4 ----------------------------------------------------------------
def test_T0_4a_credit_note_never_blocked():
    db, shop = make_db(); p = add_purchase(db, shop)
    add_note(db, shop, p, "D", 100.0)           # fully returned
    assert check_over_return(db, shop.id, payload(p, 50.0, "C")) is None


def test_T0_4b_addition_raises_returnable():
    db, shop = make_db(); p = add_purchase(db, shop)
    add_note(db, shop, p, "D", 100.0)
    add_note(db, shop, p, "C", 20.0)            # returnable now 20
    assert check_over_return(db, shop.id, payload(p, 20.0, "D")) is None
    assert check_over_return(db, shop.id, payload(p, 21.0, "D")) is not None


def test_T0_4c_plain_over_return_still_blocked():
    db, shop = make_db(); p = add_purchase(db, shop)
    assert check_over_return(db, shop.id, payload(p, 101.0, "D")) is not None


# ---- P0-3 ----------------------------------------------------------------
def itc_total(db, shop):
    today = datetime.now().strftime("%Y-%m-%d")
    r = get_gstr2(start_date=today, end_date=today, db=db, current_shop=shop)
    return r.total_itc_cgst + r.total_itc_sgst + r.total_itc_igst


def test_T0_3_d_subtracts_c_adds():
    db, shop = make_db(); p = add_purchase(db, shop)
    base = itc_total(db, shop)
    add_note(db, shop, p, "D", 1.0, availed_itc_central_tax=9.0, availed_itc_state_tax=9.0)
    after_d = itc_total(db, shop)
    assert round(base - after_d, 2) == 18.0
    add_note(db, shop, p, "C", 1.0, availed_itc_central_tax=4.5, availed_itc_state_tax=4.5)
    after_c = itc_total(db, shop)
    assert round(after_c - after_d, 2) == 9.0
