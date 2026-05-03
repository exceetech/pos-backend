from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.shop import Shop
from app.firebase_service import send_broadcast

router = APIRouter()

@router.post("/admin/broadcast")
def broadcast_notification(title: str, body: str, db: Session = Depends(get_db)):

    shops = db.query(Shop).all()

    tokens = [shop.fcm_token for shop in shops if shop.fcm_token]

    send_broadcast(tokens, title, body)

    return {"message": "Notification sent"}