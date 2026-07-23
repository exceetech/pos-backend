from .bill import Bill
from .bill_items import BillItem
from .billing_settings import BillingSettings
from .credit import CreditAccount, CreditTransaction
from .global_products import GlobalProduct
from .inventory import Inventory
from .inventory_log import InventoryLog
from .shop import Shop
from .shop_products import ShopProduct
from .subscription import Subscription
from .gst_profile import StoreGstProfile
# GstSalesRecord retired (Report 3, C3) — table dropped via startup
# migration in main.py. gst_sales_invoice(+items) is the GST-sales source
# of truth now.
from .gst_purchase_record import GstPurchaseRecord
from .gst_sales_invoice import GstSalesInvoice, GstSalesInvoiceItem
from .purchase_return import PurchaseReturn
from .scrap import Scrap
from .purchase_batch import PurchaseBatch
from .credit_note import CreditNote, CreditNoteItem
from .import_service import ImportService
from .shop_category import ShopCategory
from .customer import Customer
# Imported here, not only from the route module — main.py runs
# Base.metadata.create_all() near the top, long before the routers are
# included, so a model registered only at router-import time would never get
# its table created.
from .supplier import Supplier

__all__ = [
    "Bill",
    "BillItem",
    "BillingSettings",
    "CreditAccount",
    "CreditTransaction",
    "GlobalProduct",
    "Inventory",
    "InventoryLog",
    "Shop",
    "ShopProduct",
    "Subscription",
    "StoreGstProfile",
    "GstPurchaseRecord",
    "GstSalesInvoice",
    "GstSalesInvoiceItem",
    "PurchaseReturn",
    "Scrap",
    "PurchaseBatch",
    "CreditNote",
    "CreditNoteItem",
    "ImportService",
    "ShopCategory",
    "Customer",
    "Supplier",
]
