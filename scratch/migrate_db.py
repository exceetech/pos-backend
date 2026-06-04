import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.database import engine
from sqlalchemy import text

def run():
    with engine.begin() as conn:
        try:
            conn.execute(text("ALTER TABLE purchase_items ADD COLUMN supply_classification VARCHAR NOT NULL DEFAULT 'TAXABLE'"))
            print("Migration successful")
        except Exception as e:
            print(f"Migration skipped/failed: {e}")

if __name__ == "__main__":
    run()
