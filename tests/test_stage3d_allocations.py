"""Stage 3D tests T3D-1 .. T3D-4 (allocation / pool / claim sync and profit).
Run: cd pos-backend && python -m pytest tests/test_stage3d_allocations.py -v
"""
import os
os.environ.setdefault("APP_TIMEZONE", "Asia/Kolkata")

import time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.dependencies import get_current_shop
from app.models.shop import Shop
from app.models.sale_allocation import SaleBatchAllocation, PdnGonePool, CostCorrectionClaim
from app.routes.sale_allocation_routes import router
from app.routes.profit_routes import get_profit

app = FastAPI()
app.include_router(router)


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
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_shop] = lambda: shop
    return TestClient(app), db, shop


NOW = int(time.time() * 1000)


def alloc(lid, **kw):
    d = dict(local_id=lid, source_type="SALE", source_id=7, bill_number="INV-1", line_ordinal=0,
             product_id=5, purchase_invoice_id=11, batch_local_id=3, quantity=60.0,
             quantity_restored=0.0, unit_cost_net=10.0, unit_cost_gross=11.8, created_at=NOW)
    d.update(kw)
    return d


def pool(lid, **kw):
    d = dict(local_id=lid, note_local_id=1, purchase_invoice_id=11, product_id=5,
             gone_qty=60.0, delta_gross=-1.18, note_date=NOW)
    d.update(kw)
    return d


def claim(lid, **kw):
    d = dict(local_id=lid, allocation_local_id=1, pool_local_id=1, note_local_id=1, product_id=5,
             qty=5.0, amount=5.90, claim_date=NOW, source_type="SALES_RETURN", source_id=70)
    d.update(kw)
    return d


def test_T3D_1_push_pull_round_trip():
    c, db, shop = setup()
    try:
        r = c.post("/sale-allocations/sync", json={"allocations": [alloc(1)], "pools": [pool(1)], "claims": [claim(1)]})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["allocation_ids"] == [1] and j["pool_ids"] == [1] and j["claim_ids"] == [1]
        g = c.get(f"/sale-allocations/{shop.id}").json()
        assert g["allocations"][0]["purchase_invoice_id"] == 11 and g["allocations"][0]["bill_number"] == "INV-1"
        assert g["pools"][0]["gone_qty"] == 60.0
        assert g["claims"][0]["amount"] == 5.90
    finally:
        app.dependency_overrides.clear()


def test_T3D_4_resend_is_idempotent_and_updates_restored():
    c, db, shop = setup()
    try:
        c.post("/sale-allocations/sync", json={"allocations": [alloc(1)], "pools": [pool(1)], "claims": [claim(1)]})
        c.post("/sale-allocations/sync", json={"allocations": [alloc(1, quantity_restored=5.0)],
                                               "pools": [pool(1)], "claims": [claim(1)]})
        assert db.query(SaleBatchAllocation).count() == 1
        assert db.query(PdnGonePool).count() == 1
        assert db.query(CostCorrectionClaim).count() == 1
        db.expire_all()
        assert db.query(SaleBatchAllocation).first().quantity_restored == 5.0
    finally:
        app.dependency_overrides.clear()


def test_cross_shop_read_denied():
    c, db, shop = setup()
    try:
        assert c.get(f"/sale-allocations/{shop.id + 1}").status_code == 403
    finally:
        app.dependency_overrides.clear()


def profit(db, shop):
    return get_profit(filter="all", start_date=None, end_date=None, db=db, current_shop=shop)["summary"]


def test_T3D_3_claim_reverses_gain_in_profit():
    c, db, shop = setup()
    try:
        base = profit(db, shop)
        c.post("/sale-allocations/sync", json={"pools": [pool(1), pool(2, delta_gross=0.4)], "claims": [claim(1, amount=5.90)]})
        s = profit(db, shop)
        assert round(s["profit"] - base["profit"], 2) == -5.90        # loss reduces profit
        assert round(s["purchaseReturnVariance"] - base["purchaseReturnVariance"], 2) == 5.90
        c.post("/sale-allocations/sync", json={"claims": [claim(2, amount=-2.0, pool_local_id=2)]})   # a price-up reversal = gain
        s2 = profit(db, shop)
        assert round(s2["profit"] - s["profit"], 2) == 2.0
    finally:
        app.dependency_overrides.clear()


