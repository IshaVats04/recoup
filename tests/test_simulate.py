"""SimulatedExecutor should be a pure function of its inputs - all
randomness is externalized via `u`, so the same (event, cause, action, u)
always produces the same outcome. That's what makes the smart-vs-baseline
comparison in run.py a fair, common-random-numbers comparison instead of
two independently-noisy runs.
"""
from __future__ import annotations

from datetime import datetime

from recoup.models import Action, Category, Event, RootCause
from recoup.simulate import HUMAN_ESCALATION_COST, SimulatedExecutor

NOW = datetime(2026, 8, 24, 15, 0, 0)


def _payment() -> Event:
    return Event(
        event_id="PAY", category=Category.FAILED_PAYMENT, customer_id="C1",
        amount=1_000.0, currency="INR", occurred_at=NOW,
    )


def test_same_inputs_always_produce_the_same_outcome():
    executor = SimulatedExecutor()
    event = _payment()
    a = executor.execute(event, RootCause.ISSUER_TIMEOUT, Action.RETRY_BACKOFF, u=0.5)
    b = executor.execute(event, RootCause.ISSUER_TIMEOUT, Action.RETRY_BACKOFF, u=0.5)
    assert a.recovered == b.recovered
    assert a.amount_recovered == b.amount_recovered


def test_u_below_probability_recovers_and_above_does_not():
    executor = SimulatedExecutor()
    event = _payment()
    # issuer_timeout + retry_backoff has P(success) = 0.80 in the success table.
    low = executor.execute(event, RootCause.ISSUER_TIMEOUT, Action.RETRY_BACKOFF, u=0.1)
    high = executor.execute(event, RootCause.ISSUER_TIMEOUT, Action.RETRY_BACKOFF, u=0.95)
    assert low.recovered is True
    assert high.recovered is False


def test_escalation_never_counts_as_an_automated_recovery():
    executor = SimulatedExecutor()
    event = _payment()
    outcome = executor.execute(event, RootCause.RISK_BLOCK, Action.ESCALATE_HUMAN, u=0.0)
    assert outcome.recovered is False
    assert outcome.cost == HUMAN_ESCALATION_COST


def test_no_op_guardrail_actions_never_recover_and_never_cost_anything():
    executor = SimulatedExecutor()
    event = _payment()
    for action in (Action.WAIT_PROMISE_TO_PAY, Action.DEFER_DND, Action.WRITE_OFF,
                   Action.GIVE_UP, Action.NO_ACTION_LOW_VALUE):
        outcome = executor.execute(event, RootCause.UNKNOWN, action, u=0.0)
        assert outcome.recovered is False
        assert outcome.cost == 0.0
