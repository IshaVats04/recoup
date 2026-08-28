"""Deterministic, bounded decision policy with compliance guardrails.

Design rule: an LLM (see llm.py) may only *diagnose* root cause and *draft*
customer-facing copy - it never chooses the action. Every action comes from
a fixed whitelist per event category, chosen by the rule tables below, and
every guardrail in decide() runs before any recovery action is allowed to
fire. That is what keeps the agent explainable, bounded, and gated, and
it's what makes the guardrails testable independent of any LLM call.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List

from .models import Action, Category, Decision, Diagnosis, Event, GuardrailCheck, RootCause

MAX_PAYMENT_RETRIES = 3
RETRY_BACKOFF_HOURS = (1, 6, 24)
MAX_MESSAGES_PER_DAY = 1
DND_START_HOUR = 21
DND_END_HOUR = 9
HIGH_VALUE_THRESHOLD_INR = 50_000
MAX_DAYS_OVERDUE_BEFORE_WRITEOFF = 90
MAX_DISCOUNT_PCT = 10
LOW_VALUE_FLOOR_INR = 300
GIVE_UP_FLOOR_INR = 500

CONTACT_ACTIONS = {
    Action.SEND_REMINDER_IMMEDIATE, Action.SEND_REMINDER_WITH_DISCOUNT,
    Action.SEND_PAYMENT_METHOD_NUDGE, Action.SEND_GENTLE_REMINDER,
    Action.SEND_FIRM_REMINDER, Action.SEND_UPDATE_PAYMENT_LINK,
    Action.OFFER_PAYMENT_PLAN, Action.OFFER_ALT_PAYMENT_METHOD,
}

_PAYMENT_ACTION_MAP = {
    RootCause.ISSUER_TIMEOUT: Action.RETRY_BACKOFF,
    RootCause.BANK_SERVER_ERROR: Action.RETRY_BACKOFF,
    RootCause.INSUFFICIENT_FUNDS: Action.RETRY_BACKOFF,
    RootCause.EXPIRED_CARD: Action.SEND_UPDATE_PAYMENT_LINK,
    RootCause.UPI_MANDATE_FAILED: Action.SEND_UPDATE_PAYMENT_LINK,
    RootCause.RISK_BLOCK: Action.ESCALATE_HUMAN,
    RootCause.UNKNOWN: Action.RETRY_NOW,
}

_ABANDONMENT_ACTION_MAP = {
    RootCause.PRICE_SHOCK: Action.SEND_REMINDER_WITH_DISCOUNT,
    RootCause.MISSING_PAYMENT_METHOD: Action.SEND_PAYMENT_METHOD_NUDGE,
    RootCause.OTP_DELAY: Action.SEND_REMINDER_IMMEDIATE,
    RootCause.DISTRACTION: Action.SEND_REMINDER_IMMEDIATE,
    RootCause.UNKNOWN: Action.SEND_REMINDER_IMMEDIATE,
}


def discount_pct_for(event: Event) -> int:
    """Illustrative discount used only in drafted copy - always <= MAX_DISCOUNT_PCT."""
    return 5 if event.amount > 5_000 else MAX_DISCOUNT_PCT


def _in_dnd_window(ts: datetime) -> bool:
    hour = ts.hour
    if DND_START_HOUR > DND_END_HOUR:
        return hour >= DND_START_HOUR or hour < DND_END_HOUR
    return DND_START_HOUR <= hour < DND_END_HOUR


def _invoice_action(diagnosis: Diagnosis, event: Event) -> Action:
    if diagnosis.root_cause == RootCause.CASH_FLOW_ISSUE:
        if event.prior_contact_count >= 3:
            return Action.ESCALATE_HUMAN
        return Action.OFFER_PAYMENT_PLAN
    # FORGOTTEN or UNKNOWN
    return Action.SEND_FIRM_REMINDER if event.prior_contact_count >= 2 else Action.SEND_GENTLE_REMINDER


def decide(event: Event, diagnosis: Diagnosis, now: datetime, smart: bool = True) -> Decision:
    """Choose an action for one event.

    When smart=False, the action-selection step ignores the diagnosis and
    always applies the same action per category (a naive baseline). Every
    guardrail below still applies identically in both modes - the baseline
    is naive about *which action to pick*, not about compliance.
    """
    guardrails: List[GuardrailCheck] = []

    def stopped(action: Action, name: str, detail: str) -> Decision:
        guardrails.append(GuardrailCheck(name, True, detail))
        return Decision(action=action, reasoning=detail, guardrails=guardrails)

    # ---- Hard compliance / cost stops - identical for smart and naive runs ----
    if event.category == Category.OVERDUE_INVOICE and event.dispute_flag:
        return stopped(Action.ESCALATE_HUMAN, "dispute_routing",
                        "disputed invoices always go to a human, never automated")

    if event.amount > HIGH_VALUE_THRESHOLD_INR:
        return stopped(Action.ESCALATE_HUMAN, "high_value_threshold",
                        f"amount {event.amount:,.0f} exceeds the autonomous limit of "
                        f"{HIGH_VALUE_THRESHOLD_INR:,.0f}")

    if event.category == Category.OVERDUE_INVOICE:
        if event.promise_to_pay_date and event.promise_to_pay_date > now:
            return stopped(Action.WAIT_PROMISE_TO_PAY, "promise_to_pay",
                            f"customer promised payment by {event.promise_to_pay_date.date()}; "
                            "no contact until that date has passed")
        if event.days_overdue > MAX_DAYS_OVERDUE_BEFORE_WRITEOFF:
            return stopped(Action.WRITE_OFF, "max_overdue_days",
                            f"{event.days_overdue} days overdue exceeds the "
                            f"{MAX_DAYS_OVERDUE_BEFORE_WRITEOFF}-day pursue limit")
        min_contact_gap = timedelta(days=1) / MAX_MESSAGES_PER_DAY
        if event.last_contacted_at is not None and (now - event.last_contacted_at) < min_contact_gap:
            return stopped(Action.DEFER_DND, "contact_frequency_cap",
                            f"already contacted this customer within the last {min_contact_gap}")

    if event.category == Category.FAILED_PAYMENT:
        if event.attempts_so_far >= MAX_PAYMENT_RETRIES:
            if event.amount < GIVE_UP_FLOOR_INR:
                return stopped(Action.GIVE_UP, "max_retry_cap",
                                f"{event.attempts_so_far} attempts already made on a small amount "
                                f"({event.amount:,.0f}); not worth a human escalation")
            return stopped(Action.ESCALATE_HUMAN, "max_retry_cap",
                            f"{event.attempts_so_far} attempts already made, cap is {MAX_PAYMENT_RETRIES}")
        if event.last_attempt_at is not None:
            gap_index = min(event.attempts_so_far, len(RETRY_BACKOFF_HOURS) - 1)
            required_gap = timedelta(hours=RETRY_BACKOFF_HOURS[gap_index])
            elapsed = now - event.last_attempt_at
            if elapsed < required_gap:
                return stopped(Action.DEFER_DND, "retry_backoff_window",
                                f"must wait {required_gap} between attempts, only {elapsed} has passed")

    if event.category == Category.CHECKOUT_ABANDONMENT and event.amount < LOW_VALUE_FLOOR_INR:
        return stopped(Action.NO_ACTION_LOW_VALUE, "low_value_floor",
                        f"cart value {event.amount:,.0f} is below the "
                        f"{LOW_VALUE_FLOOR_INR:,.0f} outreach-cost floor")

    # ---- Everything above passed: record the non-triggers, then choose the action ----
    guardrails.append(GuardrailCheck("dispute_routing", False, "not disputed"))
    guardrails.append(GuardrailCheck("high_value_threshold", False, "within autonomous limit"))

    if not smart:
        action = {
            Category.FAILED_PAYMENT: Action.RETRY_NOW,
            Category.CHECKOUT_ABANDONMENT: Action.SEND_REMINDER_IMMEDIATE,
            Category.OVERDUE_INVOICE: Action.SEND_GENTLE_REMINDER,
        }[event.category]
        reasoning = "naive baseline: same action every time, regardless of diagnosis"
    elif event.category == Category.FAILED_PAYMENT:
        action = _PAYMENT_ACTION_MAP.get(diagnosis.root_cause, Action.RETRY_NOW)
        reasoning = (f"diagnosed '{diagnosis.root_cause.value}' ({diagnosis.source}, "
                     f"confidence {diagnosis.confidence:.2f}) -> {action.value}")
    elif event.category == Category.CHECKOUT_ABANDONMENT:
        action = _ABANDONMENT_ACTION_MAP.get(diagnosis.root_cause, Action.SEND_REMINDER_IMMEDIATE)
        if action == Action.SEND_REMINDER_WITH_DISCOUNT:
            guardrails.append(GuardrailCheck("discount_ceiling", False,
                                              f"offer capped at {discount_pct_for(event)}% "
                                              f"(ceiling {MAX_DISCOUNT_PCT}%)"))
        reasoning = (f"diagnosed '{diagnosis.root_cause.value}' ({diagnosis.source}, "
                     f"confidence {diagnosis.confidence:.2f}) -> {action.value}")
    else:  # OVERDUE_INVOICE
        action = _invoice_action(diagnosis, event)
        reasoning = (f"diagnosed '{diagnosis.root_cause.value}' ({diagnosis.source}, "
                     f"confidence {diagnosis.confidence:.2f}), {event.prior_contact_count} prior "
                     f"contact(s) -> {action.value}")

    if action in CONTACT_ACTIONS and _in_dnd_window(now):
        guardrails.append(GuardrailCheck("dnd_hours", True,
                                          f"would have sent '{action.value}' but {now.hour}:00 "
                                          "falls inside the no-contact window"))
        return Decision(action=Action.DEFER_DND,
                         reasoning=f"deferred: {reasoning}, blocked by DND hours",
                         guardrails=guardrails)
    guardrails.append(GuardrailCheck("dnd_hours", False, f"{now.hour}:00 is outside the DND window"))

    if action == Action.ESCALATE_HUMAN:
        guardrails.append(GuardrailCheck("escalate_collections", True, reasoning))

    return Decision(action=action, reasoning=reasoning, guardrails=guardrails)
