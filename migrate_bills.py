import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv("app/.env")
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("No DB URL")
    exit(1)

# Enable autocommit
engine = create_engine(DATABASE_URL, isolation_level="AUTOCOMMIT")

bill_columns = {
    "subtotal": "FLOAT NOT NULL DEFAULT 0.0",
    "discount_amount": "FLOAT NOT NULL DEFAULT 0.0",
    "taxable_amount": "FLOAT NOT NULL DEFAULT 0.0",
    "cgst_amount": "FLOAT NOT NULL DEFAULT 0.0",
    "sgst_amount": "FLOAT NOT NULL DEFAULT 0.0",
    "igst_amount": "FLOAT NOT NULL DEFAULT 0.0",
    "cess_amount": "FLOAT NOT NULL DEFAULT 0.0",
    "gst_amount": "FLOAT NOT NULL DEFAULT 0.0",
    "round_off": "FLOAT NOT NULL DEFAULT 0.0",
    "final_amount": "FLOAT NOT NULL DEFAULT 0.0",
    "gst_scheme": "VARCHAR NOT NULL DEFAULT 'Regular'",
    "supply_type": "VARCHAR NOT NULL DEFAULT 'intrastate'",
    "customer_state": "VARCHAR",
    "customer_state_code": "VARCHAR",
    "invoice_type": "VARCHAR NOT NULL DEFAULT 'B2C'",
    "is_gst_invoice": "BOOLEAN NOT NULL DEFAULT FALSE",
}

bill_items_columns = {
    "unit_price": "FLOAT NOT NULL DEFAULT 0.0",
    "line_subtotal": "FLOAT NOT NULL DEFAULT 0.0",
    "discount_amount": "FLOAT NOT NULL DEFAULT 0.0",
    "taxable_amount": "FLOAT NOT NULL DEFAULT 0.0",
    "gst_rate": "FLOAT NOT NULL DEFAULT 0.0",
    "cgst_rate": "FLOAT NOT NULL DEFAULT 0.0",
    "sgst_rate": "FLOAT NOT NULL DEFAULT 0.0",
    "igst_rate": "FLOAT NOT NULL DEFAULT 0.0",
    "cgst_amount": "FLOAT NOT NULL DEFAULT 0.0",
    "sgst_amount": "FLOAT NOT NULL DEFAULT 0.0",
    "igst_amount": "FLOAT NOT NULL DEFAULT 0.0",
    "cess_amount": "FLOAT NOT NULL DEFAULT 0.0",
    "total_amount": "FLOAT NOT NULL DEFAULT 0.0",
    "hsn_code": "VARCHAR NOT NULL DEFAULT ''",
}

with engine.connect() as conn:
    for col, dtype in bill_columns.items():
        try:
            conn.execute(text(f"ALTER TABLE bills ADD COLUMN {col} {dtype}"))
            print(f"Added {col} to bills")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                print(f"{col} already exists in bills")
            else:
                print(e)
                
    for col, dtype in bill_items_columns.items():
        try:
            conn.execute(text(f"ALTER TABLE bill_items ADD COLUMN {col} {dtype}"))
            print(f"Added {col} to bill_items")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                print(f"{col} already exists in bill_items")
            else:
                print(e)

print("Migration completed")
