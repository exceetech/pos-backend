# routes/purchase.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import datetime

from app.database import get_db
from app.dependencies import get_current_shop
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.purchase_batch import PurchaseBatch
from app.models.credit import CreditAccount
from app.models.shop_products import ShopProduct
from app.models.global_products import GlobalProduct
from app.schemas.purchase_schema import PurchaseSyncRequest, PurchaseSyncResponse
from app.utils import normalize_name
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/purchases", tags=["Purchases"])


def _apply_sales_tax_to_product(sp: ShopProduct | None, item) -> None:
    """Write sales-tax fields from a purchase line onto a ShopProduct row.

    Safe to call with sp=None (no-op).  Only overwrites tax rates when the
    purchase line carries a non-zero combined sales rate so we never
    accidentally zero out rates that were set through the product master.
    HSN code is updated whenever the line carries one (non-destructive).
    """
    if sp is None:
        return
    sales_combined = (
        item.sales_cgst_percentage
        + item.sales_sgst_percentage
        + item.sales_igst_percentage
    )
    if sales_combined > 0:
        sp.cgst_percentage  = item.sales_cgst_percentage
        sp.sgst_percentage  = item.sales_sgst_percentage
        sp.igst_percentage  = item.sales_igst_percentage
        sp.default_gst_rate = sales_combined
    if item.hsn_code:
        sp.hsn_code = item.hsn_code


