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
    owner_name = getattr(shop, "owner_name", "Merchant") or "Merchant"
    shop_name = getattr(shop, "shop_name", "your business") or "your business"
    email = getattr(shop, "email", "") or ""
    msg_nonce = f"{int(time.time())}-reg"

    plain_body = f"""Hello {owner_name},

Thank you for registering your business "{shop_name}" with ExPOS.

Registration Details:
- Shop Name: {shop_name}
- Owner Name: {owner_name}
- Email: {email}

Our onboarding team will review your account and contact you shortly if assistance is needed.

Regards,
ExPOS Team
[Ref: {msg_nonce}]
"""

    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Welcome to ExPOS</title>
    <style>
        @font-face {{
            font-family: 'Marcellus';
            font-style: normal;
            font-weight: 400;
            font-display: swap;
            src: url('https://fonts.gstatic.com/s/marcellus/v14/wEO_EBrOk8hQLDvIAF8FUQ.ttf') format('truetype');
        }}
    </style>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Marcellus&display=swap" rel="stylesheet">
</head>
<body style="margin: 0; padding: 0; background-color: #FFFFFF; font-family: 'Google Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1A1A18; -webkit-font-smoothing: antialiased;">

    <!-- Hidden Preheader (prevents Gmail thread collapsing and trimmed content) -->
    <div style="display:none !important; visibility:hidden; opacity:0; color:transparent; height:0; width:0; max-height:0; max-width:0; overflow:hidden; font-size:1px; line-height:1px;">
        Welcome to ExPOS, {owner_name}! Your registration for {shop_name} is confirmed. Ref: {msg_nonce}
    </div>

    <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #FFFFFF; padding: 36px 20px;">
        <tr>
            <td align="left" style="max-width: 540px; margin: 0 auto; display: block;">
                
                <!-- App Brand Header -->
                <div style="margin-bottom: 24px;">
                    <span style="font-family: 'Marcellus', Georgia, 'Times New Roman', serif; font-size: 24px; font-weight: 400; color: #1A1A18;">Ex</span><span style="font-family: 'Marcellus', Georgia, 'Times New Roman', serif; font-size: 24px; font-weight: 400; color: #B8895A;">POS</span>
                </div>

                <!-- Eyebrow -->
                <div style="font-family: 'Google Sans', -apple-system, BlinkMacSystemFont, sans-serif; font-size: 11px; font-weight: 600; color: #B8895A; text-transform: uppercase; letter-spacing: 2px; margin-bottom: 6px;">
                    REGISTRATION RECEIVED
                </div>

                <!-- Two-Tone Serif Page Heading -->
                <h1 style="margin: 0 0 12px 0; font-size: 24px; line-height: 1.3; font-weight: normal;">
                    <span style="font-family: Georgia, 'Times New Roman', serif; font-weight: 400; color: #1A1A18;">Welcome to </span>
                    <span style="font-family: Georgia, 'Times New Roman', serif; font-style: italic; font-weight: 400; color: #0F6E56;">ExPOS</span>
                </h1>

                <!-- Subtitle / Greeting -->
                <p style="font-family: 'Google Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 14px; font-weight: 400; color: #8A8272; margin: 0 0 24px 0; line-height: 1.6;">
                    Hello <strong>{owner_name}</strong>,<br>
                    Thank you for registering your business with ExPOS. We are thrilled to welcome you to smart, modern retail management.
                </p>

                <!-- Registration Summary Card -->
                <div style="background-color: #FAF7F2; border: 1.5px solid #0F6E56; border-radius: 14px; padding: 22px 20px; margin-bottom: 24px;">
                    <div style="font-family: 'Google Sans', sans-serif; font-size: 11px; font-weight: 700; color: #0F6E56; text-transform: uppercase; letter-spacing: 1.5px; margin-bottom: 14px;">
                        REGISTRATION DETAILS
                    </div>

                    <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="font-size: 13.5px; font-family: 'Google Sans', sans-serif; color: #1A1A18; line-height: 1.8;">
                        <tr>
                            <td style="color: #8A8272; width: 110px; padding-bottom: 6px;">Shop Name</td>
                            <td style="font-weight: 600; color: #1A1A18; padding-bottom: 6px;">{shop_name}</td>
                        </tr>
                        <tr>
                            <td style="color: #8A8272; padding-bottom: 6px;">Owner Name</td>
                            <td style="font-weight: 600; color: #1A1A18; padding-bottom: 6px;">{owner_name}</td>
                        </tr>
                        <tr>
                            <td style="color: #8A8272; padding-bottom: 6px;">Email</td>
                            <td style="font-weight: 500; color: #1A1A18; padding-bottom: 6px;">{email}</td>
                        </tr>
                    </table>

                    <div style="margin-top: 14px; padding-top: 14px; border-top: 1px solid #EBE4D5; text-align: left;">
                        <span style="display: inline-block; background-color: #E4F1EC; color: #0F6E56; font-size: 12px; font-weight: 600; padding: 6px 14px; border-radius: 20px;">
                            ✓ Registration Confirmed
                        </span>
                    </div>
                </div>

                <!-- What Happens Next Section -->
                <div style="margin-bottom: 28px;">
                    <div style="font-family: 'Google Sans', sans-serif; font-size: 13px; font-weight: 700; color: #1A1A18; margin-bottom: 12px;">
                        ✨ What happens next?
                    </div>

                    <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="font-size: 13px; font-family: 'Google Sans', sans-serif; color: #6E6759; line-height: 1.7;">
                        <tr>
                            <td style="vertical-align: top; width: 22px; color: #0F6E56; font-weight: bold;">1.</td>
                            <td style="padding-bottom: 8px;">Our onboarding team will review your account and contact you shortly if setup assistance is needed.</td>
                        </tr>
                        <tr>
                            <td style="vertical-align: top; width: 22px; color: #0F6E56; font-weight: bold;">2.</td>
                            <td style="padding-bottom: 8px;">Open the <strong>ExPOS App</strong> on your device and sign in using your registered credentials.</td>
                        </tr>
                        <tr>
                            <td style="vertical-align: top; width: 22px; color: #0F6E56; font-weight: bold;">3.</td>
                            <td>Start adding products, creating invoices, and managing your inventory seamlessly!</td>
                        </tr>
                    </table>
                </div>

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
                    <div style="font-family: 'Marcellus', Georgia, 'Times New Roman', serif; font-size: 13px; font-weight: 400; color: #1A1A18; letter-spacing: 3px; text-transform: uppercase;">
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

    # Email to shop owner
    send_email(
        to_email=shop.email,
        subject="Welcome to ExPOS - Registration Received",
        body=plain_body,
        html_body=html_body
    )

    phone = getattr(shop, "phone", "N/A") or "N/A"
    admin_nonce = f"{int(time.time())}-adm"

    admin_plain_body = f"""New Shop Registration Alert:

Shop Name: {shop_name}
Owner Name: {owner_name}
Email: {email}
Phone: {phone}

Action Required: Review account profile and initiate merchant onboarding.

Regards,
ExPOS System
[Ref: {admin_nonce}]
"""

    admin_html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>New Shop Registered - ExPOS Admin</title>
    <style>
        @font-face {{
            font-family: 'Marcellus';
            font-style: normal;
            font-weight: 400;
            font-display: swap;
            src: url('https://fonts.gstatic.com/s/marcellus/v14/wEO_EBrOk8hQLDvIAF8FUQ.ttf') format('truetype');
        }}
    </style>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Marcellus&display=swap" rel="stylesheet">
