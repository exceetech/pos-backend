import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
engine = create_engine(os.getenv("DATABASE_URL"))
with engine.connect() as conn:
    conn.execute(text("UPDATE alembic_version SET version_num = '0009_is_tax_inclusive'"))
    conn.commit()
    print("Fixed alembic version!")
