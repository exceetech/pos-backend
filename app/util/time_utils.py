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
from datetime import datetime, date
from zoneinfo import ZoneInfo

APP_TZ = ZoneInfo(os.getenv("APP_TIMEZONE", "Asia/Kolkata"))


def local_now() -> datetime:
    """Naive datetime in the app timezone — comparable to Bill.created_at."""
    return datetime.now(APP_TZ).replace(tzinfo=None)


def local_today() -> date:
    """Today's date in the app timezone."""
    return local_now().date()