</head>
<body style="margin: 0; padding: 0; background-color: #FFFFFF; font-family: 'Google Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1A1A18; -webkit-font-smoothing: antialiased;">

    <!-- Hidden Preheader -->
    <div style="display:none !important; visibility:hidden; opacity:0; color:transparent; height:0; width:0; max-height:0; max-width:0; overflow:hidden; font-size:1px; line-height:1px;">
        New merchant registration: {shop_name} ({owner_name}). Ref: {admin_nonce}
    </div>

    <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #FFFFFF; padding: 36px 20px;">
        <tr>
            <td align="left" style="max-width: 540px; margin: 0 auto; display: block;">
                
                <!-- App Brand Header -->
                <div style="margin-bottom: 24px;">
                    <span style="font-family: 'Marcellus', Georgia, 'Times New Roman', serif; font-size: 24px; font-weight: 400; color: #1A1A18;">Ex</span><span style="font-family: 'Marcellus', Georgia, 'Times New Roman', serif; font-size: 24px; font-weight: 400; color: #B8895A;">POS</span>
                </div>

                <!-- Eyebrow -->
                <div style="font-family: 'Google Sans', -apple-system, BlinkMacSystemFont, sans-serif; font-size: 11px; font-weight: 600; color: #B8895A; text-transform: uppercase; letter-spacing: 2px; margin-bottom: 6px;">
                    ADMIN NOTIFICATION
                </div>

                <!-- Two-Tone Serif Page Heading -->
                <h1 style="margin: 0 0 12px 0; font-size: 24px; line-height: 1.3; font-weight: normal;">
                    <span style="font-family: Georgia, 'Times New Roman', serif; font-weight: 400; color: #1A1A18;">New Shop </span>
                    <span style="font-family: Georgia, 'Times New Roman', serif; font-style: italic; font-weight: 400; color: #0F6E56;">Registered</span>
                </h1>

                <!-- Subtitle / Notice -->
                <p style="font-family: 'Google Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 14px; font-weight: 400; color: #8A8272; margin: 0 0 24px 0; line-height: 1.6;">
                    A new merchant has registered on the ExPOS platform. Review their account profile below:
                </p>

                <!-- Merchant Profile Card -->
                <div style="background-color: #FAF7F2; border: 1.5px solid #0F6E56; border-radius: 14px; padding: 22px 20px; margin-bottom: 24px;">
                    <div style="font-family: 'Google Sans', sans-serif; font-size: 11px; font-weight: 700; color: #0F6E56; text-transform: uppercase; letter-spacing: 1.5px; margin-bottom: 14px;">
                        MERCHANT PROFILE
                    </div>

                    <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="font-size: 13.5px; font-family: 'Google Sans', sans-serif; color: #1A1A18; line-height: 1.8;">
                        <tr>
                            <td style="color: #8A8272; width: 110px; padding-bottom: 6px;">Shop Name</td>
                            <td style="font-weight: 600; color: #1A1A18; padding-bottom: 6px;">{shop_name}</td>
                        </tr>
                        <tr>
                            <td style="color: #8A8272; padding-bottom: 6px;">Owner Name</td>
                            <td style="font-weight: 600; color: #1A1A18; padding-bottom: 6px;">{owner_name}</td>
                        </tr>
                        <tr>
                            <td style="color: #8A8272; padding-bottom: 6px;">Email</td>
                            <td style="font-weight: 500; color: #1A1A18; padding-bottom: 6px;">{email}</td>
                        </tr>
                        <tr>
                            <td style="color: #8A8272; padding-bottom: 6px;">Phone</td>
                            <td style="font-weight: 500; color: #1A1A18; padding-bottom: 6px;">{phone}</td>
                        </tr>
                    </table>

                    <div style="margin-top: 14px; padding-top: 14px; border-top: 1px solid #EBE4D5; text-align: left;">
                        <span style="display: inline-block; background-color: #FEF3D6; color: #8A6526; font-size: 12px; font-weight: 600; padding: 6px 14px; border-radius: 20px;">
                            🔔 Action Needed: Onboarding Review
                        </span>
                    </div>
                </div>

                <!-- Admin Next Actions Section -->
                <div style="margin-bottom: 28px;">
                    <div style="font-family: 'Google Sans', sans-serif; font-size: 13px; font-weight: 700; color: #1A1A18; margin-bottom: 12px;">
                        📌 Admin Next Actions
                    </div>

                    <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="font-size: 13px; font-family: 'Google Sans', sans-serif; color: #6E6759; line-height: 1.7;">
                        <tr>
                            <td style="vertical-align: top; width: 22px; color: #0F6E56; font-weight: bold;">•</td>
                            <td style="padding-bottom: 6px;">Contact the merchant to assist with initial store setup and onboarding.</td>
                        </tr>
                        <tr>
                            <td style="vertical-align: top; width: 22px; color: #0F6E56; font-weight: bold;">•</td>
                            <td>Verify merchant details and subscription entitlements in the Admin Portal.</td>
                        </tr>
                    </table>
                </div>

                <!-- Divider & Footer -->
                <hr style="border: none; border-top: 1px solid #EBE4D5; margin: 0 0 18px 0;">
                <p style="font-family: 'Google Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 12px; font-weight: 400; color: #A39988; margin: 0; line-height: 1.5; text-align: center;">
                    Internal Admin Alert • ExPOS POS System<br>
                    Need help? Contact <a href="mailto:support@expos.in" style="color: #0F6E56; text-decoration: none; font-weight: normal;">support@expos.in</a>
                </p>

                <!-- Powered By Scalancer -->
                <div style="margin-top: 24px; text-align: center;">
                    <div style="font-family: 'Google Sans', -apple-system, BlinkMacSystemFont, sans-serif; font-size: 8px; font-weight: 600; color: #B4A98F; text-transform: uppercase; letter-spacing: 2px; margin-bottom: 2px;">
                        POWERED BY
                    </div>
                    <div style="font-family: 'Marcellus', Georgia, 'Times New Roman', serif; font-size: 13px; font-weight: 400; color: #1A1A18; letter-spacing: 3px; text-transform: uppercase;">
                        SCALANCER
                    </div>
                </div>

            </td>
        </tr>
    </table>

    <!-- Nonce comment to prevent Gmail content trimming -->
    <!-- ref:{admin_nonce} -->
