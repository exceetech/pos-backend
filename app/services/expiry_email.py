import time
from app.services.email_service import send_email


def send_expiry_email(shop, days_left: int, is_trial: bool = False):
    """
    Sends trial / subscription expiry emails formatted with the ExPOS HTML email template.
    """
    owner_name = getattr(shop, "owner_name", "Merchant") or "Merchant"
    shop_name = getattr(shop, "shop_name", "your business") or "your business"
    expiry_nonce = f"{int(time.time())}-exp"

    if is_trial:
        if days_left <= 0:
            subject = "Your free trial has ended - ExPOS"
            eyebrow = "TRIAL EXPIRED"
            heading_first = "Trial Has "
            heading_accent = "Ended"
            subtitle = f"Hello <strong>{owner_name}</strong>,<br>Your ExPOS free trial for <strong>{shop_name}</strong> has ended."
            badge_text = "⚠️ Free Trial Expired"
            badge_bg = "#FCE8E6"
            badge_color = "#C5221F"
            details_html = f"""
                        <tr>
                            <td style="color: #8A8272; width: 110px; padding-bottom: 6px;">Shop Name</td>
                            <td style="font-weight: 600; color: #1A1A18; padding-bottom: 6px;">{shop_name}</td>
                        </tr>
                        <tr>
                            <td style="color: #8A8272; padding-bottom: 6px;">Status</td>
                            <td style="font-weight: 600; color: #C5221F; padding-bottom: 6px;">Trial Expired</td>
                        </tr>
                        <tr>
                            <td style="color: #8A8272; padding-bottom: 6px;">Impact</td>
                            <td style="font-weight: 500; color: #1A1A18; padding-bottom: 6px;">Premium features locked (everyday billing unaffected)</td>
                        </tr>
"""
            next_steps_title = "🔄 Keep Premium Going"
            next_steps_html = """
                        <tr>
                            <td style="vertical-align: top; width: 22px; color: #0F6E56; font-weight: bold;">1.</td>
                            <td style="padding-bottom: 6px;">Open the ExPOS app on your mobile device.</td>
                        </tr>
                        <tr>
                            <td style="vertical-align: top; width: 22px; color: #0F6E56; font-weight: bold;">2.</td>
                            <td>Navigate to Subscription to pick up right where you left off.</td>
                        </tr>
"""
        else:
            subject = "🎉 Your free trial is ending - ExPOS"
            eyebrow = "TRIAL EXPIRY WARNING"
            heading_first = "Trial Ending "
            heading_accent = "Soon"
            subtitle = f"Hello <strong>{owner_name}</strong>,<br>Your ExPOS free trial for <strong>{shop_name}</strong> will end in <strong>{days_left} day(s)</strong>."
            badge_text = f"⏳ {days_left} Day(s) Remaining"
            badge_bg = "#FEF3D6"
            badge_color = "#8A6526"
            details_html = f"""
                        <tr>
                            <td style="color: #8A8272; width: 110px; padding-bottom: 6px;">Shop Name</td>
                            <td style="font-weight: 600; color: #1A1A18; padding-bottom: 6px;">{shop_name}</td>
                        </tr>
                        <tr>
                            <td style="color: #8A8272; padding-bottom: 6px;">Days Left</td>
                            <td style="font-weight: 600; color: #8A6526; padding-bottom: 6px;">{days_left} day(s)</td>
                        </tr>
"""
            next_steps_title = "✨ Stay Premium"
            next_steps_html = """
                        <tr>
                            <td style="vertical-align: top; width: 22px; color: #0F6E56; font-weight: bold;">•</td>
                            <td style="padding-bottom: 6px;">Subscribe before your trial ends for uninterrupted GST reports & profit analytics.</td>
                        </tr>
"""

    else:
        if days_left <= 0:
            subject = "⚠️ Subscription Expiry Alert - ExPOS"
            eyebrow = "SUBSCRIPTION EXPIRED"
            heading_first = "Subscription Has "
            heading_accent = "Expired"
            subtitle = f"Hello <strong>{owner_name}</strong>,<br>Your subscription for <strong>{shop_name}</strong> has expired."
            badge_text = "🚫 Subscription Expired"
            badge_bg = "#FCE8E6"
            badge_color = "#C5221F"
            details_html = f"""
                        <tr>
                            <td style="color: #8A8272; width: 110px; padding-bottom: 6px;">Shop Name</td>
                            <td style="font-weight: 600; color: #1A1A18; padding-bottom: 6px;">{shop_name}</td>
                        </tr>
                        <tr>
                            <td style="color: #8A8272; padding-bottom: 6px;">Status</td>
                            <td style="font-weight: 600; color: #C5221F; padding-bottom: 6px;">Expired</td>
                        </tr>
"""
            next_steps_title = "🔄 Easy Instant Renewal"
            next_steps_html = """
                        <tr>
                            <td style="vertical-align: top; width: 22px; color: #0F6E56; font-weight: bold;">1.</td>
                            <td style="padding-bottom: 6px;">Open the <strong>ExPOS App</strong> on your mobile device.</td>
                        </tr>
                        <tr>
                            <td style="vertical-align: top; width: 22px; color: #0F6E56; font-weight: bold;">2.</td>
                            <td>Navigate to <strong>Subscription</strong> screen and select your plan to reactivate instantly online.</td>
                        </tr>
"""
        else:
            subject = "⚠️ Subscription Expiry Alert - ExPOS"
            eyebrow = "SUBSCRIPTION EXPIRY ALERT"
            heading_first = "Subscription Expiry "
            heading_accent = "Warning"
            subtitle = f"Hello <strong>{owner_name}</strong>,<br>Your subscription for <strong>{shop_name}</strong> is nearing expiry."
            badge_text = f"⏳ {days_left} Day(s) Remaining"
            badge_bg = "#FEF3D6"
            badge_color = "#8A6526"
            details_html = f"""
                        <tr>
                            <td style="color: #8A8272; width: 110px; padding-bottom: 6px;">Shop Name</td>
                            <td style="font-weight: 600; color: #1A1A18; padding-bottom: 6px;">{shop_name}</td>
                        </tr>
                        <tr>
                            <td style="color: #8A8272; padding-bottom: 6px;">Time Left</td>
                            <td style="font-weight: 600; color: #8A6526; padding-bottom: 6px;">{days_left} day(s)</td>
                        </tr>
"""
            next_steps_title = "🔔 Renewal Reminder"
            next_steps_html = """
                        <tr>
                            <td style="vertical-align: top; width: 22px; color: #0F6E56; font-weight: bold;">•</td>
                            <td style="padding-bottom: 6px;">Renew early to avoid any interruption in your billing operations.</td>
                        </tr>
"""

    plain_body = f"""Hello {owner_name},

{subject}

Shop: {shop_name}
Days Remaining: {days_left if days_left > 0 else 'Expired'}

Please renew your subscription to maintain uninterrupted services.

Regards,
ExPOS Team
[Ref: {expiry_nonce}]
"""

    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{subject}</title>
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
        {subject} for {shop_name}. Ref: {expiry_nonce}
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
                    {eyebrow}
                </div>

                <!-- Two-Tone Serif Page Heading -->
                <h1 style="margin: 0 0 12px 0; font-size: 24px; line-height: 1.3; font-weight: normal;">
                    <span style="font-family: Georgia, 'Times New Roman', serif; font-weight: 400; color: #1A1A18;">{heading_first}</span>
                    <span style="font-family: Georgia, 'Times New Roman', serif; font-style: italic; font-weight: 400; color: #0F6E56;">{heading_accent}</span>
                </h1>

                <!-- Subtitle / Greeting -->
                <p style="font-family: 'Google Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 14px; font-weight: 400; color: #8A8272; margin: 0 0 24px 0; line-height: 1.6;">
                    {subtitle}
                </p>

                <!-- Expiry Summary Card -->
                <div style="background-color: #FAF7F2; border: 1.5px solid #0F6E56; border-radius: 14px; padding: 22px 20px; margin-bottom: 24px;">
                    <div style="font-family: 'Google Sans', sans-serif; font-size: 11px; font-weight: 700; color: #0F6E56; text-transform: uppercase; letter-spacing: 1.5px; margin-bottom: 14px;">
                        SUBSCRIPTION STATUS
                    </div>

                    <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="font-size: 13.5px; font-family: 'Google Sans', sans-serif; color: #1A1A18; line-height: 1.8;">
                        {details_html}
                    </table>

                    <div style="margin-top: 14px; padding-top: 14px; border-top: 1px solid #EBE4D5; text-align: left;">
                        <span style="display: inline-block; background-color: {badge_bg}; color: {badge_color}; font-size: 12px; font-weight: 600; padding: 6px 14px; border-radius: 20px;">
                            {badge_text}
                        </span>
                    </div>
                </div>

                <!-- Next Steps Section -->
                <div style="margin-bottom: 28px;">
                    <div style="font-family: 'Google Sans', sans-serif; font-size: 13px; font-weight: 700; color: #1A1A18; margin-bottom: 12px;">
                        {next_steps_title}
                    </div>

                    <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="font-size: 13px; font-family: 'Google Sans', sans-serif; color: #6E6759; line-height: 1.7;">
                        {next_steps_html}
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
    <!-- ref:{expiry_nonce} -->
</body>
</html>
"""

    send_email(to_email=shop.email, subject=subject, body=plain_body, html_body=html_body)