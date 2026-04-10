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
    shop_name: str | None
    store_address: str | None
    phone: str | None
    store_gstin: str | None


class ShopSettingsUpdate(BaseModel):
    shop_name: str | None
    store_address: str | None
    phone: str | None
    store_gstin: str | None

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    is_first_login: bool
    shop_id: int