</body>
</html>
"""

    # Email to admin
    send_email(
        to_email=ADMIN_EMAIL,
        subject=f"🔔 New Shop Registration: {shop_name}",
        body=admin_plain_body,
        html_body=admin_html_body
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
    <style>
        @font-face {{
            font-family: 'Marcellus';
            font-style: normal;
            font-weight: 400;
            font-display: swap;
            src: url('https://fonts.gstatic.com/s/marcellus/v14/wEO_EBrOk8hQLDvIAF8FUQ.ttf') format('truetype');
        }}
    </style>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Marcellus&display=swap" rel="stylesheet">
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
                    <span style="font-family: 'Marcellus', Georgia, 'Times New Roman', serif; font-size: 24px; font-weight: 400; color: #1A1A18;">Ex</span><span style="font-family: 'Marcellus', Georgia, 'Times New Roman', serif; font-size: 24px; font-weight: 400; color: #B8895A;">POS</span>
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
                    <div style="font-family: 'Marcellus', Georgia, 'Times New Roman', serif; font-size: 13px; font-weight: 400; color: #1A1A18; letter-spacing: 3px; text-transform: uppercase;">
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
    owner_name = getattr(shop, "owner_name", "Merchant") or "Merchant"
    shop_name = getattr(shop, "shop_name", "your business") or "your business"
    plan_str = str(plan).strip()
    plan_name = plan_str.capitalize()
    sub_nonce = f"{int(time.time())}-sub"

    is_base_plan = "base" in plan_str.lower()

    if is_base_plan:
        badge_text = "✓ Base Plan Active"
        badge_bg = "#FAF2E6"
        badge_color = "#B8895A"
        subtitle_text = f"Hello <strong>{owner_name}</strong>,<br>Your <strong>Base Plan</strong> subscription for ExPOS has been successfully activated!"
        benefits_title = "✨ Included Base Plan Benefits"
        benefits_html = """
                        <tr>
                            <td style="vertical-align: top; width: 22px; color: #0F6E56; font-weight: bold;">✔</td>
                            <td style="padding-bottom: 4px;"><strong>Unlimited Billing & Invoices</strong> — Create and print sales invoices without limits.</td>
                        </tr>
                        <tr>
                            <td style="vertical-align: top; width: 22px; color: #0F6E56; font-weight: bold;">✔</td>
                            <td style="padding-bottom: 4px;"><strong>Inventory & Stock Control</strong> — Track stock levels, low-stock alerts, and purchase orders.</td>
                        </tr>
                        <tr>
                            <td style="vertical-align: top; width: 22px; color: #0F6E56; font-weight: bold;">✔</td>
                            <td style="padding-bottom: 4px;"><strong>Customer & Credit Ledgers</strong> — Manage customer payments, debit notes, and purchase returns.</td>
                        </tr>
                        <tr>
                            <td style="vertical-align: top; width: 22px; color: #0F6E56; font-weight: bold;">✔</td>
                            <td><strong>Secure Cloud Backup</strong> — Automated data backup and business safety.</td>
                        </tr>
