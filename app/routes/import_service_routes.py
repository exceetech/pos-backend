from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.dependencies import get_current_shop
from app.models.shop import Shop
from app.models.import_service import ImportService
from app.schemas.import_service_schema import ImportServiceCreate, ImportServiceResponse
from datetime import datetime
from app.util.time_utils import epoch_ms_to_local, local_to_epoch_ms

router = APIRouter(prefix="/import_services", tags=["Import Services"])


@router.post("/sync")
def sync_import_services(
    records: List[ImportServiceCreate],
    db: Session = Depends(get_db),
    current_shop: Shop = Depends(get_current_shop)
):
    """
    Upserts ImportService records from the Android client.

    The shop comes from the bearer token, never from the URL. Taking it as a
    path parameter left both of these routes fully unauthenticated — anyone
    could read or write any shop's import-service records by changing the
    number in the path. Every other route in this API derives the shop from
    the token; these two were the exception.

    Returns `accepted_local_ids` so the client marks ONLY those rows synced,
    instead of blanket-marking the whole batch on HTTP 200 and silently
    dropping any row the server skipped.

    Also returns `rejected` — records that broke a GSTR-2 rule, each with the
    reason. A bad record is SKIPPED, not fatal: returning 400 for the whole
    batch meant one pre-existing invalid row (saved before these rules existed)
    would fail the request for ever, taking every valid row queued behind it
    down with it. sync_purchases skips-and-continues for the same reason.
    """
    shop_id = current_shop.id
    accepted_local_ids: list[int] = []
    rejected: list[dict] = []

    # Same tolerance as the client (PurchaseLineDialog / AddImportServiceActivity).
    # Without it the app can save a record — a claim within a rounding hair of
    # the tax paid — that the server then refuses, which is exactly the
    # mismatch that used to wedge the queue.
    EPS = 0.011

    def rule_violation(item) -> str | None:
        """First GSTR-2 rule this record breaks, or None if it is clean."""
        if item.invoice_value <= 0:
            return "invoice_value must be > 0"
        for field in ("invoice_value", "rate", "taxable_value", "igst_paid",
                      "cess_paid", "availed_itc_igst", "availed_itc_cess"):
            if getattr(item, field) < 0:
                return f"{field} must be >= 0"
        if item.availed_itc_igst > item.igst_paid + EPS:
            return "availed_itc_igst cannot exceed igst_paid"
        if item.availed_itc_cess > item.cess_paid + EPS:
            return "availed_itc_cess cannot exceed cess_paid"
        if item.eligibility_for_itc in ("Ineligible", "None"):
            if abs(item.availed_itc_igst) > 0.01 or abs(item.availed_itc_cess) > 0.01:
                return "availed ITC must be 0 when ineligible/None"
        return None

    for item in records:
        reason = rule_violation(item)
        if reason is not None:
            # Skipped, not stored. The client marks it "rejected" so it stops
            # being retried and shows in the list as needing attention.
            rejected.append({
                "local_id": item.local_id,
                "invoice_number": item.invoice_number,
                "reason": reason,
            })
            continue

        # Identify the row by (shop, device, local_id).
        #
        # local_id is the row number on the device that created the record, and
        # every device counts from 1 independently. Matching on (shop, local_id)
        # alone meant terminal B's 5th record found terminal A's 5th record and
        # overwrote it — A's invoice destroyed on the server, and A's app then
        # pulling down B's figures. device_id was stored on every row but never
        # used to tell them apart. bill_routes already matches on the device id
        # for exactly this reason.
        db_item = None
        if item.local_id:
            db_item = db.query(ImportService).filter(
                ImportService.shop_id == shop_id,
                ImportService.local_id == item.local_id,
                ImportService.device_id == item.device_id,
            ).first()

            # Rows written before device_id was recorded have none, so the match
            # above misses them and they would be duplicated on first sync.
            # Adopt such a row — but ONLY when the invoice number matches too.
            #
            # An empty device_id does not mean the row is unowned; it belongs to
            # some device, we just don't know which. Adopting on (shop, local_id)
            # alone would let terminal B claim terminal A's legacy row and
            # overwrite it — the exact collision this fix exists to prevent.
            # Requiring the invoice number makes the match specific to the
            # actual record rather than to a position in a counter.
            if db_item is None and item.device_id:
                db_item = db.query(ImportService).filter(
                    ImportService.shop_id == shop_id,
                    ImportService.local_id == item.local_id,
                    ImportService.device_id.is_(None),
                    ImportService.invoice_number == item.invoice_number,
                ).first()
                if db_item is not None:
                    db_item.device_id = item.device_id

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
        "rejected": rejected,
    }


@router.get("", response_model=List[ImportServiceResponse])
def get_import_services(
    db: Session = Depends(get_db),
    current_shop: Shop = Depends(get_current_shop)
):
    """
    Returns this shop's ImportService records (used for the initial pull).
    The shop is taken from the bearer token — see the note on /sync.
    """
    records = db.query(ImportService).filter(
        ImportService.shop_id == current_shop.id
    ).all()
    # convert datetime back to epoch for Android
    for record in records:
        record.invoice_date = local_to_epoch_ms(record.invoice_date)
    return records
