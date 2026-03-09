from pydantic import BaseModel

class SaveTokenRequest(BaseModel):
    token: str