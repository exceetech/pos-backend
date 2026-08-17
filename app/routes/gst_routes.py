"""
GST Routes — All endpoints for GST profile management, data sync, and report generation.
Prefix: /gst
"""

import httpx
from datetime import datetime
from app.util.time_utils import local_now, utc_now
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, and_
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_shop, require_premium_tier
from app.services.gst_service import INDIA_STATES
from app.models.gst_profile import StoreGstProfile
# GstSalesRecord retired (Report 3, C3) — table dropped, model deleted.
from app.models.gst_purchase_record import GstPurchaseRecord
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.import_service import ImportService
from app.models.purchase_import_details import PurchaseImportDetails
from app.models.purchase_return import PurchaseReturn
from app.models.gst_sales_invoice import GstSalesInvoice
from app.models.credit_note import CreditNote, CreditNoteItem
from app.models.bill import Bill
from app.util.gst_sales_lookup import get_active_invoice_line_items, supply_type_of
from app.schemas.gst_schema import (
    GstProfileUpsert, GstProfileResponse,
    GstPurchaseSyncRequest,
    Gstr1Response, Gstr1B2BInvoice, Gstr1B2CItem,
    Gstr1B2CLItem, Gstr1B2CSItem, Gstr1CdnrItem, Gstr1CdnurItem, Gstr1DocsItem,
    Gstr1EcoItem, Gstr1EcoB2BItem, Gstr1EcoB2CItem, Gstr1EcoUrp2BItem, Gstr1EcoUrp2CItem,
    Gstr2Response, Gstr2B2bItem, Gstr2B2burItem, Gstr2ImpsItem, Gstr2ImpgItem,
    Gstr2CdnrItem, Gstr2CdnurItem, Gstr2ExempItem, Gstr2HsnsumItem,
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
        existing.updated_at = utc_now()

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
# 4. GST Sales Records — Batch Sync — REMOVED (Report 3, C3)
# ============================================================
# POST /gst/sales/sync and its GstSalesRecord model/table are gone. The
# client stopped calling this in C2; the table itself was dropped from the
# backend in this change (see the startup migration in main.py). All GST
# reporting reads gst_sales_invoice(+items) exclusively now (A2/C1).
# ============================================================


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

    # Batch-fetch every existing row this payload could touch in one
    # query instead of one SELECT per record (N+1) — a shop syncing after
    # being offline a while can easily send hundreds of records, and this
    # used to be hundreds of individual round-trips to the database.
    record_ids = [rec.id for rec in payload.records]
    existing_by_id = {
        row.id: row
        for row in db.query(GstPurchaseRecord)
        .filter(GstPurchaseRecord.id.in_(record_ids))
        .all()
    } if record_ids else {}

    for rec in payload.records:
        existing = existing_by_id.get(rec.id)

        if existing:
            incoming_ts = rec.updated_at or utc_now()
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
                existing.updated_at = utc_now()
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
                created_at=rec.created_at or local_now()
            )
            db.add(new_rec)
            synced += 1

    db.commit()
    return {"message": f"Synced {synced}, skipped {skipped}"}


# ============================================================
# 6. GSTR-1 Report (Outward Supplies)
# ============================================================

# B2C-large reporting threshold for inter-state supplies to unregistered
# persons (Table 5, GSTR-1). Notification 12/2024-Central Tax (10 Jul 2024)
# reduced it from Rs 2.5 lakh to Rs 1 lakh with effect from 1 August 2024.
# It is period-dependent, so old filing periods still use the old limit —
# do NOT hardcode a single value.
_B2CL_THRESHOLD_OLD = 250_000.0   # up to Jul 2024 return period
_B2CL_THRESHOLD_NEW = 100_000.0   # Aug 2024 onward
_B2CL_CUTOVER = datetime(2024, 8, 1)


def b2cl_threshold_for(period_start: datetime) -> float:
    """The B2CL threshold applicable to the return period starting [period_start]."""
    return _B2CL_THRESHOLD_NEW if period_start >= _B2CL_CUTOVER else _B2CL_THRESHOLD_OLD


