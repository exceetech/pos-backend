"""Phase 1 (QDN / PDN backend) tests T1-1 .. T1-7 + migration + over-return netting.
Run: cd pos-backend && python -m pytest tests/test_phase1_correction_notes.py -v
"""
import os
os.environ.setdefault("APP_TIMEZONE", "Asia/Kolkata")

import time
from datetime import datetime
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.dependencies import get_current_shop
from app.models.shop import Shop
from app.models.global_products import GlobalProduct
from app.models.shop_products import ShopProduct
from app.models.inventory import Inventory
from app.models.inventory_log import InventoryLog  # noqa: F401
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.purchase_return import PurchaseReturn
from app.routes.inventory_routes import router as inventory_router
from app.routes.purchase_return_routes import router as pr_router
from app.routes.profit_routes import get_profit
from app.routes.gst_routes import get_gstr2
from app.services.insights_service import _is_genuine_supplier_return

app = FastAPI()
app.include_router(inventory_router)
app.include_router(pr_router)


def setup():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_db():
        d = Session()
        try:
            yield d
        finally:
            d.close()

    db = Session()
    shop = Shop(shop_name="T", owner_name="O", email="t@example.com")
    db.add(shop); db.commit(); db.refresh(shop)
    gp = GlobalProduct(name="Pen"); db.add(gp); db.commit(); db.refresh(gp)
    prod = ShopProduct(shop_id=shop.id, global_product_id=gp.id, price=10.0, is_active=True)
    db.add(prod); db.commit(); db.refresh(prod)
    pur = Purchase(shop_id=shop.id, invoice_number="INV1", supplier_name="Sup", state="Tamil Nadu",
                   taxable_amount=1000.0, invoice_value=1180.0)
    db.add(pur); db.commit(); db.refresh(pur)
    db.add(PurchaseItem(purchase_id=pur.id, shop_product_id=prod.id, product_name="Pen", quantity=100.0,
                        taxable_amount=1000.0, invoice_value=1180.0, cost_price=10.0))
    db.commit()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_shop] = lambda: shop
    return TestClient(app), db, shop, prod, pur, engine


def seed_stock(client, pid, qty=100, avg=11.80):
    r = client.post("/inventory/sync", json=[{"product_id": pid, "type": "ADD", "quantity": qty,
                                              "price": avg, "client_uid": "seed", "resulting_average_cost": avg}])
    assert r.status_code == 200, r.text


def inv(client, pid):
    return next(x for x in client.get("/inventory/my").json() if x["product_id"] == pid)


def note_payload(prod, pur, local_id, kind, ntype, qty, variance=0.0, value=118.0, taxable=100.0, **kw):
    gst = round(value - taxable, 2)
    d = dict(
        local_id=local_id, shop_id="GSTIN", shop_product_id=prod.id, product_name="Pen",
        quantity_returned=qty, taxable_amount=taxable, invoice_value=value,
        cgst_percentage=9, sgst_percentage=9, cgst_amount=gst / 2, sgst_amount=gst / 2,
        state="Tamil Nadu", supplier_gstin="33ABCDE1234F1Z5", supplier_name="Sup",
        created_at=int(time.time() * 1000), note_number=f"X-{local_id}", note_date=int(time.time() * 1000),
        note_type=ntype, note_kind=kind, original_invoice_id=pur.id, original_invoice_number="INV1",
        document_type="Debit Note" if ntype == "D" else "Credit Note",
        reason_for_issuing_document="Price correction", note_refund_voucher_value=value, rate=18,
        eligibility_for_itc="Inputs", availed_itc_central_tax=gst / 2, availed_itc_state_tax=gst / 2,
        invoice_type="Regular", place_of_supply_code="33", inventory_valuation_variance=variance,
    )
    d.update(kw)
    return d


def sync(client, *notes):
    r = client.post("/purchase-returns/sync", json={"records": list(notes)})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------- T1-1 / T1-2 / T1-3: inventory sync ----------------
