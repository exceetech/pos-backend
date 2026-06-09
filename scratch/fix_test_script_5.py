filepath = "/Users/adeebfarhan/.gemini/antigravity/brain/bfb1db26-2cee-4b41-a28b-ad6f4807923e/scratch/test_all_insights_final.py"
with open(filepath, "r") as f:
    content = f.read()

content = content.replace('shop = Shop(id=1, shop_name="Test Shop", owner_id=1)', 'shop = Shop(id=1, shop_name="Test Shop", owner_name="Owner")')

with open(filepath, "w") as f:
    f.write(content)
