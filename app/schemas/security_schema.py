from pydantic import BaseModel

class ChangePasswordRequest(BaseModel):
    new_password: str