def test_T1_1_qty_corr_reduce():
    c, db, shop, prod, pur, _ = setup()
    try:
        seed_stock(c, prod.id)
        c.post("/inventory/sync", json=[{"product_id": prod.id, "type": "QTY_CORR_REDUCE", "quantity": 10,
                                         "price": 11.80, "client_uid": "q1", "resulting_average_cost": 11.80}])
        row = inv(c, prod.id)
        assert row["stock"] == 90.0 and abs(row["avg_cost"] - 11.80) < 1e-9
    finally:
        app.dependency_overrides.clear()


def test_T1_1b_reduce_fallback_average_without_client_value():
    c, db, shop, prod, pur, _ = setup()
    try:
        seed_stock(c, prod.id, 100, 12.0)
        c.post("/inventory/sync", json=[{"product_id": prod.id, "type": "QTY_CORR_REDUCE", "quantity": 10,
                                         "price": 11.80, "client_uid": "q1"}])
        row = inv(c, prod.id)
        assert row["stock"] == 90.0
        assert abs(row["avg_cost"] - ((100 * 12.0 - 10 * 11.80) / 90)) < 1e-9
    finally:
        app.dependency_overrides.clear()


def test_T1_1c_reduce_to_zero_sets_average_zero():
    c, db, shop, prod, pur, _ = setup()
    try:
        seed_stock(c, prod.id, 10, 11.80)
        c.post("/inventory/sync", json=[{"product_id": prod.id, "type": "QTY_CORR_REDUCE", "quantity": 10,
                                         "price": 11.80, "client_uid": "q1"}])
        row = inv(c, prod.id)
        assert row["stock"] == 0.0 and row["avg_cost"] == 0.0
    finally:
        app.dependency_overrides.clear()


def test_T1_2_qty_corr_add():
    c, db, shop, prod, pur, _ = setup()
    try:
        seed_stock(c, prod.id, 100, 11.80)
        c.post("/inventory/sync", json=[{"product_id": prod.id, "type": "QTY_CORR_ADD", "quantity": 10,
                                         "price": 13.0, "client_uid": "q1", "resulting_average_cost": 11.9182}])
        row = inv(c, prod.id)
        assert row["stock"] == 110.0 and abs(row["avg_cost"] - 11.9182) < 1e-9
    finally:
        app.dependency_overrides.clear()


def test_T1_3_cost_adjust_changes_only_average():
    c, db, shop, prod, pur, _ = setup()
    try:
        seed_stock(c, prod.id, 100, 11.80)
        c.post("/inventory/sync", json=[{"product_id": prod.id, "type": "COST_ADJUST", "quantity": 0,
                                         "price": 0, "client_uid": "c1", "resulting_average_cost": 10.62}])
        row = inv(c, prod.id)
        assert row["stock"] == 100.0 and abs(row["avg_cost"] - 10.62) < 1e-9
        # retry of the same log (lost response) must not apply twice
        c.post("/inventory/sync", json=[{"product_id": prod.id, "type": "COST_ADJUST", "quantity": 0,
                                         "price": 0, "client_uid": "c1", "resulting_average_cost": 10.62}])
        assert inv(c, prod.id)["stock"] == 100.0
    finally:
        app.dependency_overrides.clear()


def test_T1_3b_cost_adjust_without_client_average_changes_nothing():
    c, db, shop, prod, pur, _ = setup()
    try:
        seed_stock(c, prod.id, 100, 11.80)
        c.post("/inventory/sync", json=[{"product_id": prod.id, "type": "COST_ADJUST", "quantity": 0,
                                         "price": 0, "client_uid": "c1"}])
        row = inv(c, prod.id)
        assert row["stock"] == 100.0 and abs(row["avg_cost"] - 11.80) < 1e-9
    finally:
        app.dependency_overrides.clear()


# ---------------- T1-4: profit ----------------
def profit(db, shop):
    return get_profit(filter="all", start_date=None, end_date=None, db=db, current_shop=shop)["summary"]


