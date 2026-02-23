from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.database import get_db
from app.security import verify_token
from app.models.shop import Shop

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def get_current_shop(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    shop_id = verify_token(token)

    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=401, detail="Shop not found")

    return shop