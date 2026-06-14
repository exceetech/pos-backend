"""Shared SQLAlchemy column type for money amounts (R3 fix).

Why not Float: FLOAT/double precision is binary floating point — sums
across thousands of bills accumulate paise-level drift, and aggregate
totals stop matching bill-by-bill arithmetic.

Why Numeric(12, 2): exact decimal storage and exact SQL aggregation
(SUM/AVG over NUMERIC in PostgreSQL is exact). 12,2 allows values up to
9,999,999,999.99 — ample for per-bill and per-line amounts.

Why asdecimal=False: SQLAlchemy keeps returning plain Python floats to
application code, so every existing code path (float() conversions,
float arithmetic in routes/services, JSON serialization) behaves exactly
as before. The exactness lives in the database, where storage and
aggregation happen.

NOT for: quantities (can be 0.333 kg), GST rates (percentages), or
counts — those stay Float/Integer.
"""

from sqlalchemy import Numeric

MONEY = Numeric(12, 2, asdecimal=False)
