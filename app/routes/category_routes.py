from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional

from app.database import get_db
from app.models.shop_category import ShopCategory
# Report 5 fix: this file used to define its own local get_current_shop_id
# — a thinner duplicate that skipped the `scope` check (and every other
# check) that the real app.dependencies.get_current_shop_id has. That meant
# a password-reset-scoped token could still authenticate here even after
# the scope check was added elsewhere, because this was different code that
# happened to look similar. Using the shared dependency means any future
# fix to it reaches this file automatically.
from app.dependencies import get_current_shop_id

router = APIRouter(prefix="/categories", tags=["Categories"])


class CategoryDto(BaseModel):
    local_id: int
    name: str


class CategorySyncRequest(BaseModel):
    categories: List[CategoryDto]


class CategorySyncResponse(BaseModel):
    success_count: int = 0
    category_id_map: dict = {}
    message: Optional[str] = None


class CategoryItem(BaseModel):
    id: int
    name: str


class CategoryListResponse(BaseModel):
    categories: List[CategoryItem] = []


@router.post("/sync", response_model=CategorySyncResponse)
def sync_categories(
    data: CategorySyncRequest,
    db: Session = Depends(get_db),
    shop_id: int = Depends(get_current_shop_id),
):
    id_map: dict = {}
    count = 0
    for c in data.categories:
        name = (c.name or "").strip()
        if not name:
            continue
        existing = (
            db.query(ShopCategory)
            .filter(ShopCategory.shop_id == shop_id, ShopCategory.name == name)
            .first()
        )
        if existing:
            if not existing.is_active:
                existing.is_active = True
            id_map[str(c.local_id)] = existing.id
        else:
            row = ShopCategory(shop_id=shop_id, name=name, is_active=True)
            db.add(row)
            db.flush()
            id_map[str(c.local_id)] = row.id
        count += 1
    db.commit()
    return CategorySyncResponse(success_count=count, category_id_map=id_map)


@router.get("", response_model=CategoryListResponse)
def list_categories(
    db: Session = Depends(get_db),
    shop_id: int = Depends(get_current_shop_id),
):
    rows = (
        db.query(ShopCategory)
        .filter(ShopCategory.shop_id == shop_id, ShopCategory.is_active == True)  # noqa: E712
        .order_by(ShopCategory.name.asc())
        .all()
    )
    return CategoryListResponse(
        categories=[CategoryItem(id=r.id, name=r.name) for r in rows]
    )
