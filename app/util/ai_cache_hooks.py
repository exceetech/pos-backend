"""Auto-invalidate the AI caches whenever a shop's data changes.

A single SQLAlchemy listener watches the tables that feed the AI report, so every
write path — current and future — clears the affected shop's cache automatically.
No route has to remember to call invalidate(), which is what kept coverage patchy.

Import this module once at startup (see app/main.py) to register the listeners.
"""

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.util.ai_cache import invalidate
from app.models.bill import Bill
from app.models.purchase import Purchase
from app.models.credit import CreditTransaction
from app.models.scrap import Scrap
from app.models.purchase_return import PurchaseReturn
from app.models.credit_note import CreditNote
from app.models.inventory import Inventory

# Writing any of these for a shop changes what the AI report / insights say.
# (BillItem is covered transitively — it's always written alongside a Bill.)
_WATCHED = (Bill, Purchase, CreditTransaction, Scrap, PurchaseReturn, CreditNote, Inventory)
_SHOPS_KEY = "_ai_dirty_shops"


@event.listens_for(Session, "before_flush")
def _collect_dirty_shops(session, flush_context, instances):
    # Attributes are still loaded here (a commit expires them), so capture the affected
    # shop ids now and act only after the commit actually succeeds.
    bucket = session.info.setdefault(_SHOPS_KEY, set())
    for obj in (session.new | session.dirty | session.deleted):
        if isinstance(obj, _WATCHED):
            shop_id = getattr(obj, "shop_id", None)
            if shop_id is not None:
                bucket.add(shop_id)


@event.listens_for(Session, "after_commit")
def _flush_invalidations(session):
    shops = session.info.pop(_SHOPS_KEY, None)
    if shops:
        for shop_id in shops:
            invalidate(shop_id)


@event.listens_for(Session, "after_rollback")
def _drop_pending(session):
    session.info.pop(_SHOPS_KEY, None)
