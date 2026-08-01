
from app.services.email_service import send_email


def send_expiry_email(shop, days_left: int, is_trial: bool = False):
    """
    is_trial distinguishes trial-ending messaging from paid-subscription
    -expiry messaging (plan §4.6) — a trial ending isn't a billing
    disruption the way a lapsed paid plan is, so it shouldn't read like
    one ("contact admin for activation" makes no sense for a trial that
    was never paid). Callers pass this based on the Subscription's
    status BEFORE it flips to "expired" — see expiry_service.py.
    """

    subject = "🎉 Your free trial is ending - ExPOS" if is_trial and days_left > 0 else \
              "Your free trial has ended - ExPOS" if is_trial else \
              "⚠️ Subscription Expiry Alert - ExPOS"

    if is_trial:
        if days_left <= 0:
            body = f"""
Hello {shop.owner_name},

Your ExPOS free trial has ended.

━━━━━━━━━━━━━━━━━━━━━━━
⚠️ What This Means
━━━━━━━━━━━━━━━━━━━━━━━
• Premium features (GST reports, profit insights, AI insights) are now locked
• Your billing data and everyday billing tools are unaffected

━━━━━━━━━━━━━━━━━━━━━━━
🔄 Keep Premium Going
━━━━━━━━━━━━━━━━━━━━━━━
Subscribe any time from the Subscription screen in the app to pick up right where you left off.

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

⏳ Your ExPOS free trial is ending soon.

━━━━━━━━━━━━━━━━━━━━━━━
📅 Days Remaining: {days_left} day(s)
━━━━━━━━━━━━━━━━━━━━━━━

Subscribe before your trial ends to keep uninterrupted access to GST reports, profit insights, and AI insights.

━━━━━━━━━━━━━━━━━━━━━━━
🙏 Need Help?
━━━━━━━━━━━━━━━━━━━━━━━
If you have any questions, contact our support team anytime.

Regards,
eXCee Team
📧 Support: support@expos.com
"""
        send_email(to_email=shop.email, subject=subject, body=body)
        return

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