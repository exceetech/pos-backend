"""
GST Routes — All endpoints for GST profile management, data sync, and report generation.
Prefix: /gst
"""

import httpx
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.dependencies import get_current_shop
from app.models.gst_profile import StoreGstProfile
from app.models.gst_sales_record import GstSalesRecord
from app.models.gst_purchase_record import GstPurchaseRecord
from app.schemas.gst_schema import (
    GstProfileUpsert, GstProfileResponse,
    GstSalesSyncRequest, GstPurchaseSyncRequest,
    Gstr1Response, Gstr1B2BInvoice, Gstr1B2CItem,
    Gstr2Response, Gstr2Item,
    Gstr3BResponse, Gstr3BSupplyDetail,
    HsnSummaryItem
)

router = APIRouter(prefix="/gst", tags=["GST"])


# ============================================================
# 1. GSTIN Lookup
# ============================================================

@router.get("/lookup/{gstin}")
async def lookup_gstin(
    gstin: str,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):
    gstin = gstin.strip().upper()

    if len(gstin) != 15:
        raise HTTPException(status_code=400, detail="Invalid GSTIN")

    url = f"https://api.gst.gov.in/commonapi/v1.1/search?action=TP&gstin={gstin}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers={"Accept": "application/json"})

        if response.status_code == 200:
            data = response.json()

            return {
                "gstin": gstin,
                "legal_name": data.get("lgnm", ""),
                "trade_name": data.get("tradeName", ""),
                "gst_scheme": data.get("dty", "Regular"),
                "registration_type": data.get("sts", "Active"),
                "state_code": gstin[:2],
                "address": data.get("adr", "")  # 🔥 FIX
            }

    except Exception:
        pass

    return {
        "gstin": gstin,
        "legal_name": "",
        "trade_name": "",
        "gst_scheme": "Regular",
        "registration_type": "Active",
        "state_code": gstin[:2],
        "address": ""  # 🔥 FIX
    }


# ============================================================
# 2. GST Profile — Upsert
# ============================================================

@router.post("/profile", response_model=GstProfileResponse)
def upsert_gst_profile(
    data: GstProfileUpsert,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):

    existing = db.query(StoreGstProfile).filter(
        StoreGstProfile.shop_id == current_shop.id
    ).first()

    if existing:
        existing.gstin = data.gstin
        existing.legal_name = data.legal_name or existing.legal_name
        existing.trade_name = data.trade_name or existing.trade_name
        existing.gst_scheme = data.gst_scheme or existing.gst_scheme
        existing.registration_type = data.registration_type or existing.registration_type
        existing.state_code = data.state_code or existing.state_code
        existing.address = data.address or existing.address   # 🔥 FIX

        existing.sync_status = "synced"
        existing.device_id = data.device_id or existing.device_id
        existing.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(existing)
        return existing

    else:
        profile = StoreGstProfile(
            shop_id=current_shop.id,
            gstin=data.gstin,
            legal_name=data.legal_name or "",
            trade_name=data.trade_name or "",
            gst_scheme=data.gst_scheme or "",
            registration_type=data.registration_type or "",
            state_code=data.state_code or data.gstin[:2],
            address=data.address or "",   # 🔥 FIX
            sync_status="synced",
            device_id=data.device_id or ""
        )

        db.add(profile)
        db.commit()
        db.refresh(profile)
        return profile


# ============================================================
# 3. GST Profile — Get
# ============================================================

@router.get("/profile", response_model=GstProfileResponse)
def get_gst_profile(
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):
    profile = db.query(StoreGstProfile).filter(
        StoreGstProfile.shop_id == current_shop.id
    ).first()

    if not profile:
        raise HTTPException(status_code=404, detail="GST profile not configured")

    return profile


# ============================================================
# 4. HSN Summary (SHORT EXAMPLE — REST SAME)
# ============================================================

