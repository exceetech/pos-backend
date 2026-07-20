from app.database import engine; from sqlalchemy import text;
with engine.connect() as conn:
    conn.execute(text('ALTER TABLE sale_items ADD COLUMN IF NOT EXISTS bill_number VARCHAR;'))
    conn.execute(text('CREATE INDEX IF NOT EXISTS ix_sale_items_bill_number ON sale_items (bill_number);'))
    conn.commit()
