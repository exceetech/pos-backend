filepath = "/Users/adeebfarhan/Desktop/expos/pos-backend/scratch/run_live_test.py"
with open(filepath, "r") as f:
    content = f.read()

content = content.replace("shop.name", "shop.shop_name")

with open(filepath, "w") as f:
    f.write(content)
