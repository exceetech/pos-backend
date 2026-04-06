from pydantic import BaseModel

class CreditAccountCreate(BaseModel):
    name: str
    phone: str


class CreditTransactionCreate(BaseModel):
    account_id: int
    amount: float
    type: str  # ADD / PAY / SETTLE