import re

filepath = "/Users/adeebfarhan/.gemini/antigravity/brain/bfb1db26-2cee-4b41-a28b-ad6f4807923e/scratch/test_all_insights.py"
with open(filepath, "r") as f:
    content = f.read()

# Remove Supplier import
content = re.sub(r'from app\.models\.supplier import Supplier\n', '', content)

# Fix supplier mock data
replacement_supplier = """    # Supplier Dependency (1 supplier has 90% of purchases)
    # 3 purchases from Main
    pur1 = Purchase(id=1, shop_id=1, supplier_name="Main Supplier", invoice_number="INV1", state="Kerala", taxable_amount=10000.0, invoice_value=10000.0, created_at=now, is_credit=0)
    pur2 = Purchase(id=2, shop_id=1, supplier_name="Main Supplier", invoice_number="INV2", state="Kerala", taxable_amount=10000.0, invoice_value=10000.0, created_at=now - timedelta(days=40), is_credit=1) # Unpaid Supplier Bills
    pur3 = Purchase(id=3, shop_id=1, supplier_name="Main Supplier", invoice_number="INV3", state="Kerala", taxable_amount=10000.0, invoice_value=10000.0, created_at=now, is_credit=0)

    # Stale Purchase Batch
    pb1 = PurchaseBatch(id=1, shop_id=1, product_id=1, quantity_purchased=100, quantity_remaining=50, created_at=now - timedelta(days=70))

    db.add_all([pur1, pur2, pur3, pb1])"""

content = re.sub(r'    # Supplier Dependency \(1 supplier has 90% of purchases\).*?    db\.add_all\(\[s1, s2, pur1, pur2, pur3, pb1\]\)', replacement_supplier, content, flags=re.DOTALL)

# Add customer missing model import 
# It already has from app.models.customer import Customer

with open(filepath, "w") as f:
    f.write(content)
