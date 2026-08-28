"""End-to-end sanity checks across a full generated batch."""
from __future__ import annotations

from datetime import datetime

from recoup.data_gen import generate_batch
from recoup.models import Action, Category
from recoup.policy import HIGH_VALUE_THRESHOLD_INR
from recoup.report import compute_metrics
from recoup.run import run_policy

NOW = datetime(2026, 8, 24, 15, 0, 0)


def test_batch_generation_is_deterministic_for_a_given_seed():
    batch_a = generate_batch(n=150, seed=7, now=NOW)
    batch_b = generate_batch(n=150, seed=7, now=NOW)
    assert [e.event_id for e in batch_a] == [e.event_id for e in batch_b]


def test_disputed_and_high_value_events_always_escalate_across_a_full_batch():
    events = generate_batch(n=400, seed=11, now=NOW)
    records = run_policy(events, smart=True, use_llm=False, now=NOW, seed=11)
    for record in records:
        if record.event.category == Category.OVERDUE_INVOICE and record.event.dispute_flag:
            assert record.decision.action == Action.ESCALATE_HUMAN
        if record.event.amount > HIGH_VALUE_THRESHOLD_INR:
            assert record.decision.action == Action.ESCALATE_HUMAN


def test_diagnosis_driven_policy_recovers_more_than_the_naive_baseline():
    events = generate_batch(n=2_000, seed=3, now=NOW)
    smart = run_policy(events, smart=True, use_llm=False, now=NOW, seed=3)
    baseline = run_policy(events, smart=False, use_llm=False, now=NOW, seed=4)

    smart_metrics = compute_metrics(smart, "smart")
    baseline_metrics = compute_metrics(baseline, "baseline")

    assert smart_metrics.recovered > baseline_metrics.recovered