def test_T3D_5_timestamps_round_trip_under_utc_process():
    """Bug A: server process TZ must not shift created_at/note_date/claim_date on pull."""
    import time as _t
    old = os.environ.get("TZ")
    os.environ["TZ"] = "UTC"; _t.tzset()
    try:
        c, db, shop = setup()
        stamp = 1_760_000_000_000
        c.post("/sale-allocations/sync", json={"allocations": [alloc(1, created_at=stamp)],
                                               "pools": [pool(1, note_date=stamp)],
                                               "claims": [claim(1, claim_date=stamp)]})
        g = c.get(f"/sale-allocations/{shop.id}").json()
        assert g["allocations"][0]["created_at"] == stamp
        assert g["pools"][0]["note_date"] == stamp
        assert g["claims"][0]["claim_date"] == stamp
    finally:
        if old is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old
        _t.tzset()
        app.dependency_overrides.clear()


def test_H_1_same_local_id_from_two_installs_does_not_overwrite():
    c, db, shop = setup()
    try:
        c.post("/sale-allocations/sync", json={"origin": "install-A", "allocations": [alloc(1, quantity=10.0)]})
        c.post("/sale-allocations/sync", json={"origin": "install-B", "allocations": [alloc(1, quantity=99.0)]})
        assert db.query(SaleBatchAllocation).count() == 2
        g = c.get(f"/sale-allocations/{shop.id}").json()
        assert sorted(a["quantity"] for a in g["allocations"]) == [10.0, 99.0]
        assert {a["origin"] for a in g["allocations"]} == {"install-A", "install-B"}
    finally:
        app.dependency_overrides.clear()


def test_H_4a_claim_waits_for_its_pool():
    c, db, shop = setup()
    try:
        r = c.post("/sale-allocations/sync", json={"origin": "o", "claims": [claim(1)]}).json()
        assert r["claim_ids"] == []                         # not acked, app retries later
        assert db.query(CostCorrectionClaim).count() == 0
        r = c.post("/sale-allocations/sync", json={"origin": "o", "pools": [pool(1)], "claims": [claim(1)]}).json()
        assert r["claim_ids"] == [1] and db.query(CostCorrectionClaim).count() == 1
    finally:
        app.dependency_overrides.clear()


def test_H_4b_claim_validation():
    c, db, shop = setup()
    try:
        # pool: 60 gone, delta -1.18 -> a claim is a LOSS (positive), at most qty*1.18
        r = c.post("/sale-allocations/sync", json={"origin": "o", "pools": [pool(1)], "claims": [
            claim(1, qty=5.0, amount=500.0),       # too big -> clamped to 5.91
            claim(2, qty=5.0, amount=-5.0),        # wrong sign -> rejected (acked, not stored)
            claim(3, qty=90.0, amount=1.0),        # more than the pool -> rejected
        ]}).json()
        assert sorted(r["claim_ids"]) == [1, 2, 3]
        rows = db.query(CostCorrectionClaim).all()
        assert [x.local_id for x in rows] == [1]
        assert round(rows[0].amount, 2) == 5.91
    finally:
        app.dependency_overrides.clear()


def test_H_4c_pull_cursor():
    c, db, shop = setup()
    try:
        c.post("/sale-allocations/sync", json={"origin": "o", "allocations": [alloc(1), alloc(2)], "pools": [pool(1)]})
        g = c.get(f"/sale-allocations/{shop.id}").json()
        top = max(a["id"] for a in g["allocations"])
        g2 = c.get(f"/sale-allocations/{shop.id}?after_alloc_id={top}&after_pool_id=999").json()
        assert g2["allocations"] == [] and g2["pools"] == []
        g3 = c.get(f"/sale-allocations/{shop.id}?after_alloc_id={top - 1}").json()
        assert len(g3["allocations"]) == 1
    finally:
        app.dependency_overrides.clear()


def test_H_3_claims_of_archived_bills_leave_profit():
    from app.models.bill import Bill
    c, db, shop = setup()
    try:
        bill = Bill(shop_id=shop.id, bill_number="INV-A1")
        db.add(bill); db.commit()
        base = profit(db, shop)
        c.post("/sale-allocations/sync", json={"origin": "o", "pools": [pool(1)],
                                               "claims": [claim(1, amount=5.90, bill_number="INV-A1")]})
        s = profit(db, shop)
        assert round(s["profit"] - base["profit"], 2) == -5.90
        bill.active = False
        db.commit()
        s2 = profit(db, shop)
        assert round(s2["profit"] - base["profit"], 2) == 0.0       # "Clear bills" archived it
    finally:
        app.dependency_overrides.clear()