@router.get("/reports/hsn-summary")
def get_hsn_summary(
    start_date: str,
    end_date: str,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):

    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    results = db.query(
        GstSalesRecord.hsn_code,
        func.sum(GstSalesRecord.taxable_value)
    ).filter(
        GstSalesRecord.shop_id == current_shop.id,
        GstSalesRecord.invoice_date >= start,
        GstSalesRecord.invoice_date <= end
    ).group_by(GstSalesRecord.hsn_code).all()

    return results


# ============================================================
# 4. GST Sales Records — Batch Sync (Idempotent)
# ============================================================

@router.post("/sales/sync")
def sync_gst_sales_records(
    payload: GstSalesSyncRequest,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):
    """
    Batch upsert GST sales records.
    Idempotent: if record with same id exists, update it.
    Conflict on (shop_id, invoice_number) is handled via id uniqueness.
    """
    synced = 0
    skipped = 0

    for rec in payload.records:
        existing = db.query(GstSalesRecord).filter(
            GstSalesRecord.id == rec.id
        ).first()

        if existing:
            # Update only if incoming is newer (conflict resolution: prefer latest updated_at)
            incoming_ts = rec.updated_at or datetime.utcnow()
            if existing.updated_at and incoming_ts > existing.updated_at:
                existing.invoice_number = rec.invoice_number
                existing.customer_type = rec.customer_type
                existing.customer_gstin = rec.customer_gstin
                existing.place_of_supply = rec.place_of_supply
                existing.supply_type = rec.supply_type
                existing.hsn_code = rec.hsn_code
                existing.product_name = rec.product_name
                existing.quantity = rec.quantity
                existing.unit = rec.unit
                existing.taxable_value = rec.taxable_value
                existing.gst_rate = rec.gst_rate
                existing.cgst_amount = rec.cgst_amount
                existing.sgst_amount = rec.sgst_amount
                existing.igst_amount = rec.igst_amount
                existing.total_amount = rec.total_amount
                existing.sync_status = "synced"
                existing.updated_at = datetime.utcnow()
                synced += 1
            else:
                skipped += 1
        else:
            new_rec = GstSalesRecord(
                id=rec.id,
                shop_id=current_shop.id,
                invoice_number=rec.invoice_number,
                invoice_date=rec.invoice_date,
                customer_type=rec.customer_type,
                customer_gstin=rec.customer_gstin,
                place_of_supply=rec.place_of_supply,
                supply_type=rec.supply_type,
                hsn_code=rec.hsn_code,
                product_name=rec.product_name,
                quantity=rec.quantity,
                unit=rec.unit,
                taxable_value=rec.taxable_value,
                gst_rate=rec.gst_rate,
                cgst_amount=rec.cgst_amount,
                sgst_amount=rec.sgst_amount,
                igst_amount=rec.igst_amount,
                total_amount=rec.total_amount,
                sync_status="synced",
                device_id=rec.device_id or "",
                created_at=rec.created_at or datetime.utcnow()
            )
            db.add(new_rec)
            synced += 1

    db.commit()
    return {"message": f"Synced {synced}, skipped {skipped}"}


# ============================================================
# 5. GST Purchase Records — Batch Sync
# ============================================================

