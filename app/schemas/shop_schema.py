from pydantic import BaseModel, EmailStr

class ShopRegister(BaseModel):
    shop_name: str
    owner_name: str
    email: EmailStr
    phone: str


class ShopLogin(BaseModel):
    email: EmailStr
    password: str

class ShopActivate(BaseModel):
    email: EmailStr
    temporary_password: str