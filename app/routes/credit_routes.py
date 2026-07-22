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

    # ── SIGN CONVENTION — DO NOT PUT PAY BACK WITH PURCHASE_RETURN ───────
    #
    #   ADD / PURCHASE_CREDIT  client sends POSITIVE  → debt goes UP
    #   PURCHASE_RETURN        client sends NEGATIVE  → adding it lowers debt
    #   PAY                    client sends POSITIVE  → debt must come DOWN
    #
    # PAY is the ONLY type the client sends unsigned, so it is the only one
    # that subtracts. Sharing a branch with PURCHASE_RETURN and adding meant
    # every payment moved the balance the wrong way: the app subtracted it
    # while the server added it. Pay ₹5,000 on a zero balance and the device
    # held −5,000 while the server held +5,000; the next pull copied the
    # server's figure down, so billing ₹100 afterwards showed ₹5,100 owing
    # with the advance wiped, instead of ₹4,900 in credit.
    # Amounts arrive as magnitudes for every type except PURCHASE_RETURN, which
    # is signed negative by the client. Enforced here rather than trusted, so a
    # malformed request can't invert a balance.
    if data.type in ("ADD", "PURCHASE_CREDIT", "PAY", "WRITE_OFF", "REFUND",
                     "SALE_RETURN", "BILL_CANCEL", "DEBIT_NOTE"):
        if data.amount <= 0:
            raise HTTPException(
                status_code=400,
                detail=f"{data.type} amount must be greater than 0"
            )
    # PURCHASE_RETURN is sign-agnostic on purpose. Older clients sent it as a
    # NEGATIVE amount (added to lower the debt); the current client sends a
    # POSITIVE magnitude (the shared adjustment core normalises every type to a
    # magnitude and carries direction in the type). Both must lower what is
    # owed to the supplier, so it is applied as -abs() below and not validated
    # for sign here — validating either way would reject one of the two clients.

    if data.type == "ADD" or data.type == "PURCHASE_CREDIT":
        account.due_amount += data.amount
    elif data.type == "PAY":
        account.due_amount -= data.amount
    elif data.type == "PURCHASE_RETURN":
        # Always lowers the payable, whichever sign the client used.
        account.due_amount -= abs(data.amount)

    # WRITE_OFF and REFUND replace the old catch-all SETTLE. One type meaning
    # two opposite events — debt forgiven vs money handed back — is what forced
    # every reader to reconstruct the meaning by replaying the ledger, and what
    # let a refund be counted as if it were a sale.
    #
    #   WRITE_OFF  debt forgiven, no cash moved
    #   REFUND     the customer's advance handed back, cash left the shop
    #
    # Both CLOSE the account, so both set the balance to zero rather than
    # subtracting. That is deliberate: settling means "this account is now
    # square", and an absolute instruction re-synchronises a device and server
    # that have drifted apart. Applying them as deltas left any drift in place,
    # which mattered while balances damaged by the old PAY bug were still
    # circulating.
    #
    # `amount` is still stored, and is what the ledger and reports read to say
    # how much was written off or handed back.
    elif data.type in ("WRITE_OFF", "REFUND"):
        account.due_amount = 0

    # Bill adjustments from the app, all arriving as positive magnitudes
    # (validated above). The client has already clamped each to what the bill
    # still had on credit, so the server just applies the delta — the same
    # trust model as PAY.
    #
    #   DEBIT_NOTE   an extra charge on a credit bill    → debt goes UP
    #   SALE_RETURN  a credit note put back on the bill  → debt comes DOWN
    #   BILL_CANCEL  a cancelled credit bill             → debt comes DOWN
    elif data.type == "DEBIT_NOTE":
        account.due_amount += data.amount
    elif data.type in ("SALE_RETURN", "BILL_CANCEL"):
        account.due_amount -= data.amount

    # Still accepted so older app builds keep working through the rollover.
    # Clients on this version no longer send it.
    elif data.type == "SETTLE":
        account.due_amount = 0
    else:
        raise HTTPException(status_code=400, detail="Invalid type")

    txn = CreditTransaction(
        account_id=data.account_id,
        shop_id=shop_id,
        amount=data.amount,
        type=data.type,
        reference_invoice=data.reference_invoice
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