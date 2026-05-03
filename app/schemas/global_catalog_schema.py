from pydantic import BaseModel


class VariantResponse(BaseModel):
    id: int
    variant_name: str
    unit: str

    class Config:
        from_attributes = True


class HsnResponse(BaseModel):
    hsn_code: str

    class Config:
        from_attributes = True