@router.get("/reports/gstr1", response_model=Gstr1Response)
def get_gstr1(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
    # Premium-gated: GST reports are a Premium-only feature (see the
    # onboarding/subscription plan, §5.1/§5.2). require_premium_tier
    # already runs the same auth/subscription checks get_current_shop
    # does, plus the tier check, so this is a straight swap, not an
    # addition of a second check.
    current_shop = Depends(require_premium_tier)
):
    """
    Phase 1 (GSTR-1 online-parity plan): ported from the on-device
    Gstr1Generator.kt so the app can be switched from Room-only to this
    endpoint without losing any section. Sections covered: B2B, B2CL, B2CS,
    CDNR, CDNUR, HSN (split B2B/B2C, plus the legacy combined fields kept
    for back-compat), DOCS.

    Phase 2 of the GST-reports error-fix round: ECO / ECO-B2B / ECO-B2C /
    ECO-URP2B / ECO-URP2C e-commerce-operator tables are now also ported
    (previously deferred here as a follow-up — this is that follow-up).
    Same classification rules as Gstr1Generator.kt: any active invoice with
    a non-blank eco_role counts, then role text ("B2B"/"B2C"/"URP") plus
    presence of customer_gst / eco_recipient_gstin decides which detail
    table each rate-slab of the invoice lands in.

    Phase 2 (leap-year fix): this endpoint takes start/end as plain
    YYYY-MM-DD strings and relies on the caller to pass calendar-correct
    boundaries — unlike the old client-side Gstr2ViewModel.resolveDates(),
    there is no hardcoded "Feb 1-28" anywhere in this date handling.

    Phase 5 (rounding fix): every row below is rounded to 2 decimals (3 for
    quantities) at construction time, not just in the final totals, so a
    report's own line items always sum to its own summary numbers.
    """
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    profile = db.query(StoreGstProfile).filter(StoreGstProfile.shop_id == current_shop.id).first()
    shop_state = (profile.state_code if profile else None) or ""

    def r2(v) -> float:
        return round(v or 0.0, 2)

    def fmt_date(dt: datetime) -> str:
        return dt.strftime("%d-%b-%y").upper() if dt else ""

    def fmt_ms(ms) -> str:
        return datetime.fromtimestamp(ms / 1000).strftime("%d-%b-%y").upper() if ms else ""

    def effective_rate(item) -> float:
        cgst_sgst = (item.sales_cgst_percentage or 0.0) + (item.sales_sgst_percentage or 0.0)
        return round((item.sales_igst_percentage or 0.0) if (item.sales_igst_percentage or 0.0) > 0.0 else cgst_sgst, 2)

    def map_gstr_invoice_type(t) -> str:
        """Mirror of Gstr1Generator.mapGstrInvoiceType — only the three special
        GST portal wordings pass through; anything else is a Regular supply."""
        allowed = ("SEZ supplies with payment", "SEZ supplies without payment", "Deemed Exp")
        return t if t in allowed else "Regular"

    def fmt_pos(state_code, place_of_supply) -> str:
        pos = place_of_supply or ""
        if state_code and "-" not in pos:
            return f"{state_code}-{pos}"
        return pos

    def norm_pos(raw) -> str:
        """
        Normalise a credit/debit note's place of supply to the portal's
        "NN-State Name" form.

        Notes copy Bill.placeOfSupply, which stores only the bare 2-digit state
        code ("33"), while the invoice tables run their POS through fmt_pos()
        and emit "33-Tamil Nadu". That left CDNR/CDNUR inconsistent with the
        rest of the report and in a shape the offline utility doesn't expect.
        Normalised on output so existing notes are fixed without a migration.
        """
        pos = (raw or "").strip()
        if not pos or "-" in pos:
            return pos
        if pos.isdigit():
            code = pos.zfill(2)
            name = INDIA_STATES.get(code)
            return f"{code}-{name}" if name else code
        # Stored as a bare state name — recover the code from the name.
        for code, name in INDIA_STATES.items():
            if name.lower() == pos.lower():
                return f"{code}-{name}"
        return pos

    # ── Pull active (non-cancelled) invoice+item rows, source of truth ─────
    active_rows = get_active_invoice_line_items(db, current_shop.id, start, end)

    invoices_by_id: dict[int, GstSalesInvoice] = {}
    items_by_invoice: dict[int, list] = {}
    for inv, item in active_rows:
        invoices_by_id[inv.id] = inv
        items_by_invoice.setdefault(inv.id, []).append(item)

    b2b_invoice_ids = [iid for iid, inv in invoices_by_id.items() if inv.invoice_type == "B2B"]
    b2c_invoice_ids = [iid for iid, inv in invoices_by_id.items() if inv.invoice_type != "B2B"]

    def is_interstate_invoice(iid: int) -> bool:
        """
        Is this supply inter-state (the B2CL / Table 5 test)?

        Two bugs used to live in the old one-liner
        `bool(pos_code) and pos_code != shop_state`:

        1. `shop_state` falls back to "" when the store's GST profile has no
           state code (the column defaults to "" and the upsert schema treats
           it as optional). Every customer state code then compared "different",
           so local B2C sales above the threshold were filed as inter-state
           B2CL. Now a blank shop state means "can't tell" and we do NOT guess.

        2. It ignored the tax actually charged. An invoice with IGST on it IS
           inter-state by definition, even if customer_state_code was never
           captured — those used to slide into B2CS. B2B already derives supply
           type from IGST (supply_type_of), so this also makes the two sections
           agree on what inter-state means.
        """
        # Strongest evidence: IGST was charged on the invoice.
        if any((i.igst_amount or 0.0) > 0.0 for i in items_by_invoice.get(iid, [])):
            return True
        # Fall back to state codes, but only when the shop's own state is known.
        if not shop_state:
            return False
        pos_code = invoices_by_id[iid].customer_state_code or ""
        return bool(pos_code) and pos_code != shop_state

    b2cl_threshold = b2cl_threshold_for(start)
    b2cl_ids = []
    for iid in b2c_invoice_ids:
        inv = invoices_by_id[iid]
        if is_interstate_invoice(iid) and (inv.grand_total or 0.0) > b2cl_threshold:
            b2cl_ids.append(iid)
    b2cl_id_set = set(b2cl_ids)
    b2cs_ids = [iid for iid in b2c_invoice_ids if iid not in b2cl_id_set]

    # ── B2B rows (grouped per invoice per rate) ─────────────────────────────
    b2b_rows: list[Gstr1B2BInvoice] = []
    for iid in b2b_invoice_ids:
        inv = invoices_by_id[iid]
        by_rate: dict[float, list] = {}
        for item in items_by_invoice[iid]:
            by_rate.setdefault(effective_rate(item), []).append(item)
        for rate, items in by_rate.items():
            taxable = sum(i.taxable_amount or 0.0 for i in items)
            cgst = sum(i.cgst_amount or 0.0 for i in items)
            sgst = sum(i.sgst_amount or 0.0 for i in items)
            igst = sum(i.igst_amount or 0.0 for i in items)
            cess = sum(i.cess_amount or 0.0 for i in items)
            b2b_rows.append(Gstr1B2BInvoice(
                customer_gstin=inv.customer_gst or "",
                invoice_number=inv.invoice_number or "",
                invoice_date=fmt_ms(inv.invoice_date),
                invoice_value=r2(inv.grand_total),
                place_of_supply=fmt_pos(inv.customer_state_code, inv.customer_state),
                supply_type=supply_type_of(items[0]),
                taxable_value=r2(taxable),
                gst_rate=rate,
                cgst=r2(cgst), sgst=r2(sgst), igst=r2(igst),
                # Table 4 attributes that decide 4A vs 4B vs SEZ/deemed-export
                # treatment. These columns already existed on the invoice; the
                # report just never carried them through.
                receiver_name=inv.business_name or inv.customer_name or "",
                reverse_charge=inv.reverse_charge or "N",
                invoice_type=map_gstr_invoice_type(inv.gstr_invoice_type),
                ecom_gstin=inv.ecommerce_gstin or "",
                cess_amount=r2(cess)
            ))

    # ── B2CL rows ────────────────────────────────────────────────────────
    b2cl_rows: list[Gstr1B2CLItem] = []
    for iid in b2cl_ids:
        inv = invoices_by_id[iid]
        by_rate: dict[float, list] = {}
        for item in items_by_invoice[iid]:
            by_rate.setdefault(effective_rate(item), []).append(item)
        for rate, items in by_rate.items():
            b2cl_rows.append(Gstr1B2CLItem(
                invoice_number=inv.invoice_number or "",
                invoice_date=fmt_ms(inv.invoice_date),
                invoice_value=r2(inv.grand_total),
                place_of_supply=fmt_pos(inv.customer_state_code, inv.customer_state),
                rate=rate,
                taxable_value=r2(sum(i.taxable_amount or 0.0 for i in items)),
                cess_amount=r2(sum(i.cess_amount or 0.0 for i in items)),
                ecom_gstin=inv.ecommerce_gstin or ""
            ))

    # ── B2CS rows (aggregate per place-of-supply per rate per ecom flag) ──
    b2cs_agg: dict[tuple, dict] = {}
    for iid in b2cs_ids:
        inv = invoices_by_id[iid]
        pos = fmt_pos(inv.customer_state_code, inv.customer_state)
        ecom = inv.ecommerce_gstin or ""
        for item in items_by_invoice[iid]:
            rate = effective_rate(item)
            key = (pos, rate, ecom)
            agg = b2cs_agg.setdefault(key, {"taxable": 0.0, "cess": 0.0, "is_ecom": bool(ecom)})
            agg["taxable"] += item.taxable_amount or 0.0
            agg["cess"] += item.cess_amount or 0.0
    # NOTE: b2cs_rows are built further down, AFTER the credit/debit notes are
    # processed. Table 7 has to be reported *net* of notes issued against small
    # B2C supplies, so those notes subtract from b2cs_agg before it's frozen
    # into rows. Building the rows here would report gross sales.

    # ── CDNR / CDNUR (sales-side credit/debit notes) ────────────────────────
    # CreditNote has no invoice_date-style column to filter on directly for
    # "period" the way invoices do — it uses note_date (epoch ms), which is
    # the correct field to filter a CDN report by (the note itself, not the
    # original sale, is what belongs to this return period).
    #
    # Round 5 fix: this query used to have no exclusion at all for a note
    # issued against a bill that was LATER cancelled — so a voided sale's
    # credit note kept appearing in GSTR-1's CDNR/CDNUR indefinitely,
    # referencing an invoice number that's no longer valid once the
    # original bill is void. The on-device Room path already had this
    # exact fix (Gstr1Repository.fetchForPeriod's `cancelledBillIds`
    # filter, "Deep-dive fix Issue 5"), and the email service's own GSTR-1
    # summary had the same fix — but the exclusion was never carried over
    # to this newer backend endpoint when it was built. Joined on
    # `bill_number` rather than `original_invoice_id`, matching the email
    # service's proven pattern (original_invoice_id is a soft, non-FK
    # pointer that isn't safe to trust for a join — see the purchase-return
    # audit's local-id-collision finding from an earlier round).
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    notes = (
        db.query(CreditNote)
        .outerjoin(Bill, CreditNote.original_invoice_number == Bill.bill_number)
        .filter(
            CreditNote.shop_id == current_shop.id,
            CreditNote.note_date >= start_ms,
            CreditNote.note_date <= end_ms,
            or_(
                Bill.id == None,  # noqa: E711 - SQLAlchemy requires `== None`, not `is None`
                and_(Bill.active == True, Bill.is_cancelled == False),  # noqa: E712
            ),
        )
        .all()
    )
    # Original invoices behind unregistered notes. Whether a note belongs in
    # CDNUR depends on the ORIGINAL supply, not on the note — and the original
    # may predate this return period, so it needs its own lookup.
    _orig_numbers = {
        (n.original_invoice_number or "").strip()
        for n in notes if not n.customer_gstin
    } - {""}
    originals_by_number: dict[str, GstSalesInvoice] = {}
    if _orig_numbers:
        for _inv in (
            db.query(GstSalesInvoice)
            .filter(
                GstSalesInvoice.shop_id == current_shop.id,
                GstSalesInvoice.invoice_number.in_(_orig_numbers),
            )
            .all()
        ):
            originals_by_number[(_inv.invoice_number or "").strip()] = _inv

    def cdnur_type_for(note):
        """
        The CDNUR ur_type for an unregistered note, or None when the note does
        not belong in Table 9B at all (net it into Table 7 instead).

        Only notes against B2CL / export / SEZ supplies go to CDNUR. A note
        against an ordinary small B2C sale is netted into Table 7, which is
        where Table 7's negatives come from.

        Deliberately does NOT trust ur_type == "B2CS" as a decision: the app
        only ever writes "B2CS" (unregistered) or "B2B" (registered) and never
        "B2CL", so believing it would misfile every note raised against a
        genuine B2CL sale. The original invoice decides instead, and the
        threshold is applied to the ORIGINAL invoice value — a small partial
        refund against a large B2CL sale is still a B2CL note.
        """
        ut = (note.ur_type or "").strip().upper()
        if ut in ("EXPWP", "EXPWOP", "EXPORT", "DEXP", "SEZWP", "SEZWOP"):
            return ut

        orig = originals_by_number.get((note.original_invoice_number or "").strip())
        if orig is not None:
            was_inter = (orig.total_igst or 0.0) > 0.0 or bool(
                shop_state
                and (orig.customer_state_code or "")
                and orig.customer_state_code != shop_state
            )
            if was_inter and (orig.grand_total or 0.0) > b2cl_threshold:
                return "B2CL"
            return None

        # Original not found (e.g. imported history) — fall back to the note's
        # own substance, which is the best evidence left.
        is_inter = (note.supply_type or "").strip().lower() == "interstate" or \
                   any((i.igst_amount or 0.0) > 0.0 for i in note.items)
        if is_inter and abs(note.total_amount or 0.0) > b2cl_threshold:
            return "B2CL"
        return None

    cdnr_rows: list[Gstr1CdnrItem] = []
    cdnur_rows: list[Gstr1CdnurItem] = []
    for note in notes:
        note_date_str = fmt_ms(note.note_date)
        items = note.items
        if note.customer_gstin:
            by_rate: dict[float, list] = {}
            for i in items:
                by_rate.setdefault(i.gst_rate or 0.0, []).append(i)
            for rate, its in by_rate.items():
                cdnr_rows.append(Gstr1CdnrItem(
                    customer_gstin=note.customer_gstin,
                    receiver_name=note.customer_name or "",
                    note_number=note.note_number,
                    note_date=note_date_str,
                    note_type=note.note_type or "C",
                    place_of_supply=norm_pos(note.place_of_supply),
                    reverse_charge=note.reverse_charge or "N",
                    note_supply_type=note.note_supply_type or "",
                    note_value=r2(note.total_amount),
                    rate=rate,
                    taxable_value=r2(sum(i.taxable_value or 0.0 for i in its)),
                    cess_amount=r2(sum(i.cess_amount or 0.0 for i in its))
                ))
        elif (cdnur_ur_type := cdnur_type_for(note)) is not None:
            by_rate: dict[float, list] = {}
            for i in items:
                by_rate.setdefault(i.gst_rate or 0.0, []).append(i)
            for rate, its in by_rate.items():
                cdnur_rows.append(Gstr1CdnurItem(
                    # Derived, not copied: the stored ur_type is only ever
                    # "B2CS"/"B2B", neither of which is a valid CDNUR category.
                    ur_type=cdnur_ur_type,
                    note_number=note.note_number,
                    note_date=note_date_str,
                    note_type=note.note_type or "C",
                    place_of_supply=norm_pos(note.place_of_supply),
                    note_value=r2(note.total_amount),
                    rate=rate,
                    taxable_value=r2(sum(i.taxable_value or 0.0 for i in its)),
                    cess_amount=r2(sum(i.cess_amount or 0.0 for i in its))
                ))
        else:
            # Note against a SMALL B2C supply. Table 9B (CDNUR) only covers
            # notes on B2CL / export / SEZ supplies — a note on a B2CS sale is
            # netted into Table 7 instead, because Table 7 carries no invoice
            # detail to adjust. Credit notes reduce the bucket, debit notes add
            # to it. Buckets may go negative in a month of heavy refunds; that
            # is legitimate and the portal accepts it.
            sign = -1.0 if (note.note_type or "C").upper() == "C" else 1.0
            # Must be the SAME shape as the invoice-side key (fmt_pos gives
            # "33-Tamil Nadu"); a raw "33" here would never match, and the note
            # would create its own negative row instead of netting off.
            pos = norm_pos(note.place_of_supply)
            for i in items:
                rate = i.gst_rate or 0.0
                key = (pos, rate, "")
                agg = b2cs_agg.setdefault(
                    key, {"taxable": 0.0, "cess": 0.0, "is_ecom": False}
                )
                agg["taxable"] += sign * (i.taxable_value or 0.0)
                agg["cess"] += sign * (i.cess_amount or 0.0)

    # ── B2CS rows — built here, now that notes have been netted in ──────────
    # Deferred from the aggregation above on purpose: Table 7 must be reported
    # net of credit/debit notes issued against small B2C supplies.
    b2cs_rows = [
        Gstr1B2CSItem(
            type="E" if v["is_ecom"] else "OE",
            place_of_supply=pos,
            rate=rate,
            taxable_value=r2(v["taxable"]),
            cess_amount=r2(v["cess"]),
            ecom_gstin=ecom
        )
        for (pos, rate, ecom), v in b2cs_agg.items()
    ]

    # ── HSN summary, split B2B / B2C (B2CL + B2CS) ──────────────────────────
    def add_to_hsn_agg(agg: dict, iid: int):
        inv = invoices_by_id[iid]
        for item in items_by_invoice[iid]:
            # Blank, not "N/A", when a product has no HSN: "N/A" is not a valid
            # HSN value and the portal rejects it. An empty cell is the honest
            # representation, and the validator already warns about it.
            key = ((item.hsn_code or "").strip(), item.uqc or "NOS", effective_rate(item), item.hsn_description or item.product_name)
            a = agg.setdefault(key, {"qty": 0.0, "value": 0.0, "taxable": 0.0, "igst": 0.0, "cgst": 0.0, "sgst": 0.0, "cess": 0.0})
            a["qty"] += item.quantity or 0.0
            a["value"] += item.net_value or 0.0
            a["taxable"] += item.taxable_amount or 0.0
            a["igst"] += item.igst_amount or 0.0
            a["cgst"] += item.cgst_amount or 0.0
            a["sgst"] += item.sgst_amount or 0.0
            a["cess"] += item.cess_amount or 0.0

    hsn_b2b_agg: dict = {}
    hsn_b2c_agg: dict = {}
    for iid in b2b_invoice_ids:
        add_to_hsn_agg(hsn_b2b_agg, iid)
    for iid in b2cl_ids + b2cs_ids:
        add_to_hsn_agg(hsn_b2c_agg, iid)

    def agg_to_hsn_rows(agg: dict) -> list[HsnSummaryItem]:
        rows = []
        for (hsn, uqc, rate, desc), v in agg.items():
            total_tax = r2(v["cgst"] + v["sgst"] + v["igst"])
            # Total Value is the real accumulated line value where we have it;
            # fall back to taxable + tax + cess rather than dropping cess.
            total_value = v["value"] if v["value"] else (
                v["taxable"] + v["cgst"] + v["sgst"] + v["igst"] + v["cess"]
            )
            rows.append(HsnSummaryItem(
                hsn_code=hsn,
                description=desc or "",
                uom=(uqc or "NOS").upper(),
                total_quantity=round(v["qty"], 3),
                taxable_value=r2(v["taxable"]),
                cgst_amount=r2(v["cgst"]),
                sgst_amount=r2(v["sgst"]),
                igst_amount=r2(v["igst"]),
                total_tax=total_tax,
                total_value=r2(total_value),
                cess_amount=r2(v["cess"]),
                rate=rate
            ))
        return rows

    hsn_b2b_rows = agg_to_hsn_rows(hsn_b2b_agg)
    hsn_b2c_rows = agg_to_hsn_rows(hsn_b2c_agg)

    # ── DOCS: document-series summary — needs ALL invoices in period,
    #    including cancelled ones (they're counted, not excluded) ──────────
    all_invoices_in_period = (
        db.query(GstSalesInvoice)
        .filter(
            GstSalesInvoice.shop_id == current_shop.id,
            GstSalesInvoice.invoice_date >= int(start.timestamp() * 1000),
            GstSalesInvoice.invoice_date <= int(end.timestamp() * 1000),
        )
        .all()
    )
    docs_agg: dict[tuple, dict] = {}
    for inv in all_invoices_in_period:
        key = (inv.document_series or "INV", inv.document_nature or "Invoices for outward supply")
        agg = docs_agg.setdefault(key, {"numbers": [], "cancelled": 0})
        agg["numbers"].append(inv.invoice_number or "")
        if inv.is_cancelled:
            agg["cancelled"] += 1
    # Table 13 is about document-number CONTINUITY, so it counts every document
    # issued in the period — including notes raised against a bill that was
    # later cancelled. `notes` above is filtered to drop those (correct for
    # CDNR/CDNUR, where a voided sale's note must not be reported), but here
    # that filter would leave a hole in the series. Re-query without it.
    docs_notes = (
        db.query(CreditNote)
        .filter(
            CreditNote.shop_id == current_shop.id,
            CreditNote.note_date >= start_ms,
            CreditNote.note_date <= end_ms,
        )
        .all()
    )
    for note in docs_notes:
        series = note.document_series or ("CN" if (note.note_type or "C") == "C" else "DN")
        nature = note.document_nature or ("Credit Notes" if (note.note_type or "C") == "C" else "Debit Notes")
        key = (series, nature)
        agg = docs_agg.setdefault(key, {"numbers": [], "cancelled": 0})
        agg["numbers"].append(note.note_number)

    def doc_sort_key(number: str):
        """
        Order document numbers the way a human numbers them.

        Bill numbers are built as prefix + an UNPADDED integer
        (f"{prefix}{next_num}" in bill_routes.py), so a plain text sort puts
        "..._100" before "..._9" and Table 13 then declares a backwards range
        (from _10 to _9). Sort on the trailing number when there is one, and
        fall back to text for genuinely non-numeric series — so mixed or
        custom numbering still gets a stable, sensible order.
        """
        s = (number or "").strip()
        trailing = ""
        for ch in reversed(s):
            if ch.isdigit():
                trailing = ch + trailing
            else:
                break
        if trailing:
            return (0, s[: len(s) - len(trailing)], int(trailing), "")
        return (1, "", 0, s)

    docs_rows = []
    for (series, nature), agg in docs_agg.items():
        if not agg["numbers"]:
            continue
        nums = sorted(agg["numbers"], key=doc_sort_key)
        docs_rows.append(Gstr1DocsItem(
            nature_of_document=nature,
            sr_from=nums[0],
            sr_to=nums[-1],
            total_number=len(agg["numbers"]),
            cancelled=agg["cancelled"]
        ))

    # ── ECO (e-commerce operator) tables — Phase 2 of the GST-reports fix
    #    plan. Ported from Gstr1Generator.kt's ECO section (the same
    #    classification rules that ran on-device before GSTR-1 moved
    #    online). Any active invoice with a non-blank eco_role is an
    #    e-commerce-operator sale; role text decides which of the four
    #    detail tables it lands in, same as the Kotlin `when` block did.
    eco_iids = [iid for iid in b2b_invoice_ids + b2c_invoice_ids if (invoices_by_id[iid].eco_role or "").strip()]

    eco_agg: dict = {}
    for iid in eco_iids:
        inv = invoices_by_id[iid]
        key = (inv.ecommerce_gstin or "", inv.ecommerce_operator_name or "", inv.eco_nature_of_supply or "B2C")
        a = eco_agg.setdefault(key, {"net": 0.0, "igst": 0.0, "cgst": 0.0, "sgst": 0.0, "cess": 0.0})
        a["net"] += inv.grand_total or 0.0
        a["igst"] += inv.total_igst or 0.0
        a["cgst"] += inv.total_cgst or 0.0
        a["sgst"] += inv.total_sgst or 0.0
        # Cess used to be hardcoded to 0.0 on the row below even though the
        # line items carry it. The invoice has no cess total column, so sum it
        # from the items the same way the detail tables do.
        a["cess"] += sum(i.cess_amount or 0.0 for i in items_by_invoice[iid])
    eco_rows = [
        Gstr1EcoItem(
            nature_of_supply=nature, eco_gstin=gstin, eco_name=name,
            net_value=r2(v["net"]), igst=r2(v["igst"]), cgst=r2(v["cgst"]), sgst=r2(v["sgst"]),
            cess=r2(v["cess"])
        )
        for (gstin, name, nature), v in eco_agg.items()
    ]

    eco_b2b_rows: list[Gstr1EcoB2BItem] = []
    eco_b2c_rows: list[Gstr1EcoB2CItem] = []
    eco_urp2b_rows: list[Gstr1EcoUrp2BItem] = []
    eco_urp2c_rows: list[Gstr1EcoUrp2CItem] = []

    for iid in eco_iids:
        inv = invoices_by_id[iid]
        role = (inv.eco_role or "").upper()
        doc_date = fmt_ms(inv.invoice_date)
        pos = fmt_pos(inv.customer_state_code, inv.customer_state)

        by_rate: dict[float, list] = {}
        for item in items_by_invoice[iid]:
            by_rate.setdefault(effective_rate(item), []).append(item)

        for rate, items in by_rate.items():
            taxable = r2(sum(i.taxable_amount or 0.0 for i in items))
            cess = r2(sum(i.cess_amount or 0.0 for i in items))

            if "B2B" in role and (inv.customer_gst or "").strip():
                eco_b2b_rows.append(Gstr1EcoB2BItem(
                    supplier_gstin=inv.eco_supplier_gstin or "", supplier_name=inv.eco_supplier_name or "",
                    recipient_gstin=inv.customer_gst, recipient_name=inv.business_name or inv.customer_name or "",
                    doc_number=inv.invoice_number or "", doc_date=doc_date, supply_value=r2(inv.grand_total),
                    place_of_supply=pos, doc_type=inv.eco_document_type or "Invoice",
                    rate=rate, taxable_value=taxable, cess_amount=cess
                ))
            elif "B2C" in role:
                # No GSTIN requirement here — and there must not be one. This
                # branch used to read `"B2C" in role and inv.customer_gst`,
                # which is self-contradictory: B2C means the RECIPIENT is
                # unregistered, so a customer GSTIN never exists. The branch
                # was therefore unreachable and every registered-supplier B2C
                # sale fell through to URP2C — a table that declares the
                # SUPPLIER unregistered, i.e. it told the portal this shop
                # isn't registered. Role alone decides, exactly like URP2C.
                eco_b2c_rows.append(Gstr1EcoB2CItem(
                    supplier_gstin=inv.eco_supplier_gstin or "", supplier_name=inv.eco_supplier_name or "",
                    place_of_supply=pos, rate=rate, taxable_value=taxable, cess_amount=cess
                ))
            elif "URP" in role and (inv.eco_recipient_gstin or "").strip():
                eco_urp2b_rows.append(Gstr1EcoUrp2BItem(
                    recipient_gstin=inv.eco_recipient_gstin, recipient_name=inv.eco_recipient_name or "",
                    doc_number=inv.invoice_number or "", doc_date=doc_date, supply_value=r2(inv.grand_total),
                    place_of_supply=pos, doc_type=inv.eco_document_type or "Invoice",
                    rate=rate, taxable_value=taxable, cess_amount=cess
                ))
            else:
                # Round 3 fix: this used to be `elif "URP" in role:`, so a
                # role of "B2B" or "B2C" with a BLANK GSTIN (the field each
                # of those branches above requires) matched no branch at
                # all — the sale silently vanished from every ECO
                # sub-report with no row, no warning, no error. A role of
                # "URP" with no eco_recipient_gstin still correctly falls
                # here too (URP2C is its designed catch-all). Routing every
                # unmatched case to URP2C — the one detail table needing no
                # GSTIN at all — means the taxable value is never lost from
                # the ECO report even when the row can't be attributed to a
                # specific registered party.
                eco_urp2c_rows.append(Gstr1EcoUrp2CItem(
                    place_of_supply=pos, rate=rate, taxable_value=taxable, cess_amount=cess
                ))

    # ── Legacy combined fields, kept so existing consumers of `b2c` /
    #    `hsn_summary` don't break while the app switches over. Built from
    #    the real per-item tax amounts (not derived from rate), so these
    #    stay exact rather than approximated. ───────────────────────────
    legacy_b2c_agg: dict = {}
    for iid in b2cl_ids + b2cs_ids:
        inv = invoices_by_id[iid]
        pos = fmt_pos(inv.customer_state_code, inv.customer_state)
        for item in items_by_invoice[iid]:
            key = (pos, effective_rate(item))
            agg = legacy_b2c_agg.setdefault(key, {"taxable": 0.0, "cgst": 0.0, "sgst": 0.0, "igst": 0.0})
            agg["taxable"] += item.taxable_amount or 0.0
            agg["cgst"] += item.cgst_amount or 0.0
            agg["sgst"] += item.sgst_amount or 0.0
            agg["igst"] += item.igst_amount or 0.0
    legacy_b2c_rows = [
        Gstr1B2CItem(
            place_of_supply=pos, supply_type="", gst_rate=rate,
            taxable_value=r2(v["taxable"]), cgst=r2(v["cgst"]), sgst=r2(v["sgst"]), igst=r2(v["igst"])
        )
        for (pos, rate), v in legacy_b2c_agg.items()
    ]
    legacy_hsn_rows = agg_to_hsn_rows({**hsn_b2b_agg, **hsn_b2c_agg})

    # Totals from the raw active rows directly (not from b2cl_rows/b2cs_rows,
    # which — matching the GST portal's own CSV format — only carry
    # taxable_value + rate, no separate cgst/sgst/igst columns, since the
    # portal derives tax from rate itself for those two sheets).
    total_taxable = r2(sum((it.taxable_amount or 0.0) for iid in invoices_by_id for it in items_by_invoice[iid]))
    total_cgst = r2(sum((it.cgst_amount or 0.0) for iid in invoices_by_id for it in items_by_invoice[iid]))
    total_sgst = r2(sum((it.sgst_amount or 0.0) for iid in invoices_by_id for it in items_by_invoice[iid]))
    total_igst = r2(sum((it.igst_amount or 0.0) for iid in invoices_by_id for it in items_by_invoice[iid]))

    return Gstr1Response(
        period_start=start_date,
        period_end=end_date,
        b2b=b2b_rows,
        b2c=legacy_b2c_rows,
        b2cl=b2cl_rows,
        b2cs=b2cs_rows,
        cdnr=cdnr_rows,
        cdnur=cdnur_rows,
        docs=docs_rows,
        eco=eco_rows,
        eco_b2b=eco_b2b_rows,
        eco_b2c=eco_b2c_rows,
        eco_urp2b=eco_urp2b_rows,
        eco_urp2c=eco_urp2c_rows,
        hsn_summary=legacy_hsn_rows,
        hsn_b2b=hsn_b2b_rows,
        hsn_b2c=hsn_b2c_rows,
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
    current_shop = Depends(require_premium_tier)  # Premium-gated, see get_gstr1 above
):
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    # Round 4 fix: a cancelled purchase is correctly excluded from Purchase
    # History totals (PurchaseHistoryViewModel.kt: `if (!p.isCancelled ...)`)
    # and from every Profit-report Purchase query, but this endpoint never
    # checked `Purchase.is_cancelled` at all — so a voided purchase's
    # taxable value and ITC kept flowing into GSTR-2's totals regardless.
    # `ImportService` (the separate services-import table, below) has no
    # cancellation concept at all, so it needs no equivalent filter.
    purchases_query = db.query(Purchase, PurchaseItem).join(
        PurchaseItem, Purchase.id == PurchaseItem.purchase_id
    ).filter(
        Purchase.shop_id == current_shop.id,
        Purchase.invoice_date >= start,
        Purchase.invoice_date <= end,
        Purchase.is_cancelled == 0
    ).all()

    imports_query = db.query(ImportService).filter(
        ImportService.shop_id == current_shop.id,
        ImportService.invoice_date >= start,
        ImportService.invoice_date <= end
    ).all()

    # A purchase return belongs to the period of the NOTE, not the period in
    # which someone happened to type it in. This used to filter on created_at
    # (the row's insert timestamp), so a note dated 28 Jul but entered on 3 Aug
    # landed in August — and a catch-up data-entry session dumped a whole
    # month's returns into the wrong period, reversing ITC away from the credit
    # it reverses. GSTR-1's credit notes already filter on note_date for
    # exactly this reason; this brings GSTR-2 in line.
    #
    # note_date is epoch-ms (BigInteger) and nullable, so it needs the same
    # start_ms/end_ms conversion GSTR-1 uses, with a created_at fallback for
    # legacy rows that never got one — those must not vanish from every period.
    ret_start_ms = int(start.timestamp() * 1000)
    ret_end_ms = int(end.timestamp() * 1000)
    returns_query = db.query(PurchaseReturn).filter(
        PurchaseReturn.shop_id == current_shop.id,
        or_(
            and_(
                PurchaseReturn.note_date.isnot(None),
                PurchaseReturn.note_date >= ret_start_ms,
                PurchaseReturn.note_date <= ret_end_ms,
            ),
            and_(
                PurchaseReturn.note_date.is_(None),
                PurchaseReturn.created_at >= start,
                PurchaseReturn.created_at <= end,
            ),
        ),
    ).all()

    import_goods_query = db.query(Purchase, PurchaseItem, PurchaseImportDetails).join(
        PurchaseItem, Purchase.id == PurchaseItem.purchase_id
    ).join(
        PurchaseImportDetails, Purchase.id == PurchaseImportDetails.purchase_id
    ).filter(
        Purchase.shop_id == current_shop.id,
        Purchase.is_cancelled == 0,
        Purchase.invoice_date >= start,
        Purchase.invoice_date <= end
    ).all()

    b2b_list = []
    b2bur_list = []
    imps_list = []
    impg_list = []
    cdnr_list = []
    cdnur_list = []
    exemp_list = []
    hsn_map = {}

    total_taxable_value = 0.0
    total_itc_cgst = 0.0
    total_itc_sgst = 0.0
    total_itc_igst = 0.0

    comp = 0.0
    nil = 0.0
    exe = 0.0
    ngst = 0.0

    # 1. B2B, B2BUR, EXEMP, HSN SUM
    #
    # Phase 4 fix: GSTR-1's equivalent code guards every arithmetic/string
    # read with `(x or default)` since a nullable column with no value
    # would otherwise crash the whole report. This loop used to read most
    # fields raw. It hasn't crashed yet because these particular columns
    # currently all declare NOT NULL with a default, but that's an
    # incidental protection, not a guarantee — a future column change or a
    # legacy row could break this the same way GSTR-1 is already immune to.
    # Guarded here to match, not because a live bug was reproduced.
    for p, item in purchases_query:
        is_registered = bool(p.supplier_gstin and p.supplier_gstin.strip() != "")
        date_str = p.invoice_date.strftime("%d-%b-%y") if p.invoice_date else ""
        rate = (item.purchase_cgst_percentage or 0.0) + (item.purchase_sgst_percentage or 0.0) + \
            (item.purchase_igst_percentage or 0.0)

        # HSN
        # Phase 5 fix: uqc was hardcoded to "OTH" regardless of the item's
        # real unit, even though PurchaseItem.official_uqc exists
        # specifically "for GSTR-2 support" (see purchase_item.py) and was
        # simply never read here. GSTR-1's HSN builder correctly uses the
        # item's real uqc; this brings GSTR-2 in line with it.
        # Group by (hsn, uqc, rate), matching GSTR-1's HSN builder.
        #
        # This used to key on the HSN code alone, which merged everything about
        # that code into one row: two rates of the same HSN became a single
        # indistinguishable line (and the schema carried no rate to tell them
        # apart), while two different units — 8 KGS and 40 PCS — had their
        # quantities added to give 48 of nothing. The first item's uqc and
        # description also silently won for the whole group.
        #
        # Blank, not "Unknown", when a product has no HSN: "Unknown" is not a
        # valid HSN value. GSTR-1 was changed the same way.
        hsn_code = (item.hsn_code or "").strip()
        hsn_uqc = item.official_uqc or "OTH"
        hsn_key = (hsn_code, hsn_uqc, rate)
        if hsn_key not in hsn_map:
            hsn_map[hsn_key] = Gstr2HsnsumItem(
                hsn=hsn_code, description=item.product_name or "", uqc=hsn_uqc,
                rate=rate,
                total_quantity=0.0, total_value=0.0, taxable_value=0.0,
                igst=0.0, cgst=0.0, sgst=0.0, cess=0.0
            )
        hsn_map[hsn_key].total_quantity += item.quantity or 0.0
        hsn_map[hsn_key].total_value += item.invoice_value or 0.0
        hsn_map[hsn_key].taxable_value += item.taxable_amount or 0.0
        hsn_map[hsn_key].igst += item.purchase_igst_amount or 0.0
        hsn_map[hsn_key].cgst += item.purchase_cgst_amount or 0.0
        hsn_map[hsn_key].sgst += item.purchase_sgst_amount or 0.0
        hsn_map[hsn_key].cess += item.cess_amount or 0.0

        # Exempt tracking
        if p.invoice_type == "From Composition Taxable Person":
            comp += item.taxable_amount or 0.0
        elif item.supply_classification == "NIL_RATED":
            nil += item.taxable_amount or 0.0
        elif item.supply_classification == "EXEMPT":
            exe += item.taxable_amount or 0.0
        elif item.supply_classification == "NON_GST":
            ngst += item.taxable_amount or 0.0
        else:
            # ITC eligibility, read from the purchase item instead of assumed.
            #
            # Every row here used to declare itc_eligibility="Inputs" outright,
            # even though each PurchaseItem carries its own eligibility_for_itc
            # and the import service / purchase return paths below already
            # read it. (The Purchase header used to carry a copy of this too,
            # but that header-level column was unused and has been removed —
            # this always read the line item, not the header.) Two
            # problems: capital goods and input services were reported as
            # Inputs, and — the costly one — a purchase marked Ineligible
            # (blocked credit under s.17(5): motor vehicles, food and
            # beverages, personal use, and so on) still carried its availed ITC
            # through, so blocked credit was being claimed.
            #
            # When the credit is blocked the tax is still reported (it was
            # charged and paid) but the AVAILED amounts are forced to zero —
            # that is the distinction the ITC columns exist to make.
            itc_elig = (item.eligibility_for_itc or "Inputs").strip() or "Inputs"
            itc_blocked = itc_elig.lower() in ("ineligible", "none")
            av_igst = 0.0 if itc_blocked else (item.availed_itc_igst or 0.0)
            av_cgst = 0.0 if itc_blocked else (item.availed_itc_cgst or 0.0)
            av_sgst = 0.0 if itc_blocked else (item.availed_itc_sgst or 0.0)
            av_cess = 0.0 if itc_blocked else (item.availed_itc_cess or 0.0)

            if is_registered:
                b2b_list.append(Gstr2B2bItem(
                    supplier_gstin=p.supplier_gstin,
                    invoice_number=p.invoice_number or "",
                    invoice_date=date_str,
                    invoice_value=item.invoice_value or 0.0,
                    place_of_supply=p.place_of_supply_code or "",
                    reverse_charge="Y" if p.reverse_charge else "N",
                    invoice_type=p.invoice_type or "Regular",
                    rate=rate,
                    taxable_value=item.taxable_amount or 0.0,
                    igst=item.purchase_igst_amount or 0.0,
                    cgst=item.purchase_cgst_amount or 0.0,
                    sgst=item.purchase_sgst_amount or 0.0,
                    cess=item.cess_amount or 0.0,
                    itc_eligibility=itc_elig,
                    availed_itc_igst=av_igst,
                    availed_itc_cgst=av_cgst,
                    availed_itc_sgst=av_sgst,
                    availed_itc_cess=av_cess
                ))
            else:
                b2bur_list.append(Gstr2B2burItem(
                    supplier_name=p.supplier_name or "Unknown",
                    invoice_number=p.invoice_number or "",
                    invoice_date=date_str,
                    invoice_value=item.invoice_value or 0.0,
                    place_of_supply=p.place_of_supply_code or "",
                    supply_type=p.supply_type or "",
                    reverse_charge="Y" if p.reverse_charge else "N",
                    rate=rate,
                    taxable_value=item.taxable_amount or 0.0,
                    igst=item.purchase_igst_amount or 0.0,
                    cgst=item.purchase_cgst_amount or 0.0,
                    sgst=item.purchase_sgst_amount or 0.0,
                    cess=item.cess_amount or 0.0,
                    itc_eligibility=itc_elig,
                    availed_itc_igst=av_igst,
                    availed_itc_cgst=av_cgst,
                    availed_itc_sgst=av_sgst,
                    availed_itc_cess=av_cess
                ))

            total_taxable_value += item.taxable_amount or 0.0
            # Blocked credit must not reach the ITC totals either — these feed
            # the summary the user reads as "input tax credit available".
            total_itc_cgst += av_cgst
            total_itc_sgst += av_sgst
            total_itc_igst += av_igst

    # 2. IMPG
    for p, item, p_imp in import_goods_query:
        boe_date_str = p_imp.bill_of_entry_date.strftime("%d-%b-%y") if p_imp.bill_of_entry_date else ""
        rate = (item.purchase_cgst_percentage or 0.0) + (item.purchase_sgst_percentage or 0.0) + \
            (item.purchase_igst_percentage or 0.0)
        # Same treatment as B2B above: read the purchase's own eligibility, and
        # withhold the availed credit when it is blocked.
        impg_elig = (item.eligibility_for_itc or "Inputs").strip() or "Inputs"
        impg_blocked = impg_elig.lower() in ("ineligible", "none")
        impg_list.append(Gstr2ImpgItem(
            port_code=p_imp.port_code or "",
            bill_of_entry_number=p_imp.bill_of_entry_number or "",
            bill_of_entry_date=boe_date_str,
            bill_of_entry_value=p_imp.bill_of_entry_value or 0.0,
            document_type=p_imp.document_type or "",
            sez_supplier_gstin=p_imp.sez_supplier_gstin or "",
            rate=rate,
            taxable_value=item.taxable_amount or 0.0,
            igst=item.purchase_igst_amount or 0.0,
            cess=item.cess_amount or 0.0,
            itc_eligibility=impg_elig,
            availed_itc_igst=0.0 if impg_blocked else (item.availed_itc_igst or 0.0),
            availed_itc_cess=0.0 if impg_blocked else (item.availed_itc_cess or 0.0)
        ))

    # 3. IMPS
    for im in imports_query:
        date_str = im.invoice_date.strftime("%d-%b-%y") if im.invoice_date else ""
        # This path always READ eligibility_for_itc correctly, but it never
        # acted on it: an import marked Ineligible/None still carried its
        # availed credit through to the row and the ITC total. Reading the
        # label and honouring it are different things — same treatment as B2B,
        # B2BUR and IMPG now.
        imps_elig = (im.eligibility_for_itc or "Inputs").strip() or "Inputs"
        imps_blocked = imps_elig.lower() in ("ineligible", "none")
        imps_av_igst = 0.0 if imps_blocked else (im.availed_itc_igst or 0.0)
        imps_av_cess = 0.0 if imps_blocked else (im.availed_itc_cess or 0.0)
        imps_list.append(Gstr2ImpsItem(
            invoice_number=im.invoice_number or "",
            invoice_date=date_str,
            invoice_value=im.invoice_value or 0.0,
            place_of_supply=im.place_of_supply or "",
            rate=im.rate or 0.0,
            taxable_value=im.taxable_value or 0.0,
            igst=im.igst_paid or 0.0,
            cess=im.cess_paid or 0.0,
            itc_eligibility=imps_elig,
            availed_itc_igst=imps_av_igst,
            availed_itc_cess=imps_av_cess
        ))
        total_taxable_value += im.taxable_value or 0.0
        total_itc_igst += imps_av_igst

    # 4. CDNR & CDNUR
    for r in returns_query:
        is_registered = bool(r.supplier_gstin and r.supplier_gstin.strip() != "")
        note_date_str = datetime.fromtimestamp(r.note_date / 1000).strftime("%d-%b-%y") if r.note_date else ""
        orig_inv_date_str = datetime.fromtimestamp(r.original_invoice_date / 1000).strftime("%d-%b-%y") if r.original_invoice_date else ""
        # Phase 4 fix: a blank document_type used to be defaulted straight
        # to "C" (Credit Note), which silently mislabelled a genuine Debit
        # Note as a Credit Note on any old row missing this field. Derive it
        # from note_type instead — same source of truth the row's own
        # note_type/note_number/reason fields already use — and only fall
        # back to "C" if note_type itself is also missing.
        document_type_effective = r.document_type or (
            "Debit Note" if (r.note_type or "D") == "D" else "Credit Note"
        )

        # A purchase return REVERSES credit previously availed. If the original
        # purchase was ineligible no credit was ever claimed, so there is
        # nothing to reverse — carrying an availed figure here would create a
        # phantom reversal. Same rule as the forward paths above.
        ret_elig = (r.eligibility_for_itc or "Inputs").strip() or "Inputs"
        ret_blocked = ret_elig.lower() in ("ineligible", "none")
        ret_av_igst = 0.0 if ret_blocked else (r.availed_itc_integrated_tax or 0.0)
        ret_av_cgst = 0.0 if ret_blocked else (r.availed_itc_central_tax or 0.0)
        ret_av_sgst = 0.0 if ret_blocked else (r.availed_itc_state_tax or 0.0)
        ret_av_cess = 0.0 if ret_blocked else (r.availed_itc_cess or 0.0)

        # Bug found during a deeper audit of the cancelled-purchase/purchase-
        # return interaction: these CDNR/CDNUR rows have always carried the
        # ITC-reversal amount (ret_av_igst/cgst/sgst above), but nothing ever
        # subtracted it from the summary totals below (total_itc_cgst/sgst/
        # igst) — those are only ever incremented by the B2B/B2BUR and IMPS
        # loops. A purchase return (full or partial) reduces the net ITC you
        # can actually claim for the period, whether it's a registered-supplier
        # note (CDNR) or an unregistered one (CDNUR), debit or credit note —
        # either way it's a value adjustment against previously-availed ITC.
        # Net it here so the headline totals match the sum of the detail rows.
        total_itc_igst -= ret_av_igst
        total_itc_cgst -= ret_av_cgst
        total_itc_sgst -= ret_av_sgst

        if is_registered:
            cdnr_list.append(Gstr2CdnrItem(
                supplier_gstin=r.supplier_gstin,
                note_number=r.note_number or "",
                note_date=note_date_str,
                invoice_number=r.original_invoice_number or "",
                invoice_date=orig_inv_date_str,
                pre_gst=r.pre_gst or "N",
                document_type=document_type_effective,
                reason=r.reason_for_issuing_document or "Purchase return",
                supply_type=r.supply_type or "",
                note_value=r.note_refund_voucher_value or 0.0,
                rate=r.rate or 0.0,
                taxable_value=r.taxable_amount or 0.0,
                igst=r.igst_amount or 0.0,
                cgst=r.cgst_amount or 0.0,
                sgst=r.sgst_amount or 0.0,
                cess=r.cess_amount or 0.0,
                itc_eligibility=ret_elig,
                availed_itc_igst=ret_av_igst,
                availed_itc_cgst=ret_av_cgst,
                availed_itc_sgst=ret_av_sgst,
                availed_itc_cess=ret_av_cess
            ))
        else:
            cdnur_list.append(Gstr2CdnurItem(
                note_number=r.note_number or "",
                note_date=note_date_str,
                invoice_number=r.original_invoice_number or "",
                invoice_date=orig_inv_date_str,
                pre_gst=r.pre_gst or "N",
                document_type=document_type_effective,
                reason=r.reason_for_issuing_document or "Purchase return",
                supply_type=r.supply_type or "",
                invoice_type=r.invoice_type or "Regular",
                note_value=r.note_refund_voucher_value or 0.0,
                rate=r.rate or 0.0,
                taxable_value=r.taxable_amount or 0.0,
                igst=r.igst_amount or 0.0,
                cgst=r.cgst_amount or 0.0,
                sgst=r.sgst_amount or 0.0,
                cess=r.cess_amount or 0.0,
                itc_eligibility=ret_elig,
                availed_itc_igst=ret_av_igst,
                availed_itc_cgst=ret_av_cgst,
                availed_itc_sgst=ret_av_sgst,
                availed_itc_cess=ret_av_cess
            ))

    if comp > 0 or nil > 0 or exe > 0 or ngst > 0:
        exemp_list.append(Gstr2ExempItem(
            description="Total",
            composition=comp,
            nil_rated=nil,
            exempted=exe,
            non_gst=ngst
        ))

    # Phase 5 fix: every row above was built from raw, unrounded floats
    # (only the final summary totals below got round(x, 2)) — so a detail
    # row and the summary card could disagree by a cent or two. Round every
    # money-shaped float field on every row here, in one pass, right before
    # they go out, rather than rounding at each of the ~14 construction
    # sites above (same numeric result, far less places to miss one).
    def _round_money_fields(rows):
        for row in rows:
            for field_name, value in list(row.__dict__.items()):
                if isinstance(value, float) and field_name != "total_quantity":
                    setattr(row, field_name, round(value, 2))
                elif field_name == "total_quantity" and isinstance(value, float):
                    setattr(row, field_name, round(value, 3))

    for rows in (b2b_list, b2bur_list, imps_list, impg_list, cdnr_list, cdnur_list, exemp_list, hsn_map.values()):
        _round_money_fields(rows)

    return Gstr2Response(
        period_start=start_date,
        period_end=end_date,
        b2b=b2b_list,
        b2bur=b2bur_list,
        imps=imps_list,
        impg=impg_list,
        cdnr=cdnr_list,
        cdnur=cdnur_list,
        exemp=exemp_list,
        hsnsum=list(hsn_map.values()),
        total_taxable_value=round(total_taxable_value, 2),
        total_itc_cgst=round(total_itc_cgst, 2),
        total_itc_sgst=round(total_itc_sgst, 2),
        total_itc_igst=round(total_itc_igst, 2)
    )

