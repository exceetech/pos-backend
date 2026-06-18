"""Shared, bounded per-shop caches for the AI-report endpoint, plus invalidation.

Both the product-revenue pass (route) and the structured-insights pass (service) read
from here, so write paths (new bill / purchase / credit) can drop a shop's cached
result in one call and have the next AI-report request recompute fresh numbers.

⚠️ Scope (audit M2): this cache is per-process. Under a multi-worker server (e.g.
gunicorn with >1 worker), each worker keeps its own copy, so:
  - an `invalidate()` in the worker that handled a write does NOT clear the others, and
  - two requests served by different workers may briefly see values cached at
    different times (bounded by the TTL).
For advisory insights this staleness is acceptable. If you need cross-worker
consistency, swap `TTLCache` here for a shared store (Redis) keyed the same way —
the `get`/`set`/`pop` interface is intentionally small so only this file changes.
"""

from app.util.ttl_cache import TTLCache

REPORT_TTL_SECONDS = 300
INSIGHTS_TTL_SECONDS = 300

report_cache = TTLCache(ttl_seconds=REPORT_TTL_SECONDS, max_size=512)
insights_cache = TTLCache(ttl_seconds=INSIGHTS_TTL_SECONDS, max_size=512)


def invalidate(shop_id: int) -> None:
    """Drop a shop's cached report + insights so the next request recomputes."""
    report_cache.pop(shop_id)
    insights_cache.pop(shop_id)
