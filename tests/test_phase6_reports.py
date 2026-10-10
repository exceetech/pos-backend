"""Phase 6: GSTR-2 shows correction notes (CDNR) and nets taxable value and ITC.
Run: cd pos-backend && python -m pytest tests/test_phase6_reports.py -v
"""
from tests.test_stage1_purchase_notes import make_db, add_purchase, add_note
from datetime import datetime
from app.routes.gst_routes import get_gstr2


def report(db, shop):
    today = datetime.now().strftime("%Y-%m-%d")
    return get_gstr2(start_date=today, end_date=today, db=db, current_shop=shop)


def test_T6_2_price_note_in_cdnr_and_nets_totals():
    db, shop = make_db(); p = add_purchase(db, shop)
    p.supplier_gstin = "33ABCDE1234F1Z5"; db.commit()
    base = report(db, shop)
    add_note(db, shop, p, "D", 100.0, note_kind="PRICE_CORRECTION", supplier_gstin="33ABCDE1234F1Z5",
             note_number="DN-00001", taxable_amount=100.0, note_refund_voucher_value=118.0,
             cgst_amount=9.0, sgst_amount=9.0, availed_itc_central_tax=9.0, availed_itc_state_tax=9.0,
             document_type="Debit Note")
    r = report(db, shop)
    assert any(n.note_number == "DN-00001" and n.document_type == "Debit Note" for n in r.cdnr)
    assert round(base.total_taxable_value - r.total_taxable_value, 2) == 100.0
    assert round((base.total_itc_cgst + base.total_itc_sgst) - (r.total_itc_cgst + r.total_itc_sgst), 2) == 18.0


def test_T6_2b_credit_note_raises_taxable():
    db, shop = make_db(); p = add_purchase(db, shop)
    p.supplier_gstin = "33ABCDE1234F1Z5"; db.commit()
    base = report(db, shop)
    add_note(db, shop, p, "C", 5.0, note_kind="QTY_CORRECTION", supplier_gstin="33ABCDE1234F1Z5",
             note_number="CN-00001", taxable_amount=50.0, note_refund_voucher_value=59.0, document_type="Credit Note")
    r = report(db, shop)
    assert round(r.total_taxable_value - base.total_taxable_value, 2) == 50.0
