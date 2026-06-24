from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
from app.util.time_utils import epoch_ms_to_local, epoch_ms_to_utc, local_to_epoch_ms, utc_to_epoch_ms

from app.database import get_db
from app.dependencies import get_current_shop
from app.models.shop import Shop
from app.models.purchase_import_details import PurchaseImportDetails
from app.models.purchase import Purchase
from app.schemas.purchase_import_details_schema import (
    PurchaseImportDetailsSyncRequest,
    PurchaseImportDetailsSyncResponse,
    PurchaseImportDetailsOut
)

router = APIRouter(
    prefix="/purchase-import-details",
    tags=["Purchase Import Details"]
)

@router.post("/sync", response_model=PurchaseImportDetailsSyncResponse)
def sync_purchase_import_details(
    request: PurchaseImportDetailsSyncRequest,
    db: Session = Depends(get_db),
    current_shop: Shop = Depends(get_current_shop)
):
    success_count = 0
    failed = []
    record_id_map = {}

    for record in request.records:
        try:
            # Validate document type
            if record.document_type not in ["Bill of Entry", "Bill of Entry SEZ", "Bill of Entry from Bonded Warehouse"]:
                raise ValueError(f"Invalid document_type: {record.document_type}")
            
            if record.document_type == "Bill of Entry SEZ" and not record.sez_supplier_gstin:
                raise ValueError("SEZ Supplier GSTIN is required for 'Bill of Entry SEZ'")
            
            if record.bill_of_entry_value <= 0:
                raise ValueError("Bill of Entry Value must be greater than 0")

            # Resolve purchase_id
            server_purchase_id = None
            if record.purchase_id is not None:
                # Verify purchase belongs to current shop
                purchase = db.query(Purchase).filter(
                    Purchase.id == record.purchase_id,
                    Purchase.shop_id == current_shop.id
                ).first()
                if purchase:
                    server_purchase_id = purchase.id
            else:
                # Try to find purchase by local_purchase_id
                purchase = db.query(Purchase).filter(
                    Purchase.local_id == record.local_purchase_id,
                    Purchase.shop_id == current_shop.id
                ).first()
                if purchase:
                    server_purchase_id = purchase.id
            
            boe_date = epoch_ms_to_local(record.bill_of_entry_date)
            created_at = epoch_ms_to_local(record.created_at)
            updated_at = epoch_ms_to_utc(record.updated_at)

            # Check if exists (Idempotent)
            existing = db.query(PurchaseImportDetails).filter(
                PurchaseImportDetails.shop_id == current_shop.id,
                PurchaseImportDetails.local_id == record.local_id
            ).first()

            if not existing:
                # Try alternative idempotency
                existing = db.query(PurchaseImportDetails).filter(
                    PurchaseImportDetails.shop_id == current_shop.id,
                    PurchaseImportDetails.local_purchase_id == record.local_purchase_id,
                    PurchaseImportDetails.bill_of_entry_number == record.bill_of_entry_number
                ).first()

            if existing:
                # Update
                existing.purchase_id = server_purchase_id or existing.purchase_id
                existing.local_id = record.local_id
                existing.local_purchase_id = record.local_purchase_id
                existing.port_code = record.port_code
                existing.bill_of_entry_number = record.bill_of_entry_number
                existing.bill_of_entry_date = boe_date
                existing.bill_of_entry_value = record.bill_of_entry_value
                existing.document_type = record.document_type
                existing.sez_supplier_gstin = record.sez_supplier_gstin
                existing.sync_status = "synced"
                existing.device_id = record.device_id
                existing.updated_at = updated_at
            else:
                # Insert
                new_detail = PurchaseImportDetails(
                    shop_id=current_shop.id,
                    purchase_id=server_purchase_id,
                    local_id=record.local_id,
                    local_purchase_id=record.local_purchase_id,
                    port_code=record.port_code,
                    bill_of_entry_number=record.bill_of_entry_number,
                    bill_of_entry_date=boe_date,
                    bill_of_entry_value=record.bill_of_entry_value,
                    document_type=record.document_type,
                    sez_supplier_gstin=record.sez_supplier_gstin,
                    sync_status="synced",
                    device_id=record.device_id,
                    created_at=created_at,
                    updated_at=updated_at
                )
                db.add(new_detail)
                db.flush() # get id
                existing = new_detail

            success_count += 1
            record_id_map[str(record.local_id)] = existing.id

        except Exception as e:
            db.rollback()
            failed.append(f"local_id {record.local_id}: {str(e)}")
            continue

    db.commit()

    return PurchaseImportDetailsSyncResponse(
        success_count=success_count,
        record_id_map=record_id_map,
        failed=failed,
        message="Sync complete"
    )

@router.get("/{shop_id}", response_model=List[PurchaseImportDetailsOut])
def get_purchase_import_details(
    shop_id: int,
    db: Session = Depends(get_db),
    current_shop: Shop = Depends(get_current_shop)
):
    if shop_id != current_shop.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this shop's data")
    
    records = db.query(PurchaseImportDetails).filter(
        PurchaseImportDetails.shop_id == shop_id
    ).all()

    # Convert dates to epoch millis for output
    result = []
    for r in records:
        out_dict = {
            "id": r.id,
            "shop_id": r.shop_id,
            "purchase_id": r.purchase_id,
            "local_id": r.local_id,
            "local_purchase_id": r.local_purchase_id,
            "port_code": r.port_code,
            "bill_of_entry_number": r.bill_of_entry_number,
            "bill_of_entry_date": local_to_epoch_ms(r.bill_of_entry_date) if r.bill_of_entry_date else 0,
            "bill_of_entry_value": r.bill_of_entry_value,
            "document_type": r.document_type,
            "sez_supplier_gstin": r.sez_supplier_gstin,
            "sync_status": r.sync_status,
            "device_id": r.device_id,
            "created_at": local_to_epoch_ms(r.created_at) if r.created_at else 0,
            "updated_at": utc_to_epoch_ms(r.updated_at) if r.updated_at else 0
        }
        result.append(PurchaseImportDetailsOut(**out_dict))

    return result
