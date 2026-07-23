from pydantic import BaseModel

class CreditAccountCreate(BaseModel):
    name: str
    phone: str


class CreditTransactionCreate(BaseModel):
    account_id: int
    amount: float
    type: str  # ADD / PAY / SETTLE / PURCHASE_CREDIT / PURCHASE_RETURN / WRITE_OFF / REFUND / SALE_RETURN / BILL_CANCEL / DEBIT_NOTE
    reference_invoice: str = None
    # Idempotency key from the client (e.g. "CN:12", "PBUY:5"). Optional so
    # older app builds without it still sync; the server just can't dedupe
    # those calls until the app is updated to send it.
    source_doc: str = None