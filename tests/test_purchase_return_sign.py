"""
Verifies the fix for the purchase-return sign bug in
app/routes/inventory_routes.py::sync_inventory_logs.

Scenario (from the bug report): purchase 100 + 100 (=200), sell 50 (=150),
return 60, then return 10. Correct final stock = 80. Before the fix,
"RETURN" was bucketed as additive, producing 150 + 60 + 10 = 220.

Run with:
    cd pos-backend && python -m pytest tests/test_purchase_return_sign.py -v
"""

import os

os.environ.setdefault("APP_TIMEZONE", "Asia/Kolkata")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.dependencies import get_current_shop
from app.models.shop import Shop
from app.models.global_products import GlobalProduct
from app.models.shop_products import ShopProduct
from app.models.inventory import Inventory  # noqa: F401 (registers table)
from app.models.inventory_log import InventoryLog  # noqa: F401 (registers table)
from app.routes.inventory_routes import router as inventory_router

# Only the inventory router is mounted (not the full app.main), so this test
# doesn't need every unrelated subsystem's env vars (mail, firebase, etc.)
# configured just to import the app.
app = FastAPI()
app.include_router(inventory_router)


def make_client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
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
    shop = Shop(shop_name="Test Shop", owner_name="Owner", email="t@example.com")
    db.add(shop)
    db.commit()
    db.refresh(shop)

    gp = GlobalProduct(name="Widget")
    db.add(gp)
    db.commit()
    db.refresh(gp)

    product = ShopProduct(shop_id=shop.id, global_product_id=gp.id, price=10.0, is_active=True)
    db.add(product)
    db.commit()
    db.refresh(product)

    def override_get_current_shop():
        return shop

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_shop] = override_get_current_shop

    return TestClient(app), product.id, TestingSessionLocal


def test_purchase_return_sign_end_to_end():
    client, product_id, SessionLocal = make_client()
    try:
        logs = [
            {"product_id": product_id, "type": "ADD", "quantity": 100, "price": 10, "client_uid": "u1"},
            {"product_id": product_id, "type": "ADD", "quantity": 100, "price": 15, "client_uid": "u2"},
            {"product_id": product_id, "type": "SALE", "quantity": 50, "price": 10, "client_uid": "u3"},
            {"product_id": product_id, "type": "PURCHASE_RETURN", "quantity": 60, "price": 10, "client_uid": "u4"},
            {"product_id": product_id, "type": "PURCHASE_RETURN", "quantity": 10, "price": 10, "client_uid": "u5"},
        ]

        resp = client.post("/inventory/sync", json=logs)
        assert resp.status_code == 200, resp.text

        resp = client.get("/inventory/my")
        assert resp.status_code == 200, resp.text
        rows = resp.json()
        row = next(r for r in rows if r["product_id"] == product_id)

        assert row["stock"] == 80.0, f"expected 80, got {row['stock']}"
    finally:
        app.dependency_overrides.clear()


def test_legacy_return_type_still_additive_for_backward_compat():
    """
    The historical "RETURN" type (never actually written by the app for
    purchase returns, but present in old synced data) stays in the
    additive bucket unchanged — only the new PURCHASE_RETURN type is
    subtractive. This test just documents/locks that behavior.
    """
    client, product_id, SessionLocal = make_client()
    try:
        logs = [
            {"product_id": product_id, "type": "ADD", "quantity": 50, "price": 10, "client_uid": "u1"},
            {"product_id": product_id, "type": "RETURN", "quantity": 20, "price": 10, "client_uid": "u2"},
        ]
        resp = client.post("/inventory/sync", json=logs)
        assert resp.status_code == 200, resp.text

        resp = client.get("/inventory/my")
        row = next(r for r in resp.json() if r["product_id"] == product_id)
        assert row["stock"] == 70.0, f"expected 70 (additive RETURN bucket unchanged), got {row['stock']}"
    finally:
        app.dependency_overrides.clear()
