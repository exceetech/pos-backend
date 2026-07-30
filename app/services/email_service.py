import smtplib
import os
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")


def send_email(to_email: str, subject: str, body: str):
    msg = EmailMessage()
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.send_message(msg)


def send_registration_emails(shop):
    # Email to shop owner
    send_email(
        to_email=shop.email,
        subject="Registration Received - POS System",
        body=f"""
Hello {shop.owner_name},

Thank you for registering your shop "{shop.shop_name}".

Our team will contact you soon.

Regards,
eXCee Team
"""
    )

    # Email to admin
    send_email(
        to_email=ADMIN_EMAIL,
        subject="New Shop Registration",
        body=f"""
New shop registered:

Shop Name: {shop.shop_name}
Owner: {shop.owner_name}
Email: {shop.email}
Phone: {shop.phone}
"""
    )

def send_otp_email(shop, otp):
    send_email(
    to_email=shop.email, 
    subject="Password Reset OTP - eXCee POS",
    body=f"""
    Hello {shop.owner_name},

    We received a request to reset your password.

    Your OTP is:

        {otp}

    This OTP is valid for 5 minutes.
    """
        )
    
def send_subscription_email(shop, plan, expiry):
    send_email(
        to_email=shop.email,
        subject="🎉 Subscription Activated Successfully - ExPOS",
        body=f"""
Hello {shop.owner_name},

Your subscription for ExPOS- Smart POS for modern businesses has been successfully activated! 🎉

━━━━━━━━━━━━━━━━━━━━━━━
📦 Subscription Details
━━━━━━━━━━━━━━━━━━━━━━━
🛒 Shop Name : {shop.shop_name}
📅 Plan       : {plan.capitalize()}
⏳ Valid Till : {expiry}

━━━━━━━━━━━━━━━━━━━━━━━
✨ What You Get
━━━━━━━━━━━━━━━━━━━━━━━
✔ Unlimited billing & invoices  
✔ Advanced reports & analytics  
✔ Secure data management  
✔ Priority support  

You can now enjoy all premium features without any interruption.

━━━━━━━━━━━━━━━━━━━━━━━
🔔 Important Reminder
━━━━━━━━━━━━━━━━━━━━━━━
You will receive notifications before your subscription expires, so you never miss a renewal.

If you have any questions or need assistance, feel free to contact our support team anytime.


Thank you for choosing ExPOS to power your business.

Warm regards,  
eXCee Team  
📧 Support: support@expos.in
"""
    )


async def send_gst_report_email(shop, report_type: str, start_date: str, end_date: str, db):
    """
    Generate and email a GST report (gstr1 / gstr2 / hsn).

    GST-reports fix round 2, Phase 3: this used to be a THIRD, independent
    implementation of the same numbers the in-app GSTR-1/GSTR-2 screens
    compute — a hand-rolled aggregation for gstr1/hsn (duplicating logic
    that could silently drift from the real endpoint), and for gstr2 a
    query against `GstPurchaseRecord`, a table that was retired on the
    Android side (see AppDatabase.kt's MIGRATION_42_43 note) and no longer
    receives any data — meaning every emailed GSTR-2 report was reporting
    on a frozen or empty purchase register regardless of what the shop
    actually purchased.

    Fixed by calling the real, already-fixed `get_gstr1()` / `get_gstr2()`
    route functions directly and reading their totals — same numbers the
    in-app screens show, computed exactly once, in exactly one place.
    """
    from datetime import datetime
    from app.routes.gst_routes import get_gstr1, get_gstr2

    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    except ValueError:
        raise ValueError("Invalid date format — use YYYY-MM-DD")

    subject_map = {
        "gstr1": "GSTR-1 Outward Supplies Report",
        "gstr2": "GSTR-2 Purchase Register Report",
        "hsn": "HSN-wise Summary Report"
    }
    subject = f"📊 {subject_map.get(report_type, 'GST Report')} | {start_date} to {end_date} — {shop.shop_name}"

    if report_type in ("gstr1", "hsn"):
        # get_gstr1() is a plain function underneath its @router.get
        # decorator — calling it directly with the same args FastAPI's
        # dependency injection would have supplied is the same pattern
        # used to test it; no HTTP round-trip needed.
        report = get_gstr1(start_date=start_date, end_date=end_date, db=db, current_shop=shop)
        credit_note_count = sum(1 for r in report.cdnr if r.note_type == "C") + \
            sum(1 for r in report.cdnur if r.note_type == "C")
        debit_note_count = sum(1 for r in report.cdnr if r.note_type == "D") + \
            sum(1 for r in report.cdnur if r.note_type == "D")
        total_records = len(report.b2b) + len(report.b2cl) + len(report.b2cs)

        body = (
            f"GST Report: {subject_map.get(report_type)}\n"
            f"Shop: {shop.shop_name} | GSTIN: {shop.store_gstin or 'N/A'}\n"
            f"Period: {start_date} to {end_date}\n\n"
            f"Total Records:  {total_records}"
            f" ({credit_note_count} credit note(s), {debit_note_count} debit note(s) applied)\n"
            f"Taxable Value:  Rs.{report.total_taxable_value:.2f}\n"
            f"CGST:           Rs.{report.total_cgst:.2f}\n"
            f"SGST:           Rs.{report.total_sgst:.2f}\n"
            f"IGST:           Rs.{report.total_igst:.2f}\n"
        )

    elif report_type == "gstr2":
        report = get_gstr2(start_date=start_date, end_date=end_date, db=db, current_shop=shop)
        total_invoices = len(report.b2b) + len(report.b2bur) + len(report.imps) + len(report.impg)
        taxable = sum(r.taxable_value for r in report.b2b) + sum(r.taxable_value for r in report.b2bur) + \
            sum(r.taxable_value for r in report.imps) + sum(r.taxable_value for r in report.impg)
        body = (
            f"GSTR-2 Purchase Register\n"
            f"Shop: {shop.shop_name} | GSTIN: {shop.store_gstin or 'N/A'}\n"
            f"Period: {start_date} to {end_date}\n\n"
            f"Total Invoices: {total_invoices}\n"
            f"Taxable Value:  Rs.{taxable:.2f}\n"
            f"ITC CGST:       Rs.{report.total_itc_cgst:.2f}\n"
            f"ITC SGST:       Rs.{report.total_itc_sgst:.2f}\n"
            f"ITC IGST:       Rs.{report.total_itc_igst:.2f}\n"
        )

    else:
        body = f"GST Report for {start_date} to {end_date}\nShop: {shop.shop_name}"

    send_email(to_email=shop.email, subject=subject, body=body)