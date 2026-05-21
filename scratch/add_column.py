from app.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE shop_products ADD COLUMN is_purchased BOOLEAN DEFAULT FALSE;"))
        print("Added is_purchased column.")
    except Exception as e:
        print("Column may already exist:", e)

    try:
        conn.execute(text("ALTER TABLE shop_products ADD CONSTRAINT uix_shop_global_variant UNIQUE (shop_id, global_product_id, variant_name);"))
        print("Added unique constraint.")
    except Exception as e:
        print("Constraint may already exist:", e)

    conn.commit()