def test_T1_4_pdn_gain_raises_profit_loss_lowers_it_and_expense_nets():
    c, db, shop, prod, pur, _ = setup()
    try:
        base = profit(db, shop)
        r = sync(c, note_payload(prod, pur, 1, "PRICE_CORRECTION", "D", 100, variance=-70.80,
                                 value=118.0, taxable=100.0, shelf_value_delta=-47.20, rate_delta_net=-1.0))
        assert r["success_count"] == 1, r
        s1 = profit(db, shop)
        assert round(s1["profit"] - base["profit"], 2) == 70.80
        assert s1["purchaseReturnVariance"] == -70.80
        assert round(s1["expense"] - base["expense"], 2) == -118.0   # D lowers Expense
        r = sync(c, note_payload(prod, pur, 2, "PRICE_CORRECTION", "C", 100, variance=40.0,
                                 value=59.0, taxable=50.0))
        assert r["success_count"] == 1, r
        s2 = profit(db, shop)
        assert round(s2["profit"] - s1["profit"], 2) == -40.0
        assert round(s2["expense"] - s1["expense"], 2) == 59.0       # C raises Expense
    finally:
        app.dependency_overrides.clear()


# ---------------- T1-5: GSTR-2 ----------------
def test_T1_5_gstr2_one_row_per_note_right_sign():
    c, db, shop, prod, pur, _ = setup()
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        sync(c, note_payload(prod, pur, 1, "PRICE_CORRECTION", "D", 100, value=118.0, taxable=100.0))
        sync(c, note_payload(prod, pur, 2, "QTY_CORRECTION", "C", 5, value=59.0, taxable=50.0))
        r = get_gstr2(start_date=today, end_date=today, db=db, current_shop=shop)
        assert len(r.cdnr) == 2
        types = sorted(x.document_type for x in r.cdnr)
        assert types == ["Credit Note", "Debit Note"]
        # D: -18, C: +9 on top of an (empty) base
        assert round(r.total_itc_cgst + r.total_itc_sgst + r.total_itc_igst, 2) == round(-18.0 + 9.0, 2)
    finally:
        app.dependency_overrides.clear()


# ---------------- T1-6: insights ----------------
def test_T1_6_insights_filter_counts_only_genuine_returns():
    c, db, shop, prod, pur, _ = setup()
    try:
        sync(c, note_payload(prod, pur, 1, "RETURN", "D", 5, value=59.0, taxable=50.0))
        sync(c, note_payload(prod, pur, 2, None, "D", 5, value=59.0, taxable=50.0))          # legacy
        sync(c, note_payload(prod, pur, 3, "QTY_CORRECTION", "D", 5, value=59.0, taxable=50.0))
        sync(c, note_payload(prod, pur, 4, "PRICE_CORRECTION", "D", 100, value=118.0, taxable=100.0))
        sync(c, note_payload(prod, pur, 5, "ADDITION", "C", 5, value=59.0, taxable=50.0))
        n = db.query(PurchaseReturn).filter(PurchaseReturn.shop_id == shop.id, _is_genuine_supplier_return()).count()
        assert n == 2
    finally:
        app.dependency_overrides.clear()


# ---------------- T1-7: validation ----------------
def test_T1_7_unknown_kind_rejected_legacy_null_loads():
    c, db, shop, prod, pur, _ = setup()
    try:
        r = sync(c, note_payload(prod, pur, 1, "BOGUS", "D", 5, value=59.0, taxable=50.0))
        assert r["success_count"] == 0 and "note_kind" in r["failed"][0]["reason"]
        r = sync(c, note_payload(prod, pur, 2, None, "D", 5, value=59.0, taxable=50.0))
        assert r["success_count"] == 1
        rows = c.get(f"/purchase-return/{shop.id}").json()
        assert rows[0]["note_kind"] is None and rows[0]["rate_delta_net"] == 0.0
    finally:
        app.dependency_overrides.clear()


