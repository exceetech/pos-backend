"""Single source of truth for "now" across the backend (H6 fix).

Bill.created_at is stored as a NAIVE device-local timestamp (the app sends
the device time; see bill_routes). Report period boundaries must therefore
be computed in that same timezone — not the server's clock. Previously the
report routes mixed datetime.utcnow(), datetime.now() and date.today(),
which on a UTC server shifted "today" by +5:30 for IST shops (bills made
between 00:00 and 05:30 IST landed on the previous day's report).

The timezone is configurable via the APP_TIMEZONE env var and defaults to
Asia/Kolkata.
"""

import os
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo

APP_TZ = ZoneInfo(os.getenv("APP_TIMEZONE", "Asia/Kolkata"))


# ── Bucket A: event time (wall clock in the shop timezone) ──────────────────
# Use these for anything that represents WHEN a business thing happened
# (created_at, bill/sale/purchase/return/scrap/log dates). They are what
# reports compute against. Stored NAIVE and interpreted in APP_TZ.

def local_now() -> datetime:
    """Naive datetime in the app timezone — comparable to Bill.created_at."""
    return datetime.now(APP_TZ).replace(tzinfo=None)


def local_today() -> date:
    """Today's date in the app timezone."""
    return local_now().date()


def epoch_ms_to_local(ms: int) -> datetime:
    """Client epoch-millis (a true instant) → naive wall clock in APP_TZ.

    This is the ONLY way to ingest a client-sent event timestamp. Replaces the
    old mix of datetime.utcfromtimestamp() (UTC) and datetime.fromtimestamp()
    (server-local), which stored the same instant as different wall times
    depending on which route handled it.
    """
    return datetime.fromtimestamp(ms / 1000, APP_TZ).replace(tzinfo=None)


def local_to_epoch_ms(dt: datetime) -> int:
    """Naive APP_TZ wall clock → epoch-millis instant (for sending back out)."""
    return int(dt.replace(tzinfo=APP_TZ).timestamp() * 1000)


# ── Bucket B: technical time (UTC instant) ──────────────────────────────────
# Use these for sync cursors (updated_at), JWT/OTP/subscription expiry, and any
# bookkeeping value that is never shown to the user as a wall clock. Kept in UTC
# so the cursor is comparable regardless of the shop timezone.

def utc_now() -> datetime:
    """Naive UTC datetime — for sync cursors and security expiry."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_to_epoch_ms(dt: datetime) -> int:
    """Naive UTC datetime → epoch-millis (Bucket-B emit, e.g. sync cursors).

    A plain dt.timestamp() reinterprets a naive value in the SERVER's local
    timezone, which shifts a UTC cursor by the server offset (e.g. 5.5h on an
    IST host). Pinning tzinfo to UTC first keeps the cursor symmetric with
    epoch_ms_to_utc on ingest.
    """
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


def epoch_ms_to_utc(ms: int) -> datetime:
    """Client epoch-millis → naive UTC datetime (Bucket-B ingest, e.g. cursors)."""
    return datetime.fromtimestamp(ms / 1000, timezone.utc).replace(tzinfo=None)
