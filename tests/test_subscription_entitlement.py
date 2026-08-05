"""
Unit tests for subscription_entitlement_service — covers every scenario
raised in the design discussion: fresh purchase, trial→paid conversion,
Base renewal, Base→Premium upgrade (with and without an original
coupon), Premium→Base downgrade, and expired→anything. Uses plain
in-memory stand-in objects (not the real ORM models / a DB session) so
these run anywhere with no Postgres connection required — a fake `db`
object only needs to support the one-shot `.query(...).filter(...).first()`
chain used by compute_upgrade_credit_paise.
"""
import sys
import os
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.util.time_utils import utc_now
from app.services.subscription_entitlement_service import (
    resolve_entitlement_state, is_trial_offerable, classify_transition,
    compute_upgrade_credit_paise, apply_transition,
)


class FakeSub:
    def __init__(self, tier=None, status="active", expiry_date=None, funding_order_id=None):
        self.shop_id = 1
        self.tier = tier
        self.status = status
        self.expiry_date = expiry_date
        self.start_date = None
        self.plan = None
        self.trial_started_at = None
        self.funding_order_id = funding_order_id


class FakePlan:
    def __init__(self, plan_code, tier, price_paise, duration_days=30):
        self.plan_code = plan_code
        self.tier = tier
        self.price_paise = price_paise
        self.duration_days = duration_days


class FakeOrder:
    def __init__(self, plan_code, amount_paise, status="paid"):
        self.plan_code = plan_code
        self.amount_paise = amount_paise
        self.status = status


class FakeQuery:
    """Minimal stand-in for db.query(Model).filter(...).first() chains."""
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._rows[0] if self._rows else None


class FakeDb:
    def __init__(self, orders=None, plans=None):
        self._orders = orders or []
        self._plans = plans or []

    def query(self, model):
        name = getattr(model, "__name__", str(model))
        if name == "Order":
            return FakeQuery(self._orders)
        if name == "Plan":
            return FakeQuery(self._plans)
        return FakeQuery([])

    def add(self, obj):
        pass


BASE = FakePlan("base_monthly", "base", 69900, 30)
PREMIUM = FakePlan("premium_monthly", "premium", 99900, 30)


def test_resolve_state_no_plan():
    assert resolve_entitlement_state(None) == "no_plan"


def test_resolve_state_expired():
    sub = FakeSub(tier="base", expiry_date=utc_now() - timedelta(days=1))
    assert resolve_entitlement_state(sub) == "expired"


def test_resolve_state_trialing():
    sub = FakeSub(tier="premium", status="trial", expiry_date=utc_now() + timedelta(days=5))
    assert resolve_entitlement_state(sub) == "trialing"


def test_resolve_state_active_base_and_premium():
    base_sub = FakeSub(tier="base", expiry_date=utc_now() + timedelta(days=5))
    prem_sub = FakeSub(tier="premium", expiry_date=utc_now() + timedelta(days=5))
    assert resolve_entitlement_state(base_sub) == "active_base"
    assert resolve_entitlement_state(prem_sub) == "active_premium"


def test_resolve_state_explicit_expired_status_overrides_future_expiry():
    # e.g. admin_refund_order sets status="expired" without touching
    # expiry_date — must resolve to "expired" even though expiry_date is
    # still in the future.
    sub = FakeSub(tier="premium", status="expired", expiry_date=utc_now() + timedelta(days=10))
    assert resolve_entitlement_state(sub) == "expired"


def test_trial_offerable_fresh_shop():
    assert is_trial_offerable(False, None) is True


def test_trial_blocked_once_used():
    assert is_trial_offerable(True, None) is False


def test_trial_blocked_while_active_base():
    # This is the exact bug: trial card must NOT show for a shop on a
    # live paid Base subscription, even if has_used_trial is False.
    sub = FakeSub(tier="base", expiry_date=utc_now() + timedelta(days=10))
    assert is_trial_offerable(False, sub) is False


def test_trial_offerable_after_expiry():
    sub = FakeSub(tier="base", expiry_date=utc_now() - timedelta(days=1))
    assert is_trial_offerable(False, sub) is True


def test_classify_fresh_purchase():
    assert classify_transition(None, BASE, is_trial=False) == "fresh"
    assert classify_transition(None, PREMIUM, is_trial=False) == "fresh"


def test_classify_trial_start():
    assert classify_transition(None, PREMIUM, is_trial=True) == "trial_start"


def test_classify_trial_start_blocked_when_active():
    sub = FakeSub(tier="base", expiry_date=utc_now() + timedelta(days=5))
    try:
        classify_transition(sub, PREMIUM, is_trial=True)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_classify_trial_convert():
    sub = FakeSub(tier="premium", status="trial", expiry_date=utc_now() + timedelta(days=5))
    assert classify_transition(sub, PREMIUM, is_trial=False) == "trial_convert"


def test_classify_renewal_base_to_base():
    sub = FakeSub(tier="base", expiry_date=utc_now() + timedelta(days=5))
    assert classify_transition(sub, BASE, is_trial=False) == "renewal"


def test_classify_upgrade_base_to_premium():
    sub = FakeSub(tier="base", expiry_date=utc_now() + timedelta(days=5))
    assert classify_transition(sub, PREMIUM, is_trial=False) == "upgrade"


def test_classify_downgrade_premium_to_base():
    sub = FakeSub(tier="premium", expiry_date=utc_now() + timedelta(days=5))
    assert classify_transition(sub, BASE, is_trial=False) == "downgrade"


