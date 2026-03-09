import firebase_admin
from firebase_admin import credentials, messaging

cred = credentials.Certificate("firebase-key.json")

firebase_admin.initialize_app(cred)


def send_notification(token, title, body):

    message = messaging.Message(
        notification=messaging.Notification(
            title=title,
            body=body
        ),
        token=token
    )

    messaging.send(message)


def send_broadcast(tokens, title, body):

    message = messaging.MulticastMessage(
        notification=messaging.Notification(
            title=title,
            body=body
        ),
        tokens=tokens
    )

    response = messaging.send_each_for_multicast(message)

    print("Success:", response.success_count)
    print("Failure:", response.failure_count)