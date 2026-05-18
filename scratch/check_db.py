from sqlalchemy import create_engine, text
import os

DATABASE_URL = "postgresql://faraan:adeebfarhan@localhost:5432/ExPOS"

engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    print("HSN DATA:")
    res = conn.execute(text("SELECT * FROM global_hsn"))
    for row in res:
        print(row)

    print("\nPRODUCT DATA (verified only):")
    res = conn.execute(text("SELECT * FROM global_products WHERE is_verified = TRUE"))
    for row in res:
        print(row)
