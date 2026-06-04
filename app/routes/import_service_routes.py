from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.import_service import ImportService
from app.schemas.import_service_schema import ImportServiceCreate, ImportServiceResponse
from datetime import datetime

router = APIRouter(prefix="/import_services", tags=["Import Services"])

@router.post("/sync/{shop_id}")
def sync_import_services(shop_id: int, records: List[ImportServiceCreate], db: Session = Depends(get_db)):
    """
    Upserts ImportService records from the Android client based on local_id.
    """
    for item in records:
        # Check if record already exists by local_id (if valid) and shop_id
        db_item = None
        if item.local_id:
            db_item = db.query(ImportService).filter(
                ImportService.shop_id == shop_id,
                ImportService.local_id == item.local_id
            ).first()

        if db_item:
            # Update existing
            db_item.invoice_number = item.invoice_number
            db_item.invoice_date = datetime.fromtimestamp(item.invoice_date / 1000.0)
            db_item.invoice_value = item.invoice_value
            db_item.place_of_supply = item.place_of_supply
            db_item.rate = item.rate
            db_item.taxable_value = item.taxable_value
            db_item.igst_paid = item.igst_paid
            db_item.cess_paid = item.cess_paid
            db_item.eligibility_for_itc = item.eligibility_for_itc
            db_item.availed_itc_igst = item.availed_itc_igst
            db_item.availed_itc_cess = item.availed_itc_cess
            db_item.sync_status = "synced"
            db_item.device_id = item.device_id
        else:
            # Create new
            new_item = ImportService(
                shop_id=shop_id,
                local_id=item.local_id,
                invoice_number=item.invoice_number,
                invoice_date=datetime.fromtimestamp(item.invoice_date / 1000.0),
                invoice_value=item.invoice_value,
                place_of_supply=item.place_of_supply,
                rate=item.rate,
                taxable_value=item.taxable_value,
                igst_paid=item.igst_paid,
                cess_paid=item.cess_paid,
                eligibility_for_itc=item.eligibility_for_itc,
                availed_itc_igst=item.availed_itc_igst,
                availed_itc_cess=item.availed_itc_cess,
                sync_status="synced",
                device_id=item.device_id
            )
            db.add(new_item)

    db.commit()
    return {"message": "Import services synced successfully"}

@router.get("/{shop_id}", response_model=List[ImportServiceResponse])
def get_import_services(shop_id: int, db: Session = Depends(get_db)):
    """
    Returns all ImportService records for a given shop (used for initial pull).
    """
    records = db.query(ImportService).filter(ImportService.shop_id == shop_id).all()
    # convert datetime back to epoch for Android
    for record in records:
        record.invoice_date = int(record.invoice_date.timestamp() * 1000)
    return records
