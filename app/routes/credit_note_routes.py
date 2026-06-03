# routes/credit_note_routes.py
"""
Credit Note (Sales Return) endpoints.

  • POST /credit-notes/sync  — bulk offline replay, idempotent on local_id
  • GET  /credit-notes       — list all credit notes for the authenticated shop

Matches the Android-side API calls in ApiService.kt:
    syncCreditNotes  → POST /credit-notes/sync
    getCreditNotes   → GET  /credit-notes

Architecture contract:
  • Idempotent on (shop_id, local_id): if a credit note with the same
    local_id already exists for this shop, it is updated in place (items
    replaced wholesale) rather than duplicated.  This makes retrying a
    failed sync safe.
  • Items are replaced wholesale on upsert — simpler than diffing, and
    credit note line items are small enough that this is fine.
  • `shop_id` in the DB row is ALWAYS taken from the authenticated shop
    (`current_shop.id`) — the client's shop_id field is ignored for
    security.
"""

from __future__ import annotations

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.dependencies import get_current_shop
from app.models.credit_note import CreditNote, CreditNoteItem
from app.schemas.credit_note_schema import (
    CreditNoteDto,
    CreditNoteItemDto,
    CreditNoteOut,
    CreditNoteSyncRequest,
    CreditNoteSyncResponse,
)

