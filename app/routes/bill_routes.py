from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.database import get_db
from app.models.bill import Bill
from app.models.bill_items import BillItem
from app.models.shop_products import ShopProduct
from app.models.global_products import GlobalProduct
from app.models.billing_settings import BillingSettings

from app.schemas.bill_schema import CreateBillRequest, CancelBillRequest
from app.util.time_utils import APP_TZ, local_now, local_to_epoch_ms, utc_to_epoch_ms, epoch_ms_to_utc
from app.dependencies import get_current_shop
from app.models.gst_profile import StoreGstProfile
from app.services.gst_service import normalize_customer_state, extract_state_code


def _resolve_shop_state_code(db: Session, shop) -> str:
    """Shop's own 2-digit state code: GST profile first, else GSTIN prefix."""
    profile = db.query(StoreGstProfile).filter(
        StoreGstProfile.shop_id == shop.id
    ).first()
    if profile and (profile.state_code or "").strip():
        return profile.state_code.strip()
    if profile and profile.gstin:
        code = extract_state_code(profile.gstin)
        if code:
            return code
    return extract_state_code(getattr(shop, "store_gstin", "") or "")

router = APIRouter(prefix="/bills", tags=["Bills"])


def _cancelled_ms_to_local(ms):
    """Epoch millis (device clock) → naive app-local datetime.
    Falls back to 'now' in the app timezone when absent/invalid."""
    from datetime import datetime
    if ms:
        try:
            return datetime.fromtimestamp(ms / 1000, tz=APP_TZ).replace(tzinfo=None)
        except (ValueError, OSError, OverflowError):
            pass
    return local_now()


# ================= CANCEL (VOID) BILL =================

@router.put("/cancel")
def cancel_bill(
    payload: CancelBillRequest,
    db: Session = Depends(get_db),
    current_shop=Depends(get_current_shop)
):
    """
    Void a single bill. Locates the row by bill_number OR by the
    idempotency pair (client_device_id, client_bill_id) — whichever the
    client supplies. Sets is_cancelled=True and active=False, so every
    report excludes it automatically (they all filter active == True).
    Never deletes the row — it must remain for audit. Idempotent:
    cancelling an already-cancelled bill succeeds.
    """
    if not payload.bill_number and payload.client_bill_id is None:
        raise HTTPException(
            status_code=400,
            detail="Either bill_number or client_bill_id is required"
        )

    query = db.query(Bill).filter(Bill.shop_id == current_shop.id)

    if payload.bill_number:
        query = query.filter(Bill.bill_number == payload.bill_number)
    else:
        query = query.filter(
            Bill.client_bill_id == payload.client_bill_id,
            Bill.client_device_id == payload.client_device_id
        )

    bill = query.first()
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")

    if not bill.is_cancelled:
        bill.is_cancelled = True
        bill.cancelled_at = _cancelled_ms_to_local(payload.cancelled_at)
        bill.active = False
        db.commit()

    return {"message": "Bill cancelled", "bill_number": bill.bill_number}


# ================= CREATE BILL =================