@router.post("/purchases/sync")
def sync_gst_purchase_records(
    payload: GstPurchaseSyncRequest,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):
    synced = 0
    skipped = 0

    for rec in payload.records:
        existing = db.query(GstPurchaseRecord).filter(
            GstPurchaseRecord.id == rec.id
        ).first()

        if existing:
            incoming_ts = rec.updated_at or datetime.utcnow()
            if existing.updated_at and incoming_ts > existing.updated_at:
                existing.supplier_gstin = rec.supplier_gstin
                existing.invoice_number = rec.invoice_number
                existing.expense_type = rec.expense_type
                existing.hsn_sac_code = rec.hsn_sac_code
                existing.description = rec.description
                existing.taxable_value = rec.taxable_value
                existing.gst_rate = rec.gst_rate
                existing.cgst_amount = rec.cgst_amount
                existing.sgst_amount = rec.sgst_amount
                existing.igst_amount = rec.igst_amount
                existing.total_amount = rec.total_amount
                existing.sync_status = "synced"
                existing.updated_at = datetime.utcnow()
                synced += 1
            else:
                skipped += 1
        else:
            new_rec = GstPurchaseRecord(
                id=rec.id,
                shop_id=current_shop.id,
                supplier_gstin=rec.supplier_gstin,
                invoice_number=rec.invoice_number,
                invoice_date=rec.invoice_date,
                expense_type=rec.expense_type,
                hsn_sac_code=rec.hsn_sac_code,
                description=rec.description or "",
                taxable_value=rec.taxable_value,
                gst_rate=rec.gst_rate,
                cgst_amount=rec.cgst_amount,
                sgst_amount=rec.sgst_amount,
                igst_amount=rec.igst_amount,
                total_amount=rec.total_amount,
                sync_status="synced",
                device_id=rec.device_id or "",
                created_at=rec.created_at or datetime.utcnow()
            )
            db.add(new_rec)
            synced += 1

    db.commit()
    return {"message": f"Synced {synced}, skipped {skipped}"}


# ============================================================
# 6. GSTR-1 Report (Outward Supplies)
# ============================================================

