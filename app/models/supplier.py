from sqlalchemy import Column, Integer, String, DateTime, Boolean, BigInteger, UniqueConstraint
from app.database import Base
from app.util.time_utils import local_now


class Supplier(Base):
    """
    Supplier master, mirroring the Android `supplier_table`.

    Identity rules — the same ones the client enforces:

      • A GSTIN identifies a supplier uniquely within a shop. Two suppliers
        may share a trade name (branches in different states), so the name
        alone is never a key.
      • Unregistered suppliers have no GSTIN. They fall back to being keyed
        by `name_key` (the lowercased name), and `state` must then be stored
        explicitly since there is no GSTIN to derive it from.

    `(shop_id, gstin)` is unique. SQL treats NULLs as distinct, so registered
    suppliers get one row each while any number of unregistered rows coexist —
    the "one row per name" rule for those is enforced in the upsert, not by an
    index, because two *registered* suppliers are allowed to share a name.
    """

    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, index=True)

    shop_id = Column(Integer, nullable=False, index=True)

    name = Column(String, nullable=False)

    # name.strip().lower() — the fallback key for suppliers with no GSTIN.
    name_key = Column(String, nullable=False, index=True)

    gstin = Column(String, nullable=True, index=True)

    state = Column(String, nullable=True)
    state_code = Column(String, nullable=True)

    # Epoch millis, kept as sent by the client so ordering matches the app.
    last_used_at = Column(BigInteger, default=0)

    # The physical column is `updated_at_ms` — that is what the table was
    # created with, and create_all() never ALTERs an existing table, so a
    # plain `updated_at` here compiled fine and then failed at query time
    # with "column suppliers.updated_at does not exist".
    #
    # Mapped rather than renamed so the attribute, the schema and the client
    # DTO all stay `updated_at`, and no existing data has to move.
    updated_at = Column("updated_at_ms", BigInteger, default=0)

    created_at = Column(DateTime, default=local_now)
    is_active = Column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint("shop_id", "gstin", name="uq_supplier_shop_gstin"),
    )
