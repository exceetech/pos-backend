from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.credit import CreditAccount, CreditTransaction
from app.schemas.credit_schema import CreditAccountCreate, CreditTransactionCreate

router = APIRouter(prefix="/credit", tags=["Credit"])

@router.post("/account")
def create_account(data: CreditAccountCreate, db: Session = Depends(get_db)):

    # prevent duplicate phone
    existing = db.query(CreditAccount).filter(
        CreditAccount.phone == data.phone
    ).first()

    if existing:
        return existing

    account = CreditAccount(
        name=data.name,
        phone=data.phone,
        due_amount=0.0
    )

    db.add(account)
    db.commit()
    db.refresh(account)

    return account

@router.get("/accounts")
def get_accounts(db: Session = Depends(get_db)):

    return db.query(CreditAccount).all()

@router.post("/sync")
def sync_credit(data: CreditTransactionCreate, db: Session = Depends(get_db)):

    account = db.query(CreditAccount).filter(
        CreditAccount.id == data.account_id
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    # 🔥 APPLY LOGIC
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
        amount=data.amount,
        type=data.type
    )

    db.add(txn)
    db.commit()

    return {"status": "success"}

@router.get("/search")
def search_accounts(query: str, db: Session = Depends(get_db)):

    return db.query(CreditAccount).filter(
        CreditAccount.name.ilike(f"%{query}%") |
        CreditAccount.phone.ilike(f"%{query}%")
    ).all()

@router.get("/transactions/{account_id}")
def get_transactions(account_id: int, db: Session = Depends(get_db)):
    return db.query(CreditTransaction)\
        .filter(CreditTransaction.account_id == account_id)\
        .order_by(CreditTransaction.id.desc())\
        .all()