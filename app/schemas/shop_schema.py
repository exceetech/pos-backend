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

class ShopSettingsResponse(BaseModel):
    shop_name: str
    store_address: str | None
    phone: str | None
    store_gstin: str | None


class ShopSettingsUpdate(BaseModel):
    shop_name: str
    store_address: str
    phone: str
    store_gstin: str
    
class ForgotPasswordRequest(BaseModel):
    email: EmailStr
