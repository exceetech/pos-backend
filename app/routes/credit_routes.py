from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.credit import CreditAccount, CreditTransaction
from app.schemas.credit_schema import CreditAccountCreate, CreditTransactionCreate
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from app.security import decode_token

router = APIRouter(prefix="/credit", tags=["Credit"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def get_current_shop_id(token: str = Depends(oauth2_scheme)):

    payload = decode_token(token)
    shop_id = payload.get("shop_id")

    if shop_id is None:
        raise HTTPException(status_code=401, detail="Invalid token")

    return shop_id

# ================= CREATE ACCOUNT =================
@router.post("/account")
def create_account(
    data: CreditAccountCreate,
    db: Session = Depends(get_db),
    shop_id: int = Depends(get_current_shop_id)
):

    existing = db.query(CreditAccount).filter(
        CreditAccount.phone == data.phone,
        CreditAccount.shop_id == shop_id
    ).first()

    if existing:

        # 🔥 CASE 1: RESTORE ACCOUNT
        if not existing.is_active:
            existing.is_active = True

            # ✅ update name if different
            if data.name and data.name != existing.name:
                existing.name = data.name

            db.commit()
            db.refresh(existing)

            return {
                "id": existing.id,
                "name": existing.name,
                "phone": existing.phone,
                "due_amount": existing.due_amount,
                "restored": True   # 🔥 IMPORTANT FLAG
            }

        # 🔥 CASE 2: ALREADY EXISTS
        raise HTTPException(
            status_code=400,
            detail="Account already exists"
        )

    # 🔥 CASE 3: CREATE NEW
    account = CreditAccount(
        name=data.name,
        phone=data.phone,
        due_amount=0.0,
        is_active=True,
        shop_id=shop_id
    )

    db.add(account)
    db.commit()
    db.refresh(account)

    return {
        "id": account.id,
        "name": account.name,
        "phone": account.phone,
        "due_amount": account.due_amount,
        "restored": False
    }

# ================= GET ACCOUNTS =================
@router.get("/accounts")
def get_accounts(
    db: Session = Depends(get_db),
    shop_id: int = Depends(get_current_shop_id)
):

    return db.query(CreditAccount).filter(
        CreditAccount.shop_id == shop_id,
        CreditAccount.is_active.is_(True)
    ).all()


# ================= SYNC =================
@router.post("/sync")
def sync_credit(
    data: CreditTransactionCreate,
    db: Session = Depends(get_db),
    shop_id: int = Depends(get_current_shop_id)
):

    account = db.query(CreditAccount).filter(
        CreditAccount.id == data.account_id,
        CreditAccount.shop_id == shop_id,
        CreditAccount.is_active.is_(True)
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if data.type == "ADD":
        account.due_amount += data.amount
    elif data.type == "PAY":
        account.due_amount -= data.amount
    elif data.type == "SETTLE":
        account.due_amount = 0
    else:
        raise HTTPException(status_code=400, detail="Invalid type")

    txn = CreditTransaction(
        account_id=data.account_id,
        shop_id=shop_id,
        amount=data.amount,
        type=data.type
    )

    db.add(txn)
    db.commit()

    return {"status": "success"}


# ================= SEARCH =================
@router.get("/search")
def search_accounts(
    query: str,
    db: Session = Depends(get_db),
    shop_id: int = Depends(get_current_shop_id)
):

    return db.query(CreditAccount).filter(
        CreditAccount.shop_id == shop_id,
        CreditAccount.is_active.is_(True),
        (CreditAccount.name.ilike(f"%{query}%") |
         CreditAccount.phone.ilike(f"%{query}%"))
    ).all()


# ================= TRANSACTIONS =================
@router.get("/transactions/{account_id}")
def get_transactions(
    account_id: int,
    db: Session = Depends(get_db),
    shop_id: int = Depends(get_current_shop_id)
):

    account = db.query(CreditAccount).filter(
        CreditAccount.id == account_id,
        CreditAccount.shop_id == shop_id
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    return db.query(CreditTransaction)\
        .filter(CreditTransaction.account_id == account_id, CreditTransaction.shop_id == shop_id)\
        .order_by(CreditTransaction.id.desc())\
        .all()


# ================= SOFT DELETE =================
@router.patch("/account/{account_id}/deactivate")
def deactivate_account(
    account_id: int,
    db: Session = Depends(get_db),
    shop_id: int = Depends(get_current_shop_id)
):

    account = db.query(CreditAccount).filter(
        CreditAccount.id == account_id,
        CreditAccount.shop_id == shop_id,
        CreditAccount.is_active.is_(True)
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if abs(account.due_amount) > 0.01:
        raise HTTPException(
            status_code=400,
            detail="Account must be settled before deleting"
        )

    account.is_active = False
    db.commit()

    return {"message": "Account deactivated successfully"}


# ================= RESET =================
@router.patch("/reset")
def reset_credit(
    db: Session = Depends(get_db),
    shop_id: int = Depends(get_current_shop_id)
):

    db.query(CreditAccount).filter(
        CreditAccount.shop_id == shop_id
    ).update({
        CreditAccount.is_active: False
    })

    db.commit()

    return {
        "status": "success",
        "message": f"Credit reset for shop {shop_id}"
    }