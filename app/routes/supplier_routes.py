from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.dependencies import get_current_shop
from app.models.shop import Shop
from app.models.supplier import Supplier
from app.schemas.supplier_schema import (
    SupplierSyncRequest, SupplierSyncResponse, SupplierRemote,
    SupplierListResponse, SupplierLookupResponse, SupplierMatchResponse,
    SupplierAccountRequest,
)

router = APIRouter(prefix="/suppliers", tags=["Suppliers"])


def _norm_gstin(gstin: Optional[str]) -> Optional[str]:
    """GSTINs are stored uppercased; blank is treated as absent, not as ''."""
    g = (gstin or "").strip().upper()
    return g or None


def _name_key(name: str) -> str:
    return (name or "").strip().lower()


def _find_existing(db: Session, shop_id: int, gstin: Optional[str], name_key: str):
    """
    Resolves a supplier the same way the client does.

    A GSTIN is the identity when present. Without one, the lowercased name is
    the fallback key — which is why two *registered* suppliers may share a name
    but two unregistered ones may not.
    """
    if gstin:
        return db.query(Supplier).filter(
            Supplier.shop_id == shop_id,
            Supplier.gstin == gstin,
        ).first()

    return db.query(Supplier).filter(
        Supplier.shop_id == shop_id,
        Supplier.gstin.is_(None),
        Supplier.name_key == name_key,
    ).first()


def _apply(row: Supplier, name: str, gstin: Optional[str], state: Optional[str],
           state_code: Optional[str], last_used_at: int, updated_at: int) -> None:
    """
    Writes incoming values onto a row, newest-wins.

    A device that has been offline can push an older copy of a supplier the
    user has since renamed elsewhere. Comparing updated_at stops that stale
    copy overwriting the newer one — but last_used_at always takes the highest
    value, because "most recently used" is a fact about the supplier, not about
    which device is reporting it.
    """
    if updated_at >= (row.updated_at or 0):
        row.name = name
        row.name_key = _name_key(name)
        row.gstin = gstin
        row.state = state
        row.state_code = state_code
        row.updated_at = updated_at

    row.last_used_at = max(row.last_used_at or 0, last_used_at or 0)
    row.is_active = True


@router.post("/sync", response_model=SupplierSyncResponse)
def sync_suppliers(
    body: SupplierSyncRequest,
    db: Session = Depends(get_db),
    current_shop: Shop = Depends(get_current_shop),
):
    """
    Batch upsert. Returns local_id -> server id so the client can stamp its
    rows, which is what stops the next sync creating duplicates.
    """
    shop_id = current_shop.id
    id_map: dict[str, int] = {}
    count = 0

    for item in body.suppliers:
        name = (item.name or "").strip()
        if not name:
            continue

        gstin = _norm_gstin(item.gstin)
        key = _name_key(name)

        row = _find_existing(db, shop_id, gstin, key)

        if row is None:
            row = Supplier(
                shop_id=shop_id,
                name=name,
                name_key=key,
                gstin=gstin,
                state=item.state,
                state_code=item.state_code,
                last_used_at=item.last_used_at,
                updated_at=item.updated_at,
                is_active=True,
            )
            db.add(row)
            # Needed before the id exists, so the map can be returned.
            db.flush()
        else:
            _apply(row, name, gstin, item.state, item.state_code,
                   item.last_used_at, item.updated_at)

        id_map[str(item.local_id)] = row.id
        count += 1

    db.commit()
    return SupplierSyncResponse(
        success_count=count,
        supplier_id_map=id_map,
        message="Suppliers synced",
    )


@router.post("/account", response_model=SupplierRemote)
def upsert_supplier_account(
    body: SupplierAccountRequest,
    db: Session = Depends(get_db),
    current_shop: Shop = Depends(get_current_shop),
):
    """Single-supplier upsert, same identity rules as /sync."""
    shop_id = current_shop.id
    name = (body.name or "").strip()
    gstin = _norm_gstin(body.gstin)
    key = _name_key(name)

    row = _find_existing(db, shop_id, gstin, key)

    if row is None:
        row = Supplier(
            shop_id=shop_id,
            name=name,
            name_key=key,
            gstin=gstin,
            state=body.state,
            state_code=body.state_code,
            last_used_at=body.last_used_at,
            updated_at=body.updated_at,
            is_active=True,
        )
        db.add(row)
    else:
        _apply(row, name, gstin, body.state, body.state_code,
               body.last_used_at, body.updated_at)

    db.commit()
    db.refresh(row)
    return row


@router.get("", response_model=SupplierListResponse)
def get_suppliers(
    db: Session = Depends(get_db),
    current_shop: Shop = Depends(get_current_shop),
):
    """Full pull for seeding a fresh device. Most recently used first."""
    rows = db.query(Supplier).filter(
        Supplier.shop_id == current_shop.id,
        Supplier.is_active.is_(True),
    ).order_by(Supplier.last_used_at.desc()).all()

    return SupplierListResponse(suppliers=rows)


@router.get("/by-gstin", response_model=SupplierLookupResponse)
def get_supplier_by_gstin(
    gstin: str = Query(...),
    db: Session = Depends(get_db),
    current_shop: Shop = Depends(get_current_shop),
):
    """Identity lookup — at most one row, because GSTIN is unique per shop."""
    g = _norm_gstin(gstin)
    if not g:
        return SupplierLookupResponse(found=False, supplier=None)

    row = db.query(Supplier).filter(
        Supplier.shop_id == current_shop.id,
        Supplier.gstin == g,
        Supplier.is_active.is_(True),
    ).first()

    return SupplierLookupResponse(found=row is not None, supplier=row)


@router.get("/by-name", response_model=SupplierMatchResponse)
def get_suppliers_by_name(
    name: str = Query(...),
    db: Session = Depends(get_db),
    current_shop: Shop = Depends(get_current_shop),
):
    """
    Returns a LIST, never a single row.

    A trade name can belong to several suppliers — different GSTIN, different
    branch, different state. The client must not autofill unless exactly one
    comes back: guessing puts the wrong state on the invoice, which flips
    CGST+SGST to IGST and produces a wrong tax figure.
    """
    key = _name_key(name)
    if not key:
        return SupplierMatchResponse(suppliers=[])

    rows = db.query(Supplier).filter(
        Supplier.shop_id == current_shop.id,
        Supplier.name_key == key,
        Supplier.is_active.is_(True),
    ).order_by(Supplier.last_used_at.desc()).all()

    return SupplierMatchResponse(suppliers=rows)