@router.post("/create")
def create_bill(
    data: CreateBillRequest,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):

    # ── Idempotency guard ──
    # A retried or concurrent sync of the same local bill must not create
    # a second row. The app sends its local Room bill id + device id; if a
    # bill with that key already exists for this shop, return it as-is.
    if data.client_bill_id is not None and data.client_device_id:

        # Step 1: Purge ALL stale cancelled bills for this local ID.
        # After an app reinstall / Room DB reset the device reuses IDs
        # starting from 1. There may be multiple old cancelled rows for
        # the same client_bill_id. Delete every one of them so they never
        # appear in Bill History for the new install.
        if not data.is_cancelled:
            stale = db.query(Bill).filter(
                Bill.shop_id == current_shop.id,
                Bill.client_bill_id == data.client_bill_id,
                Bill.client_device_id == data.client_device_id,
                Bill.is_cancelled == True,
            ).all()
            for s in stale:
                db.query(BillItem).filter(BillItem.bill_id == s.id).delete()
                db.delete(s)
            if stale:
                db.commit()

        # Step 2: Check for a live (non-cancelled) duplicate — true retry.
        existing = db.query(Bill).filter(
            Bill.shop_id == current_shop.id,
            Bill.client_bill_id == data.client_bill_id,
            Bill.client_device_id == data.client_device_id,
            Bill.is_cancelled == False,
        ).first()
        if existing:
            # N2 FIX: retried create may carry a void flag — apply it.
            if data.is_cancelled:
                existing.is_cancelled = True
                existing.cancelled_at = _cancelled_ms_to_local(data.cancelled_at)
                existing.active = False
                db.commit()

            return {
                "message": "Bill already exists",
                "bill_id": existing.id,
                "bill_number": existing.bill_number,
                "total_amount": existing.final_amount
            }

    # If the bill arrives already-cancelled and has no existing server record,
    # it is stale Room DB data from a previous session syncing on app startup.
    # Acknowledge it without writing a row — this prevents old cancelled bills
    # from ever appearing in Bill History.
    if data.is_cancelled:
        return {
            "message": "Cancelled bill acknowledged",
            "bill_id": -1,
            "bill_number": "",
            "total_amount": 0
        }

    total_items = 0.0

    # 🔥 BILL NUMBER
    # bill_number has a GLOBAL unique constraint (ix_bills_bill_number) —
    # it is not scoped per shop. Querying only the current shop's bills to
    # derive the next sequence number causes a UniqueViolation after a
    # factory reset: the new shop has no bills, so next_num=1, but
    # INV_{year}_1 already exists under the archived shop.
    # Fix: find the global maximum numeric suffix for INV_{year}_ across
    # ALL shops, then increment from there.
    from datetime import datetime
    from sqlalchemy import func, cast as sa_cast
    from sqlalchemy.dialects.postgresql import INTEGER as PG_INTEGER

    current_year = str(local_now().year)  # H6: app-timezone year, not server clock
    prefix = f"INV_{current_year}_"

    max_suffix = db.query(
        func.max(
            sa_cast(
                func.split_part(Bill.bill_number, "_", 3),
                PG_INTEGER
            )
        )
    ).filter(
        Bill.bill_number.like(f"{prefix}%")
    ).scalar()

    next_num = (max_suffix or 0) + 1
    next_bill_number = f"{prefix}{next_num}"

    bill_items = []

    for item in data.items:
        quantity = item.quantity
        total_items += quantity

        # Default fallback for old apps: if they don't send name, we need to fetch it.
        # But we shouldn't fail or recalculate.
        product_name = item.product_name
        if not product_name:
            product = db.query(GlobalProduct).join(
                ShopProduct,
                ShopProduct.global_product_id == GlobalProduct.id
            ).filter(
                ShopProduct.id == item.shop_product_id
            ).first()
            if product:
                product_name = product.name
            else:
                product_name = "Unknown Product"

        bill_items.append({
            "product_name": product_name,
            "shop_product_id": item.shop_product_id,
            "quantity": quantity,
            "unit": item.unit,
            "variant": item.variant,
            "unit_price": item.unit_price,
            "line_subtotal": item.line_subtotal,
            "discount_amount": item.discount_amount,
            "taxable_amount": item.taxable_amount,
            "gst_rate": item.gst_rate,
            "cgst_rate": item.cgst_rate,
            "sgst_rate": item.sgst_rate,
            "igst_rate": item.igst_rate,
            "cgst_amount": item.cgst_amount,
            "sgst_amount": item.sgst_amount,
            "igst_amount": item.igst_amount,
            "cess_amount": item.cess_amount,
            "total_amount": item.total_amount,
            "hsn_code": item.hsn_code,
            # legacy fields mapping for old app versions or backward compatibility
            "price": item.unit_price if item.unit_price > 0 else (item.line_subtotal / quantity if quantity > 0 else 0),
            "subtotal": item.line_subtotal if item.line_subtotal > 0 else item.total_amount
        })

    # Backward compatibility mappings for older app versions
    fallback_final_amount = data.final_amount if data.final_amount > 0 else data.total_amount
    fallback_discount = data.discount_amount if data.discount_amount > 0 else data.discount
    fallback_gst = data.gst_amount if data.gst_amount > 0 else data.gst

    # ── Normalize customer state: always store a consistent name + code
    # pair; when the app sends neither (local B2C sale) default both to
    # the shop's own state.
    norm_state, norm_state_code = normalize_customer_state(
        data.customer_state,
        data.customer_state_code,
        shop_state_code=_resolve_shop_state_code(db, current_shop),
    )

    bill = Bill(
        shop_id=current_shop.id,
        bill_number=str(next_bill_number),
        final_amount=fallback_final_amount,
        total_items=total_items,
        payment_method=data.payment_method,
        
        subtotal=data.subtotal if data.subtotal > 0 else data.total_amount - fallback_gst + fallback_discount,
        discount_amount=fallback_discount,
        taxable_amount=data.taxable_amount,
        
        cgst_amount=data.cgst_amount,
        sgst_amount=data.sgst_amount,
        igst_amount=data.igst_amount,
        cess_amount=data.cess_amount,
        gst_amount=fallback_gst,
        
        round_off=data.round_off,
        
        gst_scheme=data.gst_scheme,
        supply_type=data.supply_type,
        customer_state=norm_state,
        customer_state_code=norm_state_code,
        invoice_type=data.invoice_type,
        is_gst_invoice=data.is_gst_invoice,
        client_bill_id=data.client_bill_id,
        client_device_id=data.client_device_id
    )
    
    if data.created_at:
        bill.created_at = data.created_at
    else:
        # H6: fallback must use the app timezone, not the server clock,
        # so it stays comparable with device-supplied timestamps.
        bill.created_at = local_now()

    # Cancellation: a bill voided on the device BEFORE its first sync
    # arrives already cancelled — it must never count in reports.
    if data.is_cancelled:
        bill.is_cancelled = True
        bill.cancelled_at = _cancelled_ms_to_local(data.cancelled_at)
        bill.active = False

    db.add(bill)
    db.commit()
    db.refresh(bill)

    # 🔥 INSERT BILL ITEMS
    for i in bill_items:
        bill_item = BillItem(
            bill_id=bill.id,
            shop_product_id=i["shop_product_id"],
            product_name=i["product_name"],
            quantity=i["quantity"],
            unit=i["unit"],
            variant=i["variant"],
            unit_price=i["unit_price"],
            line_subtotal=i["line_subtotal"],
            discount_amount=i["discount_amount"],
            taxable_amount=i["taxable_amount"],
            gst_rate=i["gst_rate"],
            cgst_rate=i["cgst_rate"],
            sgst_rate=i["sgst_rate"],
            igst_rate=i["igst_rate"],
            cgst_amount=i["cgst_amount"],
            sgst_amount=i["sgst_amount"],
            igst_amount=i["igst_amount"],
            cess_amount=i["cess_amount"],
            total_amount=i["total_amount"],
            hsn_code=i["hsn_code"]
        )
        db.add(bill_item)

    db.commit()

    return {
        "message": "Bill created successfully",
        "bill_id": bill.id,
        "bill_number": bill.bill_number,
        "total_amount": bill.final_amount
    }


