from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional

from app.database import get_db
from app.models.customer import Customer
from app.security import decode_token

router = APIRouter(prefix="/customers", tags=["Customers"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def get_current_shop_id(token: str = Depends(oauth2_scheme)):
    payload = decode_token(token)
    shop_id = payload.get("shop_id")
    if shop_id is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    return shop_id


class CustomerDto(BaseModel):
    local_id: int
    phone: str
    name: str = ""
    customer_type: str = "B2C"
    business_name: Optional[str] = None
    gstin: Optional[str] = None
    state: Optional[str] = None
    state_code: Optional[str] = None
    updated_at: int = 0


class CustomerSyncRequest(BaseModel):
    customers: List[CustomerDto]


class CustomerSyncResponse(BaseModel):
    success_count: int = 0
    customer_id_map: dict = {}
    message: Optional[str] = None


class CustomerRemote(BaseModel):
    id: int
    phone: str
    name: Optional[str] = None
    customer_type: Optional[str] = "B2C"
    business_name: Optional[str] = None
    gstin: Optional[str] = None
    state: Optional[str] = None
    state_code: Optional[str] = None
    updated_at: int = 0


class CustomerLookupResponse(BaseModel):
    found: bool = False
    customer: Optional[CustomerRemote] = None


class CustomerListResponse(BaseModel):
    customers: List[CustomerRemote] = []


class CustomerAccountRequest(BaseModel):
    phone: str
    name: str = ""
    customer_type: str = "B2C"
    business_name: Optional[str] = None
    gstin: Optional[str] = None
    state: Optional[str] = None
    state_code: Optional[str] = None
    updated_at: int = 0


def _to_remote(c: Customer) -> CustomerRemote:
    return CustomerRemote(
        id=c.id,
        phone=c.phone,
        name=c.name,
        customer_type=c.customer_type,
        business_name=c.business_name,
        gstin=c.gstin,
        state=c.state,
        state_code=c.state_code,
        updated_at=c.updated_at_ms or 0,
    )


def _apply_upsert(db: Session, shop_id: int, c) -> Customer:
    """
    Upsert one customer by (shop_id, phone, customer_type), last-write-wins.
    B2C and B2B are kept as separate rows under the same phone.
    """
    ph = (c.phone or "").strip()
    ctype = (c.customer_type or "B2C")
    existing = (
        db.query(Customer)
        .filter(
            Customer.shop_id == shop_id,
            Customer.phone == ph,
            Customer.customer_type == ctype,
        )
        .first()
    )
    if existing:
        if (c.updated_at or 0) >= (existing.updated_at_ms or 0):
            existing.name = c.name or existing.name
            # Blank fields don't overwrite saved values.
            existing.business_name = c.business_name if c.business_name else existing.business_name
            existing.gstin = c.gstin if c.gstin else existing.gstin
            existing.state = c.state if c.state else existing.state
            existing.state_code = c.state_code if c.state_code else existing.state_code
            existing.updated_at_ms = c.updated_at or existing.updated_at_ms
            existing.is_active = True
        return existing
    row = Customer(
        shop_id=shop_id,
        phone=ph,
        name=c.name or "",
        customer_type=ctype,
        business_name=c.business_name,
        gstin=c.gstin,
        state=c.state,
        state_code=c.state_code,
        updated_at_ms=c.updated_at or 0,
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


@router.get("/by-phone", response_model=CustomerLookupResponse)
def get_customer_by_phone(
    phone: str,
    type: Optional[str] = None,
    db: Session = Depends(get_db),
    shop_id: int = Depends(get_current_shop_id),
):
    ph = (phone or "").strip()
    if not ph:
        return CustomerLookupResponse(found=False)
    q = db.query(Customer).filter(
        Customer.shop_id == shop_id,
        Customer.phone == ph,
        Customer.is_active == True,  # noqa: E712
    )
    # When a type is given, return that specific (phone, type) record;
    # otherwise return the most recently updated record for the phone.
    if type:
        q = q.filter(Customer.customer_type == type)
    row = q.order_by(Customer.updated_at_ms.desc()).first()
    if not row:
        return CustomerLookupResponse(found=False)
    return CustomerLookupResponse(found=True, customer=_to_remote(row))


@router.get("", response_model=CustomerListResponse)
def list_customers(
    db: Session = Depends(get_db),
    shop_id: int = Depends(get_current_shop_id),
):
    rows = (
        db.query(Customer)
        .filter(Customer.shop_id == shop_id, Customer.is_active == True)  # noqa: E712
        .all()
    )
    return CustomerListResponse(customers=[_to_remote(r) for r in rows])


@router.post("/sync", response_model=CustomerSyncResponse)
def sync_customers(
    data: CustomerSyncRequest,
    db: Session = Depends(get_db),
    shop_id: int = Depends(get_current_shop_id),
):
    id_map: dict = {}
    count = 0
    for c in data.customers:
        if not (c.phone or "").strip():
            continue
        row = _apply_upsert(db, shop_id, c)
        id_map[str(c.local_id)] = row.id
        count += 1
    db.commit()
    return CustomerSyncResponse(success_count=count, customer_id_map=id_map)


@router.post("/account", response_model=CustomerRemote)
def upsert_customer_account(
    data: CustomerAccountRequest,
    db: Session = Depends(get_db),
    shop_id: int = Depends(get_current_shop_id),
):
    if not (data.phone or "").strip():
        raise HTTPException(status_code=400, detail="phone is required")
    row = _apply_upsert(db, shop_id, data)
    db.commit()
    db.refresh(row)
    return _to_remote(row)