@router.post("/sync", response_model=PurchaseSyncResponse)
def sync_purchases(
    payload: PurchaseSyncRequest,
    db: Session = Depends(get_db),
    current_shop = Depends(get_current_shop)
):
    purchase_id_map = {}
    success_count = 0

    try:
        for p in payload.purchases:
            # Backend validation
            if not p.place_of_supply_code:
                return JSONResponse(status_code=400, content={"message": "place_of_supply_code is required"})
            if p.reverse_charge not in ["Y", "N"]:
                return JSONResponse(status_code=400, content={"message": "reverse_charge must be Y or N"})
            if not p.invoice_type:
                return JSONResponse(status_code=400, content={"message": "invoice_type is required"})
            if p.supply_type not in ["intrastate", "interstate"]:
                return JSONResponse(status_code=400, content={"message": "supply_type must be intrastate or interstate"})
            if p.cess_paid < 0:
                return JSONResponse(status_code=400, content={"message": "cess_paid must be >= 0"})
            if not p.eligibility_for_itc:
                return JSONResponse(status_code=400, content={"message": "eligibility_for_itc is required"})
            if (p.availed_itc_integrated_tax < 0 or p.availed_itc_central_tax < 0 or
                    p.availed_itc_state_tax < 0 or p.availed_itc_cess < 0):
                return JSONResponse(status_code=400, content={"message": "availed ITC fields must be >= 0"})

            if p.availed_itc_integrated_tax > p.igst_amount:
                return JSONResponse(status_code=400, content={"message": "availed_itc_integrated_tax cannot exceed igst_amount"})
            if p.availed_itc_central_tax > p.cgst_amount:
                return JSONResponse(status_code=400, content={"message": "availed_itc_central_tax cannot exceed cgst_amount"})
            if p.availed_itc_state_tax > p.sgst_amount:
                return JSONResponse(status_code=400, content={"message": "availed_itc_state_tax cannot exceed sgst_amount"})
            if p.availed_itc_cess > p.cess_paid:
                return JSONResponse(status_code=400, content={"message": "availed_itc_cess cannot exceed cess_paid"})

            if p.eligibility_for_itc in ["Ineligible", "None"]:
                if (p.availed_itc_integrated_tax != 0 or p.availed_itc_central_tax != 0 or
                        p.availed_itc_state_tax != 0 or p.availed_itc_cess != 0):
                    return JSONResponse(status_code=400, content={"message": "availed ITC fields must be 0 when ineligible/None"})

            # Item-level validation
            for item in p.items:
                if item.cess_percentage < 0:
                    return JSONResponse(status_code=400, content={"message": "item cess_percentage must be >= 0"})
                if item.cess_amount < 0:
                    return JSONResponse(status_code=400, content={"message": "item cess_amount must be >= 0"})
                if not item.eligibility_for_itc:
                    return JSONResponse(status_code=400, content={"message": "item eligibility_for_itc is required"})
                if (item.availed_itc_igst < 0 or item.availed_itc_cgst < 0 or
                        item.availed_itc_sgst < 0 or item.availed_itc_cess < 0):
                    return JSONResponse(status_code=400, content={"message": "item availed ITC fields must be >= 0"})

                if item.availed_itc_igst > item.purchase_igst_amount:
                    return JSONResponse(status_code=400, content={"message": "item availed_itc_igst cannot exceed purchase_igst_amount"})
                if item.availed_itc_cgst > item.purchase_cgst_amount:
                    return JSONResponse(status_code=400, content={"message": "item availed_itc_cgst cannot exceed purchase_cgst_amount"})
                if item.availed_itc_sgst > item.purchase_sgst_amount:
                    return JSONResponse(status_code=400, content={"message": "item availed_itc_sgst cannot exceed purchase_sgst_amount"})
                if item.availed_itc_cess > item.cess_amount:
                    return JSONResponse(status_code=400, content={"message": "item availed_itc_cess cannot exceed cess_amount"})

                if item.eligibility_for_itc in ["Ineligible", "None"]:
                    if (item.availed_itc_igst != 0 or item.availed_itc_cgst != 0 or
                            item.availed_itc_sgst != 0 or item.availed_itc_cess != 0):
                        return JSONResponse(status_code=400, content={"message": "item availed ITC fields must be 0 when ineligible/None"})

                if item.hsn_code and not item.official_uqc:
                    return JSONResponse(status_code=400, content={"message": "item official_uqc is required when hsn_code is present"})

            # Check if purchase already exists for this shop by local_id
            existing = db.query(Purchase).filter(
                Purchase.shop_id == current_shop.id,
                Purchase.local_id == p.local_id
            ).first()

            if existing is not None:
                purchase = existing
                purchase.invoice_number = p.invoice_number
                purchase.supplier_gstin = p.supplier_gstin
                purchase.supplier_name = p.supplier_name
                purchase.state = p.state
                purchase.taxable_amount = p.taxable_amount
                purchase.cgst_percentage = p.cgst_percentage
                purchase.sgst_percentage = p.sgst_percentage
                purchase.igst_percentage = p.igst_percentage
                purchase.cgst_amount = p.cgst_amount
                purchase.sgst_amount = p.sgst_amount
                purchase.igst_amount = p.igst_amount
                purchase.invoice_value = p.invoice_value
                purchase.invoice_date = (
                    datetime.utcfromtimestamp(p.invoice_date / 1000)
                    if p.invoice_date else None
                )
                purchase.is_credit = 1 if p.is_credit else 0
                purchase.credit_account_id = p.credit_account_id
                purchase.place_of_supply_code = p.place_of_supply_code
                purchase.reverse_charge = p.reverse_charge
                purchase.invoice_type = p.invoice_type
                purchase.supply_type = p.supply_type
                purchase.cess_paid = p.cess_paid
                purchase.eligibility_for_itc = p.eligibility_for_itc
                purchase.availed_itc_integrated_tax = p.availed_itc_integrated_tax
                purchase.availed_itc_central_tax = p.availed_itc_central_tax
                purchase.availed_itc_state_tax = p.availed_itc_state_tax
                purchase.availed_itc_cess = p.availed_itc_cess

                # Delete items and batches
                db.query(PurchaseItem).filter(PurchaseItem.purchase_id == purchase.id).delete()
                db.query(PurchaseBatch).filter(PurchaseBatch.purchase_invoice_id == purchase.id).delete()
            else:
                # ✅ Create purchase header
                purchase = Purchase(
                    shop_id=current_shop.id,
                    local_id=p.local_id,
                    invoice_number=p.invoice_number,
                    supplier_gstin=p.supplier_gstin,
                    supplier_name=p.supplier_name,
                    state=p.state,
                    taxable_amount=p.taxable_amount,
                    cgst_percentage=p.cgst_percentage,
                    sgst_percentage=p.sgst_percentage,
                    igst_percentage=p.igst_percentage,
                    cgst_amount=p.cgst_amount,
                    sgst_amount=p.sgst_amount,
                    igst_amount=p.igst_amount,
                    invoice_value=p.invoice_value,
                    invoice_date=(
                        datetime.utcfromtimestamp(p.invoice_date / 1000)
                        if p.invoice_date else None
                    ),
                    is_credit=1 if p.is_credit else 0,
                    credit_account_id=p.credit_account_id,
                    place_of_supply_code=p.place_of_supply_code,
                    reverse_charge=p.reverse_charge,
                    invoice_type=p.invoice_type,
                    supply_type=p.supply_type,
                    cess_paid=p.cess_paid,
                    eligibility_for_itc=p.eligibility_for_itc,
                    availed_itc_integrated_tax=p.availed_itc_integrated_tax,
                    availed_itc_central_tax=p.availed_itc_central_tax,
                    availed_itc_state_tax=p.availed_itc_state_tax,
                    availed_itc_cess=p.availed_itc_cess,
                    created_at=datetime.utcfromtimestamp(p.created_at / 1000)
                )
                db.add(purchase)

            # ✅ Validation: Ensure credit account exists and belongs to this shop
            if purchase.credit_account_id and purchase.credit_account_id > 0:
                acc = db.query(CreditAccount).filter(
                    CreditAccount.id == purchase.credit_account_id,
                    CreditAccount.shop_id == current_shop.id
                ).first()
                if not acc:
                    return JSONResponse(
                        status_code=400,
                        content={"message": f"Credit account {purchase.credit_account_id} not found for this shop"}
                    )

            db.flush()

            # ✅ Insert items
            for item in p.items:
                hsn_desc = item.hsn_description if item.hsn_description else item.product_name
                db.add(
                    PurchaseItem(
                        purchase_id=purchase.id,
                        shop_product_id=item.shop_product_id,
                        product_name=item.product_name,
                        variant=item.variant,
                        hsn_code=item.hsn_code,
                        quantity=item.quantity,
                        unit=item.unit,
                        taxable_amount=item.taxable_amount,
                        invoice_value=item.invoice_value,
                        cost_price=item.cost_price,
                        purchase_cgst_percentage=item.purchase_cgst_percentage,
                        purchase_sgst_percentage=item.purchase_sgst_percentage,
                        purchase_igst_percentage=item.purchase_igst_percentage,
                        purchase_cgst_amount=item.purchase_cgst_amount,
                        purchase_sgst_amount=item.purchase_sgst_amount,
                        purchase_igst_amount=item.purchase_igst_amount,
                        sales_cgst_percentage=item.sales_cgst_percentage,
                        sales_sgst_percentage=item.sales_sgst_percentage,
                        sales_igst_percentage=item.sales_igst_percentage,
                        cess_percentage=item.cess_percentage,
                        cess_amount=item.cess_amount,
                        eligibility_for_itc=item.eligibility_for_itc,
                        availed_itc_igst=item.availed_itc_igst,
                        availed_itc_cgst=item.availed_itc_cgst,
                        availed_itc_sgst=item.availed_itc_sgst,
                        availed_itc_cess=item.availed_itc_cess,
                        hsn_description=hsn_desc,
                        official_uqc=item.official_uqc or ""
                    )
                )

                # ✅ Update shop_product sales-tax fields regardless of whether the
                # client knows the server-side product id yet.
                #   • Known product  → look up directly by shop_product_id (fast path).
                #   • Unknown product → fall back to name+variant+unit lookup so that
                #     products added through purchase but not yet fully synced still
                #     get their tax rates written to the backend.
                if item.shop_product_id:
                    sp = db.query(ShopProduct).filter(
                        ShopProduct.id == item.shop_product_id,
                        ShopProduct.shop_id == current_shop.id
                    ).first()
                    _apply_sales_tax_to_product(sp, item)
                else:
                    # Fallback: match by normalised name + variant + unit
                    gp = db.query(GlobalProduct).filter(
                        GlobalProduct.name == normalize_name(item.product_name)
                    ).first()
                    if gp:
                        variant = item.variant.strip() if item.variant else None
                        unit_str = (item.unit or "piece").lower().strip()
                        sp = db.query(ShopProduct).filter(
                            ShopProduct.shop_id == current_shop.id,
                            ShopProduct.global_product_id == gp.id,
                            ShopProduct.unit == unit_str,
                            (
                                ShopProduct.variant_name.is_(None)
                                if variant is None
                                else ShopProduct.variant_name == variant
                            )
                        ).first()
                        _apply_sales_tax_to_product(sp, item)

                # ✅ Auto-create PurchaseBatch for Hybrid Inventory
                if item.shop_product_id:
                    unit_cost = (item.taxable_amount / item.quantity) if item.quantity > 0 else 0.0
                    gst_pct = item.purchase_cgst_percentage + item.purchase_sgst_percentage + item.purchase_igst_percentage

                    db.add(
                        PurchaseBatch(
                            shop_id=current_shop.id,
                            local_id=item.local_id,
                            product_id=item.shop_product_id,
                            purchase_invoice_id=purchase.id,
                            supplier_name=p.supplier_name,
                            supplier_gstin=p.supplier_gstin,
                            invoice_number=p.invoice_number,
                            batch_code=p.invoice_number,
                            quantity_purchased=item.quantity,
                            quantity_remaining=item.quantity,
                            unit_cost_excluding_tax=unit_cost,
                            gst_percent=gst_pct,
                            cgst_percent=item.purchase_cgst_percentage,
                            sgst_percent=item.purchase_sgst_percentage,
                            igst_percent=item.purchase_igst_percentage,
                            invoice_value=item.invoice_value,
                            taxable_value=item.taxable_amount,
                            invoice_date=purchase.invoice_date,
                            created_at=purchase.created_at
                        )
                    )

            purchase_id_map[str(p.local_id)] = purchase.id
            success_count += 1

        db.commit()

    except IntegrityError as e:
        db.rollback()
        return JSONResponse(
            status_code=400,
            content={"message": f"Database integrity error: {str(e.orig)}"}
        )
    except Exception as e:
        db.rollback()
        return JSONResponse(
            status_code=500,
            content={"message": f"Server error during purchase sync: {str(e)}"}
        )

    return PurchaseSyncResponse(
        success_count=success_count,
        purchase_id_map=purchase_id_map
    )