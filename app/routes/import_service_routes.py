from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.import_service import ImportService
from app.schemas.import_service_schema import ImportServiceCreate, ImportServiceResponse
from datetime import datetime
from app.util.time_utils import epoch_ms_to_local, local_to_epoch_ms

router = APIRouter(prefix="/import_services", tags=["Import Services"])

@router.post("/sync/{shop_id}")
def sync_import_services(shop_id: int, records: List[ImportServiceCreate], db: Session = Depends(get_db)):
    """
    Upserts ImportService records from the Android client based on local_id.

    Returns the list of local_ids that were accepted (M1) so the client marks
    ONLY those rows synced — instead of blanket-marking the whole batch on HTTP
    200, which would silently drop any row the server skipped.
    """
    accepted_local_ids: list[int] = []
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
            db_item.invoice_date = epoch_ms_to_local(item.invoice_date)
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
                invoice_date=epoch_ms_to_local(item.invoice_date),
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

        # A record with no local_id can't be acknowledged back to the client
        # (it has no key to mark synced), so only echo ones that carry it.
        if item.local_id:
            accepted_local_ids.append(item.local_id)

    db.commit()
    return {
        "message": "Import services synced successfully",
        "accepted_local_ids": accepted_local_ids,
    }

@router.get("/{shop_id}", response_model=List[ImportServiceResponse])
def get_import_services(shop_id: int, db: Session = Depends(get_db)):
    """
    Returns all ImportService records for a given shop (used for initial pull).
    """
    records = db.query(ImportService).filter(ImportService.shop_id == shop_id).all()
    # convert datetime back to epoch for Android
    for record in records:
        record.invoice_date = local_to_epoch_ms(record.invoice_date)
    return records
