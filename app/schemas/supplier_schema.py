from pydantic import BaseModel
from typing import List, Optional, Dict


class SupplierDto(BaseModel):
    """One supplier as pushed by the Android client."""
    local_id: int
    name: str
    gstin: Optional[str] = None
    state: Optional[str] = None
    state_code: Optional[str] = None
    last_used_at: int = 0
    updated_at: int = 0


class SupplierSyncRequest(BaseModel):
    suppliers: List[SupplierDto]


class SupplierSyncResponse(BaseModel):
    success_count: int = 0
    # local_id (as a string key, because JSON object keys are strings) -> server id
    supplier_id_map: Dict[str, int] = {}
    message: Optional[str] = None


class SupplierRemote(BaseModel):
    id: int
    name: str
    gstin: Optional[str] = None
    state: Optional[str] = None
    state_code: Optional[str] = None
    last_used_at: int = 0
    updated_at: int = 0

    class Config:
        # from_attributes only — this project is on Pydantic v2, where
        # `orm_mode` is the removed v1 spelling. Matches the pattern the
        # other schemas here use.
        from_attributes = True


class SupplierListResponse(BaseModel):
    suppliers: List[SupplierRemote] = []


class SupplierLookupResponse(BaseModel):
    found: bool = False
    supplier: Optional[SupplierRemote] = None


class SupplierMatchResponse(BaseModel):
    """Plural by design — a trade name can belong to several suppliers."""
    suppliers: List[SupplierRemote] = []


class SupplierAccountRequest(BaseModel):
    name: str = ""
    gstin: Optional[str] = None
    state: Optional[str] = None
    state_code: Optional[str] = None
    last_used_at: int = 0
    updated_at: int = 0
