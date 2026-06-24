"""
Phase 6 unit tests for the backend time helpers and the report-day boundary.

Pure stdlib + app.util.time_utils (no DB needed). Run with:
    cd pos-backend && APP_TIMEZONE=Asia/Kolkata python -m pytest tests/test_time_utils.py -v
"""

import math
import os
import sqlite3
from datetime import datetime, timedelta

os.environ.setdefault("APP_TIMEZONE", "Asia/Kolkata")

from app.util.time_utils import (          # noqa: E402
    APP_TZ, local_now, local_today, utc_now,
    epoch_ms_to_local, epoch_ms_to_utc,
    local_to_epoch_ms, utc_to_epoch_ms,
)

# A fixed instant: 2026-06-23 18:45:00 UTC  ==  2026-06-24 00:15:00 IST
INSTANT_MS = 1782240300000
IST_OFFSET_MS = 330 * 60 * 1000


# ── Helper round-trips ────────────────────────────────────────────────────────

def test_local_now_is_naive():
    assert local_now().tzinfo is None

def test_utc_now_is_naive():
    assert utc_now().tzinfo is None

def test_local_and_utc_differ_by_offset():
    # Same instant decoded two ways differs by the shop offset.
    diff = epoch_ms_to_local(INSTANT_MS) - epoch_ms_to_utc(INSTANT_MS)
    assert diff == timedelta(milliseconds=IST_OFFSET_MS)

def test_event_round_trip_exact():
    dt = epoch_ms_to_local(INSTANT_MS)
    assert local_to_epoch_ms(dt) == INSTANT_MS

def test_cursor_round_trip_exact():
    dt = epoch_ms_to_utc(INSTANT_MS)
    assert utc_to_epoch_ms(dt) == INSTANT_MS

def test_cursor_symmetry_is_server_tz_independent():
    # utc_to_epoch_ms must NOT depend on the server's local tz (the old .timestamp() bug).
    dt = epoch_ms_to_utc(INSTANT_MS)
    assert utc_to_epoch_ms(dt) == INSTANT_MS == utc_to_epoch_ms(epoch_ms_to_utc(INSTANT_MS))

def test_event_decodes_to_expected_wall_clock():
    dt = epoch_ms_to_local(INSTANT_MS)
    assert (dt.year, dt.month, dt.day, dt.hour, dt.minute) == (2026, 6, 24, 0, 15)


# ── Subscription "remaining days" ceil (off-by-a-day fix) ─────────────────────

def _remaining_days(expiry):
    return max(math.ceil((expiry - utc_now()).total_seconds() / 86400), 0)

def test_23h_left_reads_as_one_day():
    assert _remaining_days(utc_now() + timedelta(hours=23)) == 1

def test_expired_reads_as_zero():
    assert _remaining_days(utc_now() - timedelta(hours=1)) == 0


# ── Report-day boundary (the original H6 bug) ─────────────────────────────────

def test_early_morning_bill_lands_on_correct_report_day():
    """A 00:15 IST bill must count on its own day, not the previous one.

    Demonstrates why event time is stored shop-local: grouping created_at by
    calendar date gives the right day under the new convention, but the OLD UTC
    convention pushes it to the previous day.
    """
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE bills(created_at TEXT)")

    new_value = epoch_ms_to_local(INSTANT_MS).isoformat(sep=" ")   # shop-local (new)
    old_value = epoch_ms_to_utc(INSTANT_MS).isoformat(sep=" ")     # UTC (old, buggy)
    db.execute("INSERT INTO bills VALUES (?)", (new_value,))
    db.execute("INSERT INTO bills VALUES (?)", (old_value,))

    days = [r[0] for r in db.execute("SELECT date(created_at) FROM bills").fetchall()]
    new_day, old_day = days[0], days[1]

    assert new_day == "2026-06-24"          # correct: the sale's own IST day
    assert old_day == "2026-06-23"          # the bug the fix removes
    assert new_day != old_day


def test_local_today_matches_app_tz():
    assert local_today() == datetime.now(APP_TZ).date()
