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
from .plan import Plan
from .coupon import Coupon
from .coupon_redemption import CouponRedemption
from .order import Order
from .processed_webhook_event import ProcessedWebhookEvent
from .app_config import AppConfig
from .audit_log import AuditLog
from .user_event_log import UserEventLog
from .diagnostic_report import DiagnosticReport
# Purchase, PurchaseItem, SaleItem, GlobalHSN, GlobalProductVariant — found
# missing from this file 2026-08-15 while debugging a fresh-database
# migration failure. These tables were only ever getting registered on
# Base.metadata as a side effect of various route modules importing
# these classes directly (purchase_routes.py, sales_routes.py, etc.),
# which happened to run before the old Base.metadata.create_all() call
# in main.py — exactly the fragile pattern the comment above (for
# Supplier) already warned about, just not applied consistently. Adding
# them here directly means these tables register correctly regardless
# of import order or which routes happen to be wired up.
from .purchase import Purchase
from .purchase_item import PurchaseItem
from .sale_item import SaleItem
from .global_hsn import GlobalHSN
from .global_product_variant import GlobalProductVariant

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
    "Plan",
    "Coupon",
    "CouponRedemption",
    "Order",
    "ProcessedWebhookEvent",
    "AppConfig",
    "AuditLog",
    "UserEventLog",
    "DiagnosticReport",
    "Purchase",
    "PurchaseItem",
    "SaleItem",
    "GlobalHSN",
    "GlobalProductVariant",
]
