import firebase_admin
from firebase_admin import credentials, messaging

# ✅ Initialize Firebase ONLY ONCE
cred = credentials.Certificate("app/firebase-key.json")

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)


# ================= SINGLE NOTIFICATION =================
def send_notification(token: str, title: str, body: str):

    print("📲 Sending PUSH to:", token)

    message = messaging.Message(
        data={   # ✅ IMPORTANT: use DATA
            "title": title,
            "body": body
        },
        token=token
    )

    response = messaging.send(message)

    print("✅ PUSH SENT:", response)


# ================= BROADCAST =================
def send_broadcast(tokens: list[str], title: str, body: str):

    if not tokens:
        print("❌ No tokens provided")
        return

    print("📢 Broadcasting to:", tokens)

    message = messaging.MulticastMessage(
        data={   # ✅ IMPORTANT: use DATA
            "title": title,
            "body": body
        },
        tokens=tokens
    )

    response = messaging.send_each_for_multicast(message)

    print("✅ Success:", response.success_count)
    print("❌ Failure:", response.failure_count)