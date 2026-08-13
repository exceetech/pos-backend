"""
Shared slowapi Limiter instance. Kept in its own module (not app/main.py)
so route files can import and apply @limiter.limit(...) to individual
endpoints without a circular import back into main.py, which is what
registers this limiter on the FastAPI app and its exception handler.

Keyed by client IP (get_remote_address) — good enough for a single-app
API with no auth-based per-user throttling requirement yet. If this ever
sits behind a load balancer/proxy that doesn't forward the real client
IP, this will need switching to an X-Forwarded-For-aware key func.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
