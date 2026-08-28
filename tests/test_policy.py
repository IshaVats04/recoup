"""Guardrail invariants for the deterministic policy engine.

These back up the track's bar: "compliant escalation, stopping rules, and
an audit trail." Every one of these must hold no matter what the diagnosis
says - guardrails run before the "smart" choice, in both smart and naive
(baseline) mode.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from recoup.models import Action, Category, Diagnosis, Event, RootCause
from recoup.policy import (
    GIVE_UP_FLOOR_INR,
    HIGH_VALUE_THRESHOLD_INR,
    MAX_DAYS_OVERDUE_BEFORE_WRITEOFF,
    MAX_DISCOUNT_PCT,
    MAX_PAYMENT_RETRIES,
    decide,
    discount_pct_for,
)

NOW = datetime(2026, 8, 24, 15, 0, 0)  # 3pm, outside DND hours


def _invoice(**kwargs) -> Event:
    defaults = dict(
        event_id="INV_TEST", category=Category.OVERDUE_INVOICE, customer_id="C1",
        amount=10_000.0, currency="INR", occurred_at=NOW, days_overdue=10,
        prior_contact_count=0, dispute_flag=False,
    )
    defaults.update(kwargs)
    return Event(**defaults)


def _payment(**kwargs) -> Event:
    defaults = dict(
        event_id="PAY_TEST", category=Category.FAILED_PAYMENT, customer_id="C1",
        amount=1_000.0, currency="INR", occurred_at=NOW, attempts_so_far=0,
    )
    defaults.update(kwargs)
    return Event(**defaults)


def _cart(**kwargs) -> Event:
    defaults = dict(
        event_id="CART_TEST", category=Category.CHECKOUT_ABANDONMENT, customer_id="C1",
        amount=2_000.0, currency="INR", occurred_at=NOW, signal="price_shock",
    )
    defaults.update(kwargs)
    return Event(**defaults)


def _diag(root_cause: RootCause, confidence: float = 0.9) -> Diagnosis:
    return Diagnosis(root_cause=root_cause, confidence=confidence, rationale="test", source="rule")


def test_disputed_invoice_always_escalates_regardless_of_diagnosis():
    event = _invoice(dispute_flag=True)
    for smart in (True, False):
        decision = decide(event, _diag(RootCause.DISPUTED), now=NOW, smart=smart)
        assert decision.action == Action.ESCALATE_HUMAN
        assert any(g.name == "dispute_routing" and g.triggered for g in decision.guardrails)


@pytest.mark.parametrize("builder_name", ["invoice", "payment"])
def test_high_value_always_escalates(builder_name):
    builder = _invoice if builder_name == "invoice" else _payment
    event = builder(amount=HIGH_VALUE_THRESHOLD_INR + 1)
    decision = decide(event, _diag(RootCause.UNKNOWN), now=NOW, smart=True)
    assert decision.action == Action.ESCALATE_HUMAN


def test_promise_to_pay_is_honored_until_the_date_passes():
    future = NOW + timedelta(days=3)
    event = _invoice(promise_to_pay_date=future, prior_contact_count=1)

    decision = decide(event, _diag(RootCause.CASH_FLOW_ISSUE), now=NOW, smart=True)
    assert decision.action == Action.WAIT_PROMISE_TO_PAY

    decision_after = decide(
        event, _diag(RootCause.CASH_FLOW_ISSUE), now=future + timedelta(days=1), smart=True
    )
    assert decision_after.action != Action.WAIT_PROMISE_TO_PAY


def test_invoice_written_off_past_the_overdue_ceiling():
    event = _invoice(days_overdue=MAX_DAYS_OVERDUE_BEFORE_WRITEOFF + 1)
    decision = decide(event, _diag(RootCause.CASH_FLOW_ISSUE), now=NOW, smart=True)
    assert decision.action == Action.WRITE_OFF


def test_payment_retry_cap_is_never_exceeded():
    event = _payment(attempts_so_far=MAX_PAYMENT_RETRIES, amount=5_000.0)
    decision = decide(event, _diag(RootCause.ISSUER_TIMEOUT), now=NOW, smart=True)
    assert decision.action not in (Action.RETRY_NOW, Action.RETRY_BACKOFF)
    assert decision.action == Action.ESCALATE_HUMAN


def test_payment_retry_cap_gives_up_on_small_amounts_instead_of_escalating():
    event = _payment(attempts_so_far=MAX_PAYMENT_RETRIES, amount=GIVE_UP_FLOOR_INR - 1)
    decision = decide(event, _diag(RootCause.ISSUER_TIMEOUT), now=NOW, smart=True)
    assert decision.action == Action.GIVE_UP


def test_retry_backoff_window_defers_too_soon_a_retry():
    event = _payment(attempts_so_far=1, last_attempt_at=NOW - timedelta(minutes=10))
    decision = decide(event, _diag(RootCause.ISSUER_TIMEOUT), now=NOW, smart=True)
    assert decision.action == Action.DEFER_DND


def test_dnd_hours_defer_contact_actions():
    late_night = NOW.replace(hour=23, minute=0)
    event = _cart(occurred_at=late_night, signal="missing_payment_method")
    decision = decide(event, _diag(RootCause.MISSING_PAYMENT_METHOD), now=late_night, smart=True)
    assert decision.action == Action.DEFER_DND
    assert any(g.name == "dnd_hours" and g.triggered for g in decision.guardrails)


def test_low_value_cart_gets_no_automated_outreach():
    event = _cart(amount=50.0)
    decision = decide(event, _diag(RootCause.DISTRACTION), now=NOW, smart=True)
    assert decision.action == Action.NO_ACTION_LOW_VALUE


def test_naive_baseline_ignores_diagnosis_but_still_obeys_guardrails():
    disputed = _invoice(dispute_flag=True)
    decision = decide(disputed, _diag(RootCause.DISPUTED), now=NOW, smart=False)
    assert decision.action == Action.ESCALATE_HUMAN  # guardrail still applies

    ordinary = _payment(attempts_so_far=0)
    decision = decide(ordinary, _diag(RootCause.EXPIRED_CARD), now=NOW, smart=False)
    assert decision.action == Action.RETRY_NOW  # ignores that expired_card needs a different action


@pytest.mark.parametrize("amount", [100, 4_999, 5_000, 5_001, 250_000])
def test_discount_never_exceeds_ceiling(amount):
    event = _cart(amount=float(amount))
    assert discount_pct_for(event) <= MAX_DISCOUNT_PCT