@router.get("/reports/gstr1", response_model=Gstr1Response)
def get_gstr1(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    records = db.query(GstSalesRecord).filter(
        GstSalesRecord.shop_id == current_shop.id,
        GstSalesRecord.invoice_date >= start,
        GstSalesRecord.invoice_date <= end
    ).all()

    # B2B: customer_type == "B2B"
    b2b_map = {}
    for r in records:
        if r.customer_type == "B2B" and r.customer_gstin:
            key = (r.customer_gstin, r.invoice_number)
            if key not in b2b_map:
                b2b_map[key] = Gstr1B2BInvoice(
                    customer_gstin=r.customer_gstin,
                    invoice_number=r.invoice_number,
                    invoice_date=r.invoice_date.strftime("%d-%m-%Y"),
                    invoice_value=0.0,
                    place_of_supply=r.place_of_supply,
                    supply_type=r.supply_type,
                    taxable_value=0.0,
                    gst_rate=r.gst_rate,
                    cgst=0.0, sgst=0.0, igst=0.0
                )
            b2b_map[key].taxable_value = round(b2b_map[key].taxable_value + r.taxable_value, 2)
            b2b_map[key].cgst = round(b2b_map[key].cgst + r.cgst_amount, 2)
            b2b_map[key].sgst = round(b2b_map[key].sgst + r.sgst_amount, 2)
            b2b_map[key].igst = round(b2b_map[key].igst + r.igst_amount, 2)
            b2b_map[key].invoice_value = round(
                b2b_map[key].taxable_value + b2b_map[key].cgst + b2b_map[key].sgst + b2b_map[key].igst, 2
            )

    # B2C: group by place_of_supply + gst_rate
    b2c_map = {}
    for r in records:
        if r.customer_type == "B2C":
            key = (r.place_of_supply, r.gst_rate, r.supply_type)
            if key not in b2c_map:
                b2c_map[key] = Gstr1B2CItem(
                    place_of_supply=r.place_of_supply,
                    supply_type=r.supply_type,
                    gst_rate=r.gst_rate,
                    taxable_value=0.0,
                    cgst=0.0, sgst=0.0, igst=0.0
                )
            b2c_map[key].taxable_value = round(b2c_map[key].taxable_value + r.taxable_value, 2)
            b2c_map[key].cgst = round(b2c_map[key].cgst + r.cgst_amount, 2)
            b2c_map[key].sgst = round(b2c_map[key].sgst + r.sgst_amount, 2)
            b2c_map[key].igst = round(b2c_map[key].igst + r.igst_amount, 2)

    # HSN Summary
    hsn_map = {}
    for r in records:
        if r.hsn_code not in hsn_map:
            hsn_map[r.hsn_code] = HsnSummaryItem(
                hsn_code=r.hsn_code,
                uom=r.unit.upper() if r.unit else "NOS",
                total_quantity=0.0,
                taxable_value=0.0,
                cgst_amount=0.0,
                sgst_amount=0.0,
                igst_amount=0.0,
                total_tax=0.0
            )
        hsn_map[r.hsn_code].total_quantity = round(hsn_map[r.hsn_code].total_quantity + r.quantity, 3)
        hsn_map[r.hsn_code].taxable_value = round(hsn_map[r.hsn_code].taxable_value + r.taxable_value, 2)
        hsn_map[r.hsn_code].cgst_amount = round(hsn_map[r.hsn_code].cgst_amount + r.cgst_amount, 2)
        hsn_map[r.hsn_code].sgst_amount = round(hsn_map[r.hsn_code].sgst_amount + r.sgst_amount, 2)
        hsn_map[r.hsn_code].igst_amount = round(hsn_map[r.hsn_code].igst_amount + r.igst_amount, 2)
        hsn_map[r.hsn_code].total_tax = round(
            hsn_map[r.hsn_code].cgst_amount + hsn_map[r.hsn_code].sgst_amount + hsn_map[r.hsn_code].igst_amount, 2
        )

    total_taxable = round(sum(r.taxable_value for r in records), 2)
    total_cgst = round(sum(r.cgst_amount for r in records), 2)
    total_sgst = round(sum(r.sgst_amount for r in records), 2)
    total_igst = round(sum(r.igst_amount for r in records), 2)

    return Gstr1Response(
        period_start=start_date,
        period_end=end_date,
        b2b=list(b2b_map.values()),
        b2c=list(b2c_map.values()),
        hsn_summary=list(hsn_map.values()),
        total_taxable_value=total_taxable,
        total_cgst=total_cgst,
        total_sgst=total_sgst,
        total_igst=total_igst
    )


# ============================================================
# 7. GSTR-2 Report (Inward / Purchases)
# ============================================================

@router.get("/reports/gstr2", response_model=Gstr2Response)
def get_gstr2(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    records = db.query(GstPurchaseRecord).filter(
        GstPurchaseRecord.shop_id == current_shop.id,
        GstPurchaseRecord.invoice_date >= start,
        GstPurchaseRecord.invoice_date <= end
    ).all()

    items = [
        Gstr2Item(
            supplier_gstin=r.supplier_gstin,
            invoice_number=r.invoice_number,
            invoice_date=r.invoice_date.strftime("%d-%m-%Y"),
            expense_type=r.expense_type,
            hsn_sac_code=r.hsn_sac_code,
            description=r.description or "",
            taxable_value=r.taxable_value,
            gst_rate=r.gst_rate,
            cgst=r.cgst_amount,
            sgst=r.sgst_amount,
            igst=r.igst_amount,
            total=r.total_amount
        )
        for r in records
    ]

    return Gstr2Response(
        period_start=start_date,
        period_end=end_date,
        records=items,
        total_taxable_value=round(sum(r.taxable_value for r in records), 2),
        total_itc_cgst=round(sum(r.cgst_amount for r in records), 2),
        total_itc_sgst=round(sum(r.sgst_amount for r in records), 2),
        total_itc_igst=round(sum(r.igst_amount for r in records), 2)
    )


# ============================================================
# 8. GSTR-3B (Tax Liability Summary)
# ============================================================

@router.get("/reports/gstr3b", response_model=Gstr3BResponse)
def get_gstr3b(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    sales = db.query(GstSalesRecord).filter(
        GstSalesRecord.shop_id == current_shop.id,
        GstSalesRecord.invoice_date >= start,
        GstSalesRecord.invoice_date <= end
    ).all()

    purchases = db.query(GstPurchaseRecord).filter(
        GstPurchaseRecord.shop_id == current_shop.id,
        GstPurchaseRecord.invoice_date >= start,
        GstPurchaseRecord.invoice_date <= end
    ).all()

    # 3.1(a) Normal rated outward supplies
    normal_sales = [r for r in sales if r.gst_rate > 0]
    zero_rated = [r for r in sales if r.gst_rate == 0]

    def make_supply_detail(records) -> Gstr3BSupplyDetail:
        return Gstr3BSupplyDetail(
            total_taxable_value=round(sum(r.taxable_value for r in records), 2),
            total_cgst=round(sum(r.cgst_amount for r in records), 2),
            total_sgst=round(sum(r.sgst_amount for r in records), 2),
            total_igst=round(sum(r.igst_amount for r in records), 2)
        )

    outward_normal = make_supply_detail(normal_sales)
    outward_zero = make_supply_detail(zero_rated)
    empty_detail = Gstr3BSupplyDetail(
        total_taxable_value=0, total_cgst=0, total_sgst=0, total_igst=0
    )

    itc = Gstr3BSupplyDetail(
        total_taxable_value=round(sum(r.taxable_value for r in purchases), 2),
        total_cgst=round(sum(r.cgst_amount for r in purchases), 2),
        total_sgst=round(sum(r.sgst_amount for r in purchases), 2),
        total_igst=round(sum(r.igst_amount for r in purchases), 2)
    )

    # Net payable = outward tax - ITC
    net_cgst = round(outward_normal.total_cgst - itc.total_cgst, 2)
    net_sgst = round(outward_normal.total_sgst - itc.total_sgst, 2)
    net_igst = round(outward_normal.total_igst - itc.total_igst, 2)

    return Gstr3BResponse(
        period_start=start_date,
        period_end=end_date,
        outward_taxable_supplies=outward_normal,
        outward_zero_rated=outward_zero,
        outward_nil_rated=empty_detail,
        inward_nil_exempt=empty_detail,
        itc_available=itc,
        net_tax_payable_cgst=max(0, net_cgst),
        net_tax_payable_sgst=max(0, net_sgst),
        net_tax_payable_igst=max(0, net_igst)
    )


# ============================================================
# 9. HSN Summary Report
# ============================================================

@router.get("/reports/hsn-summary")
def get_hsn_summary(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    results = db.query(
        GstSalesRecord.hsn_code,
        GstSalesRecord.unit,
        func.sum(GstSalesRecord.quantity).label("total_quantity"),
        func.sum(GstSalesRecord.taxable_value).label("taxable_value"),
        func.sum(GstSalesRecord.cgst_amount).label("cgst_amount"),
        func.sum(GstSalesRecord.sgst_amount).label("sgst_amount"),
        func.sum(GstSalesRecord.igst_amount).label("igst_amount"),
    ).filter(
        GstSalesRecord.shop_id == current_shop.id,
        GstSalesRecord.invoice_date >= start,
        GstSalesRecord.invoice_date <= end
    ).group_by(GstSalesRecord.hsn_code, GstSalesRecord.unit).all()

    return [
        {
            "hsn_code": r.hsn_code,
            "uom": r.unit.upper() if r.unit else "NOS",
            "total_quantity": round(r.total_quantity or 0, 3),
            "taxable_value": round(r.taxable_value or 0, 2),
            "cgst_amount": round(r.cgst_amount or 0, 2),
            "sgst_amount": round(r.sgst_amount or 0, 2),
            "igst_amount": round(r.igst_amount or 0, 2),
            "total_tax": round((r.cgst_amount or 0) + (r.sgst_amount or 0) + (r.igst_amount or 0), 2)
        }
        for r in results
    ]


# ============================================================
# 10. Email GST Report
# ============================================================

@router.post("/reports/email")
async def email_gst_report(
    report_type: str = Query(..., description="gstr1 / gstr2 / gstr3b / hsn"),
    start_date: str = Query(...),
    end_date: str = Query(...),
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):
    """
    Backend-triggered email of GST report.
    Generates the report data and sends via existing email service.
    """
    from app.services.email_service import send_gst_report_email
    try:
        await send_gst_report_email(
            shop=current_shop,
            report_type=report_type,
            start_date=start_date,
            end_date=end_date,
            db=db
        )
        return {"message": f"GST {report_type.upper()} report emailed to {current_shop.email}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Email failed: {str(e)}")
