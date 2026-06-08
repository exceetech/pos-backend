import re

with open("app/routes/purchase_routes.py", "r") as f:
    content = f.read()

# Let's just find and replace the auto-creation logic
new_content = re.sub(
    r"# ✅ Auto-create PurchaseBatch for Hybrid Inventory\s+if resolved_product_id:.*?db\.add\(\n\s+PurchaseBatch\([\s\S]*?\)\n\s+\)",
    "# Removed auto-creation of PurchaseBatch. Android now pushes them directly via /purchase-batches/sync.",
    content,
    flags=re.MULTILINE
)

# And remove the deletion of PurchaseBatch
new_content = re.sub(
    r"db\.query\(PurchaseBatch\)\.filter\(PurchaseBatch\.purchase_invoice_id == purchase\.id\)\.delete\(\)",
    "# Removed deletion of PurchaseBatch because Android syncs them directly",
    new_content
)

with open("app/routes/purchase_routes.py", "w") as f:
    f.write(new_content)

print("Modifications done.")