# ================= GET SINGLE BILL =================

@router.get("/{bill_id:int}")
def get_bill(
    bill_id: int,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):

    # N1 FIX: voided bills must stay VIEWABLE (audit + "Cancelled" badge).
    # Only clear-bills archives are hidden. Reports still exclude voids
    # via their own active == True filter.
    bill = db.query(Bill).filter(
        Bill.id == bill_id,
        Bill.shop_id == current_shop.id,
        or_(Bill.active == True, Bill.is_cancelled == True)
    ).first()

    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")

    items = db.query(BillItem).filter(
        BillItem.bill_id == bill_id
    ).all()

    return {
        "bill": {
            "bill_id": bill.id,
            "bill_number": bill.bill_number,
            "subtotal": bill.subtotal,
            "gst": bill.gst_amount,
            "discount": bill.discount_amount,
            "total_amount": bill.final_amount,
            "payment_method": bill.payment_method,
            "created_at": str(bill.created_at),
            "invoice_type": bill.invoice_type or "B2C",
            "customer_state": bill.customer_state,
            "customer_state_code": bill.customer_state_code,
            "supply_type": bill.supply_type,
            "is_cancelled": bool(bill.is_cancelled)  # N1
        },
        "items": [
            {
                "product_name": item.product_name,
                "price": item.unit_price,
                "quantity": item.quantity,
                "unit": item.unit,
                "variant": item.variant,
                "shop_product_id": item.shop_product_id,
                "subtotal": item.total_amount
            }
            for item in items
        ]
    }


# ================= GET ALL BILLS =================

