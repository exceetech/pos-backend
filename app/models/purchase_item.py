# models/purchase_item.py

from sqlalchemy import Column, Integer, String, Float, ForeignKey
from app.database import Base


class PurchaseItem(Base):
    __tablename__ = "purchase_items"

    id = Column(Integer, primary_key=True, index=True)
    purchase_id = Column(Integer, ForeignKey("purchases.id", ondelete="CASCADE"))

    shop_product_id = Column(Integer, nullable=True)

    product_name = Column(String, nullable=False)
    variant = Column(String, nullable=True)
    hsn_code = Column(String, nullable=True)

    quantity = Column(Float, nullable=False)
    unit = Column(String, nullable=True)

    taxable_amount = Column(Float, nullable=False)
    invoice_value = Column(Float, nullable=False)
    cost_price = Column(Float, nullable=False)

    # Purchase tax
    purchase_cgst_percentage = Column(Float, default=0.0)
    purchase_sgst_percentage = Column(Float, default=0.0)
    purchase_igst_percentage = Column(Float, default=0.0)

    purchase_cgst_amount = Column(Float, default=0.0)
    purchase_sgst_amount = Column(Float, default=0.0)
    purchase_igst_amount = Column(Float, default=0.0)

    # Sales tax
    sales_cgst_percentage = Column(Float, default=0.0)
    sales_sgst_percentage = Column(Float, default=0.0)
    sales_igst_percentage = Column(Float, default=0.0)