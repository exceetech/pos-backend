from sqlalchemy import create_engine, text

DATABASE_URL = "postgresql://faraan:adeebfarhan@localhost:5432/ExPOS"
engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    print("--- ACTIVE SHOPS ---")
    res = conn.execute(text("SELECT id, shop_name, email, phone, status, workspace_version FROM shops WHERE status = 'ACTIVE'"))
    active_shop_ids = []
    for row in res:
        print(row)
        active_shop_ids.append(row[0])

    print("\n--- ALL SHOPS ---")
    res = conn.execute(text("SELECT id, shop_name, email, phone, status, workspace_version FROM shops"))
    for row in res:
        print(row)

    for shop_id in active_shop_ids:
        print(f"\n--- PRODUCTS FOR SHOP {shop_id} ---")
        q = f"""
            SELECT sp.id, gp.name, sp.variant_name, sp.is_active, sp.is_purchased 
            FROM shop_products sp
            JOIN global_products gp ON sp.global_product_id = gp.id
            WHERE sp.shop_id = {shop_id}
        """
        res = conn.execute(text(q))
        for row in res:
            print(row)

        print(f"\n--- INVENTORY FOR SHOP {shop_id} ---")
        res = conn.execute(text(f"SELECT product_id, current_stock, average_cost, is_active FROM inventory WHERE shop_id = {shop_id}"))
        for row in res:
            print(row)
            
        print(f"\n--- INVENTORY LOGS FOR SHOP {shop_id} ---")
        res = conn.execute(text(f"SELECT id, product_id, type, quantity, price, created_at FROM inventory_logs WHERE shop_id = {shop_id} LIMIT 20"))
        for row in res:
            print(row)
