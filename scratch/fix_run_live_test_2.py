filepath = "/Users/adeebfarhan/Desktop/expos/pos-backend/scratch/run_live_test.py"
with open(filepath, "r") as f:
    content = f.read()

content = content.replace("insights = generate_structured_insights(shop_id, db)", "insights = generate_structured_insights(db, shop_id)")

with open(filepath, "w") as f:
    f.write(content)
