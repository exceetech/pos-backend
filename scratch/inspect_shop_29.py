from sqlalchemy import create_engine, text

DATABASE_URL = "postgresql://faraan:adeebfarhan@localhost:5432/ExPOS"
engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    print("--- SHOP 29 INFO ---")
    res = conn.execute(text("SELECT * FROM shops WHERE id = 29"))
    for row in res:
        print(row)

    print("\n--- PRODUCTS FOR SHOP 29 ---")
    res = conn.execute(text("SELECT * FROM shop_products WHERE shop_id = 29"))
    for row in res:
        print(dict(row._mapping))

    print("\n--- INVENTORY FOR SHOP 29 ---")
    res = conn.execute(text("SELECT * FROM inventory WHERE shop_id = 29"))
    for row in res:
        print(dict(row._mapping))

    print("\n--- INVENTORY LOGS FOR SHOP 29 ---")
    res = conn.execute(text("SELECT * FROM inventory_logs WHERE shop_id = 29"))
    for row in res:
        print(dict(row._mapping))
