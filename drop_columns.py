import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv("app/.env")
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("No DB URL")
    exit(1)

engine = create_engine(DATABASE_URL, isolation_level="AUTOCOMMIT")

drop_bills_cols = ["total_amount", "gst", "discount"]
drop_bill_items_cols = ["price", "subtotal"]

with engine.connect() as conn:
    for col in drop_bills_cols:
        try:
            conn.execute(text(f"ALTER TABLE bills DROP COLUMN IF EXISTS {col}"))
            print(f"Dropped {col} from bills")
        except Exception as e:
            print(e)
            
    for col in drop_bill_items_cols:
        try:
            conn.execute(text(f"ALTER TABLE bill_items DROP COLUMN IF EXISTS {col}"))
            print(f"Dropped {col} from bill_items")
        except Exception as e:
            print(e)

print("Drop completed")