def test_T1_7b_kind_must_agree_with_direction_and_quantity():
    c, db, shop, prod, pur, _ = setup()
    try:
        bad = sync(c, note_payload(prod, pur, 1, "RETURN", "C", 5), note_payload(prod, pur, 2, "ADDITION", "D", 5),
                   note_payload(prod, pur, 3, "QTY_CORRECTION", "D", 0),
                   note_payload(prod, pur, 4, "PRICE_CORRECTION", "D", -1))
        assert bad["success_count"] == 0 and len(bad["failed"]) == 4
        ok = sync(c, note_payload(prod, pur, 5, "PRICE_CORRECTION", "D", 0))
        assert ok["success_count"] == 1
    finally:
        app.dependency_overrides.clear()


def test_price_note_fields_round_trip():
    c, db, shop, prod, pur, _ = setup()
    try:
        sync(c, note_payload(prod, pur, 1, "PRICE_CORRECTION", "D", 80, variance=-70.80,
                             rate_delta_net=-1.0, shelf_value_delta=-23.60))
        row = c.get(f"/purchase-return/{shop.id}").json()[0]
        assert row["note_kind"] == "PRICE_CORRECTION" and row["rate_delta_net"] == -1.0
        assert row["shelf_value_delta"] == -23.60 and row["inventory_valuation_variance"] == -70.80
    finally:
        app.dependency_overrides.clear()


# ---------------- over-return with the new kinds ----------------
def test_price_note_never_blocked_and_never_counted_in_over_return():
    c, db, shop, prod, pur, _ = setup()
    try:
        # PDN covering all 100 pens, then a full return of 100 must still be allowed
        assert sync(c, note_payload(prod, pur, 1, "PRICE_CORRECTION", "D", 100))["success_count"] == 1
        assert sync(c, note_payload(prod, pur, 2, "RETURN", "D", 100))["success_count"] == 1
        # 1 more is over-return
        r = sync(c, note_payload(prod, pur, 3, "RETURN", "D", 1))
        assert r["success_count"] == 0
    finally:
        app.dependency_overrides.clear()


def test_qty_correction_counts_against_returnable():
    c, db, shop, prod, pur, _ = setup()
    try:
        assert sync(c, note_payload(prod, pur, 1, "QTY_CORRECTION", "D", 10))["success_count"] == 1   # bill overstated by 10
        assert sync(c, note_payload(prod, pur, 2, "RETURN", "D", 90))["success_count"] == 1
        assert sync(c, note_payload(prod, pur, 3, "RETURN", "D", 1))["success_count"] == 0
        assert sync(c, note_payload(prod, pur, 4, "QTY_CORRECTION", "C", 10))["success_count"] == 1   # understated: +10
        assert sync(c, note_payload(prod, pur, 5, "RETURN", "D", 10))["success_count"] == 1
    finally:
        app.dependency_overrides.clear()


# ---------------- migration ----------------
def test_migration_0057_adds_columns_and_is_idempotent():
    import importlib.util
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    path = os.path.join(os.path.dirname(__file__), "..", "migrations", "versions",
                        "0057_add_purchase_return_note_kind.py")
    spec = importlib.util.spec_from_file_location("m0057", path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE purchase_returns (id INTEGER PRIMARY KEY, shop_id INTEGER)"))
        conn.execute(text("INSERT INTO purchase_returns (id, shop_id) VALUES (1, 7)"))
        with Operations.context(MigrationContext.configure(conn)):
            mod.upgrade(); mod.upgrade()          # second run must be a no-op
        cols = {c["name"] for c in inspect(conn).get_columns("purchase_returns")}
        assert {"note_kind", "rate_delta_net", "shelf_value_delta"} <= cols
        row = conn.execute(text("SELECT note_kind, rate_delta_net, shelf_value_delta FROM purchase_returns")).one()
        assert row[0] is None and row[1] == 0.0 and row[2] == 0.0
    assert mod.down_revision == "0056_add_global_variant_brand"
