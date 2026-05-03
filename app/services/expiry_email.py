
from app.services.email_service import send_email


def send_expiry_email(shop, days_left: int):

    subject = "⚠️ Subscription Expiry Alert - ExPOS"

    if days_left <= 0:
        body = f"""
Hello {shop.owner_name},

🚫 Your subscription for ExPOS has expired.

━━━━━━━━━━━━━━━━━━━━━━━
⚠️ What This Means
━━━━━━━━━━━━━━━━━━━━━━━
• Billing features may be restricted  
• Reports & premium features are disabled  
• Please renew immediately to continue using all services  

━━━━━━━━━━━━━━━━━━━━━━━
🔄 Action Required
━━━━━━━━━━━━━━━━━━━━━━━
Kindly renew your subscription as soon as possible to avoid any disruption.

If you have already made the payment, please contact admin for activation.

━━━━━━━━━━━━━━━━━━━━━━━
🙏 Need Help?
━━━━━━━━━━━━━━━━━━━━━━━
Contact our support team anytime for assistance.

Regards,  
eXCee Team
📧 Support: support@expos.com
"""
    else:
        body = f"""
Hello {shop.owner_name},

⏳ Your ExPOS subscription is nearing expiry.

━━━━━━━━━━━━━━━━━━━━━━━
📅 Days Remaining: {days_left} day(s)
━━━━━━━━━━━━━━━━━━━━━━━

We recommend renewing your subscription early to avoid any interruption in your billing operations.

━━━━━━━━━━━━━━━━━━━━━━━
🔔 Reminder
━━━━━━━━━━━━━━━━━━━━━━━
You will continue to receive alerts as your expiry date approaches.

━━━━━━━━━━━━━━━━━━━━━━━
🙏 Need Help?
━━━━━━━━━━━━━━━━━━━━━━━
If you have already completed payment, please contact admin for activation.

Regards,  
eXCee Team
📧 Support: support@expos.com
"""

    send_email(
        to_email=shop.email,
        subject=subject,
        body=body
    )