@router.get("/cancellations")
def get_bill_cancellations(
    updated_since: int = 0,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):
    """Propagate voids across terminals (Sync re-audit, cancellation propagation).
    Returns bills cancelled since the cursor, keyed on the server-set `updated_at`
    (cancelled_at is client-supplied, so it can't be a safe cursor). `>=` so
    same-instant rows aren't skipped; the client mark is idempotent."""
    from datetime import datetime as _dt

    q = db.query(Bill).filter(
        Bill.shop_id == current_shop.id,
        Bill.is_cancelled == True,
    )
    if updated_since > 0:
        q = q.filter(Bill.updated_at >= epoch_ms_to_utc(updated_since))

    rows = q.order_by(Bill.updated_at).all()
    return [
        {
            "bill_number": b.bill_number,
            "cancelled_at": local_to_epoch_ms(b.cancelled_at) if b.cancelled_at else None,
            "updated_at": utc_to_epoch_ms(b.updated_at) if b.updated_at else None,
        }
        for b in rows
    ]


@router.get("/since")
def get_bills_since(
    after_id: int = 0,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):
    """Delta pull of full bills + tax-complete items for cross-terminal mirroring
    (Sync re-audit R3). Append-only `id` cursor: returns bills with id > after_id
    so a second terminal can reprint and run accurate returns on a bill created
    elsewhere. after_id=0 returns all (first sync)."""
    from collections import defaultdict

    bills = db.query(Bill).filter(
        Bill.shop_id == current_shop.id,
        Bill.id > after_id,
        or_(Bill.active == True, Bill.is_cancelled == True),
    ).order_by(Bill.id).all()

    bill_ids = [b.id for b in bills]
    items_by_bill = defaultdict(list)
    if bill_ids:
        for it in db.query(BillItem).filter(BillItem.bill_id.in_(bill_ids)).all():
            items_by_bill[it.bill_id].append(it)

    return [
        {
            "bill_id": b.id,
            "bill_number": b.bill_number,
            "subtotal": b.subtotal,
            "discount_amount": b.discount_amount,
            "gst_amount": b.gst_amount,
            "final_amount": b.final_amount,
            "payment_method": b.payment_method,
            "invoice_type": b.invoice_type or "B2C",
            "customer_state": b.customer_state,
            "customer_state_code": b.customer_state_code,
            "supply_type": b.supply_type,
            "cgst_amount": b.cgst_amount,
            "sgst_amount": b.sgst_amount,
            "igst_amount": b.igst_amount,
            "is_cancelled": bool(b.is_cancelled),
            "cancelled_at": local_to_epoch_ms(b.cancelled_at) if b.cancelled_at else None,
            "created_at": str(b.created_at),
            "items": [
                {
                    "shop_product_id": it.shop_product_id,
                    "product_name": it.product_name,
                    "variant": it.variant,
                    "unit": it.unit,
                    "quantity": it.quantity,
                    "unit_price": it.unit_price,
                    "line_subtotal": it.line_subtotal,
                    "taxable_amount": it.taxable_amount,
                    "gst_rate": it.gst_rate,
                    "cgst_amount": it.cgst_amount,
                    "sgst_amount": it.sgst_amount,
                    "igst_amount": it.igst_amount,
                    "total_amount": it.total_amount,
                    "hsn_code": it.hsn_code,
                }
                for it in items_by_bill.get(b.id, [])
            ],
        }
        for b in bills
    ]


@router.get("")
def get_bills(
    date: str | None = None,
    item: str | None = None,
    payment: str | None = None,
    sort: str | None = None,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):

    # N1 FIX: include voided bills (shown with a "Cancelled" badge in the
    # app); only clear-bills archives stay hidden.
    query = db.query(Bill).filter(
        Bill.shop_id == current_shop.id,
        or_(Bill.active == True, Bill.is_cancelled == True)
    )

    if payment:
        query = query.filter(Bill.payment_method == payment)

    if date:
        query = query.filter(Bill.created_at.like(f"{date}%"))

    if item:
        query = query.join(BillItem).filter(
            BillItem.product_name.ilike(f"%{item}%")
        ).distinct()

    if sort == "amount":
        query = query.order_by(Bill.final_amount.desc())
    else:
        query = query.order_by(Bill.created_at.desc())

    bills = query.all()

    return [
        {
            "bill_id": b.id,
            "bill_number": b.bill_number,
            "total_amount": b.final_amount,
            "payment_method": b.payment_method,
            "created_at": str(b.created_at),
            "is_cancelled": bool(b.is_cancelled)  # N1
        }
        for b in bills
    ]