router = APIRouter(prefix="/credit-notes", tags=["Credit Notes"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _epoch_ms_to_dt(ms: int | None) -> datetime:
    """Safely convert Android epoch millis to a Python datetime."""
    if not ms:
        return datetime.utcnow()
    try:
        return datetime.utcfromtimestamp(ms / 1000)
    except (ValueError, OSError):
        return datetime.utcnow()


def _build_item(dto: CreditNoteItemDto) -> CreditNoteItem:
    return CreditNoteItem(
        product_id            = dto.product_id,
        product_name          = dto.product_name,
        variant               = dto.variant,
        hsn_code              = dto.hsn_code,
        unit                  = dto.unit,
        quantity_sold         = dto.quantity_sold,
        quantity_returned     = dto.quantity_returned,
        rate                  = dto.rate,
        cost_price_used       = dto.cost_price_used,
        taxable_value         = dto.taxable_value,
        gst_rate              = dto.gst_rate,
        cgst_amount           = dto.cgst_amount,
        sgst_amount           = dto.sgst_amount,
        igst_amount           = dto.igst_amount,
        cess_amount           = dto.cess_amount,
        tax_amount            = dto.tax_amount,
        total_amount          = dto.total_amount,
        original_bill_item_id = dto.original_bill_item_id,
    )


def _build_note(dto: CreditNoteDto, shop_id: int) -> CreditNote:
    note = CreditNote(
        shop_id                 = shop_id,
        local_id                = dto.local_id,
        note_number             = dto.note_number,
        note_date               = dto.note_date,
        note_type               = dto.note_type,
        note_supply_type        = dto.note_supply_type,
        original_invoice_id     = dto.original_invoice_id,
        original_invoice_number = dto.original_invoice_number,
        original_invoice_date   = dto.original_invoice_date,
        customer_name           = dto.customer_name,
        customer_gstin          = dto.customer_gstin,
        place_of_supply         = dto.place_of_supply,
        reverse_charge          = dto.reverse_charge,
        supply_type             = dto.supply_type,
        ur_type                 = dto.ur_type,
        document_type           = dto.document_type,
        document_nature         = dto.document_nature,
        document_series         = dto.document_series,
        taxable_value           = dto.taxable_value,
        cgst_amount             = dto.cgst_amount,
        sgst_amount             = dto.sgst_amount,
        igst_amount             = dto.igst_amount,
        cess_amount             = dto.cess_amount,
        tax_amount              = dto.tax_amount,
        total_amount            = dto.total_amount,
        sync_status             = "synced",
        created_at              = _epoch_ms_to_dt(dto.created_at),
        updated_at              = _epoch_ms_to_dt(dto.updated_at),
    )
    for item_dto in dto.items:
        note.items.append(_build_item(item_dto))
    return note


def _update_existing(existing: CreditNote, dto: CreditNoteDto) -> None:
    """Overwrite header fields and replace line items wholesale."""
    existing.note_number             = dto.note_number
    existing.note_date               = dto.note_date
    existing.note_type               = dto.note_type
    existing.note_supply_type        = dto.note_supply_type
    existing.original_invoice_id     = dto.original_invoice_id
    existing.original_invoice_number = dto.original_invoice_number
    existing.original_invoice_date   = dto.original_invoice_date
    existing.customer_name           = dto.customer_name
    existing.customer_gstin          = dto.customer_gstin
    existing.place_of_supply         = dto.place_of_supply
    existing.reverse_charge          = dto.reverse_charge
    existing.supply_type             = dto.supply_type
    existing.ur_type                 = dto.ur_type
    existing.document_type           = dto.document_type
    existing.document_nature         = dto.document_nature
    existing.document_series         = dto.document_series
    existing.taxable_value           = dto.taxable_value
    existing.cgst_amount             = dto.cgst_amount
    existing.sgst_amount             = dto.sgst_amount
    existing.igst_amount             = dto.igst_amount
    existing.cess_amount             = dto.cess_amount
    existing.tax_amount              = dto.tax_amount
    existing.total_amount            = dto.total_amount
    existing.sync_status             = "synced"
    existing.updated_at              = _epoch_ms_to_dt(dto.updated_at)

    # Replace items wholesale
    for item in list(existing.items):
        item.note_id = None  # detach before deletion
    existing.items.clear()
    for item_dto in dto.items:
        existing.items.append(_build_item(item_dto))


# ── POST /credit-notes/sync ───────────────────────────────────────────────────

@router.post("/sync", response_model=CreditNoteSyncResponse)
def sync_credit_notes(
    payload: CreditNoteSyncRequest,
    db: Session = Depends(get_db),
    current_shop=Depends(get_current_shop),
):
    """
    Idempotent bulk upsert for offline-created credit notes.

    For each note in the batch:
      1. Look up (shop_id, local_id).
      2. If found → update header + replace items.
      3. If not found → insert fresh.
    Either way the response includes a `local_id → server_id` map
    the Android client uses to mark its rows `syncStatus = 'synced'`.
    """
    response = CreditNoteSyncResponse()

    for dto in payload.credit_notes:
        try:
            if dto.note_type not in ["C", "D"]:
                raise ValueError(f"Invalid note_type: {dto.note_type}. Must be 'C' or 'D'.")
            
            if dto.note_type == "D":
                if dto.total_amount <= 0:
                    raise ValueError("Debit Note total_amount must be > 0.")
                if dto.taxable_value <= 0:
                    raise ValueError("Debit Note taxable_value must be > 0.")

            existing = (
                db.query(CreditNote)
                  .options(selectinload(CreditNote.items))
                  .filter(
                      CreditNote.shop_id  == current_shop.id,
                      CreditNote.local_id == dto.local_id,
                  )
                  .first()
            )

            if existing is not None:
                _update_existing(existing, dto)
                db.flush()
                server_id = existing.id
            else:
                note = _build_note(dto, current_shop.id)
                db.add(note)
                db.flush()
                server_id = note.id

            response.note_id_map[str(dto.local_id)] = server_id
            response.success_count += 1

        except Exception as exc:
            print(f"[credit-notes/sync] local_id={dto.local_id} failed: {exc}")
            response.failed.append({"local_id": dto.local_id, "reason": str(exc)})

    db.commit()
    response.message = f"{response.success_count}/{len(payload.credit_notes)} accepted"
    return response


# ── GET /credit-notes ─────────────────────────────────────────────────────────

@router.get("", response_model=List[CreditNoteOut])
@router.get("/", response_model=List[CreditNoteOut], include_in_schema=False)
def list_credit_notes(
    db: Session = Depends(get_db),
    current_shop=Depends(get_current_shop),
):
    """
    Returns all credit notes for the authenticated shop, newest first.
    Line items are eager-loaded so the response includes them without
    an N+1 query.
    """
    rows = (
        db.query(CreditNote)
          .options(selectinload(CreditNote.items))
          .filter(CreditNote.shop_id == current_shop.id)
          .order_by(CreditNote.created_at.desc())
          .all()
    )
    return rows