# ============================================================
# 8. GSTR-3B (Tax Liability Summary)
# ============================================================

# GSTR-3B endpoint removed (not needed for this app). Its ITC side had also
# been silently broken — it read from GstPurchaseRecord, a table the Android
# client stopped populating after retiring the legacy sync flow, so ITC was
# frozen/zero while net tax payable kept counting full output tax. GSTR-2
# above is unaffected — it already reads live Purchase/PurchaseItem data.


# ============================================================
# 9. HSN Summary Report
# ============================================================

@router.get("/reports/hsn-summary")
def get_hsn_summary(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
    current_shop = Depends(require_premium_tier)  # Premium-gated, see get_gstr1 above
):
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    # Repointed onto gst_sales_invoice(+items), cancelled excluded —
    # Report 3 fix A2/C1. (This route previously queried legacy
    # gst_sales_records; it was also unreachable dead code until this
    # change, shadowed by an earlier duplicate `/reports/hsn-summary`
    # route that has now been removed — see Report 3 dead-code notes.)
    hsn_agg: dict = {}
    for _inv, item in get_active_invoice_line_items(db, current_shop.id, start, end):
        key = (item.hsn_code or "", item.uqc)
        if key not in hsn_agg:
            hsn_agg[key] = {
                "hsn_code": item.hsn_code or "",
                "uom": (item.uqc or "NOS").upper(),
                "total_quantity": 0.0,
                "taxable_value": 0.0,
                "cgst_amount": 0.0,
                "sgst_amount": 0.0,
                "igst_amount": 0.0,
            }
        agg = hsn_agg[key]
        agg["total_quantity"] += item.quantity or 0.0
        agg["taxable_value"] += item.taxable_amount or 0.0
        agg["cgst_amount"] += item.cgst_amount or 0.0
        agg["sgst_amount"] += item.sgst_amount or 0.0
        agg["igst_amount"] += item.igst_amount or 0.0

    return [
        {
            "hsn_code": agg["hsn_code"],
            "uom": agg["uom"],
            "total_quantity": round(agg["total_quantity"], 3),
            "taxable_value": round(agg["taxable_value"], 2),
            "cgst_amount": round(agg["cgst_amount"], 2),
            "sgst_amount": round(agg["sgst_amount"], 2),
            "igst_amount": round(agg["igst_amount"], 2),
            "total_tax": round(agg["cgst_amount"] + agg["sgst_amount"] + agg["igst_amount"], 2)
        }
        for agg in hsn_agg.values()
    ]


# ============================================================
# 10. Email GST Report
# ============================================================

@router.post("/reports/email")
async def email_gst_report(
    report_type: str = Query(..., description="gstr1 / gstr2 / hsn"),
    start_date: str = Query(...),
    end_date: str = Query(...),
    db: Session = Depends(get_db),
    current_shop = Depends(require_premium_tier)  # Premium-gated, see get_gstr1 above
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