"""
        plain_benefits = """- Unlimited billing & invoices
- Inventory & stock control
- Customer ledgers & returns
- Secure cloud backup & data safety"""
    else:
        badge_text = "✓ Premium Unlocked"
        badge_bg = "#E4F1EC"
        badge_color = "#0F6E56"
        subtitle_text = f"Hello <strong>{owner_name}</strong>,<br>Your <strong>Premium Plan</strong> subscription for ExPOS has been successfully activated! You now have full access to all advanced features."
        benefits_title = "✨ Included Premium Benefits"
        benefits_html = """
                        <tr>
                            <td style="vertical-align: top; width: 22px; color: #0F6E56; font-weight: bold;">✔</td>
                            <td style="padding-bottom: 4px;"><strong>Everything in Base Plan</strong> — Unlimited billing, stock tracking, and customer ledgers.</td>
                        </tr>
                        <tr>
                            <td style="vertical-align: top; width: 22px; color: #0F6E56; font-weight: bold;">✔</td>
                            <td style="padding-bottom: 4px;"><strong>Multi-Device Sync</strong> — Real-time cloud sync across all your store devices.</td>
                        </tr>
                        <tr>
                            <td style="vertical-align: top; width: 22px; color: #0F6E56; font-weight: bold;">✔</td>
                            <td style="padding-bottom: 4px;"><strong>Advanced GST Reports & Filing</strong> — Automated GSTR-1, GSTR-2, and HSN summary reports.</td>
                        </tr>
                        <tr>
                            <td style="vertical-align: top; width: 22px; color: #0F6E56; font-weight: bold;">✔</td>
                            <td><strong>Profit Analytics & Priority Support</strong> — Revenue insights, AI forecasting, and dedicated support.</td>
                        </tr>
