import asyncio
from app.core.config import mail_config
from fastapi_mail import FastMail, MessageSchema

async def main():
    fm = FastMail(mail_config)
    # We won't actually send, just see if we can connect without cert errors
    # Wait, testing connection alone isn't exposed easily on FastMail.
    # But we can try a dummy send.
    msg = MessageSchema(
        subject="Test",
        recipients=["adeeb@example.com"],
        body="Test",
        subtype="plain"
    )
    try:
        await fm.send_message(msg)
    except Exception as e:
        print(f"Exception: {type(e).__name__}: {e}")

asyncio.run(main())