def test_classify_renewal_premium_to_premium():
    sub = FakeSub(tier="premium", expiry_date=utc_now() + timedelta(days=5))
    assert classify_transition(sub, PREMIUM, is_trial=False) == "renewal"


def test_classify_expired_treated_as_fresh():
    sub = FakeSub(tier="premium", expiry_date=utc_now() - timedelta(days=1))
    assert classify_transition(sub, BASE, is_trial=False) == "fresh"


def test_upgrade_credit_full_price_half_days_left():
    # Paid full ₹699 for Base, exactly half the 30 days remain.
    sub = FakeSub(tier="base", expiry_date=utc_now() + timedelta(days=15), funding_order_id=1)
    db = FakeDb(orders=[FakeOrder("base_monthly", 69900)], plans=[BASE])
    credit = compute_upgrade_credit_paise(db, sub, PREMIUM)
    assert 34000 < credit < 35500, credit  # ~half of 69900


def test_upgrade_credit_uses_actual_paid_not_list_price():
    # This is the specific bug we were asked to check: a 50%-off coupon
    # on the original Base purchase (paid 34950, not list 69900) must
    # produce a credit based on 34950, not 69900.
    sub = FakeSub(tier="base", expiry_date=utc_now() + timedelta(days=30), funding_order_id=1)
    db = FakeDb(orders=[FakeOrder("base_monthly", 34950)], plans=[BASE])
    credit = compute_upgrade_credit_paise(db, sub, PREMIUM)
    assert credit == 34950, credit  # full remaining days, full actual-paid amount

    db_wrong = FakeDb(orders=[FakeOrder("base_monthly", 69900)], plans=[BASE])
    credit_if_using_list_price = compute_upgrade_credit_paise(db_wrong, sub, PREMIUM)
    assert credit_if_using_list_price != credit
    assert credit_if_using_list_price == 69900


def test_upgrade_credit_zero_when_no_funding_order():
    sub = FakeSub(tier="base", expiry_date=utc_now() + timedelta(days=15), funding_order_id=None)
    db = FakeDb(orders=[], plans=[BASE])
    assert compute_upgrade_credit_paise(db, sub, PREMIUM) == 0


def test_upgrade_credit_zero_when_expired():
    sub = FakeSub(tier="base", expiry_date=utc_now() - timedelta(days=1), funding_order_id=1)
    db = FakeDb(orders=[FakeOrder("base_monthly", 69900)], plans=[BASE])
    assert compute_upgrade_credit_paise(db, sub, PREMIUM) == 0


def test_upgrade_credit_never_exceeds_new_plan_price():
    # A 12-month Base plan (huge remaining balance) upgraded on day one
    # must never produce a credit bigger than what Premium itself costs.
    long_base = FakePlan("base_yearly", "base", 500000, 365)
    sub = FakeSub(tier="base", expiry_date=utc_now() + timedelta(days=364), funding_order_id=1)
    db = FakeDb(orders=[FakeOrder("base_yearly", 500000)], plans=[long_base])
    credit = compute_upgrade_credit_paise(db, sub, PREMIUM)
    assert credit == PREMIUM.price_paise


def test_apply_transition_renewal_extends_from_current_expiry_not_now():
    current_expiry = utc_now() + timedelta(days=5)
    sub = FakeSub(tier="base", expiry_date=current_expiry)
    updated = apply_transition(None, sub, 1, BASE, "renewal", funding_order_id=99)
    # Must extend from the CURRENT expiry (5 days out), not from now —
    # otherwise a renewal would shave off the days already paid for.
    expected = current_expiry + timedelta(days=BASE.duration_days)
    assert abs((updated.expiry_date - expected).total_seconds()) < 2
    assert updated.funding_order_id == 99


def test_apply_transition_upgrade_starts_fresh_period_from_now():
    sub = FakeSub(tier="base", expiry_date=utc_now() + timedelta(days=5))
    before = utc_now()
    updated = apply_transition(None, sub, 1, PREMIUM, "upgrade", funding_order_id=100)
    assert updated.tier == "premium"
    assert updated.status == "active"
    assert updated.expiry_date > before + timedelta(days=PREMIUM.duration_days) - timedelta(seconds=2)


def test_apply_transition_trial_start_sets_trial_fields():
    trial_plan = FakePlan("trial", "premium", 0, 7)
    updated = apply_transition(FakeDb(), None, 1, trial_plan, "trial_start")
    assert updated.status == "trial"
    assert updated.tier == "premium"
    assert updated.trial_started_at is not None


def test_reject_if_downgrade_raises_for_downgrade_only():
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from fastapi import HTTPException
    from app.routes.subscription_payment_routes import _reject_if_downgrade

    sub = FakeSub(tier="premium", expiry_date=utc_now() + timedelta(days=10))

    # Downgrade must be rejected.
    try:
        _reject_if_downgrade("downgrade", sub)
        assert False, "expected HTTPException"
    except HTTPException as e:
        assert e.status_code == 400
        assert "Premium" in str(e.detail)

    # Every other transition must pass through untouched (no exception).
    for t in ["fresh", "renewal", "upgrade", "trial_start", "trial_convert"]:
        _reject_if_downgrade(t, sub)  # must not raise


if __name__ == "__main__":
    import inspect
    mod = sys.modules[__name__]
    tests = [obj for name, obj in vars(mod).items() if name.startswith("test_") and callable(obj)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS: {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL: {t.__name__} -> {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
