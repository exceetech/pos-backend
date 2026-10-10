"""Payment tracking, Phase 1: Money Book sync tests (PM-B1 .. PM-B8).
Run: cd pos-backend && python -m pytest tests/test_money_entries.py -v
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
from app.models.money_entry import MoneyEntry
from app.routes.money_entry_routes import router

app = FastAPI()
app.include_router(router)
NOW = int(time.time() * 1000)


def setup(two_shops=False):
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
    shop2 = Shop(shop_name="T2", owner_name="O2", email="t2@example.com")
    db.add_all([shop, shop2]); db.commit(); db.refresh(shop); db.refresh(shop2)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_shop] = lambda: shop
    return TestClient(app), db, shop, shop2


def entry(uid, **kw):
    d = dict(uid=uid, local_id=1, direction="IN", mode="CASH", amount=300.0, reason="SALE",
             source_type="BILL", source_id=7, parent_type="BILL", parent_id=7,
             party_name="Ravi", ref_text="INV-7", status="RECEIVED", created_at=NOW)
    d.update(kw)
    return d


def test_PMB1_push_pull_round_trip():
    c, db, shop, _ = setup()
    try:
        r = c.post("/money-entries/sync", json={"origin": "abc", "entries": [entry("u1"), entry("u2", mode="UPI", amount=200.5)]})
        assert r.status_code == 200, r.text
        assert r.json()["uids"] == ["u1", "u2"]
        g = c.get(f"/money-entries/{shop.id}").json()
        assert [e["uid"] for e in g["entries"]] == ["u1", "u2"]
        e = g["entries"][1]
        assert e["mode"] == "UPI" and e["amount"] == 200.5 and e["ref_text"] == "INV-7" and e["origin"] == "abc"
        assert g["has_more"] is False
    finally:
        app.dependency_overrides.clear()


def test_PMB2_resend_is_idempotent():
    c, db, shop, _ = setup()
    try:
        for _ in range(3):
            c.post("/money-entries/sync", json={"entries": [entry("u1")]})
        assert db.query(MoneyEntry).count() == 1
    finally:
        app.dependency_overrides.clear()


def test_PMB3_rows_are_append_only():
    c, db, shop, _ = setup()
    try:
        c.post("/money-entries/sync", json={"entries": [entry("u1")]})
        # a later push with a different amount / mode / direction must NOT change the stored row
        c.post("/money-entries/sync", json={"entries": [entry("u1", amount=1.0, mode="UPI", direction="OUT", reason="MANUAL")]})
        db.expire_all()
        row = db.query(MoneyEntry).one()
        assert (row.amount, row.mode, row.direction, row.reason) == (300.0, "CASH", "IN", "SALE")
    finally:
        app.dependency_overrides.clear()


def test_PMB4_pending_flips_to_received_once():
    c, db, shop, _ = setup()
    try:
        c.post("/money-entries/sync", json={"entries": [entry("u1", mode="UPI", status="PENDING")]})
        assert db.query(MoneyEntry).one().status == "PENDING"
        c.post("/money-entries/sync", json={"entries": [entry("u1", mode="UPI", status="RECEIVED")]})
        db.expire_all()
        assert db.query(MoneyEntry).one().status == "RECEIVED"
        c.post("/money-entries/sync", json={"entries": [entry("u1", mode="UPI", status="PENDING")]})   # stale resend
        db.expire_all()
        assert db.query(MoneyEntry).one().status == "RECEIVED"
    finally:
        app.dependency_overrides.clear()


def test_PMB5_invalid_rows_are_acked_but_not_stored():
    c, db, shop, _ = setup()
    try:
        bad = [
            entry("b1", amount=0), entry("b2", amount=-5), entry("b3", mode="GOLD"),
            entry("b4", direction="SIDEWAYS"), entry("b5", reason="LOTTERY"),
            entry("b6", status="MAYBE"), entry("b7", source_type="ALIEN"), entry("b8", amount=2e9),
            entry("b9", mode="CREDIT"),
        ]
        r = c.post("/money-entries/sync", json={"entries": bad + [entry("good")]}).json()
        assert sorted(r["uids"]) == sorted([b["uid"] for b in bad] + ["good"])    # acked: the app stops retrying
        assert [x.uid for x in db.query(MoneyEntry).all()] == ["good"]
    finally:
        app.dependency_overrides.clear()


def test_PMB6_paging_and_cursor():
    c, db, shop, _ = setup()
    try:
        c.post("/money-entries/sync", json={"entries": [entry(f"u{i}") for i in range(5)]})
        p1 = c.get(f"/money-entries/{shop.id}?limit=2").json()
        assert len(p1["entries"]) == 2 and p1["has_more"] is True
        p2 = c.get(f"/money-entries/{shop.id}?limit=2&after_id={p1['entries'][-1]['id']}").json()
        p3 = c.get(f"/money-entries/{shop.id}?limit=2&after_id={p2['entries'][-1]['id']}").json()
        got = [e["uid"] for e in p1["entries"] + p2["entries"] + p3["entries"]]
        assert got == [f"u{i}" for i in range(5)] and p3["has_more"] is False
    finally:
        app.dependency_overrides.clear()


def test_PMB7_shops_are_separate():
    c, db, shop, shop2 = setup()
    try:
        assert c.get(f"/money-entries/{shop2.id}").status_code == 403
        c.post("/money-entries/sync", json={"entries": [entry("same")]})
        # the same uid in another shop is a different row (uid is unique per shop)
        db.add(MoneyEntry(shop_id=shop2.id, uid="same", direction="IN", mode="CASH", amount=1,
                          reason="SALE", source_type="BILL", parent_type="BILL"))
        db.commit()
        assert db.query(MoneyEntry).count() == 2
        assert len(c.get(f"/money-entries/{shop.id}").json()["entries"]) == 1
    finally:
        app.dependency_overrides.clear()


def test_PMB8_timestamps_round_trip_under_utc_process():
    import time as _t
    old = os.environ.get("TZ")
    os.environ["TZ"] = "UTC"; _t.tzset()
    try:
        c, db, shop, _ = setup()
        stamp = 1_760_000_000_000
        c.post("/money-entries/sync", json={"entries": [entry("u1", created_at=stamp)]})
        assert c.get(f"/money-entries/{shop.id}").json()["entries"][0]["created_at"] == stamp
    finally:
        if old is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old
        _t.tzset()
        app.dependency_overrides.clear()


def test_PMB9_pending_can_be_cancelled_but_never_revived():
    c, db, shop, _ = setup()
    try:
        c.post("/money-entries/sync", json={"entries": [entry("u1", mode="UPI", status="PENDING")]})
        c.post("/money-entries/sync", json={"entries": [entry("u1", mode="UPI", status="CANCELLED")]})
        db.expire_all()
        assert db.query(MoneyEntry).one().status == "CANCELLED"
        c.post("/money-entries/sync", json={"entries": [entry("u1", mode="UPI", status="RECEIVED")]})   # late resend
        c.post("/money-entries/sync", json={"entries": [entry("u1", mode="UPI", status="PENDING")]})
        db.expire_all()
        assert db.query(MoneyEntry).one().status == "CANCELLED"
    finally:
        app.dependency_overrides.clear()


def test_PMB10_manual_transfer_and_reversal_rows_are_accepted():
    c, db, shop, _ = setup()
    try:
        rows = [
            entry("t1", direction="OUT", mode="CASH", amount=500.0, reason="TRANSFER", source_type="MANUAL", source_id=3, parent_type="MANUAL", parent_id=3, ref_text="Cash to bank"),
            entry("t2", direction="IN", mode="BANK", amount=500.0, reason="TRANSFER", source_type="MANUAL", source_id=3, parent_type="MANUAL", parent_id=3, ref_text="Cash to bank"),
            entry("t3", direction="IN", mode="CASH", amount=500.0, reason="TRANSFER", source_type="MANUAL", source_id=3, parent_type="MANUAL", parent_id=3, ref_text="Reversal: Cash to bank"),
        ]
        r = c.post("/money-entries/sync", json={"entries": rows})
        assert r.status_code == 200, r.text
        assert r.json()["uids"] == ["t1", "t2", "t3"]
        assert db.query(MoneyEntry).count() == 3
    finally:
        app.dependency_overrides.clear()

