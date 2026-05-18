"""
GST Calculation Service — Pure, stateless functions.
No DB, no API calls. 100% offline-safe.
Used by both the Android GstEngine (Kotlin) and the backend sync routes.
"""
from typing import Tuple


# ============================================================
# State Code Utilities
# ============================================================

INDIA_STATES = {
    "01": "Jammu & Kashmir", "02": "Himachal Pradesh", "03": "Punjab",
    "04": "Chandigarh", "05": "Uttarakhand", "06": "Haryana",
    "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
    "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh",
    "13": "Nagaland", "14": "Manipur", "15": "Mizoram", "16": "Tripura",
    "17": "Meghalaya", "18": "Assam", "19": "West Bengal",
    "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh",
    "23": "Madhya Pradesh", "24": "Gujarat", "25": "Daman & Diu",
    "26": "Dadra & Nagar Haveli", "27": "Maharashtra", "28": "Andhra Pradesh (Old)",
    "29": "Karnataka", "30": "Goa", "31": "Lakshadweep", "32": "Kerala",
    "33": "Tamil Nadu", "34": "Puducherry", "35": "Andaman & Nicobar",
    "36": "Telangana", "37": "Andhra Pradesh"
}

VALID_GST_RATES = {0.0, 0.1, 0.25, 1.5, 3.0, 5.0, 6.0, 7.5, 9.0, 12.0, 14.0, 18.0, 28.0}


def extract_state_code(gstin: str) -> str:
    """Extract 2-digit state code from GSTIN (first two characters)."""
    if not gstin or len(gstin) < 2:
        return ""
    return gstin[:2]


def is_valid_gstin(gstin: str) -> bool:
    """Basic format check: 15 alphanumeric characters."""
    if not gstin or len(gstin) != 15:
        return False
    return gstin.isalnum()


def get_state_name(state_code: str) -> str:
    return INDIA_STATES.get(state_code, "Unknown")


# ============================================================
# Supply Type Determination
# ============================================================

def determine_supply_type(seller_state_code: str, buyer_state_code: str) -> str:
    """
    Returns 'intrastate' if seller and buyer are in the same state,
    'interstate' otherwise. Empty buyer_state_code defaults to intrastate (B2C).
    """
    if not buyer_state_code:
        return "intrastate"
    return "intrastate" if seller_state_code == buyer_state_code else "interstate"


# ============================================================
# GST Split Calculation
# ============================================================

def calculate_gst_split(
    taxable_value: float,
    gst_rate: float,
    supply_type: str
) -> Tuple[float, float, float]:
    """
    Returns (cgst, sgst, igst) for a given taxable value and GST rate.
    - Intrastate: CGST = SGST = rate/2 each
    - Interstate:  IGST = full rate
    """
    if gst_rate <= 0 or taxable_value <= 0:
        return 0.0, 0.0, 0.0

    total_tax = round(taxable_value * gst_rate / 100, 2)

    if supply_type == "intrastate":
        half = round(total_tax / 2, 2)
        # ensure sum equals total_tax (avoid rounding diff)
        other_half = round(total_tax - half, 2)
        return half, other_half, 0.0
    else:
        return 0.0, 0.0, total_tax


def calculate_invoice_gst(
    taxable_value: float,
    gst_rate: float,
    seller_state_code: str,
    buyer_state_code: str
) -> dict:
    """
    Full computation including supply type detection.
    Returns dict with cgst, sgst, igst, supply_type, total.
    """
    supply_type = determine_supply_type(seller_state_code, buyer_state_code)
    cgst, sgst, igst = calculate_gst_split(taxable_value, gst_rate, supply_type)
    total_tax = round(cgst + sgst + igst, 2)

    return {
        "supply_type": supply_type,
        "taxable_value": round(taxable_value, 2),
        "gst_rate": gst_rate,
        "cgst": cgst,
        "sgst": sgst,
        "igst": igst,
        "total_tax": total_tax,
        "grand_total": round(taxable_value + total_tax, 2)
    }


# ============================================================
# GSTR-3B Helper: Aggregate multiple line records
# ============================================================

def aggregate_gst_records(records: list) -> dict:
    """
    Accepts a list of dicts with keys: taxable_value, cgst_amount, sgst_amount, igst_amount.
    Returns aggregated totals.
    """
    return {
        "total_taxable_value": round(sum(r.get("taxable_value", 0) for r in records), 2),
        "total_cgst": round(sum(r.get("cgst_amount", 0) for r in records), 2),
        "total_sgst": round(sum(r.get("sgst_amount", 0) for r in records), 2),
        "total_igst": round(sum(r.get("igst_amount", 0) for r in records), 2),
    }
