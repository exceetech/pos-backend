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
    Generate and email a GST report (gstr1 / gstr2 / gstr3b / hsn).
    Data sourced from gst_sales_records and gst_purchase_records tables only.
    """
    from app.models.gst_sales_record import GstSalesRecord
    from app.models.gst_purchase_record import GstPurchaseRecord
    from datetime import datetime

    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    except ValueError:
        raise ValueError("Invalid date format — use YYYY-MM-DD")

    subject_map = {
        "gstr1": "GSTR-1 Outward Supplies Report",
        "gstr2": "GSTR-2 Purchase Register Report",
        "gstr3b": "GSTR-3B Tax Liability Summary",
        "hsn": "HSN-wise Summary Report"
    }
    subject = f"📊 {subject_map.get(report_type, 'GST Report')} | {start_date} to {end_date} — {shop.shop_name}"

    if report_type in ("gstr1", "hsn"):
        records = db.query(GstSalesRecord).filter(
            GstSalesRecord.shop_id == shop.id,
            GstSalesRecord.invoice_date >= start,
            GstSalesRecord.invoice_date <= end
        ).all()
        body = (
            f"GST Report: {subject_map.get(report_type)}\n"
            f"Shop: {shop.shop_name} | GSTIN: {shop.store_gstin or 'N/A'}\n"
            f"Period: {start_date} to {end_date}\n\n"
            f"Total Records:  {len(records)}\n"
            f"Taxable Value:  Rs.{sum(r.taxable_value for r in records):.2f}\n"
            f"CGST:           Rs.{sum(r.cgst_amount for r in records):.2f}\n"
            f"SGST:           Rs.{sum(r.sgst_amount for r in records):.2f}\n"
            f"IGST:           Rs.{sum(r.igst_amount for r in records):.2f}\n"
        )

    elif report_type == "gstr2":
        records = db.query(GstPurchaseRecord).filter(
            GstPurchaseRecord.shop_id == shop.id,
            GstPurchaseRecord.invoice_date >= start,
            GstPurchaseRecord.invoice_date <= end
        ).all()
        body = (
            f"GSTR-2 Purchase Register\n"
            f"Shop: {shop.shop_name} | GSTIN: {shop.store_gstin or 'N/A'}\n"
            f"Period: {start_date} to {end_date}\n\n"
            f"Total Invoices: {len(records)}\n"
            f"Taxable Value:  Rs.{sum(r.taxable_value for r in records):.2f}\n"
            f"ITC CGST:       Rs.{sum(r.cgst_amount for r in records):.2f}\n"
            f"ITC SGST:       Rs.{sum(r.sgst_amount for r in records):.2f}\n"
            f"ITC IGST:       Rs.{sum(r.igst_amount for r in records):.2f}\n"
        )

    elif report_type == "gstr3b":
        sales = db.query(GstSalesRecord).filter(
            GstSalesRecord.shop_id == shop.id,
            GstSalesRecord.invoice_date >= start,
            GstSalesRecord.invoice_date <= end
        ).all()
        purchases = db.query(GstPurchaseRecord).filter(
            GstPurchaseRecord.shop_id == shop.id,
            GstPurchaseRecord.invoice_date >= start,
            GstPurchaseRecord.invoice_date <= end
        ).all()
        out_cgst = sum(r.cgst_amount for r in sales)
        out_sgst = sum(r.sgst_amount for r in sales)
        out_igst = sum(r.igst_amount for r in sales)
        itc_cgst = sum(r.cgst_amount for r in purchases)
        itc_sgst = sum(r.sgst_amount for r in purchases)
        itc_igst = sum(r.igst_amount for r in purchases)
        body = (
            f"GSTR-3B Tax Liability Summary\n"
            f"Shop: {shop.shop_name} | GSTIN: {shop.store_gstin or 'N/A'}\n"
            f"Period: {start_date} to {end_date}\n\n"
            f"OUTWARD TAX: CGST Rs.{out_cgst:.2f} | SGST Rs.{out_sgst:.2f} | IGST Rs.{out_igst:.2f}\n"
            f"ITC:         CGST Rs.{itc_cgst:.2f} | SGST Rs.{itc_sgst:.2f} | IGST Rs.{itc_igst:.2f}\n"
            f"NET PAYABLE: CGST Rs.{max(0, out_cgst-itc_cgst):.2f} | "
            f"SGST Rs.{max(0, out_sgst-itc_sgst):.2f} | IGST Rs.{max(0, out_igst-itc_igst):.2f}\n"
        )
    else:
        body = f"GST Report for {start_date} to {end_date}\nShop: {shop.shop_name}"

    send_email(to_email=shop.email, subject=subject, body=body)