"""
        plain_benefits = """- Everything in Base Plan
- Multi-device real-time sync
- Advanced GST reports & filing
- Profit analytics & priority support"""

    plain_body = f"""Hello {owner_name},

Your subscription for ExPOS has been successfully activated! 🎉

Subscription Details:
- Shop Name: {shop_name}
- Plan: {plan_name}
- Valid Till: {expiry}

Included Benefits:
{plain_benefits}

Thank you for choosing ExPOS.

Regards,
ExPOS Team
[Ref: {sub_nonce}]
"""

    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Subscription Activated Successfully - ExPOS</title>
    <style>
        @font-face {{
            font-family: 'Marcellus';
            font-style: normal;
            font-weight: 400;
            font-display: swap;
            src: url('https://fonts.gstatic.com/s/marcellus/v14/wEO_EBrOk8hQLDvIAF8FUQ.ttf') format('truetype');
        }}
    </style>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Marcellus&display=swap" rel="stylesheet">
</head>
<body style="margin: 0; padding: 0; background-color: #FFFFFF; font-family: 'Google Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1A1A18; -webkit-font-smoothing: antialiased;">

    <!-- Hidden Preheader -->
    <div style="display:none !important; visibility:hidden; opacity:0; color:transparent; height:0; width:0; max-height:0; max-width:0; overflow:hidden; font-size:1px; line-height:1px;">
        Subscription activated for {shop_name} (Plan: {plan_name}). Ref: {sub_nonce}
    </div>

    <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #FFFFFF; padding: 36px 20px;">
        <tr>
            <td align="left" style="max-width: 540px; margin: 0 auto; display: block;">
                
                <!-- App Brand Header -->
                <div style="margin-bottom: 24px;">
                    <span style="font-family: 'Marcellus', Georgia, 'Times New Roman', serif; font-size: 24px; font-weight: 400; color: #1A1A18;">Ex</span><span style="font-family: 'Marcellus', Georgia, 'Times New Roman', serif; font-size: 24px; font-weight: 400; color: #B8895A;">POS</span>
                </div>

                <!-- Eyebrow -->
                <div style="font-family: 'Google Sans', -apple-system, BlinkMacSystemFont, sans-serif; font-size: 11px; font-weight: 600; color: #B8895A; text-transform: uppercase; letter-spacing: 2px; margin-bottom: 6px;">
                    SUBSCRIPTION ACTIVATED
                </div>

                <!-- Two-Tone Serif Page Heading -->
                <h1 style="margin: 0 0 12px 0; font-size: 24px; line-height: 1.3; font-weight: normal;">
                    <span style="font-family: Georgia, 'Times New Roman', serif; font-weight: 400; color: #1A1A18;">Subscription </span>
                    <span style="font-family: Georgia, 'Times New Roman', serif; font-style: italic; font-weight: 400; color: #0F6E56;">Activated</span>
                </h1>

                <!-- Subtitle / Greeting -->
                <p style="font-family: 'Google Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 14px; font-weight: 400; color: #8A8272; margin: 0 0 24px 0; line-height: 1.6;">
                    {subtitle_text}
                </p>

                <!-- Subscription Details Summary Card -->
                <div style="background-color: #FAF7F2; border: 1.5px solid #0F6E56; border-radius: 14px; padding: 22px 20px; margin-bottom: 24px;">
                    <div style="font-family: 'Google Sans', sans-serif; font-size: 11px; font-weight: 700; color: #0F6E56; text-transform: uppercase; letter-spacing: 1.5px; margin-bottom: 14px;">
                        PLAN DETAILS
                    </div>

                    <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="font-size: 13.5px; font-family: 'Google Sans', sans-serif; color: #1A1A18; line-height: 1.8;">
                        <tr>
                            <td style="color: #8A8272; width: 110px; padding-bottom: 6px;">Shop Name</td>
                            <td style="font-weight: 600; color: #1A1A18; padding-bottom: 6px;">{shop_name}</td>
                        </tr>
                        <tr>
                            <td style="color: #8A8272; padding-bottom: 6px;">Plan</td>
                            <td style="font-weight: 600; color: #1A1A18; padding-bottom: 6px;">{plan_name}</td>
                        </tr>
                        <tr>
                            <td style="color: #8A8272; padding-bottom: 6px;">Valid Till</td>
                            <td style="font-weight: 600; color: #0F6E56; padding-bottom: 6px;">{expiry}</td>
                        </tr>
                    </table>

                    <div style="margin-top: 14px; padding-top: 14px; border-top: 1px solid #EBE4D5; text-align: left;">
                        <span style="display: inline-block; background-color: {badge_bg}; color: {badge_color}; font-size: 12px; font-weight: 600; padding: 6px 14px; border-radius: 20px;">
                            {badge_text}
                        </span>
                    </div>
                </div>

                <!-- What You Get Section -->
                <div style="margin-bottom: 28px;">
                    <div style="font-family: 'Google Sans', sans-serif; font-size: 13px; font-weight: 700; color: #1A1A18; margin-bottom: 12px;">
                        {benefits_title}
                    </div>

                    <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="font-size: 13px; font-family: 'Google Sans', sans-serif; color: #6E6759; line-height: 1.8;">
                        {benefits_html}
                    </table>
                </div>

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
                    <div style="font-family: 'Marcellus', Georgia, 'Times New Roman', serif; font-size: 13px; font-weight: 400; color: #1A1A18; letter-spacing: 3px; text-transform: uppercase;">
                        SCALANCER
                    </div>
                </div>

            </td>
        </tr>
    </table>

    <!-- Nonce comment to prevent Gmail content trimming -->
    <!-- ref:{sub_nonce} -->
</body>
</html>
"""

    send_email(
        to_email=shop.email,
        subject="🎉 Subscription Activated Successfully - ExPOS",
        body=plain_body,
        html_body=html_body
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
    owner_name = getattr(shop, "owner_name", "Merchant") or "Merchant"
    gst_nonce = f"{int(time.time())}-gst"
    report_title = subject_map.get(report_type, "GST Analytics Report")

    if report_type in ("gstr1", "hsn"):
        report = get_gstr1(start_date=start_date, end_date=end_date, db=db, current_shop=shop)
        credit_note_count = sum(1 for r in report.cdnr if r.note_type == "C") + \
            sum(1 for r in report.cdnur if r.note_type == "C")
        debit_note_count = sum(1 for r in report.cdnr if r.note_type == "D") + \
            sum(1 for r in report.cdnur if r.note_type == "D")
        total_records = len(report.b2b) + len(report.b2cl) + len(report.b2cs)

        body = (
            f"GST Report: {report_title}\n"
            f"Shop: {shop.shop_name} | GSTIN: {shop.store_gstin or 'N/A'}\n"
            f"Period: {start_date} to {end_date}\n\n"
            f"Total Records:  {total_records}"
            f" ({credit_note_count} credit note(s), {debit_note_count} debit note(s) applied)\n"
            f"Taxable Value:  Rs.{report.total_taxable_value:.2f}\n"
            f"CGST:           Rs.{report.total_cgst:.2f}\n"
            f"SGST:           Rs.{report.total_sgst:.2f}\n"
            f"IGST:           Rs.{report.total_igst:.2f}\n"
        )

        metrics_html = f"""
                        <tr>
                            <td style="color: #8A8272; width: 130px; padding-bottom: 6px;">Total Records</td>
                            <td style="font-weight: 600; color: #1A1A18; padding-bottom: 6px;">{total_records} ({credit_note_count} CN, {debit_note_count} DN)</td>
                        </tr>
                        <tr>
                            <td style="color: #8A8272; padding-bottom: 6px;">Taxable Value</td>
                            <td style="font-weight: 600; color: #1A1A18; padding-bottom: 6px;">₹{report.total_taxable_value:,.2f}</td>
                        </tr>
                        <tr>
                            <td style="color: #8A8272; padding-bottom: 6px;">CGST</td>
                            <td style="font-weight: 600; color: #0F6E56; padding-bottom: 6px;">₹{report.total_cgst:,.2f}</td>
                        </tr>
                        <tr>
                            <td style="color: #8A8272; padding-bottom: 6px;">SGST</td>
                            <td style="font-weight: 600; color: #0F6E56; padding-bottom: 6px;">₹{report.total_sgst:,.2f}</td>
                        </tr>
                        <tr>
                            <td style="color: #8A8272; padding-bottom: 6px;">IGST</td>
                            <td style="font-weight: 600; color: #0F6E56; padding-bottom: 6px;">₹{report.total_igst:,.2f}</td>
                        </tr>
"""

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

        metrics_html = f"""
                        <tr>
                            <td style="color: #8A8272; width: 130px; padding-bottom: 6px;">Total Invoices</td>
                            <td style="font-weight: 600; color: #1A1A18; padding-bottom: 6px;">{total_invoices}</td>
                        </tr>
                        <tr>
                            <td style="color: #8A8272; padding-bottom: 6px;">Taxable Value</td>
                            <td style="font-weight: 600; color: #1A1A18; padding-bottom: 6px;">₹{taxable:,.2f}</td>
                        </tr>
                        <tr>
                            <td style="color: #8A8272; padding-bottom: 6px;">ITC CGST</td>
                            <td style="font-weight: 600; color: #0F6E56; padding-bottom: 6px;">₹{report.total_itc_cgst:,.2f}</td>
                        </tr>
                        <tr>
                            <td style="color: #8A8272; padding-bottom: 6px;">ITC SGST</td>
                            <td style="font-weight: 600; color: #0F6E56; padding-bottom: 6px;">₹{report.total_itc_sgst:,.2f}</td>
                        </tr>
                        <tr>
                            <td style="color: #8A8272; padding-bottom: 6px;">ITC IGST</td>
                            <td style="font-weight: 600; color: #0F6E56; padding-bottom: 6px;">₹{report.total_itc_igst:,.2f}</td>
                        </tr>
"""

    else:
        body = f"GST Report for {start_date} to {end_date}\nShop: {shop.shop_name}"
        metrics_html = f"""
                        <tr>
                            <td style="color: #8A8272; width: 130px; padding-bottom: 6px;">Period</td>
                            <td style="font-weight: 600; color: #1A1A18; padding-bottom: 6px;">{start_date} to {end_date}</td>
                        </tr>
"""

    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{report_title} - ExPOS</title>
    <style>
        @font-face {{
            font-family: 'Marcellus';
            font-style: normal;
            font-weight: 400;
            font-display: swap;
            src: url('https://fonts.gstatic.com/s/marcellus/v14/wEO_EBrOk8hQLDvIAF8FUQ.ttf') format('truetype');
        }}
    </style>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Marcellus&display=swap" rel="stylesheet">
</head>
<body style="margin: 0; padding: 0; background-color: #FFFFFF; font-family: 'Google Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1A1A18; -webkit-font-smoothing: antialiased;">

    <!-- Hidden Preheader -->
    <div style="display:none !important; visibility:hidden; opacity:0; color:transparent; height:0; width:0; max-height:0; max-width:0; overflow:hidden; font-size:1px; line-height:1px;">
        GST Report for {shop.shop_name}: {report_title} ({start_date} to {end_date}). Ref: {gst_nonce}
    </div>

    <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #FFFFFF; padding: 36px 20px;">
        <tr>
            <td align="left" style="max-width: 540px; margin: 0 auto; display: block;">
                
                <!-- App Brand Header -->
                <div style="margin-bottom: 24px;">
                    <span style="font-family: 'Marcellus', Georgia, 'Times New Roman', serif; font-size: 24px; font-weight: 400; color: #1A1A18;">Ex</span><span style="font-family: 'Marcellus', Georgia, 'Times New Roman', serif; font-size: 24px; font-weight: 400; color: #B8895A;">POS</span>
                </div>

                <!-- Eyebrow -->
                <div style="font-family: 'Google Sans', -apple-system, BlinkMacSystemFont, sans-serif; font-size: 11px; font-weight: 600; color: #B8895A; text-transform: uppercase; letter-spacing: 2px; margin-bottom: 6px;">
                    GST ANALYTICS REPORT
                </div>

                <!-- Two-Tone Serif Page Heading -->
                <h1 style="margin: 0 0 12px 0; font-size: 24px; line-height: 1.3; font-weight: normal;">
                    <span style="font-family: Georgia, 'Times New Roman', serif; font-weight: 400; color: #1A1A18;">GST </span>
                    <span style="font-family: Georgia, 'Times New Roman', serif; font-style: italic; font-weight: 400; color: #0F6E56;">Summary</span>
                </h1>

                <!-- Subtitle / Greeting -->
                <p style="font-family: 'Google Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 14px; font-weight: 400; color: #8A8272; margin: 0 0 24px 0; line-height: 1.6;">
                    Hello <strong>{owner_name}</strong>,<br>
                    Here is your requested <strong>{report_title}</strong> for {shop.shop_name} covering {start_date} to {end_date}:
                </p>

                <!-- GST Report Details Card -->
                <div style="background-color: #FAF7F2; border: 1.5px solid #0F6E56; border-radius: 14px; padding: 22px 20px; margin-bottom: 24px;">
                    <div style="font-family: 'Google Sans', sans-serif; font-size: 11px; font-weight: 700; color: #0F6E56; text-transform: uppercase; letter-spacing: 1.5px; margin-bottom: 14px;">
                        REPORT TOTALS
                    </div>

                    <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="font-size: 13.5px; font-family: 'Google Sans', sans-serif; color: #1A1A18; line-height: 1.8;">
                        <tr>
                            <td style="color: #8A8272; width: 130px; padding-bottom: 6px;">Shop Name</td>
                            <td style="font-weight: 600; color: #1A1A18; padding-bottom: 6px;">{shop.shop_name}</td>
                        </tr>
                        <tr>
                            <td style="color: #8A8272; padding-bottom: 6px;">GSTIN</td>
                            <td style="font-weight: 600; color: #1A1A18; padding-bottom: 6px;">{shop.store_gstin or 'N/A'}</td>
                        </tr>
                        <tr>
                            <td style="color: #8A8272; padding-bottom: 6px;">Report Type</td>
                            <td style="font-weight: 600; color: #1A1A18; padding-bottom: 6px;">{report_title}</td>
                        </tr>
                        {metrics_html}
                    </table>

                    <div style="margin-top: 14px; padding-top: 14px; border-top: 1px solid #EBE4D5; text-align: left;">
                        <span style="display: inline-block; background-color: #E4F1EC; color: #0F6E56; font-size: 12px; font-weight: 600; padding: 6px 14px; border-radius: 20px;">
                            ✓ Verified System Report
                        </span>
                    </div>
                </div>

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
                    <div style="font-family: 'Marcellus', Georgia, 'Times New Roman', serif; font-size: 13px; font-weight: 400; color: #1A1A18; letter-spacing: 3px; text-transform: uppercase;">
                        SCALANCER
                    </div>
                </div>

            </td>
        </tr>
    </table>

    <!-- Nonce comment to prevent Gmail content trimming -->
    <!-- ref:{gst_nonce} -->
</body>
</html>
"""

    send_email(to_email=shop.email, subject=subject, body=body, html_body=html_body)