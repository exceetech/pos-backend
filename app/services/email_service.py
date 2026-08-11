import smtplib
import os
import uuid
import time
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")


def send_email(to_email: str, subject: str, body: str, html_body: str = None):
    msg = EmailMessage()
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = to_email
    msg["Subject"] = subject
    msg["Message-ID"] = f"<{uuid.uuid4()}@expos.in>"
    msg.set_content(body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

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
    owner_name = getattr(shop, "owner_name", "Merchant") or "Merchant"
    shop_name = getattr(shop, "shop_name", "your business") or "your business"
    otp_str = str(otp).strip()
    msg_nonce = f"{int(time.time())}-{otp_str}"

    # Generate individual border-line square boxes for each OTP digit using Google Sans
    otp_boxes_html = "".join([
        f'<td width="40" height="46" align="center" valign="middle" style="background-color: #FFFFFF; border: 1.5px solid #0F6E56; border-radius: 8px; font-family: \'Google Sans\', -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif; font-size: 22px; font-weight: 700; color: #1A1A18;">{ch}</td><td width="6"></td>'
        for ch in otp_str
    ])

    plain_body = f"""Hello {owner_name},

We received a request to verify your account or reset your password for {shop_name}.

Your verification code (OTP) is: {otp}
This code is valid for 5 minutes.

Please do not share this code with anyone.

Regards,
ExPOS Team
[Ref: {msg_nonce}]
"""

    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Verify Your Email - ExPOS</title>
</head>
<body style="margin: 0; padding: 0; background-color: #FFFFFF; font-family: 'Google Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1A1A18; -webkit-font-smoothing: antialiased;">

    <!-- Hidden Preheader (prevents Gmail thread collapsing and trimmed content) -->
    <div style="display:none !important; visibility:hidden; opacity:0; color:transparent; height:0; width:0; max-height:0; max-width:0; overflow:hidden; font-size:1px; line-height:1px;">
        Verification code for {shop_name}: {otp}. Ref: {msg_nonce}
    </div>

    <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #FFFFFF; padding: 36px 20px;">
        <tr>
            <td align="left" style="max-width: 540px; margin: 0 auto; display: block;">
                
                <!-- App Brand Header (Matching Login Card) -->
                <div style="margin-bottom: 24px;">
                    <span style="font-family: 'Marcellus', Georgia, 'Times New Roman', serif; font-size: 22px; font-weight: 700; color: #1A1A18;">Ex</span><span style="font-family: 'Marcellus', Georgia, 'Times New Roman', serif; font-size: 22px; font-weight: 700; color: #B8895A;">POS</span>
                </div>

                <!-- Eyebrow -->
                <div style="font-family: 'Google Sans', -apple-system, BlinkMacSystemFont, sans-serif; font-size: 11px; font-weight: 600; color: #B8895A; text-transform: uppercase; letter-spacing: 2px; margin-bottom: 6px;">
                    ACCOUNT VERIFICATION
                </div>

                <!-- Two-Tone Serif Page Heading Matching App -->
                <h1 style="margin: 0 0 12px 0; font-size: 24px; line-height: 1.3; font-weight: normal;">
                    <span style="font-family: Georgia, 'Times New Roman', serif; font-weight: 400; color: #1A1A18;">Verify Your </span>
                    <span style="font-family: Georgia, 'Times New Roman', serif; font-style: italic; font-weight: 400; color: #0F6E56;">Email</span>
                </h1>

                <!-- Subtitle / Body Copy (Google Sans, non-bold) -->
                <p style="font-family: 'Google Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 14px; font-weight: 400; color: #8A8272; margin: 0 0 24px 0; line-height: 1.6;">
                    Hello {owner_name},<br>
                    Please enter the 6-digit verification code below to confirm your account for {shop_name}:
                </p>

                <!-- Single Unified Box Container with Square Digit Boxes + Expiry -->
                <div style="background-color: #FAF7F2; border: 1.5px solid #0F6E56; border-radius: 14px; padding: 22px 16px; text-align: center; margin-bottom: 24px;">
                    <table role="presentation" border="0" cellspacing="0" cellpadding="0" align="center" style="margin: 0 auto 12px auto;">
                        <tr>
                            {otp_boxes_html}
                        </tr>
                    </table>
                    <div style="font-family: 'Google Sans', -apple-system, BlinkMacSystemFont, sans-serif; font-size: 12.5px; font-weight: 400; color: #B8895A; letter-spacing: 0.3px;">Code valid for 5 minutes</div>
                </div>

                <!-- Security Note -->
                <p style="font-family: 'Google Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 12.5px; font-weight: 400; color: #8A8272; margin: 0 0 28px 0; line-height: 1.5;">
                    If you did not request this verification, you can safely ignore this email. Do not share this code with anyone.
                </p>

                <!-- Divider & Footer -->
                <hr style="border: none; border-top: 1px solid #EBE4D5; margin: 0 0 18px 0;">
                <p style="font-family: 'Google Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 12px; font-weight: 400; color: #A39988; margin: 0; line-height: 1.5; text-align: center;">
                    Sent by ExPOS • Smart POS for Modern Retail<br>
                    Need help? Contact <a href="mailto:support@expos.in" style="color: #0F6E56; text-decoration: none; font-weight: normal;">support@expos.in</a>
                </p>

                <!-- Powered By Scalancer -->
                <div style="margin-top: 24px; text-align: center;">
                    <div style="font-family: 'Google Sans', -apple-system, BlinkMacSystemFont, sans-serif; font-size: 8px; font-weight: 600; color: #B4A98F; text-transform: uppercase; letter-spacing: 2px; margin-bottom: 2px;">
                        POWERED BY
                    </div>
                    <div style="font-family: 'Marcellus', Georgia, 'Times New Roman', serif; font-size: 13px; font-weight: 700; color: #1A1A18; letter-spacing: 3px; text-transform: uppercase;">
                        SCALANCER
                    </div>
                </div>

            </td>
        </tr>
    </table>

    <!-- Nonce comment to prevent Gmail content trimming -->
    <!-- ref:{msg_nonce} -->
</body>
</html>
"""

    send_email(
        to_email=shop.email,
        subject="Password Reset OTP - ExPOS",
        body=plain_body,
        html_body=html_body
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