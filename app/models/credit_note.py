# models/credit_note.py
"""
Credit Note (Sales Return) — stock returned by a customer.

Mirrors the Android Room pair `credit_notes` / `credit_note_items` 1:1
so the sync push is a straight column-for-column copy.

Design rules:
  • CreditNote holds the invoice-level header (totals, GST CDN fields).
  • CreditNoteItem holds per-line detail (product, qty returned, tax split).
  • Soft pointer back to the original bill via `original_invoice_id` —
    intentionally NOT a FK because the offline client may push the credit
    note before the original bill exists on the server.
  • `local_id` echoes the Android-side CreditNote.id so the sync response
    can return a {local_id → server_id} map.
"""

from datetime import datetime
from sqlalchemy import (
    BigInteger, Boolean, Column, Float, ForeignKey,
    Index, Integer, String, DateTime,
)
from sqlalchemy.orm import relationship

from app.database import Base
from app.util.time_utils import local_now, utc_now
from app.models.money_type import MONEY  # R3: exact decimal for money


class CreditNote(Base):
    __tablename__ = "credit_notes"

    id       = Column(Integer, primary_key=True, index=True)
    shop_id  = Column(Integer, ForeignKey("shops.id"), nullable=False, index=True)

    # Android-side primary key — lets sync be idempotent.
    local_id = Column(Integer, nullable=True, index=True)

    # ── Note identity ────────────────────────────────────────────────────
    # Auto-generated on the client: "CN-00001", "CN-00002", …
    note_number = Column(String, nullable=False, unique=False, index=True)

    # Epoch millis (Android System.currentTimeMillis())
    note_date   = Column(BigInteger, nullable=False, default=0)

    # Always "C" for Credit Note.
    note_type   = Column(String(1), nullable=False, default="C")

    # ── Back-reference to the original sales invoice ─────────────────────
    # NOT a FK — the original bill may not yet exist on the server when
    # this credit note is synced (offline-first architecture).
    original_invoice_id     = Column(Integer, nullable=True, index=True)
    original_invoice_number = Column(String, nullable=True)

    # Epoch millis of the original invoice date.
    original_invoice_date   = Column(BigInteger, nullable=True)

    # ── Customer ─────────────────────────────────────────────────────────
    customer_name  = Column(String, nullable=True)
    customer_gstin = Column(String, nullable=True)

    # ── GST CDN (GSTR-1 Credit/Debit Note reporting) ─────────────────────
    place_of_supply = Column(String, nullable=True)
    reverse_charge  = Column(String(1), nullable=False, default="N")   # "Y" / "N"
    supply_type     = Column(String, nullable=False, default="intrastate")
    note_supply_type = Column(String, nullable=True, default="Regular")

    # ur_type: B2B / B2CS / B2CL / EXPWP / EXPWOP / DEXP (CDN type)
    ur_type = Column(String, nullable=True)

    document_type   = Column(String, nullable=True)
    document_nature = Column(String, nullable=True)
    document_series = Column(String, nullable=True)

    # ── Aggregate financials ──────────────────────────────────────────────
    # R3: MONEY = Numeric(12,2, asdecimal=False)
    taxable_value = Column(MONEY, nullable=False, default=0.0)
    cgst_amount   = Column(MONEY, nullable=False, default=0.0)
    sgst_amount   = Column(MONEY, nullable=False, default=0.0)
    igst_amount   = Column(MONEY, nullable=False, default=0.0)
    cess_amount   = Column(MONEY, nullable=False, default=0.0)
    tax_amount    = Column(MONEY, nullable=False, default=0.0)
    total_amount  = Column(MONEY, nullable=False, default=0.0)

    # ── Sync status ───────────────────────────────────────────────────────
    sync_status = Column(String, nullable=False, default="pending")

    created_at = Column(DateTime, default=local_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now,
                        onupdate=utc_now, nullable=False)

    # Cascade: deleting a credit note removes its line items.
    items = relationship(
        "CreditNoteItem",
        back_populates="credit_note",
        cascade="all, delete-orphan",
    )


class CreditNoteItem(Base):
    __tablename__ = "credit_note_items"

    id      = Column(Integer, primary_key=True, index=True)
    note_id = Column(
        Integer,
        ForeignKey("credit_notes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Product ───────────────────────────────────────────────────────────
    product_id   = Column(Integer, nullable=True, index=True)
    product_name = Column(String, nullable=False)
    variant      = Column(String, nullable=True)
    hsn_code     = Column(String, nullable=True)
    unit         = Column(String, nullable=True)

    # ── Quantities ────────────────────────────────────────────────────────
    quantity_sold     = Column(Float, nullable=False, default=0.0)
    quantity_returned = Column(Float, nullable=False, default=0.0)

    # ── Pricing ───────────────────────────────────────────────────────────
    # R3: prices/amounts are MONEY; gst_rate stays Float (percentage)
    rate           = Column(MONEY, nullable=False, default=0.0)
    cost_price_used = Column(MONEY, nullable=False, default=0.0)  # for FIFO batch

    # ── Tax breakdown ─────────────────────────────────────────────────────
    taxable_value = Column(MONEY, nullable=False, default=0.0)
    gst_rate      = Column(Float, nullable=False, default=0.0)
    cgst_amount   = Column(MONEY, nullable=False, default=0.0)
    sgst_amount   = Column(MONEY, nullable=False, default=0.0)
    igst_amount   = Column(MONEY, nullable=False, default=0.0)
    cess_amount   = Column(MONEY, nullable=False, default=0.0)
    tax_amount    = Column(MONEY, nullable=False, default=0.0)
    total_amount  = Column(MONEY, nullable=False, default=0.0)

    # Back-ref to the exact BillItem row this return is against.
    # Nullable because not all old bill items carry an id on the server.
    original_bill_item_id = Column(Integer, nullable=True)

    credit_note = relationship("CreditNote", back_populates="items")


# ── Composite indices most used by report queries ────────────────────────────
Index(
    "ix_credit_notes_shop_created",
    CreditNote.shop_id,
    CreditNote.created_at,
)
Index(
    "ix_credit_notes_shop_invoice",
    CreditNote.shop_id,
    CreditNote.original_invoice_id,
)
