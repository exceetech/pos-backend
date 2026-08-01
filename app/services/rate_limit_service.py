"""
Minimal in-process rate limiter for the payment endpoints (create-order,
validate-coupon) — cheap insurance against coupon brute-forcing and
order-spam, per §6 of the onboarding/subscription plan.

Deliberately simple: an in-memory sliding window keyed by (bucket, key).
This is NOT distributed-safe — if the backend ever runs multiple
processes/instances behind a load balancer without sticky sessions, each
instance enforces its own independent limit, so the effective limit is
(configured limit × instance count). That's an acceptable gap for a v1
launch on a single instance; if this backend scales out horizontally,
swap this for a shared store (Redis) using the same function signatures
so callers don't need to change.
"""
import time
from collections import defaultdict
from fastapi import HTTPException

_hits: dict[tuple[str, str], list[float]] = defaultdict(list)


def check_rate_limit(bucket: str, key: str, max_hits: int, window_seconds: int) -> None:
    """
    Raises HTTPException(429, ...) if `key` has exceeded `max_hits` calls
    to `bucket` within the last `window_seconds`. Call at the top of the
    endpoint, before doing any real work.
    """
    now = time.time()
    cutoff = now - window_seconds
    hit_key = (bucket, key)

    recent = [t for t in _hits[hit_key] if t > cutoff]
    if len(recent) >= max_hits:
        raise HTTPException(status_code=429, detail="Too many attempts. Please wait and try again.")

    recent.append(now)
    _hits[hit_key] = recent
