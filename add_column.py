import sqlalchemy
engine = sqlalchemy.create_engine('postgresql://faraan:adeebfarhan@localhost:5432/ExPOS')
with engine.connect() as conn:
    conn.execute(sqlalchemy.text('ALTER TABLE credit_transactions ADD COLUMN reference_invoice VARCHAR'))
    conn.commit()
print("Column added successfully")
