from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, UniqueConstraint
from app.database import Base


class ShopCategory(Base):
    """
    Shop-defined custom product categories (v40).

    Predefined categories live on the client; this table only stores the
    custom ones an owner typed, so they sync across that owner's devices.
    Products carry the category as a plain string on `shop_products`, so
    this table is a convenience/lookup layer with no FK from products.
    """
    __tablename__ = "shop_categories"
    __table_args__ = (
        UniqueConstraint("shop_id", "name", name="uix_shop_category_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
