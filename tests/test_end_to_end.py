"""End-to-end sanity checks across a full generated batch."""
from __future__ import annotations

import random
from datetime import datetime
from typing import List

from recoup.data_gen import generate_batch
from recoup.models import Action, Category, Event
from recoup.policy import HIGH_VALUE_THRESHOLD_INR
from recoup.report import compute_metrics
from recoup.run import run_policy
from recoup.simulate import SimulatedExecutor

NOW = datetime(2026, 8, 24, 15, 0, 0)
EXECUTOR = SimulatedExecutor()


def _draws(events: List[Event], seed: int) -> List[float]:
    rng = random.Random(seed)
    return [rng.random() for _ in events]


def test_batch_generation_is_deterministic_for_a_given_seed():
    batch_a = generate_batch(n=150, seed=7, now=NOW)
    batch_b = generate_batch(n=150, seed=7, now=NOW)
    assert [e.event_id for e in batch_a] == [e.event_id for e in batch_b]


def test_disputed_and_high_value_events_always_escalate_across_a_full_batch():
    events = generate_batch(n=400, seed=11, now=NOW)
    records = run_policy(events, smart=True, use_llm=False, now=NOW,
                          draws=_draws(events, 11), executor=EXECUTOR)
    for record in records:
        if record.event.category == Category.OVERDUE_INVOICE and record.event.dispute_flag:
            assert record.decision.action == Action.ESCALATE_HUMAN
        if record.event.amount > HIGH_VALUE_THRESHOLD_INR:
            assert record.decision.action == Action.ESCALATE_HUMAN


def test_diagnosis_driven_policy_recovers_more_than_the_naive_baseline():
    events = generate_batch(n=2_000, seed=3, now=NOW)
    draws = _draws(events, 3)  # same draws for both runs: a fair, paired comparison

    smart = run_policy(events, smart=True, use_llm=False, now=NOW, draws=draws, executor=EXECUTOR)
    baseline = run_policy(events, smart=False, use_llm=False, now=NOW, draws=draws, executor=EXECUTOR)

    smart_metrics = compute_metrics(smart, "smart")
    baseline_metrics = compute_metrics(baseline, "baseline")

    assert smart_metrics.recovered > baseline_metrics.recovered


def test_shared_draws_give_identical_outcomes_when_both_policies_pick_the_same_action():
    """The common-random-numbers property, checked directly: whenever smart
    and baseline happen to choose the same action for the same event (both
    policies default to the same guardrail-triggered action, e.g. a
    disputed invoice always escalates either way), they must also get the
    identical simulated outcome, because they were handed the same `u`.
    """
    events = generate_batch(n=500, seed=21, now=NOW)
    draws = _draws(events, 21)

    smart = run_policy(events, smart=True, use_llm=False, now=NOW, draws=draws, executor=EXECUTOR)
    baseline = run_policy(events, smart=False, use_llm=False, now=NOW, draws=draws, executor=EXECUTOR)

    checked_any = False
    for smart_record, baseline_record in zip(smart, baseline):
        if smart_record.decision.action == baseline_record.decision.action:
            checked_any = True
            assert smart_record.outcome.recovered == baseline_record.outcome.recovered
            assert smart_record.outcome.amount_recovered == baseline_record.outcome.amount_recovered
    assert checked_any, "expected at least one event where both policies picked the same action"
